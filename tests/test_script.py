"""Trust rules of src/script.py. ask_json is always mocked."""
import pytest

from src import script
from src.script import (CLOSING, OPENING, WORDS_PER_SECOND, check_script, fit_length, judge,
                        select_stories)


def mkfact(fid="s1-f1", story="s1", quote="Producer prices rose 0.3% in October.", date="2026-11-18T08:00:00+00:00"):
    return {"id": fid, "story_id": story, "importance": 3, "conflict": False,
            "sources": [{"quote": quote, "publisher": "Reuters", "date": date, "value_in_source": "0.3%"}]}


FACTS = [mkfact()]


def line(text, ids=("s1-f1",)):
    return {"text": text, "fact_ids": list(ids)}


def run(text, ids=("s1-f1",), facts=FACTS, lang="en"):
    return check_script([line(text, ids)], facts, lang)


# ---------------------------------------------------------------- check_script
def test_good_line_kept():
    kept, dropped = run("Producer prices rose 0.3 percent in October!")
    assert len(kept) == 1 and dropped == []


def test_no_source_dropped():
    kept, dropped = run("Prices rose.", ids=())
    assert kept == [] and dropped[0]["why"] == "no source"


def test_unknown_fact_id_is_no_source():
    kept, dropped = run("Prices rose.", ids=("s9-f9",))
    assert kept == [] and dropped[0]["why"] == "no source"


def test_unverified_number_dropped():
    kept, dropped = run("Producer prices rose 0.5 percent.")
    assert kept == [] and "numbers not in sources" in dropped[0]["why"]


def test_number_word_dropped():
    kept, dropped = run("Prices doubled in October.")
    assert kept == [] and "numbers not in sources" in dropped[0]["why"]


def test_day_number_only_next_to_month():
    # article date is 18 November 2026: "18" is fine with a month name, not as "18 percent"
    ok, _ = run("It was reported on 18 November.")
    assert len(ok) == 1
    kept, dropped = run("Prices rose 18 percent.")
    assert kept == [] and dropped


def test_year_only_with_month():
    kept, _ = run("Data from November 2026.")
    assert len(kept) == 1
    kept, _ = run("Prices rose 2026 percent.")
    assert kept == []


@pytest.mark.parametrize("text", ["The market saw 18 percent.", "A decline of 18 percent."])
def test_word_starting_like_a_month_does_not_unlock_day(text):
    kept, _ = run(text)
    assert kept == []


@pytest.mark.parametrize("text", [
    "Prices hit the highest level!",
    "Prices soared!",
    "A record rise!",
    "Shares plunged.",
    "The biggest move!",
    "Prices rose for the first time!",
])
def test_unsupported_superlative_dropped(text):
    kept, dropped = run(text)
    assert kept == [] and "superlative" in dropped[0]["why"]


def test_superlative_with_support_kept():
    f = [mkfact(quote="Prices hit a record high of 0.3% in October.")]
    kept, _ = run("Prices hit a record!", facts=f)
    assert len(kept) == 1


def test_recorded_is_not_record():
    kept, dropped = run("Reuters recorded the move.")
    assert len(kept) == 1 and dropped == []


@pytest.mark.parametrize("raw,expect", [
    ("Next up! Prices rose.", "Prices rose."),
    ("Moving on: prices rose.", "Prices rose."),
    ("Weiter geht's! Preise stiegen.", "Preise stiegen."),
])
def test_stock_phrases_stripped(raw, expect):
    kept, _ = run(raw)
    assert kept[0]["text"] == expect


def test_line_with_only_stock_phrase_vanishes():
    kept, dropped = run("Next up!")
    assert kept == [] and dropped == []


def test_fact_ids_removed_from_text():
    kept, _ = run("Prices rose [s1-f1] in October (s1-f1).")
    assert "s1-f1" not in kept[0]["text"]
    assert kept[0]["fact_ids"] == ["s1-f1"]


def test_german_decimal_comma():
    kept, _ = run("Die Preise stiegen um 0,3 Prozent.", lang="de")
    assert len(kept) == 1


# ---------------------------------------------------------------- fit_length
def _budget(seconds):
    return seconds * WORDS_PER_SECOND["en"] * 1.1 - len(OPENING["en"].split()) - len(CLOSING["en"].split())


def test_fit_length_cuts_only_the_end():
    profile = {"seconds": 60, "language": "en"}
    lines = [line(" ".join(["w"] * 10)) for _ in range(int(_budget(60)) // 10 + 3)]
    kept, cut = fit_length(lines, profile)
    assert kept == lines[:len(kept)]
    assert len(cut) >= 3 and all(c["why"] == "over the requested length" for c in cut)
    assert [k["text"] for k in kept] + [c["text"] for c in cut] == [x["text"] for x in lines]


def test_fit_length_never_skips_a_middle_line():
    profile = {"seconds": 60, "language": "en"}
    long_line = line(" ".join(["w"] * (int(_budget(60)) + 5)))
    kept, cut = fit_length([line("Short."), long_line, line("Tiny.")], profile)
    assert [k["text"] for k in kept] == ["Short."]
    assert len(cut) == 2  # the later short line is cut too


def test_fit_length_all_fit():
    kept, cut = fit_length([line("Short one.")], {"seconds": 300, "language": "en"})
    assert len(kept) == 1 and cut == []


# ---------------------------------------------------------------- judge
def test_judge_drops_unsupported(monkeypatch):
    seen = {}

    def fake(step, system, user, schema, **kw):
        seen["user"] = user
        return {"verdicts": [{"n": 0, "supported": True, "why": ""},
                             {"n": 1, "supported": False, "why": "wrong direction"},
                             {"n": 7, "supported": False, "why": "out of range"}]}
    monkeypatch.setattr(script, "ask_json", fake)
    lines = [line("Good."), line("Bad."), line("Also fine.")]
    kept, dropped = judge(lines, FACTS)
    assert [k["text"] for k in kept] == ["Good.", "Also fine."]
    assert len(dropped) == 1 and dropped[0]["why"] == "content check: wrong direction"
    assert "Producer prices rose 0.3%" in seen["user"]  # the quote is shown to the judge


def test_judge_empty_makes_no_call(monkeypatch):
    monkeypatch.setattr(script, "ask_json", lambda *a, **k: pytest.fail("no call expected"))
    assert judge([], FACTS) == ([], [])


# ---------------------------------------------------------------- select_stories
STORIES = [{"id": f"s{i}", "title": f"T{i}", "publishers": ["A"]} for i in range(1, 8)]
SFACTS = [{"story_id": f"s{i}"} for i in range(1, 7)]  # s7 has no facts
PROFILE = {"seconds": 75, "language": "en", "description": "Likes markets."}  # k = 3


def pick(monkeypatch, out, profile=PROFILE):
    monkeypatch.setattr(script, "ask_json", lambda *a, **k: out)
    return select_stories(profile, STORIES, SFACTS)


def test_select_ignores_unknown_ids_and_story_without_facts(monkeypatch):
    chosen, _ = pick(monkeypatch, {"story_ids": ["s99", "s7", "s2"], "interests_without_story": []})
    assert [s["id"] for s in chosen] == ["s2"]


def test_select_at_most_k_and_dedupes(monkeypatch):
    chosen, _ = pick(monkeypatch, {"story_ids": ["s1", "s1", "s2", "s3", "s4", "s5"], "interests_without_story": []})
    assert [s["id"] for s in chosen] == ["s1", "s2", "s3"]


def test_select_minimum_k_is_two(monkeypatch):
    chosen, _ = pick(monkeypatch, {"story_ids": ["s1", "s2", "s3"], "interests_without_story": []},
                     {**PROFILE, "seconds": 20})
    assert len(chosen) == 2


def test_select_fallback_when_empty(monkeypatch):
    chosen, _ = pick(monkeypatch, {"story_ids": ["zzz"], "interests_without_story": []})
    assert [s["id"] for s in chosen] == ["s1", "s2", "s3"]


def test_missing_filters_long_and_digit_text(monkeypatch):
    _, missing = pick(monkeypatch, {"story_ids": ["s1"], "interests_without_story": [
        "Tesla", "", "  ", "one two three four five", "Top 10 stocks", "Solarenergie", "Gold"]})
    assert missing == ["Tesla", "Solarenergie"]  # at most two, no empty, no long, no digits
