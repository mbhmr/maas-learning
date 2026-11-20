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
    return {"metric": "ppi", "claim": "PPI rose", "value": value, "unit": "%", "period": "Oct",
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
