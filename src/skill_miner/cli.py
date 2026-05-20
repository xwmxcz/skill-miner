"""skill-miner CLI: scan / report / accept / install-hook."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .loader import default_claude_dir, iter_sessions
from .extractor import iter_turns
from .miner import mine
from .reporter import write_report
from .store import (
    default_state_dir,
    load_state,
    save_state,
    upsert_candidates,
)
from .synthesizer import is_low_signal, to_skill_draft


def _force_utf8_stdout() -> None:
    """Windows consoles default to a non-UTF-8 codepage. Make output safe."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _dedupe_names(drafts: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Make sure no two drafts share a name; suffix collisions with -2, -3, ..."""
    seen: dict[str, int] = {}
    out: list[tuple[str, str, str]] = []
    for name, desc, md in drafts:
        n = seen.get(name, 0) + 1
        seen[name] = n
        if n > 1:
            new_name = f"{name}-{n}"
            md = md.replace(f"name: {name}\n", f"name: {new_name}\n", 1)
            name = new_name
        out.append((name, desc, md))
    return out


def _collect_turns(claude_dir: Path):
    turns = []
    session_count = 0
    for session in iter_sessions(claude_dir):
        session_count += 1
        for t in iter_turns(session):
            turns.append(t)
    return turns, session_count


def cmd_scan(args: argparse.Namespace) -> int:
    claude_dir = Path(args.projects_dir) if args.projects_dir else default_claude_dir()
    if not claude_dir.exists():
        print(f"[skill-miner] no claude projects directory at {claude_dir}", file=sys.stderr)
        return 2
    print(f"[skill-miner] scanning {claude_dir}")
    turns, session_count = _collect_turns(claude_dir)
    print(f"[skill-miner] loaded {len(turns)} turns from {session_count} sessions")
    if not turns:
        print("[skill-miner] nothing to mine.")
        return 0

    candidates = mine(turns)
    state = load_state()
    drafts = []
    kept_candidates = []
    MIN_CONF = 0.25
    for cand in candidates:
        if cand.confidence < MIN_CONF:
            continue
        draft = to_skill_draft(cand)
        if is_low_signal(draft.description):
            continue
        drafts.append((draft.name, draft.description, draft.render()))
        kept_candidates.append(cand)
    drafts = _dedupe_names(drafts)
    print(f"[skill-miner] {len(candidates)} raw candidate(s); {len(drafts)} kept after filtering.")
    if not drafts:
        return 0

    stored = upsert_candidates(state, kept_candidates, drafts)
    save_state(state)

    # Pretty print
    for sc in stored:
        print()
        print(f"  id={sc.id}  name={sc.name}  conf={sc.confidence:.2f}  "
              f"evidence={sc.evidence_count}  sessions={len(sc.sessions)}  status={sc.status}")
        print(f"  desc: {sc.description}")
        if sc.ngram:
            print(f"  flow: {sc.ngram}")
    print()
    print(f"[skill-miner] state saved to {default_state_dir() / 'state.json'}")
    print("[skill-miner] run 'skill-miner accept <id>' to promote a candidate.")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    state = load_state()
    if not state.candidates:
        print("[skill-miner] no candidates in state. Run 'skill-miner scan' first.", file=sys.stderr)
        return 1
    out_path = write_report(state)
    print(f"[skill-miner] report written to {out_path}")
    return 0


def cmd_accept(args: argparse.Namespace) -> int:
    state = load_state()
    cand = state.candidates.get(args.id)
    if not cand:
        print(f"[skill-miner] no candidate with id {args.id}", file=sys.stderr)
        return 1
    skills_root = Path.home() / ".claude" / "skills" / cand.name
    skills_root.mkdir(parents=True, exist_ok=True)
    target = skills_root / "SKILL.md"
    target.write_text(cand.skill_md, encoding="utf-8")
    cand.status = "accepted"
    save_state(state)
    print(f"[skill-miner] accepted {cand.id} -> {target}")
    print("[skill-miner] review/edit it before relying on it.")
    return 0


def cmd_ignore(args: argparse.Namespace) -> int:
    state = load_state()
    cand = state.candidates.get(args.id)
    if not cand:
        print(f"[skill-miner] no candidate with id {args.id}", file=sys.stderr)
        return 1
    cand.status = "ignored"
    save_state(state)
    print(f"[skill-miner] {cand.id} marked ignored.")
    return 0


def cmd_install_hook(args: argparse.Namespace) -> int:
    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[skill-miner] {settings_path} is not valid JSON; aborting.", file=sys.stderr)
            return 1
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings = {}

    hooks = settings.setdefault("hooks", {})
    stop_hooks = hooks.setdefault("Stop", [])
    cmd = "skill-miner hook"
    # de-dup
    already = any(
        isinstance(h, dict)
        and any(
            isinstance(entry, dict) and entry.get("command") == cmd
            for entry in (h.get("hooks") or [])
        )
        for h in stop_hooks
    )
    if already:
        print("[skill-miner] hook already installed.")
        return 0
    stop_hooks.append({
        "matcher": "*",
        "hooks": [{"type": "command", "command": cmd}],
    })
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[skill-miner] installed Stop hook in {settings_path}")
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    """Invoked by Claude Code as a Stop hook. Runs a quiet incremental scan."""
    from .hook import run_hook
    return run_hook()


def cmd_install_skill(args: argparse.Namespace) -> int:
    """Copy the bundled SKILL.md to ~/.claude/skills/skill-miner/SKILL.md."""
    from importlib.resources import files

    target_dir = Path.home() / ".claude" / "skills" / "skill-miner"
    target = target_dir / "SKILL.md"
    if target.exists() and not args.force:
        print(f"[skill-miner] {target} already exists. Use --force to overwrite.", file=sys.stderr)
        return 1
    try:
        src = files("skill_miner.resources").joinpath("skill-miner/SKILL.md")
        content = src.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as e:
        print(f"[skill-miner] bundled SKILL.md not found: {e}", file=sys.stderr)
        return 1
    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"[skill-miner] installed SKILL.md to {target}")
    print("[skill-miner] Claude Code will pick it up on next launch.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    state = load_state()
    if not state.candidates:
        print("[skill-miner] no candidates. Run 'skill-miner scan'.")
        return 0
    rows = sorted(
        state.candidates.values(),
        key=lambda c: (c.status != "proposed", -c.confidence),
    )
    print(f"{'id':<12}{'status':<10}{'conf':<6}{'evid':<6}{'name'}")
    for c in rows:
        print(f"{c.id:<12}{c.status:<10}{c.confidence:<6.2f}{c.evidence_count:<6}{c.name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skill-miner",
        description="Mine reusable Claude Code Skills from your own session history. 100% local.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="Scan ~/.claude/projects and refresh candidate skills.")
    s.add_argument("--projects-dir", help="Override projects directory.")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("list", help="List current candidates.")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("report", help="Write a markdown report of current candidates.")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("accept", help="Promote a candidate to ~/.claude/skills/<name>/SKILL.md")
    s.add_argument("id")
    s.set_defaults(func=cmd_accept)

    s = sub.add_parser("ignore", help="Mark a candidate as ignored.")
    s.add_argument("id")
    s.set_defaults(func=cmd_ignore)

    s = sub.add_parser("install-hook", help="Register a Claude Code Stop hook.")
    s.set_defaults(func=cmd_install_hook)

    s = sub.add_parser(
        "install-skill",
        help="Install the bundled SKILL.md so Claude Code can auto-invoke skill-miner.",
    )
    s.add_argument("--force", action="store_true", help="Overwrite an existing SKILL.md.")
    s.set_defaults(func=cmd_install_skill)

    s = sub.add_parser("hook", help="(internal) entry point invoked by the Stop hook.")
    s.set_defaults(func=cmd_hook)

    return p


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
