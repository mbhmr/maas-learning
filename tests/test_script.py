"""Trust rules of src/script.py. ask_json is always mocked."""
import pytest

from src import script
from src.script import (CLOSING, OPENING, WORDS_PER_SECOND, check_script, fit_length, judge,
                        select_stories)


def mkfact(fid="s1-f1", story="s1", quote="Producer prices rose 0.3% in October.", date="2026-11-18T08:00:00+00:00"):
    return {"id": fid, "story_id": story, "importance": 3, "conflict": False, "claim": quote, "period": "October",
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
    assert [k["text"] for k in kept] == ["Good."]  # "Also fine." got no verdict: fail closed, not spoken
    assert [d["why"] for d in dropped] == ["content check: wrong direction", "content check: no verdict for this line"]
    assert "Producer prices rose 0.3%" in seen["user"]  # the quote is shown to the judge


def test_judge_empty_makes_no_call(monkeypatch):
    monkeypatch.setattr(script, "ask_json", lambda *a, **k: pytest.fail("no call expected"))
    assert judge([], FACTS) == ([], [])


# ---------------------------------------------------------------- select_stories
STORIES = [{"id": f"s{i}", "title": f"T{i}", "publishers": ["A"]} for i in range(1, 8)]
SFACTS = [{"story_id": f"s{i}"} for i in range(1, 7)]  # s7 has no facts
PROFILE = {"seconds": 60, "language": "en", "description": "Likes markets."}  # k = 3


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


# ---------------------------------------------------------------- numbers in the listener's language
@pytest.mark.parametrize("lang,raw,expect", [
    ("de", "Die Preise stiegen um 0.3 percent.", "Die Preise stiegen um 0,3 Prozent."),
    ("de", "Ein Trust über $10.5 billion.", "Ein Trust über 10,5 Milliarden Dollar."),
    ("de", "Japan gab ¥15.4 trillion aus.", "Japan gab 15,4 Billionen Yen aus."),
    ("de", "Fast 59 millionen Aktien.", "Fast 59 Millionen Aktien."),
    ("de", "Gold bei $3,852.67.", "Gold bei 3.852,67 Dollar."),
    ("de", "Am 18. November, 1.000 Leute.", "Am 18. November, 1.000 Leute."),  # already German
    ("de", "Ein Plus von 1 billion.", "Ein Plus von 1 Milliarde."),
    ("nl", "Een stijging van 0.3 percent en $7.5B.", "Een stijging van 0,3 procent en 7,5 miljard dollar."),
    ("en", "Prices rose 0.3 percent, $10.5 billion.", "Prices rose 0.3 percent, $10.5 billion."),
])
def test_localise(lang, raw, expect):
    assert script.localise(raw, lang) == expect


def test_localised_line_passes_number_check():
    f = [mkfact(quote="They moved shares worth over $10.5 billion and rose 0.3%.")]
    kept, dropped = run("Sie bewegten Aktien im Wert von $10.5 billion.", facts=f, lang="de")
    assert kept and kept[0]["text"] == "Sie bewegten Aktien im Wert von 10,5 Milliarden Dollar."


def test_german_billionen_is_trillion_and_wrong_scale_is_dropped():
    # "10,5 Billionen" is 10.5 trillion in German: the source says billion, so the line must go
    f = [mkfact(quote="Shares worth over $10.5 billion.")]
    kept, dropped = run("Aktien im Wert von 10,5 Billionen Dollar.", facts=f, lang="de")
    assert kept == [] and "numbers not in sources" in dropped[0]["why"]


def test_english_word_in_german_line_dropped():
    kept, dropped = run("Die US-Producer-Prices rose im Oktober um 0,3 Prozent.", lang="de")
    assert kept == [] and "English" in dropped[0]["why"]


def test_line_starting_with_bare_number_dropped():
    kept, dropped = run("0.3 percent, that is the rise in producer prices in October.")
    assert kept == [] and "bare number" in dropped[0]["why"]


# ---------------------------------------------------------------- line kinds
def test_kind_is_kept_and_defaults_to_claim():
    kept, _ = check_script([{"text": "That keeps prices in focus for you.", "fact_ids": ["s1-f1"], "kind": "context"},
                            line("Producer prices rose 0.3 percent.")], FACTS, "en")
    assert [k["kind"] for k in kept] == ["context", "claim"]


def test_context_with_new_number_dropped():
    kept, dropped = check_script([{"text": "For you, a 2 percent target matters.", "fact_ids": ["s1-f1"],
                                   "kind": "context"}], FACTS, "en")
    assert kept == [] and "numbers not in sources" in dropped[0]["why"]


def test_context_with_advice_dropped():
    kept, dropped = check_script([{"text": "Time to buy the dollar.", "fact_ids": ["s1-f1"], "kind": "context"}],
                                 FACTS, "en")
    assert kept == [] and "advice" in dropped[0]["why"]


def test_one_context_per_story():
    ctx = {"text": "That keeps inflation in focus for you.", "fact_ids": ["s1-f1"], "kind": "context"}
    kept, dropped = check_script([ctx, {**ctx, "text": "And rates too."}], FACTS, "en")
    assert len(kept) == 1 and "second context" in dropped[0]["why"]


# ---------------------------------------------------------------- greeting and sign-off
@pytest.mark.parametrize("text,why", [
    ("Morning, trader, central banks are running the show!", None),
    ("Morning! Prices rose 3 percent.", "number"),
    ("Morning! Two big stories.", "number"),
    ("Morning trader, time to buy the dip!", "advice"),
    ("Morning! A record day for you.", "superlative"),
    (" ".join(["word"] * 21), "longer"),
    ("", "empty"),
])
def test_check_host(text, why):
    out, reason = script.check_host(text, "en", 20)
    if why is None:
        assert out == text and reason is None
    else:
        assert out is None and why in reason


def test_host_words_short_and_long():
    assert script.host_words({"seconds": 30}) == 6 and script.host_words({"seconds": 120}) == 20


def test_frame_is_short_for_short_briefings():
    short = script.frame_texts({"seconds": 30, "language": "en"})
    assert short["sign_off"] == "" and len(short["opening"].split()) <= 5
    assert sum(len(t.split()) for t in short.values()) <= 12  # the old fixed frame had 37 words


# ---------------------------------------------------------------- judge and write_script
def test_judge_sees_kind(monkeypatch):
    seen = {}

    def fake(step, system, user, schema, **kw):
        seen["user"], seen["system"] = user, system
        return {"verdicts": [{"n": 0, "supported": True, "why": ""}]}
    monkeypatch.setattr(script, "ask_json", fake)
    judge([{"text": "Why it matters.", "fact_ids": ["s1-f1"], "kind": "context"}], FACTS)
    assert "KIND: context" in seen["user"]
    assert "sticky" in seen["system"] and "whose view" in seen["system"]


WS_FACTS = [mkfact("s1-f1", "s1", date="2026-11-18T08:00:00+00:00"),
            mkfact("s2-f1", "s2", quote="Waller wants 50 basis points.", date="2026-11-14T08:00:00+00:00")]
WS_STORIES = [{"id": "s1", "title": "PPI", "publishers": ["A"]}, {"id": "s2", "title": "Waller", "publishers": ["A"]}]


def fake_steps(script_out, verdict=lambda n, text: True):
    calls = {}

    def fake(step, system, user, schema, **kw):
        calls[step] = (system, user)
        if step == "select":
            return {"story_ids": ["s1", "s2"], "interests_without_story": []}
        if step == "script":
            return script_out
        texts = [x.split("LINE: ", 1)[1] for x in user.splitlines() if "LINE: " in x]
        return {"verdicts": [{"n": n, "supported": verdict(n, t), "why": "x"} for n, t in enumerate(texts)]}
    return fake, calls


LONG = {**PROFILE, "seconds": 120, "depth": "dense"}


def test_write_script_uses_model_greeting(monkeypatch):
    fake, calls = fake_steps({"greeting": "Morning, trader, central banks run the show!",
                              "sign_off": "Trade sharp, see you soon!",
                              "lines": [{"text": "Producer prices rose 0.3 percent.", "kind": "claim", "fact_ids": ["s1-f1"]},
                                        {"text": "For you, that keeps inflation in focus.", "kind": "context",
                                         "fact_ids": ["s1-f1"]}]})
    monkeypatch.setattr(script, "ask_json", fake)
    lines, dropped, spoken, frame = script.write_script(LONG, WS_STORIES, WS_FACTS)
    assert frame["greeting"] == "Morning, trader, central banks run the show!"
    assert frame["sign_off"] == "Trade sharp, see you soon!"
    assert frame["opening"] == script.OPENING["en"] and frame["closing"] == script.CLOSING["en"]
    assert [x["kind"] for x in lines] == ["claim", "context"]
    assert "published on 18 November 2026" in calls["script"][0]
    assert "STORY: Waller (OLDER: newest source 14 November 2026" in calls["script"][1]  # 4 days old
    assert "STORY: PPI\n" in calls["script"][1]


def test_write_script_falls_back_on_bad_greeting(monkeypatch):
    fake, _ = fake_steps({"greeting": "Morning! Nvidia jumped 5 percent!", "sign_off": "Bye, Nvidia is back!",
                          "lines": [{"text": "Producer prices rose 0.3 percent.", "kind": "claim", "fact_ids": ["s1-f1"]}]},
                         verdict=lambda n, text: "Nvidia" not in text)  # the judge rejects the named company
    monkeypatch.setattr(script, "ask_json", fake)
    lines, dropped, _, frame = script.write_script(LONG, WS_STORIES, WS_FACTS)
    assert frame["greeting"] == script.GREETING["en"] and frame["sign_off"] == script.SIGN_OFF["en"]
    whys = [d["why"] for d in dropped if d.get("kind") == "host"]
    assert any("number" in w for w in whys) and any("content check" in w for w in whys)
    assert len(lines) == 1


def test_write_script_short_has_no_sign_off(monkeypatch):
    fake, _ = fake_steps({"greeting": "Hey!", "sign_off": "Bye now!",
                          "lines": [{"text": "Producer prices rose 0.3 percent.", "kind": "claim", "fact_ids": ["s1-f1"]}]})
    monkeypatch.setattr(script, "ask_json", fake)
    _, _, _, frame = script.write_script({**PROFILE, "seconds": 30, "depth": "short"}, WS_STORIES, WS_FACTS)
    assert frame["sign_off"] == "" and frame["opening"] == script.OPENING_SHORT["en"]


def test_dash_pause_becomes_comma_but_range_stays():
    kept, _ = run("Producer prices rose 0.3 percent — in October.")
    assert kept[0]["text"] == "Producer prices rose 0.3 percent, in October."
    assert script.DASH.sub(", ", "from 3.75 - 4.00") == "from 3.75 - 4.00"
    out, _ = script.check_host("Hello, trader — rates are in play!", "en", 20)
    assert out == "Hello, trader, rates are in play!"


def test_tidy_removes_space_before_punctuation_and_pause_dashes():
    from src.script import tidy
    assert tidy("core rose to 2.6% !") == "core rose to 2.6%!"
    assert tidy("Hello—world") == "Hello, world"
    assert tidy("the 8–9 December meeting") == "the 8–9 December meeting"


def test_arrange_drops_orphan_context_and_moves_context_after_its_claims():
    from src.script import arrange
    facts = [{"id": "a", "story_id": "s1"}, {"id": "b", "story_id": "s2"}]
    lines = [{"text": "Why it matters.", "fact_ids": ["a"], "kind": "context"},
             {"text": "News.", "fact_ids": ["a"], "kind": "claim"},
             {"text": "Orphan.", "fact_ids": ["b"], "kind": "context"}]
    kept, orphans = arrange(lines, facts)
    assert [x["text"] for x in kept] == ["News.", "Why it matters."]
    assert orphans[0]["text"] == "Orphan." and "not spoken" in orphans[0]["why"]


def test_repair_rewrites_a_blocked_line_and_keeps_the_original_visible(monkeypatch):
    long_line = "Producer prices rose 0.3 percent " + "and more words " * 20 + "today."
    fake, calls = fake_steps({"greeting": "Morning, trader, prices first!", "sign_off": "See you soon!",
                              "lines": [{"text": long_line, "kind": "claim", "fact_ids": ["s1-f1"]}]})

    def with_repair(step, system, user, schema, **kw):
        if step == "repair":
            calls["repair"] = user
            return {"lines": [{"text": "Producer prices rose 0.3 percent.", "kind": "claim", "fact_ids": ["s1-f1"]}]}
        return fake(step, system, user, schema, **kw)
    monkeypatch.setattr(script, "ask_json", with_repair)
    lines, dropped, _, _ = script.write_script({**LONG, "name": "trader"}, WS_STORIES, WS_FACTS)
    assert "too long for the ear" in calls["repair"]
    assert [x["text"] for x in lines] == ["Producer prices rose 0.3 percent."]
    assert any("rewrite tried" in d["why"] for d in dropped)


def test_greeting_may_use_part_of_the_name():
    from src.script import calls_by_name
    assert calls_by_name("Hello, trader, central banks first!", "FX trader")
    assert calls_by_name("Morgen, du Anleger!", "Privatanleger")
    assert not calls_by_name("Goedemorgen, retail investor!", "Belegger")


def test_relative_dates_and_repeats_are_dropped():
    lines = [{"text": "Producer prices rose 0.3 percent last week.", "kind": "claim", "fact_ids": ["s1-f1"]},
             {"text": "Producer prices rose 0.3 percent in October.", "kind": "claim", "fact_ids": ["s1-f1"]},
             {"text": "Producer prices rose 0.3 percent in October, again.", "kind": "claim", "fact_ids": ["s1-f1"]}]
    kept, dropped = script.check_script(lines, FACTS, "en")
    whys = [d["why"] for d in dropped]
    assert any("relative date" in w for w in whys) and any("repeats" in w for w in whys)
    assert [k["text"] for k in kept] == ["Producer prices rose 0.3 percent in October."]


# ---------------------------------------------------------------- answer-key gaps (eval/REPORT.md)
def _waller_and_williams():
    waller = {**mkfact("s14-f1", "s14", "Waller called for a 50bps hike in December."),
              "claim": "Fed Governor Christopher Waller called for a 50 basis points hike."}
    williams = mkfact("s29-f1", "s29", "Markets continued to price a December hike of 25bps with approximately 98% probability.")
    return [waller, williams]


def test_person_must_be_named_in_a_quote():
    facts = _waller_and_williams()
    kept, dropped = run("Waller wants more hikes, and markets price a 25 basis point move at 98 percent.",
                        ids=("s29-f1",), facts=facts)
    assert kept == [] and dropped[0]["why"] == "person not in its quotes: Waller"
    kept, _ = run("Fed Governor Waller called for a 50 basis point hike.", ids=("s14-f1",), facts=facts)
    assert len(kept) == 1
    kept, _ = run("Wallers Forderung: 50 Basispunkte.", ids=("s14-f1",), facts=facts, lang="de")
    assert len(kept) == 1  # German genitive still counts as Waller, and the quote names him


def test_person_and_time_reasons_are_repairable():
    assert any("person not in its quotes: Waller".startswith(r) for r in script.REPAIRABLE)
    assert any("time qualifier not in its quotes: nachbörs".startswith(r) for r in script.REPAIRABLE)
    assert any("superlative not in sources: ['record']".startswith(r) for r in script.REPAIRABLE)


@pytest.mark.parametrize("text, lang", [
    ("Nvidia shares rose 1.6 percent in after-hours trading.", "en"),
    ("Nvidia-Aktien stiegen im nachbörslichen Handel um 1,6 Prozent.", "de"),
    ("Nvidia-aandelen stegen nabeurs met 1,6 procent.", "nl"),
    ("Nvidia-Aktien stiegen vorbörslich um 1,6 Prozent.", "de"),
])
def test_time_qualifier_must_be_in_a_quote(text, lang):
    regular = [mkfact("s7-f3", "s7", "Nvidia shares rose 1.6% on Wednesday.")]
    kept, dropped = run(text, ids=("s7-f3",), facts=regular, lang=lang)
    assert kept == [] and "time qualifier not in its quotes" in dropped[0]["why"]


def test_time_qualifier_backed_in_another_language_passes():
    backed = [mkfact("s7-f3", "s7", "Die Aktie stieg im nachbörslichen Handel um 2.47%.")]
    kept, _ = run("Nvidia shares rose 2.47 percent after hours.", ids=("s7-f3",), facts=backed)
    assert len(kept) == 1


def _ipo(fid, story, metric, day, quote):
    return {**mkfact(fid, story, quote, date=f"2026-11-{day}T12:00:00+00:00"), "metric": metric}


def test_older_fact_on_same_entity_and_metric_is_not_offered():
    old = _ipo("s32-f4", "s32", "anthropic_ipo_price_range", 17, "Anthropic kept its range at $70 to $78.")
    new = _ipo("s2-f1", "s2", "anthropic_ipo_price_per_share", 18, "Anthropic priced its IPO at $83.")
    other = _ipo("s32-f1", "s32", "nasdaq_open_change", 17, "The Nasdaq opened 0.09% lower.")
    same_day = _ipo("s2-f2", "s2", "anthropic_ipo_share_count", 18, "The deal included 825 million shares.")
    assert [f["id"] for f in script.current_facts([old, new, other, same_day])] == ["s2-f1", "s32-f1", "s2-f2"]


def test_same_key_older_day_is_dropped_but_different_metrics_stay():
    a = _ipo("s24-f1", "s24", "bitcoin_price", 17, "Bitcoin traded around $64,270.")
    b = _ipo("s3-f1", "s3", "bitcoin_price", 18, "Bitcoin traded below $64,000.")
    c = _ipo("s15-f5", "s15", "ttwo_fy26_net_bookings", 13, "Net bookings were $6 billion.")
    d = _ipo("s15-f4", "s15", "ttwo_fy27_net_bookings_forecast", 18, "It forecast $8 billion.")
    assert [f["id"] for f in script.current_facts([a, b, c, d])] == ["s3-f1", "s15-f5", "s15-f4"]


def test_write_script_never_offers_a_stale_fact(monkeypatch):
    old = _ipo("s1-f1", "s1", "anthropic_ipo_price_range", 17, "Anthropic kept its range at $70 to $78.")
    new = _ipo("s1-f2", "s1", "anthropic_ipo_price_per_share", 18, "Anthropic priced its IPO at $83.")
    seen = {}
    fake, _ = fake_steps({"greeting": "Morning, trader, deals first!", "sign_off": "See you soon!",
                          "lines": [{"text": "Anthropic kept its range at $70 to $78.", "kind": "claim",
                                     "fact_ids": ["s1-f1"]}]})

    def spy(step, system, user, schema, **kw):
        if step == "script":
            seen["prompt"] = user
        return fake(step, system, user, schema, **kw)
    monkeypatch.setattr(script, "ask_json", spy)
    lines, dropped, _, _ = script.write_script({**LONG, "name": "trader"}, WS_STORIES, [old, new])
    assert "s1-f1" not in seen["prompt"] and "s1-f2" in seen["prompt"]
    assert lines == [] or all("s1-f1" not in x["fact_ids"] for x in lines)


# ---------------------------------------------------------------- regen 20.11. evening
def test_missing_interest_that_a_story_title_names_is_not_said(monkeypatch):
    _, missing = pick(monkeypatch, {"story_ids": ["s1"], "interests_without_story": ["T3 news", "Solarenergie"]})
    assert missing == ["Solarenergie"]  # "T3" is in a title of the day, saying "nothing on it" would be false


def test_same_figures_twice_is_a_repeat():
    fact = mkfact(quote="USD/JPY reached 160.30 before retreating to around 159.89 on Friday.")
    lines = [{"text": "USD/JPY reached 160.30 before retreating to 159.89.", "kind": "claim", "fact_ids": ["s1-f1"]},
             {"text": "The pair hit 160.30 and then eased to about 159.89.", "kind": "claim", "fact_ids": ["s1-f1"]}]
    kept, dropped = script.check_script(lines, [fact], "en")
    assert len(kept) == 1 and dropped[0]["why"] == "repeats an earlier line"


def test_english_date_opening_in_german_line_is_dropped():
    fact = mkfact(quote="On 13 November, producer prices rose 0.3% in October.")
    kept, dropped = run("On 13 November stiegen die Erzeugerpreise um 0,3 Prozent.", facts=[fact], lang="de")
    assert kept == [] and "English" in dropped[0]["why"]


def test_date_numbers_only_next_to_a_month():
    fact = mkfact(quote="Retail sales rose 0.3% in October.", date="2026-11-18T08:00:00+00:00")
    kept, dropped = run("Retail sales rose 18 percent in October.", facts=[fact])
    assert kept == [] and "18" in dropped[0]["why"]
    kept, _ = run("On 18 November 2026, retail sales were reported up 0.3 percent.", facts=[fact])
    assert len(kept) == 1


def test_short_names_count_in_the_greeting():
    assert script.calls_by_name("Good morning, Tom, here is your news!", "Tom")


def test_german_three_decimals_from_english_quote_pass():
    fact = mkfact(quote="EUR/USD rose to 1.155 on Tuesday.")
    kept, _ = run("EUR/USD stieg auf 1.155.", facts=[fact], lang="de")
    assert len(kept) == 1


def test_weekday_is_a_relative_date_but_am_morgen_is_fine():
    fact = mkfact(quote="Producer prices rose 0.3% in October.")
    _, dropped = run("Producer prices rose 0.3 percent on Tuesday.", facts=[fact])
    assert "relative date" in dropped[0]["why"]
    kept, _ = run("Am Morgen meldeten die Erzeugerpreise ein Plus von 0,3 Prozent.", facts=[fact], lang="de")
    assert len(kept) == 1


def test_same_fact_with_a_shared_figure_is_a_repeat():
    fact = mkfact(quote="Retail sales rose 0.2% in October and sales excluding autos rose 0.6%.")
    lines = [{"text": "US retail sales rose 0.2 percent in October.", "kind": "claim", "fact_ids": ["s1-f1"]},
             {"text": "Retail sales growth slowed to 0.2 percent, while sales excluding autos rose 0.6 percent.",
              "kind": "claim", "fact_ids": ["s1-f1"]}]
    kept, dropped = script.check_script(lines, [fact], "en")
    assert len(kept) == 1 and dropped[0]["why"] == "repeats an earlier line"
