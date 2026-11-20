"""src/briefing.py: claims built from the checked script (write_script is faked, no network, no audio)."""
from src import briefing


def fact(fid, story, sources):
    return {"id": fid, "story_id": story, "conflict": False, "sources": sources}


def src(article, quote, value="0.3%"):
    return {"article_id": article, "quote": quote, "publisher": "Reuters", "url": f"https://x.test/{article}",
            "date": "2026-11-18T08:00:00+00:00", "value_in_source": value}


FACTS = [fact("s1-f1", "s1", [src("a1", "Prices rose 0.3% in October.")]),
         fact("s1-f2", "s1", [src("a1", "The annual rate was 6.5%.", "6.5%")]),  # same article, other quote
         fact("s2-f1", "s2", [src("a2", "Waller wants 50 bp.", "50")])]
FRAME = {"greeting": "Morning, trader!", "opening": "Read by an AI voice, every figure links to its source.",
         "sign_off": "Trade sharp!", "closing": "Information, not investment advice."}
LINES = [{"text": "Prices rose 0.3 percent, the annual rate was 6.5 percent.", "fact_ids": ["s1-f1", "s1-f2"],
          "kind": "claim"},
         {"text": "That keeps inflation in focus for you.", "fact_ids": ["s1-f2"], "kind": "context"},
         {"text": "Waller wants 50 basis points.", "fact_ids": ["s2-f1"], "kind": "claim"},
         {"text": "Today's sources have nothing on gold.", "fact_ids": [], "kind": "transition"}]
STORIES = [{"id": "s1", "rank": 1, "title": "PPI", "article_ids": ["a1"]}]


def build(monkeypatch, tmp_path, frame=FRAME, audio=False):
    monkeypatch.setattr(briefing, "write_script", lambda *a: (LINES, [], STORIES, frame))
    return briefing.build_briefing({"language": "en", "seconds": 120}, STORIES, FACTS, tmp_path, audio=audio)


def test_kinds_and_frame_order(monkeypatch, tmp_path):
    claims = build(monkeypatch, tmp_path)["claims"]
    assert [c["kind"] for c in claims] == ["host", "disclosure", "claim", "context", "claim", "transition",
                                           "host", "disclosure"]
    assert claims[0]["text"] == "Morning, trader!" and claims[-1]["text"] == "Information, not investment advice."
    assert all("factIds" in c for c in claims)


def test_every_cited_quote_is_shown(monkeypatch, tmp_path):
    first = build(monkeypatch, tmp_path)["claims"][2]
    assert [s["quote"] for s in first["sources"]] == ["Prices rose 0.3% in October.", "The annual rate was 6.5%."]
    assert first["factIds"] == ["s1-f1", "s1-f2"] and [s["factId"] for s in first["sources"]] == ["s1-f1", "s1-f2"]


def test_context_shows_the_spoken_facts_of_its_story(monkeypatch, tmp_path):
    ctx = build(monkeypatch, tmp_path)["claims"][3]
    assert ctx["kind"] == "context" and sorted(ctx["factIds"]) == ["s1-f1", "s1-f2"]


def test_no_sign_off_line_when_empty(monkeypatch, tmp_path):
    claims = build(monkeypatch, tmp_path, {**FRAME, "sign_off": ""})["claims"]
    assert [c["kind"] for c in claims][-2:] == ["transition", "disclosure"]


def test_tags_go_to_speech_only(monkeypatch, tmp_path):
    seen = {}

    def speak(parts, mp3, lang, tags=None, words=None):
        seen["parts"], seen["tags"] = parts, tags
        return [(0.0, 1.0)] * len(parts)
    monkeypatch.setattr(briefing, "speak", speak)
    b = build(monkeypatch, tmp_path, audio=True)
    assert seen["tags"] == ["excited", "", "excited", "", "excited", "", "cheerful", ""]
    assert "[" not in "".join(seen["parts"]) and "[" not in "".join(c["text"] for c in b["claims"])
