"""Write a human-readable markdown report of current candidates."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .store import State, default_state_dir


def write_report(state: State, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or default_state_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    path = out_dir / f"report-{stamp}.md"

    rows = sorted(state.candidates.values(), key=lambda c: -c.confidence)
    lines: list[str] = []
    lines.append(f"# skill-miner report — {stamp}")
    lines.append("")
    lines.append(f"Candidates: **{len(rows)}**  ·  Last scan: {state.last_scan_at or 'unknown'}")
    lines.append("")
    for c in rows:
        lines.append(f"## `{c.name}`  ·  id `{c.id}`  ·  status `{c.status}`")
        lines.append("")
        lines.append(f"- confidence: **{c.confidence:.2f}**")
        lines.append(f"- evidence: {c.evidence_count} prompt(s) across {len(c.sessions)} session(s)")
        if c.ngram:
            lines.append(f"- tool flow: `{c.ngram}`")
        lines.append("")
        lines.append(f"> {c.description}")
        lines.append("")
        if c.example_prompts:
            lines.append("Examples:")
            for ex in c.example_prompts[:3]:
                first = ex.strip().splitlines()[0]
                if len(first) > 200:
                    first = first[:197] + "..."
                lines.append(f"- {first}")
            lines.append("")
        lines.append(f"Accept with: `skill-miner accept {c.id}`")
        lines.append("")
        lines.append("---")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
