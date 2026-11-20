"""src/cluster.py: merge_and_rate (mocked model answer) and the ADVICE / ROUNDUP filters."""
import pytest

import re

from src.cluster import ADVICE, ROUNDUP, cluster, merge_and_rate

NOON = "2026-11-18T12:00:00+00:00"


def build(titles, date=NOON):
    """titles: {story_id: headline}. One article per story."""
    arts, stories = {}, []
    for n, (sid, title) in enumerate(titles.items()):
        aid = f"a{n}"
        # proper_names() learns names from the article BODY (capitalised mid-sentence, at least twice)
        body = " ".join(f"he said {w} left and then said {w} stayed." for w in re.findall(r"[A-Z][a-z]{3,}", title))
        arts[aid] = {"id": aid, "headline": title, "publisher": f"Pub{n}", "date": date, "text": body}
        stories.append({"id": sid, "title": title, "article_ids": [aid], "translations": {}})
    return stories, arts


def ask(merge=(), importance=None):
    def fake(step, system, user, schema, **kw):
        assert step == "merge"
        imp = importance if importance is not None else {}
        return {"merge": [list(g) for g in merge],
                "importance": [{"id": i, "score": s, "topic": "markets"} for i, s in imp.items()]}
    return fake


def titles_with(extra):
    d = dict(extra)
    for i in range(30):  # filler so the "rare name" threshold is the normal one
        d[f"f{i}"] = f"Filler headline number {i} about weather"
    return d


def test_merge_needs_shared_rare_name_in_both_titles():
    stories, arts = build({"s1": "Nvidia CEO Huang warns on chips", "s2": "Huang says Nvidia demand is strong"})
    out, info = merge_and_rate(stories, arts, ask([["s1", "s2"]], {"s1": 4, "s2": 3}), "2026-11-18")
    assert info["merges"] == 1 and len(out) == 1
    assert sorted(out[0]["article_ids"]) == ["a0", "a1"]


def test_merge_refused_without_shared_name():
    stories, arts = build({"s1": "Nvidia CEO Huang warns on chips", "s2": "Tesla recalls vehicles in Europe"})
    out, info = merge_and_rate(stories, arts, ask([["s1", "s2"]]), "2026-11-18")
    assert info["merges"] == 0 and len(out) == 2 and len(info["refused"]) == 1


def test_name_only_in_one_title_is_not_enough():
    # "Huang" appears only in the second title; the head's TITLE has no shared name
    stories, arts = build({"s1": "Chipmaker shares fall sharply", "s2": "Huang says chip demand is strong"})
    _, info = merge_and_rate(stories, arts, ask([["s1", "s2"]]), "2026-11-18")
    assert info["merges"] == 0


def test_common_name_is_not_rare():
    # "Trump" in more than max(3, 5 %) of stories is not a valid link
    d = {f"s{i}": f"Trump news item {i} about tariffs" for i in range(1, 10)}
    stories, arts = build(d)
    _, info = merge_and_rate(stories, arts, ask([["s1", "s2"]]), "2026-11-18")
    assert info["merges"] == 0


def test_big_unrelated_group_is_not_glued_together():
    # the model once proposed one group of 349 unrelated stories: the code keeps them apart
    d = {f"s{i}": f"Company{chr(97 + i % 26)}{chr(97 + i // 26)}x{'q' * (i % 5)} Zorbtek{i:03d} news" for i in range(1, 60)}
    stories, arts = build(d)
    out, info = merge_and_rate(stories, arts, ask([list(d)]), "2026-11-18")
    assert info["merges"] == 0 and len(out) == len(d) and info["refused"]


def test_name_not_in_article_body_is_not_a_proper_name():
    # "Huang" only in the headlines (Title Case proves nothing): no merge
    stories, arts = build({"s1": "Huang warns on chips", "s2": "Huang sees strong demand"})
    for a in arts.values():
        a["text"] = "nothing capitalised in here at all"
    _, info = merge_and_rate(stories, arts, ask([["s1", "s2"]]), "2026-11-18")
    assert info["merges"] == 0


def test_unknown_ids_and_single_group_ignored():
    stories, arts = build({"s1": "Huang Nvidia one", "s2": "Huang Nvidia two"})
    out, info = merge_and_rate(stories, arts, ask([["s1", "zzz"], ["s1"]]), "2026-11-18")
    assert info["merges"] == 0 and len(out) == 2


def test_reranking_by_importance_and_ids_renumbered():
    stories, arts = build({"s1": "Minor gossip about celebrity", "s2": "Fed cuts rates unexpectedly"})
    out, _ = merge_and_rate(stories, arts, ask([], {"s1": 1, "s2": 5}), "2026-11-18")
    assert [s["title"] for s in out] == ["Fed cuts rates unexpectedly", "Minor gossip about celebrity"]
    assert [s["id"] for s in out] == ["s1", "s2"] and [s["rank"] for s in out] == [1, 2]
    assert out[0]["importance"] == 5 and out[0]["topic"] == "markets"


def test_importance_clamped_and_default_for_unrated():
    stories, arts = build({"s1": "Alpha story here", "s2": "Beta story there", "s3": "Gamma unrated"})
    out, _ = merge_and_rate(stories, arts, ask([], {"s1": 99, "s2": -4}), "2026-11-18")
    by_title = {s["title"]: s for s in out}
    assert by_title["Alpha story here"]["importance"] == 5
    assert by_title["Beta story there"]["importance"] == 1
    assert by_title["Gamma unrated"]["importance"] == 2 and by_title["Gamma unrated"]["topic"] == "other"


def test_fresher_story_scores_higher_at_equal_rating():
    stories, arts = build({"s1": "Old Alpha story", "s2": "Fresh Beta story"})
    arts["a0"]["date"] = "2026-11-10T12:00:00+00:00"
    out, _ = merge_and_rate(stories, arts, ask([], {"s1": 3, "s2": 3}), "2026-11-18")
    assert out[0]["title"] == "Fresh Beta story"


# ---------------------------------------------------------------- filters
@pytest.mark.parametrize("headline", [
    "3 Stocks to Buy Now Before the Rally",
    "Should You Invest in Nvidia After the Dip?",
    "Is Apple Stock a Good Buy Right Now?",
    "Wall Street Analyst Upgrades to 'Strong Buy'",
    "Bull of the Day: Microsoft (MSFT)",
])
def test_advice_headlines_match(headline):
    assert ADVICE.search(headline)


@pytest.mark.parametrize("headline", [
    "Nvidia reports record quarterly revenue",
    "Fed holds rates steady, Powell says",
    "Tesla shares fall after delivery miss",
])
def test_normal_headlines_pass_advice(headline):
    assert not ADVICE.search(headline)


@pytest.mark.parametrize("headline", [
    "Evening Digest: markets close mixed",
    "Morning Brief: what moved overnight",
    "5 Things to Know Before the Open",
    "Week Ahead: Fed minutes and retail sales",
    "Weekly Recap: stocks end higher",
    "Abendbericht: DAX schliesst leichter",
])
def test_roundup_headlines_match(headline):
    assert ROUNDUP.search(headline)


def test_cluster_drops_advice_and_roundups():
    def art(i, headline):
        return {"id": f"x{i}", "headline": headline, "excerpt": "", "text": headline + " body text here", "feed": "rss",
                "publisher": f"P{i}", "date": NOON, "sections": ["Markets"], "language": "en", "author": None}
    arts = [art(1, "Fed holds interest rates steady"), art(2, "3 Stocks to Buy Now"),
            art(3, "Evening Digest: markets close mixed")]
    stories = cluster(arts, arts)
    ids = {i for s in stories for i in s["article_ids"]}
    assert ids == {"x1"}
