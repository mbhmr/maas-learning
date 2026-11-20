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


# ---------------------------------------------------------------- merge rule: names beyond the title
def multi(spec, date=NOON, body_names=()):
    """spec: {story_id: [headlines]}; the first headline is the title. One article (own outlet) per headline."""
    body = " ".join(f"he said {w} left and then said {w} stayed." for w in body_names)
    arts, stories, n = {}, [], 0
    for sid, heads in spec.items():
        ids = []
        for h in heads:
            aid = f"a{n}"
            arts[aid] = {"id": aid, "headline": h, "publisher": f"Pub{n}", "date": date, "text": body}
            ids.append(aid)
            n += 1
        stories.append({"id": sid, "title": heads[0], "article_ids": ids, "translations": {}})
    return stories, arts


def filler(d, nvidia=0):
    for i in range(30):
        d[f"f{i}"] = [f"Filler headline number {i} about weather"]
    for i in range(nvidia):  # make "Nvidia" a common name, as in the real week (36 stories)
        d[f"n{i}"] = [f"Nvidia chip item number {i}"]
    return d


def test_nvidia_split_is_joined_by_two_names_from_other_headline():
    # s1/s2 of 18 Nov: the title of the smaller story names only "NVIDIA" (common), its other headline says "Huang"
    d = filler({"s1": ["Jensen Huang Allies Push Nvidia Comeback", "Huang allies form war room", "Huang return?"],
                "s2": ["NVIDIA Leadership Crisis Opens Door for Chip Rivals", "Stocks to gain from the Jensen Huang saga"]},
               nvidia=6)
    stories, arts = multi(d, body_names=["Huang", "Nvidia"])
    out, info = merge_and_rate(stories, arts, ask([["s1", "s2"]]), "2026-11-18")
    assert info["merges"] == 1
    assert len(next(s for s in out if "Comeback" in s["title"])["article_ids"]) == 5


def test_one_name_from_another_headline_is_not_enough():
    d = filler({"s1": ["Bitcoin price faces a big test", "Bitcoin falls again", "Bitcoin slides"],
                "s2": ["Solana faces a death cross", "Bitcoin weakness drags Solana lower"]})
    stories, arts = multi(d, body_names=["Bitcoin", "Solana"])
    _, info = merge_and_rate(stories, arts, ask([["s1", "s2"]]), "2026-11-18")
    assert info["merges"] == 0


def test_seed_offers_only_its_title_names():
    # the old over-merge: a name in the seed's OTHER headlines must not pull in a different event
    d = filler({"s1": ["Nationwide ground stop halts all flights", "Duffy blames old systems", "Duffy wants funds"],
                "s2": ["Duffy faces senate questions about bank outage"]})
    stories, arts = multi(d, body_names=["Duffy"])
    _, info = merge_and_rate(stories, arts, ask([["s1", "s2"]]), "2026-11-18")
    assert info["merges"] == 0


def test_name_in_a_minority_of_headlines_does_not_count():
    d = filler({"s1": ["Huang and Kress lead the chipmaker", "x"],
                "s2": ["Chip stocks slide", "Chip stocks fall further", "Huang and Kress comment on chips"]})
    stories, arts = multi(d, body_names=["Huang", "Kress"])
    # s2 is the bigger story, so it is the seed; make s1 bigger to test s2 joining
    stories[0]["article_ids"] += ["a99", "a98"]
    arts["a99"] = dict(arts["a0"], id="a99")
    arts["a98"] = dict(arts["a0"], id="a98")
    _, info = merge_and_rate(stories, arts, ask([["s1", "s2"]]), "2026-11-18")
    assert info["merges"] == 0


def test_ceo_is_not_a_name():
    d = filler({"s1": ["Home Depot Names New CEO"], "s2": ["Chipmaker CEO Search Continues"]})
    stories, arts = multi(d, body_names=["CEO"])
    _, info = merge_and_rate(stories, arts, ask([["s1", "s2"]]), "2026-11-18")
    assert info["merges"] == 0


def test_roundup_abend_report_is_dropped():
    assert ROUNDUP.search("Abend-Report: Nvidia schliesst Huangs Rueckkehr aus")


# ---------------------------------------------------------------- freshness
def test_freshness_halves_every_day():
    from datetime import datetime, timedelta
    from src.cluster import FRESH, freshness
    end = datetime.fromisoformat("2026-11-18T23:59:59+00:00")
    assert freshness(end, end) == FRESH
    assert abs(freshness(end - timedelta(hours=24), end) - FRESH / 2) < 1e-9
    assert freshness(end - timedelta(days=5), end) < 0.2


def test_fresh_story_beats_old_one_but_big_multiday_story_still_leads():
    d = {"old": ["US wholesale inflation rises less than expected", "PPI cooler"],
         "fresh": ["Canada CPI holds at 3.1 percent"],
         "big": ["Chipmaker leadership crisis deepens"] + [f"Leadership crisis day {i}" for i in range(5)]}
    stories, arts = multi(d)
    for aid in stories[0]["article_ids"]:
        arts[aid]["date"] = "2026-11-13T14:39:00+00:00"
    arts[stories[1]["article_ids"][0]]["date"] = "2026-11-18T11:20:00+00:00"
    for n, aid in enumerate(stories[2]["article_ids"]):
        arts[aid]["date"] = f"2026-11-1{3 + n % 5}T08:00:00+00:00"  # 13 to 17 Nov, newest 40 h before the end
    out, _ = merge_and_rate(stories, arts, ask([], {"old": 4, "fresh": 4, "big": 4}), "2026-11-18")
    assert [s["title"][:10] for s in out] == ["Chipmaker ", "Canada CPI", "US wholesa"]


# ---------------------------------------------------------------- prepare.pick: which stories get facts
def _st(rank, title, topic="other", publishers=("P",)):
    return {"id": f"s{rank}", "rank": rank, "title": title, "topic": topic, "publishers": list(publishers)}


def test_pick_always_takes_macro_fx_and_multi_outlet_stories():
    import prepare
    stories = [_st(r, f"Celebrity gossip {r}") for r in range(1, 201)]
    stories[150] = _st(151, "Dollar Surges to 2026 High", "energy and commodities")
    stories[160] = _st(161, "ECB's Schnabel warns on growth model", "politics and world")
    stories[170] = _st(171, "Some company news", "companies and tech", publishers=("A", "B"))
    stories[180] = _st(181, "Quiet item", "currencies")
    chosen = {s["id"] for s in prepare.pick(stories)}
    assert {"s151", "s161", "s171", "s181"} <= chosen
    assert "s190" not in chosen
    assert len(chosen) <= prepare.MAX_WITH_FACTS


def test_pick_is_capped():
    import prepare
    stories = [_st(r, f"Fed item {r}") for r in range(1, 400)]
    picked = prepare.pick(stories)
    assert len(picked) == prepare.MAX_WITH_FACTS and picked[0]["rank"] == 1


# ---------------------------------------------------------------- guards from the answer key (eval/REPORT.md)
def test_news_about_a_rating_is_not_advice():
    assert not ADVICE.search("Anthropic receives its first 'Buy' rating")
    assert ADVICE.search("Wall Street Analyst Upgrades to 'Strong Buy'")  # the pitch is still caught


@pytest.mark.parametrize("headline", [
    "Wall-Street-Futures uneinheitlich vor PPI: 5 Dinge vor Handelsbeginn",
    "Wall Street-futures gemengd voor PPI-data: 5 dingen om te weten voor beursopening",
])
def test_translated_roundups_match(headline):
    assert ROUNDUP.search(headline)


def test_translation_of_a_dropped_roundup_is_dropped_too():
    def art(i, feed, headline, minute):
        return {"id": f"x{i}", "headline": headline, "excerpt": "", "text": headline + " body text", "feed": feed,
                "publisher": "Invezz", "date": f"2026-11-18T12:{minute:02d}:00+00:00", "sections": ["Markets"],
                "language": feed[-2:], "author": "Jane Doe"}
    arts = [art(1, "invezz_en", "Evening digest: oil falls, gold slips", 0),
            art(2, "invezz_de", "Abend-Übersicht: Öl fällt, Gold rutscht", 5),  # no round-up word of its own
            art(3, "invezz_en", "Fed holds interest rates steady", 30)]
    ids = {i for s in cluster(arts, arts) for i in s["article_ids"]}
    assert ids == {"x3"}


def test_shared_place_or_data_series_alone_does_not_merge():
    # s18 of 18 Nov: Trump gossip "in China" was glued to China's industrial output; s5: three CPI releases
    for a, b in (("Trump Tapping His Leg in China", "China Industrial Output Slows"),
                 ("Canada Inflation Holds Steady", "Eurozone Inflation Confirmed Higher")):
        stories, arts = build(titles_with({"s1": a, "s2": b}))
        _, info = merge_and_rate(stories, arts, ask([["s1", "s2"]]), "2026-11-18")
        assert info["merges"] == 0, (a, b)


def test_place_next_to_a_rare_name_still_merges():
    stories, arts = build(titles_with({"s1": "Huawei Sanctions Widen in China", "s2": "China Hits Back Over Huawei"}))
    _, info = merge_and_rate(stories, arts, ask([["s1", "s2"]]), "2026-11-18")
    assert info["merges"] == 1


def test_rank_score_puts_data_release_above_speculation():
    from src.cluster import rank_score
    data = {"importance": 4, "publishers": ["A", "B"], "topic": "central banks and macro",
            "title": "US wholesale inflation rises less than expected in October"}
    guess = {"importance": 4, "publishers": ["A", "B", "C"], "topic": "energy and commodities",
             "title": "Brent crude price analysis: will oil crash below $90?"}
    assert rank_score(data, 3, 1.0) > rank_score(guess, 6, 3.0)
