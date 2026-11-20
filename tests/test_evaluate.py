import json

from eval.evaluate import evaluate, event_report, pairwise, story_map

EVENTS = [
    {"id": "E1", "key": "ppi", "importance": "A", "articles": [{"id": "a1"}, {"id": "a2"}, {"id": "a2de"}], "ambiguous": ["x9"]},
    {"id": "E2", "key": "intel", "importance": "B", "articles": [{"id": "b1"}, {"id": "b2"}], "ambiguous": []},
    {"id": "E3", "key": "waller", "importance": "C", "articles": [{"id": "c1"}], "ambiguous": []},
]
# s1 holds E1 with its German translation and the ambiguous x9; E2 is split; s3 mixes b2 with c1 and an unkeyed article
STORIES = [
    {"id": "s1", "rank": 1, "title": "PPI", "article_ids": ["a1", "a2", "x9"], "translations": {"a2": {"de": "a2de"}}},
    {"id": "s2", "rank": 2, "title": "Intel", "article_ids": ["b1"], "translations": {}},
    {"id": "s3", "rank": 3, "title": "Mix", "article_ids": ["b2", "c1", "z1"], "translations": {}},
]


def test_translations_belong_to_their_story():
    assert story_map(STORIES)["a2de"] == "s1"


def test_pairwise_counts():
    p = pairwise(EVENTS, story_map(STORIES))
    # gold pairs: a1-a2, a1-a2de, a2-a2de, b1-b2 = 4; predicted together: the three E1 pairs + b2-c1
    assert (p["true_pairs"], p["false_pairs"], p["missed_pairs"]) == (3, 1, 1)
    assert p["precision"] == 0.75 and p["recall"] == 0.75


def test_split_mixed_and_ambiguous():
    rows = {r["event"]: r for r in event_report(EVENTS, STORIES, story_map(STORIES))}
    assert rows["E1"]["status"] == "ok" and rows["E1"]["rank"] == 1  # x9 is ambiguous, not a mix
    # tie 1:1, the better-ranked s2 is E2's main story, so E2 is split; the mix shows up at E3
    assert rows["E2"]["status"] == "split" and rows["E2"]["stories"] == 2 and rows["E2"]["main_story"] == "s2"
    assert rows["E3"]["mixed_with"] == ["E2"] and rows["E3"]["unkeyed_in_main"] == 1


def test_missing_article_and_end_to_end(tmp_path):
    events = EVENTS + [{"id": "E4", "key": "gone", "importance": "C", "articles": [{"id": "d1"}], "ambiguous": []}]
    (tmp_path / "stories.json").write_text(json.dumps(STORIES), encoding="utf-8")
    facts = [{"id": "s1-f1", "sources": [{"article_id": "a1", "quote": "The PPI rose 0.3% in October, below forecasts."}]}]
    (tmp_path / "facts.json").write_text(json.dumps({"facts": facts}), encoding="utf-8")
    b = tmp_path / "briefings" / "fx-trader-1234abcd"
    b.mkdir(parents=True)
    claims = [{"id": "c2", "kind": "claim", "text": "The PPI rose 0.3% in October."},
              {"id": "c3", "kind": "claim", "text": "Something new."},
              {"id": "c4", "kind": "context", "text": "Not a claim."}]
    (b / "briefing.json").write_text(json.dumps({"claims": claims}), encoding="utf-8")
    key = {"events": events,
           "facts": [{"checked_as": "s1-f1", "article_id": "a1", "quote_start": "the PPI rose 0.3%", "claim": "x",
                      "verdict": "correct", "reason": ""},
                     {"checked_as": "s9-f9", "article_id": "zz", "quote_start": "gone", "claim": "y",
                      "verdict": "wrong", "reason": ""}],
           "claims": [{"briefing": "fx-trader", "text": "The  PPI rose 0.3% in October.", "verdict": "wrong", "reason": "r"}]}
    r = evaluate(key, tmp_path)
    assert next(e for e in r["events"] if e["event"] == "E4")["status"] == "missing"
    assert r["facts_present"] == 1 and r["fact_accuracy"] == 1.0 and r["fact_accuracy_all_checked"] == 0.5
    assert len(r["claims_checked"]) == 1 and r["claim_accuracy"] == 0.0  # matched despite the double space
    assert [c["id"] for c in r["claims_unchecked"]] == ["c3"]
