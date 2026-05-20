"""Turn a mined Candidate into a SKILL.md draft, with PII scrubbed."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .miner import Candidate


# --- PII scrubbing ---------------------------------------------------------

_WIN_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"'`<>|]+")
_POSIX_PATH_RE = re.compile(r"(?:/[A-Za-z0-9_.\-]+){2,}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HOME_RE = re.compile(r"~[\\/][^\s\"'`<>|]+")
# A token >= 12 chars mixing digits and letters looks like a secret/password.
_HIGH_ENTROPY_RE = re.compile(r"\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{12,}\b")
# Auth-ish key:value pairs (e.g. "password: hunter2", "token=abc123")
_AUTH_KV_RE = re.compile(
    r"\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|auth)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def scrub(text: str) -> str:
    text = _AUTH_KV_RE.sub(lambda m: f"{m.group(1)}=<redacted>", text)
    text = _EMAIL_RE.sub("<email>", text)
    text = _IP_RE.sub("<ip>", text)
    text = _WIN_PATH_RE.sub("<path>", text)
    text = _POSIX_PATH_RE.sub("<path>", text)
    text = _HOME_RE.sub("<path>", text)
    text = _HIGH_ENTROPY_RE.sub("<token>", text)
    return text


# --- Name + description synthesis -----------------------------------------

_SAFE_NAME_RE = re.compile(r"[^a-z0-9\-]+")
_CJK_RE = re.compile(r"[一-鿿]+")
_LIKELY_SECRET_RE = re.compile(r"^(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{8,}$")


def _slugify(parts: list[str], fallback: list[str] | None = None, max_len: int = 32) -> str:
    def usable(toks: list[str]) -> list[str]:
        return [
            p for p in toks
            if not _CJK_RE.search(p)
            and any(c.isalpha() for c in p)
            and len(p) >= 3
            and not _LIKELY_SECRET_RE.match(p)
        ]
    ascii_parts = usable(parts)
    if not ascii_parts and fallback:
        ascii_parts = usable(fallback)
    if not ascii_parts:
        return "mined-skill"
    slug = "-".join(ascii_parts[:3]).lower()
    slug = _SAFE_NAME_RE.sub("-", slug).strip("-")
    return (slug or "mined-skill")[:max_len]


def _short_desc(candidate: Candidate) -> str:
    if not candidate.example_prompts:
        return "Auto-derived skill from recurring user workflow."
    medoid = candidate.example_prompts[0]
    one_line = re.sub(r"\s+", " ", medoid).strip()
    if len(one_line) > 140:
        one_line = one_line[:137] + "..."
    return one_line


def is_low_signal(scrubbed_desc: str) -> bool:
    """A description dominated by <placeholders> is not useful to show."""
    if not scrubbed_desc:
        return True
    placeholder_chars = sum(
        len(p) for p in re.findall(r"<[a-z]+>", scrubbed_desc)
    )
    alpha_chars = sum(1 for ch in scrubbed_desc if ch.isalnum() or '一' <= ch <= '鿿')
    return placeholder_chars > 0 and alpha_chars < max(8, placeholder_chars)


# --- SKILL.md rendering ----------------------------------------------------

@dataclass
class SkillDraft:
    name: str
    description: str
    body: str

    def render(self) -> str:
        return (
            f"---\n"
            f"name: {self.name}\n"
            f"description: {self.description}\n"
            f"metadata:\n"
            f"  type: derived\n"
            f"  source: skill-miner\n"
            f"---\n\n"
            f"{self.body}\n"
        )


def to_skill_draft(candidate: Candidate, *, name_hint: str | None = None) -> SkillDraft:
    # build a fallback list from the tool n-gram so CJK-only clusters still get
    # a meaningful slug (e.g. "read-edit-bash")
    tool_fallback: list[str] = []
    if candidate.ngram:
        for tok in candidate.ngram.tokens:
            name_part = tok.split(":", 1)[0].lower()
            if name_part and name_part not in tool_fallback:
                tool_fallback.append(name_part)
    name = name_hint or _slugify(candidate.cluster.top_terms, fallback=tool_fallback)
    description = scrub(_short_desc(candidate))

    steps = (
        candidate.ngram.signature if candidate.ngram else "(no consistent tool sequence detected)"
    )
    session_count = len(candidate.sessions)
    body_parts: list[str] = []
    body_parts.append("## What this skill does\n")
    body_parts.append(
        f"This skill was auto-derived from **{candidate.evidence_count}** similar requests "
        f"across **{session_count}** sessions. Review and edit before promoting it to a "
        f"first-class skill.\n"
    )

    body_parts.append("## Typical tool sequence\n")
    body_parts.append(f"```\n{steps}\n```\n")

    body_parts.append("## Example prompts from your history\n")
    for ex in candidate.example_prompts[:3]:
        clean = scrub(ex).strip().splitlines()[0]
        if len(clean) > 200:
            clean = clean[:197] + "..."
        body_parts.append(f"- {clean}")
    body_parts.append("")  # trailing newline

    body_parts.append("## Confidence")
    body_parts.append(f"{candidate.confidence:.2f}\n")

    return SkillDraft(name=name, description=description, body="\n".join(body_parts))
