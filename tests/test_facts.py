"""Trust rules of src/facts.py. No network, only short invented snippets."""
import pytest

from src.facts import _conflict, norm, numbers, verify_facts


# ---------------------------------------------------------------- numbers()
@pytest.mark.parametrize("text,expected", [
    ("rose 6.5%", {6.5}),
    ("rose 0.3 percent", {0.3}),
    ("1,000 jobs", {1000.0}),
    ("$7.5B deal", {7.5, 1e9}),
    ("¥15.4T", {15.4, 1e12}),
    ("€3bn", {3.0, 1e9}),
    ("430M units", {430.0, 1e6}),
    ("23 million", {23.0, 1e6}),
    ("doubled", {2.0}),
    ("a quarter of sales", {0.25}),
])
def test_numbers_en(text, expected):
    assert numbers(text) == expected


def test_two_thirds_is_a_fraction():
    assert 2 / 3 in numbers("two thirds of voters")


def test_numbers_decimal_comma_de_nl():
    assert numbers("um 6,5 %", "de") == {6.5}
    assert numbers("met 6,5 procent", "nl") == {6.5}
    assert numbers("1.000 Stellen", "de") == {1000.0}


def test_numbers_english_comma_is_thousands():
    assert 6.5 not in numbers("6,500", "en")
    assert numbers("6,500", "en") == {6500.0}


def test_numbers_names_are_not_figures():
    assert numbers("The S&P 500 fell in Q3") == set()
    assert numbers("Nasdaq 100 and Nikkei 225 and G7") == set()
    assert numbers("the third quarter") == set()


def test_scale_words_differ():
    assert numbers("23 million") != numbers("23 billion")


def test_one_and_ein_are_not_numbers():
    assert numbers("one of the biggest") == set()
    assert numbers("ein Anstieg", "de") == set()


def test_number_words():
    assert {3.0, 4.0} <= numbers("three or four")
    assert 11.0 in numbers("elf Prozent", "de")


# ---------------------------------------------------------------- verify_facts()
ART = {
    "a1": {"id": "a1", "publisher": "Reuters", "url": "https://x/a1", "date": "2026-11-18T08:00:00+00:00",
           "text": "US producer prices rose 0.3% in October, the Labor Department said. Analysts had expected 0.2%."},
    "a2": {"id": "a2", "publisher": "Bloomberg", "url": "https://x/a2", "date": "2026-11-18T09:00:00+00:00",
           "text": "Producer prices climbed 0.4% last month."},
    "z9": {"id": "z9", "publisher": "Other", "url": "https://x/z9", "date": "2026-11-18T09:00:00+00:00",
           "text": "Producer prices rose 0.3% in October."},
}
STORY = {"id": "s1", "title": "PPI", "article_ids": ["a1", "a2"]}


def fact(sources, value="0.3"):
    return {"metric": "ppi", "claim": "US PPI rose", "value": value, "unit": "%", "period": "Oct",
            "importance": 3, "sources": sources}


def src(aid, quote, val):
    return {"article_id": aid, "quote": quote, "value_in_source": val}


def test_verified_fact_survives_with_metadata():
    f = fact([src("a1", "US producer prices rose 0.3% in October", "0.3%")])
    ok, rej = verify_facts(STORY, [f], ART)
    assert rej == [] and len(ok) == 1
    assert ok[0]["id"] == "s1-f1" and ok[0]["sources"][0]["publisher"] == "Reuters"
    assert ok[0]["conflict"] is False


def test_quote_matching_ignores_case_and_curly_quotes():
    f = fact([src("a1", "US PRODUCER PRICES ROSE 0.3% IN OCTOBER,", "0.3%")])
    ok, _ = verify_facts(STORY, [f], ART)
    assert len(ok) == 1


def test_quote_not_verbatim_rejected():
    f = fact([src("a1", "US producer prices rose 0.3% in September", "0.3%")])
    ok, rej = verify_facts(STORY, [f], ART)
    assert ok == [] and "quote not found" in rej[0]["why"]


def test_value_must_be_in_quote():
    f = fact([src("a1", "US producer prices rose 0.3% in October", "0.5%")])
    ok, rej = verify_facts(STORY, [f], ART)
    assert ok == [] and "not in quote" in rej[0]["why"]


def test_foreign_article_rejected():
    # z9 exists in the article set but is not part of this story
    f = fact([src("z9", "Producer prices rose 0.3% in October", "0.3%")])
    ok, rej = verify_facts(STORY, [f], ART)
    assert ok == [] and "unknown article" in rej[0]["why"]


def test_nonexistent_article_rejected():
    f = fact([src("nope", "anything", "1")])
    ok, rej = verify_facts(STORY, [f], ART)
    assert ok == [] and "unknown article" in rej[0]["why"]


def test_bad_source_dropped_good_one_kept():
    f = fact([src("a1", "US producer prices rose 0.3% in October", "0.3%"),
              src("a2", "invented sentence 0.3%", "0.3%")])
    ok, rej = verify_facts(STORY, [f], ART)
    assert len(ok) == 1 and len(ok[0]["sources"]) == 1 and len(rej) == 1


def test_two_outlets_different_values_is_conflict():
    f = fact([src("a1", "US producer prices rose 0.3% in October", "0.3%"),
              src("a2", "Producer prices climbed 0.4% last month", "0.4%")])
    ok, _ = verify_facts(STORY, [f], ART)
    assert ok[0]["conflict"] is True


def test_one_source_per_article():
    f = fact([src("a1", "Analysts had expected 0.2%", "0.2%"),
              src("a1", "US producer prices rose 0.3% in October", "0.3%")], value="0.3")
    ok, _ = verify_facts(STORY, [f], ART)
    assert len(ok[0]["sources"]) == 1 and ok[0]["sources"][0]["value_in_source"] == "0.3%"


# ---------------------------------------------------------------- _conflict()
def test_conflict_rules():
    s = lambda v: {"value_in_source": v}
    assert _conflict([s("6.9%"), s("6.8%")]) is True
    assert _conflict([s("6.3% to 6.5%"), s("6.5%")]) is False
    assert _conflict([s("6.5%")]) is False
    assert _conflict([]) is False
    assert _conflict([s("0.3%"), s("0.3 percent")]) is False


def test_norm():
    assert norm("It’s  “Big” – news!") == "it's big - news"


# ---------------------------------------------------------------- decimal comma and scale words (de, nl)
@pytest.mark.parametrize("text,lang,expected", [
    ("5,28 Mio. Barrel", "de", {5.28, 1e6}),
    ("5,28 miljoen vaten", "nl", {5.28, 1e6}),
    ("3 Mrd. Euro", "de", {3.0, 1e9}),
    ("4,5 mld euro", "nl", {4.5, 1e9}),
    ("12 mln aandelen", "nl", {12.0, 1e6}),
    ("2 Billionen Dollar", "de", {2.0, 1e12}),  # German Billion = English trillion
    ("2 biljoen dollar", "nl", {2.0, 1e12}),
    ("1.234.567 Stellen", "de", {1234567.0}),
    ("1,234,567 jobs", "en", {1234567.0}),
    ("€3bn", "de", {3.0, 1e9}),                 # "bn" is 10^9 in any language
])
def test_numbers_scale_and_separators(text, lang, expected):
    assert numbers(text, lang) == expected


def test_english_billion_stays_ten_to_the_nine():
    assert numbers("2 billion") == {2.0, 1e9}
    assert numbers("2 billion") != numbers("2 Billionen", "de")


def test_same_report_in_three_languages_is_no_conflict():
    # the false conflict of fact s25-f1: Invezz EN, DE and NL give the same API figure
    src_ = lambda v, lang: {"value_in_source": v, "language": lang}
    assert _conflict([src_("5.28 million barrels", "en"), src_("5,28 Mio. Barrel", "de"),
                      src_("5,28 miljoen vaten", "nl")]) is False
    assert _conflict([src_("5.28 million barrels", "en"), src_("5,82 Mio. Barrel", "de")]) is True


ART_DE = {
    "e1": {"id": "e1", "publisher": "Invezz", "url": "https://x/e1", "date": "2026-11-18T08:00:00+00:00",
           "language": "en", "text": "Crude inventories rose by 5.28 million barrels, API data showed."},
    "d1": {"id": "d1", "publisher": "Invezz - German", "url": "https://x/d1", "date": "2026-11-18T08:05:00+00:00",
           "language": "de", "text": "Die Rohölbestände stiegen um 5,28 Mio. Barrel, wie API-Daten zeigten."},
}


def test_verify_reads_each_source_in_its_language():
    story = {"id": "s25", "title": "API", "article_ids": ["e1", "d1"]}
    f = fact([src("e1", "Crude inventories rose by 5.28 million barrels", "5.28 million barrels"),
              src("d1", "Die Rohölbestände stiegen um 5,28 Mio. Barrel", "5,28 Mio. Barrel")], value="5.28")
    ok, rej = verify_facts(story, [f], ART_DE)
    assert rej == [] and len(ok[0]["sources"]) == 2
    assert ok[0]["conflict"] is False
    assert {s["language"] for s in ok[0]["sources"]} == {"en", "de"}


def test_prompt_keeps_attribution():
    from src.facts import SYSTEM
    assert "Keep attribution" in SYSTEM and "never the institution's decision" in SYSTEM


def test_shared_scale_word_is_no_agreement():
    s = lambda v: {"value_in_source": v}
    assert _conflict([s("5.28 million barrels"), s("5.82 million barrels")]) is True
    assert _conflict([s("23 million"), s("23 billion")]) is True
    assert _conflict([s("$1.2 billion"), s("$1.2bn")]) is False
    assert _conflict([s("1,000,000"), s("1 million")]) is False


def test_rounded_value_is_no_conflict_but_real_difference_is():
    s = lambda v, lang="en": {"value_in_source": v, "language": lang}
    assert _conflict([s("$25.95 billion"), s("$25.9 billion")]) is False      # Disney, shortened
    assert _conflict([s("96.7%"), s("96.4%")]) is True                         # FedWatch, two snapshots
    assert _conflict([s("27.945", "nl"), s("27,945", "de")]) is False         # translation kept the separator


# ---------------------------------------------------------------- attribution
from src.facts import unattributed


def test_view_without_speaker_is_caught():
    q = "Hammack also argued that financial conditions are not yet sufficiently restrictive to slow economic growth."
    assert unattributed("Financial conditions are not yet sufficiently restrictive.", q) == "Hammack"
    assert unattributed("Cleveland Fed President Hammack argued conditions are not restrictive enough.", q) is None


def test_data_said_by_an_agency_and_pronouns_pass():
    assert unattributed("US producer prices rose 0.3%.", "Prices rose 0.3%, the Labor Department said.") is None
    assert unattributed("Inflation is too high.", "He warned that inflation is too high.") is None
    assert unattributed("Waller supports a hike.", "Waller, speaking in Frankfurt, supports a 25bps hike.") is None
    assert unattributed("The Fed will hike.", "Waller, speaking in Frankfurt, supports a 25bps hike.") == "Waller"


def test_verify_rejects_unattributed_view():
    art = {"h1": {"id": "h1", "publisher": "ActionForex", "url": "https://x/h1", "date": "2026-11-18T08:00:00+00:00",
                  "text": "Waller argued that a 25bps increase in December is likely."}}
    story = {"id": "s17", "title": "Fed", "article_ids": ["h1"]}
    bad = fact([src("h1", "Waller argued that a 25bps increase in December is likely", "25bps")], value="25")
    ok, rej = verify_facts(story, [bad], art)
    assert ok == [] and "Waller" in rej[0]["why"]
    good = dict(bad, claim="Fed Governor Waller argued that a 25 basis point December hike is likely.")
    ok, _ = verify_facts(story, [good], art)
    assert len(ok) == 1


# ---------------------------------------------------------------- expectations and macro figures (eval/REPORT.md)
from src.facts import missing_place


def test_expectation_without_who_expects_is_caught():
    q = "Markets continued to price a December hike of 25bps with approximately 98% probability."
    assert unattributed("The Federal Reserve is expected to raise rates by 25 basis points.", q) == "Markets"
    assert unattributed("Markets price a 25 basis point Fed hike with about 98% probability.", q) is None
    q_de = "Ökonomen erwarten, dass die Gesamtpreise um 0.4% steigen."
    assert unattributed("US PPI is expected to rise 0.4%.", q_de) == "Ökonomen"


def test_expectation_as_the_quote_says_it_passes():
    # the article itself says "is expected to", without naming who: the claim is as good as its source
    q = "October headline CPI is expected to reach 3.6%, with core inflation projected at 2.8%."
    assert unattributed("UK headline CPI is expected to reach 3.6% in October 2026.", q) is None


@pytest.mark.parametrize("claim, missing", [
    ("Core CPI increased 0.3% month on month in October 2026, exceeding forecasts of 0.2%.", True),
    ("Retail sales excluding autos rose 0.6% month on month in October 2026.", True),
    ("Inflation is running above 3%.", True),
    ("US core CPI increased 0.3% month on month in October 2026.", False),
    ("Canada's headline CPI inflation rate is expected to rise to 3.2%.", False),
    ("The Bank of Japan's policy rate was held at 1.25%.", False),
    ("Waller argued that rate cuts may not be enough to bring inflation back toward 2%.", False),  # a person
    ("Nvidia shares fell 4.3% in November 2026.", False),  # no macro figure at all
])
def test_missing_place(claim, missing):
    assert missing_place(claim) is missing


def test_verify_rejects_macro_figure_without_country():
    art = {"h1": {"id": "h1", "publisher": "ActionForex", "url": "https://x/h1", "date": "2026-11-18T08:00:00+00:00",
                  "text": "Core CPI increased 0.3%, also exceeding forecasts of 0.2%."}}
    story = {"id": "s29", "title": "Fed", "article_ids": ["h1"]}
    bad = dict(fact([src("h1", "Core CPI increased 0.3%", "0.3%")]), claim="Core CPI increased 0.3% in October 2026.")
    ok, rej = verify_facts(story, [bad], art)
    assert ok == [] and rej[0]["why"] == "macro figure without country or region"


def test_news_without_a_number_is_a_fact_too():
    # 18 Nov: the top story (Huang willing to return) had no number, so it had no fact and could not be spoken
    arts = {"h1": {"id": "h1", "publisher": "Invezz", "url": "https://x/h1", "date": "2026-11-17T17:11:00+00:00",
                   "text": "Jensen Huang has signaled that he would be willing to return as Nvidia CEO."}}
    f = {"metric": "huang_return", "claim": "Jensen Huang signaled he would be willing to return as Nvidia CEO.",
         "value": "", "unit": "", "period": "17 November 2026", "importance": 5,
         "sources": [src("h1", "Jensen Huang has signaled that he would be willing to return as Nvidia CEO.", "")]}
    ok, rej = verify_facts({"id": "s1", "title": "Huang", "article_ids": ["h1"]}, [f], arts)
    assert rej == [] and len(ok) == 1
    f["sources"][0]["quote"] = "Jensen Huang will return as Nvidia CEO."  # not in the article
    ok, _ = verify_facts({"id": "s1", "title": "Huang", "article_ids": ["h1"]}, [f], arts)
    assert ok == []
