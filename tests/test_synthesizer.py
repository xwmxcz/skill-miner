from skill_miner.miner import Candidate, NGram, PromptCluster
from skill_miner.synthesizer import scrub, to_skill_draft


def test_scrub_redacts_paths_emails_ips():
    # All literals here are RFC 5737 / RFC 1918 / placeholder values.
    text = "see C:\\Users\\Alice\\secret.txt and /home/bob/.ssh/id_rsa, mail me at foo@bar.com from 198.51.100.5"
    out = scrub(text)
    assert "Alice" not in out
    assert "bob" not in out
    assert "foo@bar.com" not in out
    assert "198.51.100.5" not in out


def _make_candidate():
    cluster = PromptCluster(
        members=[0, 1, 2],
        centroid={"polish": 0.7, "abstract": 0.5},
        top_terms=["polish", "abstract", "academic"],
        medoid_idx=0,
    )
    ngram = NGram(
        tokens=("Read:.md", "Edit:.md", "Bash:git"),
        count=3,
        sessions={"s1", "s2", "s3"},
    )
    return Candidate(
        cluster=cluster,
        ngram=ngram,
        evidence_count=3,
        sessions={"s1", "s2", "s3"},
        confidence=0.7,
        example_prompts=[
            "Polish this abstract for clarity",
            "Polish the academic writing in C:\\papers\\draft.md",
            "Make the abstract more rigorous",
        ],
    )


def test_to_skill_draft_renders_valid_frontmatter():
    cand = _make_candidate()
    draft = to_skill_draft(cand)
    md = draft.render()
    assert md.startswith("---")
    assert "name:" in md
    assert "description:" in md
    assert "Read:.md -> Edit:.md -> Bash:git" in md
    # PII in example prompts is scrubbed
    assert "C:\\papers" not in md
