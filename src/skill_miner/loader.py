"""Load Claude Code session JSONL files from ~/.claude/projects/.

Each .jsonl file is one session. Each line is one event (one JSON object).
We only care about lines with ``type`` in {"user", "assistant"}.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


def default_claude_dir() -> Path:
    return Path.home() / ".claude" / "projects"


@dataclass
class SessionEvent:
    type: str
    raw: dict
    timestamp: str | None = None
    session_id: str | None = None
    cwd: str | None = None


@dataclass
class Session:
    session_id: str
    project_dir: str
    source_path: Path
    events: list[SessionEvent] = field(default_factory=list)


def _parse_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def load_session(jsonl_path: Path) -> Session | None:
    """Parse a single .jsonl file. Returns None if the file has no usable events."""
    if not jsonl_path.exists():
        return None
    events: list[SessionEvent] = []
    session_id: str | None = None
    project_dir: str = jsonl_path.parent.name

    with jsonl_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            obj = _parse_line(line)
            if obj is None:
                continue
            ev_type = obj.get("type")
            if not ev_type:
                continue
            if ev_type not in {"user", "assistant"}:
                # capture sessionId from any line if we don't have one yet
                if session_id is None and isinstance(obj.get("sessionId"), str):
                    session_id = obj["sessionId"]
                continue
            session_id = session_id or obj.get("sessionId") or jsonl_path.stem
            events.append(
                SessionEvent(
                    type=ev_type,
                    raw=obj,
                    timestamp=obj.get("timestamp"),
                    session_id=obj.get("sessionId"),
                    cwd=obj.get("cwd"),
                )
            )

    if not events:
        return None

    return Session(
        session_id=session_id or jsonl_path.stem,
        project_dir=project_dir,
        source_path=jsonl_path,
        events=events,
    )


def iter_sessions(claude_projects_dir: Path | None = None) -> Iterator[Session]:
    """Yield every Session under ~/.claude/projects/*/*.jsonl."""
    root = claude_projects_dir or default_claude_dir()
    if not root.exists():
        return
    for jsonl_path in sorted(root.glob("*/*.jsonl")):
        session = load_session(jsonl_path)
        if session is not None:
            yield session
