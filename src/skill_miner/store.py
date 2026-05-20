"""Persist mined candidates to ~/.claude/mined-skills/state.json."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .miner import Candidate
from .synthesizer import scrub


def default_state_dir() -> Path:
    return Path.home() / ".claude" / "mined-skills"


@dataclass
class StoredCandidate:
    id: str
    name: str
    description: str
    status: str          # proposed | accepted | ignored
    evidence_count: int
    sessions: list[str]
    confidence: float
    ngram: str | None
    example_prompts: list[str]
    skill_md: str
    created_at: str
    updated_at: str


@dataclass
class State:
    last_scan_at: str | None = None
    candidates: dict[str, StoredCandidate] = field(default_factory=dict)


def _candidate_id(name: str, ngram: str | None) -> str:
    h = hashlib.sha1()
    h.update(name.encode("utf-8"))
    if ngram:
        h.update(b"::")
        h.update(ngram.encode("utf-8"))
    return h.hexdigest()[:10]


def load_state(state_dir: Path | None = None) -> State:
    sdir = state_dir or default_state_dir()
    path = sdir / "state.json"
    if not path.exists():
        return State()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return State()
    candidates = {
        cid: StoredCandidate(**c) for cid, c in (data.get("candidates") or {}).items()
    }
    return State(last_scan_at=data.get("last_scan_at"), candidates=candidates)


def save_state(state: State, state_dir: Path | None = None) -> Path:
    sdir = state_dir or default_state_dir()
    sdir.mkdir(parents=True, exist_ok=True)
    path = sdir / "state.json"
    # Idempotent re-scrub so historical entries written before scrubbing
    # was added (or that were not touched by the latest scan) cannot leak.
    for c in state.candidates.values():
        c.description = scrub(c.description)
        c.example_prompts = [scrub(p) for p in c.example_prompts]
        c.skill_md = scrub(c.skill_md)
    payload = {
        "last_scan_at": state.last_scan_at,
        "candidates": {cid: asdict(c) for cid, c in state.candidates.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def upsert_candidates(
    state: State,
    candidates: list[Candidate],
    drafts: list[tuple[str, str, str]],  # (name, description, skill_md) aligned with candidates
) -> list[StoredCandidate]:
    """Merge mined candidates into state, preserving accepted/ignored statuses."""
    now = datetime.now(timezone.utc).isoformat()
    stored: list[StoredCandidate] = []
    for cand, (name, description, skill_md) in zip(candidates, drafts):
        ngram_sig = cand.ngram.signature if cand.ngram else None
        cid = _candidate_id(name, ngram_sig)
        existing = state.candidates.get(cid)
        status = existing.status if existing else "proposed"
        created_at = existing.created_at if existing else now
        sc = StoredCandidate(
            id=cid,
            name=name,
            description=description,
            status=status,
            evidence_count=cand.evidence_count,
            sessions=sorted(cand.sessions),
            confidence=cand.confidence,
            ngram=ngram_sig,
            example_prompts=[scrub(p) for p in cand.example_prompts[:3]],
            skill_md=skill_md,
            created_at=created_at,
            updated_at=now,
        )
        state.candidates[cid] = sc
        stored.append(sc)
    state.last_scan_at = now
    return stored
