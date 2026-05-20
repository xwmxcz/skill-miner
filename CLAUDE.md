# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable) — required before running the CLI or tests
pip install -e .[dev]

# Run the full test suite
pytest

# Run a single test file / single test
pytest tests/test_miner.py
pytest tests/test_miner.py::test_mine_end_to_end_on_replicated_fixture

# Exercise the CLI locally (entry point = src/skill_miner/cli.py::main)
skill-miner scan
skill-miner list
skill-miner report
skill-miner accept <id>
skill-miner ignore <id>
skill-miner install-hook    # writes a Stop hook into ~/.claude/settings.json
skill-miner hook            # internal entry point invoked by that Stop hook
```

There is no linter or formatter configured.

## Architecture

`skill-miner` is a **read-only, stdlib-only** pipeline over Claude Code's local
session logs. It never makes network calls, never loads ML models, and has
**zero runtime dependencies** — that constraint is load-bearing for the
project's value proposition and should be preserved.

Pipeline (each stage is a module under `src/skill_miner/`):

1. **`loader.py`** — Walks `~/.claude/projects/*/*.jsonl`. Each `.jsonl` file is
   one Claude Code session; each line is one event. Only events with
   `type in {"user", "assistant"}` are kept. Output: `Session` objects.
2. **`extractor.py`** — Turns events into `Turn` records. One Turn = one user
   prompt + every assistant `tool_use` that followed it until the next user
   prompt. Tool calls are collapsed to canonical signatures like `Bash:git`,
   `Edit:.py`, `Agent:explore`. Prompt text is filtered to drop greetings,
   slash-command markers, `<system-reminder>`/`<command-name>` blocks, and
   `[Request interrupted]` noise. Tool-result-only "user" events do not
   create new Turns; they are silently attached to the pending one.
3. **`miner.py`** — Two independent miners that are then correlated:
   - `find_tool_ngrams`: per-session 3-to-5-grams over tool signatures,
     requiring `min_count >= 3` across sessions and at least 2 distinct tokens
     in the gram (to skip `Bash Bash Bash`).
   - `cluster_prompts`: tokenize prompts (ASCII words + **overlapping CJK
     bigrams** so Chinese prompts don't tokenize to nothing), TF-IDF +
     cosine similarity, greedy union-find clustering at threshold 0.35,
     `min_cluster_size >= 3`.
   - `correlate`: for each prompt cluster, pick the tool n-gram with the
     most overlap on cluster sessions. Confidence is a heuristic:
     `0.55 * size_score + 0.45 * ngram_score` (both bounded to 0..1).
4. **`synthesizer.py`** — Renders a `Candidate` into a `SKILL.md` draft.
   `scrub()` is the **last line of defense for privacy** — it must run on
   every piece of text that lands in the output: Windows + POSIX paths,
   `~/...` paths, emails, IPs, `password=...`/`token=...` k/v pairs, and
   long mixed alphanumeric blobs. `_slugify` falls back to the tool n-gram
   (e.g. `read-edit-bash`) when the cluster keywords are CJK-only, since
   skill names must be ASCII.
5. **`store.py`** — Persists state to `~/.claude/mined-skills/state.json`.
   `upsert_candidates` is **status-preserving**: re-scanning never resets a
   candidate that was previously marked `accepted` or `ignored`. Candidate IDs
   are `sha1(name || ngram)[:10]`, so renaming a candidate creates a new ID.
6. **`reporter.py`** — Renders state to `report-YYYY-MM-DD.md` in the same dir.
7. **`hook.py`** — Stop-hook entry point. **Must never raise** — any exception
   is swallowed and printed to stderr, because hook failures would block the
   Claude Code REPL from exiting cleanly.
8. **`cli.py`** — Argparse dispatcher. Two CLI-only details worth knowing:
   - `_force_utf8_stdout()` reconfigures stdout/stderr to UTF-8 because
     Windows consoles default to a non-UTF-8 codepage and the reports contain
     CJK characters.
   - `_dedupe_names` rewrites collisions to `<slug>-2`, `<slug>-3`, … by
     patching the rendered markdown's frontmatter in place.

### Output locations (all under the user's home directory, never the repo)

- `~/.claude/projects/*/*.jsonl` — **input** (Claude Code's own logs)
- `~/.claude/mined-skills/state.json` — candidate state
- `~/.claude/mined-skills/report-*.md` — human-readable reports
- `~/.claude/skills/<name>/SKILL.md` — where `accept` promotes a candidate
- `~/.claude/settings.json` — where `install-hook` writes the Stop hook

### Invariants to preserve when editing

- **No new runtime dependencies.** `pyproject.toml` lists only `pytest` (dev).
  Adding `numpy`/`scikit-learn`/etc. is a roadmap item gated on an opt-in
  `--with-embeddings` extra, not the default install.
- **Offline.** No `urllib`, `requests`, or subprocess calls to network tools.
- **Scrub before render.** Any new field that surfaces user text in a report,
  skill draft, or stored candidate must go through `synthesizer.scrub`.
- **Hook must not raise.** If you add work to `hook.py`, keep it inside the
  blanket `try/except` and return `0` on failure.

## Tests

The fixture at `tests/fixtures/sample.jsonl` is a hand-crafted minimal session
(3 user/assistant turn pairs in Chinese, tool calls `Read:.md → Edit:.md →
Bash:git`). Tests in `test_miner.py` replicate this fixture across synthetic
session IDs to clear the `min_count >= 3` / `min_cluster_size >= 3` thresholds
— do not lower those thresholds in production code to make a single-session
test pass; build a multi-session fixture instead.
