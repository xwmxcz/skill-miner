"""Stop hook entry point: quietly re-scan and update state."""
from __future__ import annotations

import sys

from .cli import _collect_turns
from .loader import default_claude_dir
from .miner import mine
from .store import load_state, save_state, upsert_candidates
from .synthesizer import to_skill_draft


def run_hook() -> int:
    try:
        turns, _ = _collect_turns(default_claude_dir())
        if not turns:
            return 0
        candidates = mine(turns)
        state = load_state()
        drafts = []
        kept = []
        from .synthesizer import is_low_signal
        for c in candidates:
            if c.confidence < 0.25:
                continue
            d = to_skill_draft(c)
            if is_low_signal(d.description):
                continue
            drafts.append((d.name, d.description, d.render()))
            kept.append(c)
        from .cli import _dedupe_names
        drafts = _dedupe_names(drafts)
        upsert_candidates(state, kept, drafts)
        save_state(state)
    except Exception as e:  # never block Claude Code on hook errors
        print(f"[skill-miner hook] non-fatal: {e}", file=sys.stderr)
        return 0
    return 0
