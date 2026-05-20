from pathlib import Path

from skill_miner.loader import load_session
from skill_miner.extractor import iter_turns
from skill_miner.miner import find_tool_ngrams, cluster_prompts, correlate, mine

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


def _turns():
    s = load_session(FIXTURE)
    assert s is not None
    return list(iter_turns(s))


def test_extractor_emits_turns_with_tool_calls():
    turns = _turns()
    assert len(turns) == 3
    assert turns[0].prompt and "润色" in turns[0].prompt
    assert [tc.signature for tc in turns[0].tool_calls] == [
        "Read:.md", "Edit:.md", "Bash:git",
    ]


def test_find_tool_ngrams_detects_repeated_flow():
    # Replicate the fixture turns across multiple synthetic sessions so the
    # n-gram min_count threshold is satisfied.
    from skill_miner.extractor import Turn, ToolCall

    def mk(sid: str):
        seq = [("Read", "Read:.md"), ("Edit", "Edit:.md"), ("Bash", "Bash:git")]
        return Turn(
            session_id=sid,
            cwd="/tmp",
            prompt="润色这段摘要",
            tool_calls=[ToolCall(name=n, signature=s) for n, s in seq],
        )

    turns = [mk(f"s{i}") for i in range(3)]
    ngrams = find_tool_ngrams(turns, n_min=3, n_max=3, min_count=3)
    assert any(ng.tokens == ("Read:.md", "Edit:.md", "Bash:git") for ng in ngrams)


def test_cluster_prompts_groups_similar_phrasing():
    prompts = [
        "润色这段学术摘要的语言",
        "帮我润色一下这段摘要",
        "润色这段学术写作",
        "随便聊点别的",  # outlier
        "今天天气真好啊",  # outlier
    ]
    clusters = cluster_prompts(prompts, similarity_threshold=0.15, min_cluster_size=2)
    assert clusters, "expected at least one cluster"
    biggest = max(clusters, key=lambda c: len(c.members))
    assert len(biggest.members) >= 2


def test_mine_end_to_end_on_replicated_fixture():
    # Stitch the same fixture three times under different session IDs.
    from skill_miner.extractor import Turn

    base = _turns()
    multi: list[Turn] = []
    for sid_suffix in range(3):
        for t in base:
            multi.append(
                Turn(
                    session_id=f"fixture-session-{sid_suffix}",
                    cwd=t.cwd,
                    prompt=t.prompt,
                    tool_calls=list(t.tool_calls),
                )
            )
    candidates = mine(multi)
    assert candidates, "expected at least one candidate"
    top = candidates[0]
    assert top.confidence > 0
