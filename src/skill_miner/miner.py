"""Find recurring patterns: tool-sequence n-grams + prompt clusters, then correlate.

Pure stdlib so the package has *zero* runtime dependencies — that is a feature.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .extractor import Turn


# ---------------------------------------------------------------------------
# Tool-sequence n-gram mining
# ---------------------------------------------------------------------------

@dataclass
class NGram:
    tokens: tuple[str, ...]
    count: int
    sessions: set[str] = field(default_factory=set)

    @property
    def signature(self) -> str:
        return " -> ".join(self.tokens)


def find_tool_ngrams(
    turns: Sequence[Turn],
    n_min: int = 3,
    n_max: int = 5,
    min_count: int = 3,
) -> list[NGram]:
    """Return n-grams that appear at least ``min_count`` times across sessions.

    Tool calls within a single turn are concatenated, then we slide n-grams over
    the per-session sequence (turns are joined in order)."""
    # group turns by session, preserving order
    by_session: dict[str, list[Turn]] = defaultdict(list)
    for t in turns:
        by_session[t.session_id].append(t)

    counts: Counter[tuple[str, ...]] = Counter()
    seen_sessions: dict[tuple[str, ...], set[str]] = defaultdict(set)

    for sid, sturns in by_session.items():
        seq: list[str] = []
        for t in sturns:
            for tc in t.tool_calls:
                seq.append(tc.signature)
        if len(seq) < n_min:
            continue
        for n in range(n_min, n_max + 1):
            if len(seq) < n:
                continue
            for i in range(len(seq) - n + 1):
                gram = tuple(seq[i : i + n])
                # require at least one distinct token (skip 'Bash Bash Bash')
                if len(set(gram)) < 2:
                    continue
                counts[gram] += 1
                seen_sessions[gram].add(sid)

    out: list[NGram] = []
    for gram, c in counts.items():
        if c >= min_count:
            out.append(NGram(tokens=gram, count=c, sessions=seen_sessions[gram]))
    out.sort(key=lambda g: (-g.count, -len(g.tokens)))
    return out


# ---------------------------------------------------------------------------
# Prompt tokenization + TF-IDF + cosine clustering (stdlib only)
# ---------------------------------------------------------------------------

# Pull both ASCII word tokens and 2-char CJK shingles so Chinese prompts
# don't collapse to empty token sets.
_ASCII_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]+")
_CJK_RE = re.compile(r"[一-鿿]+")
_STOPWORDS_EN = {
    "the", "a", "an", "of", "to", "in", "is", "it", "and", "or", "for",
    "this", "that", "with", "on", "at", "be", "are", "was", "were",
    "as", "i", "you", "me", "we", "my", "your", "our", "do", "does",
    "did", "have", "has", "had", "can", "could", "would", "should",
    "please", "help", "let", "make", "want", "need", "use", "using",
}
_STOPWORDS_CN = {
    "的", "了", "和", "是", "在", "我", "你", "他", "她", "它", "这", "那",
    "一个", "一下", "可以", "请", "怎么", "什么", "需要", "帮我", "帮忙",
}


def _tokenize(text: str) -> list[str]:
    text_l = text.lower()
    toks: list[str] = []
    # English word tokens
    for m in _ASCII_RE.findall(text_l):
        if m not in _STOPWORDS_EN and len(m) >= 2:
            toks.append(m)
    # Chinese: char bigrams (overlapping)
    for run in _CJK_RE.findall(text):
        for i in range(len(run) - 1):
            bg = run[i : i + 2]
            if bg not in _STOPWORDS_CN:
                toks.append(bg)
    return toks


def _tfidf_vectors(docs: list[list[str]]) -> tuple[list[dict[str, float]], dict[str, float]]:
    n = len(docs)
    df: Counter[str] = Counter()
    for d in docs:
        for tok in set(d):
            df[tok] += 1
    idf = {tok: math.log((n + 1) / (cnt + 1)) + 1.0 for tok, cnt in df.items()}
    vectors: list[dict[str, float]] = []
    for d in docs:
        tf: Counter[str] = Counter(d)
        if not tf:
            vectors.append({})
            continue
        vec = {tok: (cnt / len(d)) * idf[tok] for tok, cnt in tf.items()}
        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm > 0:
            vec = {k: v / norm for k, v in vec.items()}
        vectors.append(vec)
    return vectors, idf


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


@dataclass
class PromptCluster:
    members: list[int]              # indices into the input prompt list
    centroid: dict[str, float]
    top_terms: list[str]
    medoid_idx: int                 # index of most representative member


def cluster_prompts(
    prompts: Sequence[str],
    similarity_threshold: float = 0.35,
    min_cluster_size: int = 3,
    min_prompt_chars: int = 6,
) -> list[PromptCluster]:
    """Greedy single-link clustering over TF-IDF cosine similarity."""
    docs: list[list[str]] = []
    keep: list[int] = []
    for i, p in enumerate(prompts):
        if not p or len(p) < min_prompt_chars:
            continue
        toks = _tokenize(p)
        if len(toks) < 2:
            continue
        docs.append(toks)
        keep.append(i)

    if len(docs) < min_cluster_size:
        return []

    vectors, idf = _tfidf_vectors(docs)

    # connected-components via similarity threshold
    n = len(vectors)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        if not vectors[i]:
            continue
        for j in range(i + 1, n):
            if not vectors[j]:
                continue
            if _cosine(vectors[i], vectors[j]) >= similarity_threshold:
                union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    clusters: list[PromptCluster] = []
    for members in groups.values():
        if len(members) < min_cluster_size:
            continue
        # centroid
        centroid: dict[str, float] = defaultdict(float)
        for m in members:
            for k, v in vectors[m].items():
                centroid[k] += v
        for k in list(centroid):
            centroid[k] /= len(members)
        # normalize centroid
        cnorm = math.sqrt(sum(v * v for v in centroid.values()))
        if cnorm > 0:
            centroid = {k: v / cnorm for k, v in centroid.items()}
        # medoid = member most similar to centroid
        medoid = max(members, key=lambda m: _cosine(vectors[m], centroid))
        # top terms by centroid weight
        top = sorted(centroid.items(), key=lambda kv: -kv[1])[:8]
        clusters.append(
            PromptCluster(
                members=[keep[m] for m in members],
                centroid=dict(centroid),
                top_terms=[t for t, _ in top],
                medoid_idx=keep[medoid],
            )
        )
    clusters.sort(key=lambda c: -len(c.members))
    return clusters


# ---------------------------------------------------------------------------
# Correlate prompt clusters with tool n-grams
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    cluster: PromptCluster
    ngram: NGram | None
    evidence_count: int          # number of (turn) instances supporting it
    sessions: set[str]
    confidence: float            # 0..1 heuristic
    example_prompts: list[str]


def correlate(
    clusters: Sequence[PromptCluster],
    ngrams: Sequence[NGram],
    turns: Sequence[Turn],
) -> list[Candidate]:
    """For each cluster, pick the n-gram most concentrated in its sessions."""
    out: list[Candidate] = []
    for cl in clusters:
        cluster_sessions: set[str] = set()
        examples: list[str] = []
        for m in cl.members:
            cluster_sessions.add(turns[m].session_id)
            if turns[m].prompt:
                examples.append(turns[m].prompt)

        best: NGram | None = None
        best_overlap = 0
        for ng in ngrams:
            overlap = len(ng.sessions & cluster_sessions)
            if overlap > best_overlap:
                best_overlap = overlap
                best = ng

        # confidence: bounded by cluster size and n-gram support
        size_score = min(1.0, len(cl.members) / 8.0)
        ngram_score = (best_overlap / max(1, len(cluster_sessions))) if best else 0.0
        confidence = round(0.55 * size_score + 0.45 * ngram_score, 3)

        # representative examples: medoid first, then 2 distinct others
        medoid_prompt = turns[cl.medoid_idx].prompt if cl.medoid_idx < len(turns) else None
        rep: list[str] = []
        if medoid_prompt:
            rep.append(medoid_prompt)
        for ex in examples:
            if ex not in rep:
                rep.append(ex)
            if len(rep) >= 3:
                break

        out.append(
            Candidate(
                cluster=cl,
                ngram=best,
                evidence_count=len(cl.members),
                sessions=cluster_sessions,
                confidence=confidence,
                example_prompts=rep,
            )
        )
    out.sort(key=lambda c: -c.confidence)
    return out


def mine(turns: Iterable[Turn]) -> list[Candidate]:
    """High-level convenience: turns -> candidates."""
    turns_list = list(turns)
    ngrams = find_tool_ngrams(turns_list)
    prompts = [t.prompt or "" for t in turns_list]
    clusters = cluster_prompts(prompts)
    return correlate(clusters, ngrams, turns_list)
