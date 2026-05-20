# skill-miner

> **Mine your own Claude Code session history for reusable Skills.**
> No API keys. No network. Your prompts never leave your machine.

[![CI](https://github.com/xwmxcz/skill-miner/actions/workflows/ci.yml/badge.svg)](https://github.com/xwmxcz/skill-miner/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

[English](README.md) · [中文](README.zh-CN.md)

---

Every Claude Code user repeats the same things. The same review flow. The same
"polish this paragraph". The same SSH-debug ritual. Today, you have to **notice
the pattern yourself** and write a Skill by hand.

`skill-miner` flips that. It reads the JSONL session logs Claude Code already
writes to `~/.claude/projects/`, finds recurring prompt + tool-sequence pairs,
and **drafts a `SKILL.md` for each pattern**. You review, accept, ignore.

## Why skill-miner

Existing Skills registries — [`anthropics/skills`](https://github.com/anthropics/skills),
[`tech-leads-club/agent-skills`](https://github.com/tech-leads-club/agent-skills),
others — treat Skills as **something humans hand-author and publish**.

`skill-miner` treats Skills as **something the agent harvests from your own
behaviour**. You don't have to know what to write. The repetition tells you.

|                              | hand-authored Skills | `skill-miner`                       |
| ---------------------------- | -------------------- | ----------------------------------- |
| Source of truth              | what you think you do | what you **actually** do            |
| Discovery cost               | manual reflection    | runs in 1 second                    |
| Stays current                | rots                 | re-mines on every Stop hook         |
| Network / API key            | not required         | **never**                           |
| Sends your prompts anywhere  | no                   | **no, ever**                        |

## Install

```bash
pip install -e .
```

Requires Python 3.10+. **Zero runtime dependencies** — that constraint is
load-bearing, not aspirational.

## 60-second demo

```bash
# 1) Look at what you keep doing
skill-miner scan
# [skill-miner] loaded 163 turns from 51 sessions
# [skill-miner] 5 raw candidate(s); 3 kept after filtering.
#
#   id=a1b2c3d4e5  name=polish-academic-abstract  conf=0.78  evidence=12  sessions=5
#   desc: 润色这段学术摘要的语言
#   flow: Read:.md -> Edit:.md -> Bash:git

# 2) Get a markdown report you can skim
skill-miner report
# -> ~/.claude/mined-skills/report-2026-05-20.md

# 3) Promote a candidate to a real skill
skill-miner accept a1b2c3d4e5
# -> ~/.claude/skills/polish-academic-abstract/SKILL.md

# 4) Or kill it
skill-miner ignore a1b2c3d4e5

# 5) Auto-rescan after every Claude Code session
skill-miner install-hook

# 6) Let Claude Code itself auto-invoke skill-miner when you ask
#    "what am I doing repeatedly?"
skill-miner install-skill
```

## How it works

```
~/.claude/projects/*/*.jsonl
            │
            ▼
     ┌────────────┐    User prompts          ┌─────────────────────┐
     │  loader    │  ──────────────────────► │ TF-IDF + cosine     │
     │ (jsonl)    │                          │ clustering (≥ 0.35) │
     │            │  Tool calls (canonical   │ CJK bigrams handled │
     │            │  signatures: Bash:git,   └─────────┬───────────┘
     │            │  Edit:.py, WebFetch...)            │
     │            │                          ┌─────────▼───────────┐
     │            │  ──────────────────────► │ 3-to-5-gram mining  │
     └────────────┘                          │ ≥ 3 occurrences     │
                                             └─────────┬───────────┘
                                                       │
                                             ┌─────────▼───────────┐
                                             │  correlate          │
                                             │  cluster ↔ n-gram   │
                                             │  → confidence score │
                                             └─────────┬───────────┘
                                                       │
                                             ┌─────────▼───────────┐
                                             │  scrub PII +        │
                                             │  render SKILL.md    │
                                             └─────────────────────┘
```

For each `*.jsonl` under `~/.claude/projects/`:

1. **User prompts** are tokenised, TF-IDF-vectorised, clustered by cosine
   similarity (≥ 0.35). Chinese is handled via overlapping CJK bigrams.
   Greetings, slash-command markers, `[Request interrupted]` noise, and
   context-compaction summaries are dropped.
2. **Tool calls** are collapsed to canonical signatures (`Bash:git`, `Edit:.py`,
   `WebFetch`, …) then mined for 3-to-5-gram sequences that recur ≥ 3 times
   across sessions.
3. **Correlated** — each prompt cluster is paired with the tool n-gram most
   concentrated in its sessions. A heuristic confidence (`0..1`) is reported.

Each surviving pair becomes a `SKILL.md` draft with:

- a slug derived from cluster keywords (falls back to the tool flow,
  e.g. `read-edit-bash`, when the cluster is CJK-only)
- a scrubbed description and 2–3 example prompts from your history
- the typical tool sequence as a code block

## Privacy

This tool is **deliberately offline**:

- ✅ Reads only files already on your disk
- ✅ Zero runtime dependencies; nothing dials home
- ✅ Output stays under `~/.claude/mined-skills/` and `~/.claude/skills/`
- ✅ Auto-redacts emails, IPs, file paths, `~/...` paths,
  `password=` / `token=` patterns, and long alphanumeric blobs that look
  like secrets — applied at write time **and** re-applied on every save,
  so legacy entries get scrubbed too

If the regex misses something obviously sensitive, please open an issue with
a reproducer that **does not contain the real secret**.

## FAQ

**Q: My scan returned 0 candidates. Did it break?**
No. The thresholds (`min_count >= 3`, `min_cluster_size >= 3`, `confidence >=
0.25`) are set conservatively to avoid noise. With < 30 turns of history, you
will mostly see nothing — that is correct behaviour. Use Claude Code more,
then re-scan.

**Q: I see candidates whose flow is wrong (e.g. `TaskUpdate -> Write:.py` for
an SSH question).**
TF-IDF clustering is deliberately simple. Sometimes a real prompt cluster gets
paired with a tool n-gram that happened to dominate the same sessions for
unrelated reasons. **Always review before accepting.** That is what the
"Examples" section in `skill-miner report` is for.

**Q: Why no embeddings model? Why no LLM call?**
Because `pip install` of a 500 MB model or an API key gate would lose half the
audience. v0.1's hard constraint is **stdlib only, works on any Python 3.10+**.
Better ranking is on the roadmap as an opt-in extra.

**Q: Will `accept` overwrite an existing `~/.claude/skills/<name>/SKILL.md`?**
Yes — `accept` always writes the file. If you have hand-edited a previously
accepted skill, copy it elsewhere first, or `skill-miner ignore <id>` it.

**Q: Will re-scan reset my `accepted` / `ignored` decisions?**
No. State is keyed by `sha1(name || ngram)[:10]`. As long as the candidate
keeps the same name + tool flow, your decision sticks across re-scans.

**Q: I'm on Windows and the report shows mojibake.**
The CLI calls `sys.stdout.reconfigure(encoding="utf-8")` to handle this. If you
still see broken Chinese, you are probably reading `state.json` with a tool
that ignores the BOM-less UTF-8 declaration. Open it with VS Code or any
editor that respects UTF-8.

## Caveats (this is alpha)

- Designed for users with ≥ 1 week of Claude Code history. With < 30 turns it
  will produce mostly noise.
- The TF-IDF clustering can fuse unrelated prompts that share enough vocabulary.
- Confidence is a heuristic, not a probability.
- Names are slugified greedily; rename via the frontmatter after accepting.

## Roadmap

- [ ] Optional `--with-embeddings` extra for better clustering
- [ ] Side-by-side diff when re-mining (what's new since last scan?)
- [ ] Multi-machine merge (run on laptop + workstation, union the candidates)
- [ ] Smarter Bash-command signatures (extract repeated `--flag` shapes, not
      just the head program)
- [ ] Suggest n-gram **gap-grams** (e.g. `Read:.rs → ??? → Bash:cargo`) to
      catch flows where the middle step varies

## Contributing

Issues and PRs welcome. Keep the **zero runtime dependencies** rule unless
you're contributing to the (future) `--with-embeddings` extra.

```bash
pip install -e .[dev]
pytest -q
```

See [CHANGELOG.md](CHANGELOG.md) for version history.

## License

MIT. See [LICENSE](LICENSE).
