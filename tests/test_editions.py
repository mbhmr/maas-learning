"""src/editions.py without model and voice: segment, key, MP3 joining, one body for many listeners."""
import json

import pytest

from src import editions

FRAME_SECONDS = 1152 / 44100


def frame(pad=0, fill=b"\x00"):
    """One MPEG-1 layer III frame, 128 kbit/s, 44.1 kHz (417 bytes, 418 with padding)."""
    head = bytes([0xFF, 0xFB, 0x90 | (pad << 1), 0x64])
    return head + fill * (417 + pad - 4)


def mp3(n, fill=b"\x00"):
    """Like an ElevenLabs file: ID3v2 tag, a LAME Info frame, then n audio frames."""
    tag = b"ID3\x04\x00\x00" + bytes([0, 0, 0, 10]) + b"x" * 10
    info = bytes([0xFF, 0xFB, 0x90, 0x64]) + b"\x00" * 32 + b"Info" + b"\x00" * (417 - 40)
    return tag + info + b"".join(frame(pad=i % 2, fill=fill) for i in range(n))


def test_mp3_frames_strips_tag_and_info_frame():
    frames, seconds = editions.mp3_frames(mp3(10, fill=b"\x01"))
    assert frames[:2] == b"\xff\xfb" and b"Info" not in frames and b"ID3" not in frames
    assert len(frames) == 10 * 417 + 5  # five padded frames
    assert seconds == pytest.approx(10 * FRAME_SECONDS)


def test_mp3_frames_ignores_id3v1_and_cut_frame():
    data = mp3(4) + frame()[:100] + b"TAG" + b"\x00" * 125
    assert editions.mp3_frames(data)[1] == pytest.approx(4 * FRAME_SECONDS)
    with pytest.raises(ValueError):
        editions.mp3_frames(b"not an mp3 at all, no frames")


@pytest.mark.parametrize("seconds,bucket", [(20, 30), (45, 30), (46, 60), (75, 60), (90, 90), (100, 90),
                                            (150, 120), (165, 180), (240, 180), (300, 300)])
def test_length_bucket(seconds, bucket):
    assert editions.length_bucket(seconds) == bucket


@pytest.mark.parametrize("depth,bucket", [("dense, every figure with its period", "dense"), ("medium", "medium"),
                                          ("simple, explain terms in a few words", "simple"), ("", "medium"),
                                          ("bitte einfach erklären", "simple"), ("expert level", "dense"),
                                          ("whatever", "medium")])
def test_depth_bucket(depth, bucket):
    assert editions.depth_bucket(depth) == bucket


def test_edition_key_ignores_name_and_small_differences():
    a = {"name": "Anna", "language": "en", "seconds": 85, "depth": "medium", "description": "x"}
    b = {**a, "name": "Ben", "seconds": 95, "description": "y"}
    assert editions.edition_key(a, "markets-fx") == editions.edition_key(b, "markets-fx")
    key, parts = editions.edition_key(a, "markets-fx")
    assert key == "en-90s-medium-markets-fx" and parts["seconds"] == 90
    assert editions.edition_key({**a, "language": "de"}, "markets-fx")[0] != key


def test_classify_calls_model_once_per_description(tmp_path, monkeypatch):
    calls = []

    def fake_ask(step, system, user, schema, **kw):
        calls.append(user)
        assert schema["properties"]["segment"]["enum"] == list(editions.SEGMENTS)
        return {"segment": "crypto"}
    monkeypatch.setattr(editions, "ask_json", fake_ask)
    cache = tmp_path / "segments.json"
    assert editions.classify("Loves Bitcoin.", cache) == "crypto"
    assert editions.classify("  loves   bitcoin. ", cache) == "crypto"  # same words: from the cache
    assert len(calls) == 1 and json.loads(cache.read_text(encoding="utf-8"))


def test_classify_rejects_unknown_segment(tmp_path, monkeypatch):
    monkeypatch.setattr(editions, "ask_json", lambda *a, **k: {"segment": "sports"})
    with pytest.raises(RuntimeError):
        editions.classify("Football.", tmp_path / "s.json")


@pytest.mark.parametrize("lang,name,expected", [
    ("en", "Anna", "Good morning, Anna! Your news: markets and currencies."),
    ("de", "Jonas", "Guten Morgen, Jonas! Deine Nachrichten: Märkte und Währungen."),
    ("nl", "Sanne", "Goedemorgen, Sanne! Je nieuws: markten en valuta."),
    ("en", "Agent 007", "Good morning! Your news: markets and currencies."),        # digits never spoken
    ("en", "Buy now please friend", "Good morning! Your news: markets and currencies."),  # sounds like advice
])
def test_greeting_text(lang, name, expected):
    profile = {"name": name, "language": lang, "seconds": 90}
    assert editions.greeting_text(profile, "markets-fx") == expected


# ---------------------------------------------------------------- one body, many listeners

@pytest.fixture
def fake(tmp_path, monkeypatch):
    day = tmp_path / "2026-11-18"
    day.mkdir()
    log = {"build": [], "speak": [], "ask": []}

    def fake_build(profile, stories, facts, out_dir, audio=True):
        log["build"].append(profile)
        assert audio is False  # the edition speaks its body itself, without the greeting
        claims = [{"text": "Morning, listener!", "kind": "host"},
                  {"text": "Read by an AI voice.", "kind": "disclosure"},
                  {"text": "Prices rose 0.3 percent.", "kind": "claim", "sources": [{"articleId": "a1"}]},
                  {"text": "A second figure.", "kind": "claim", "sources": [{"articleId": "a1"}]},
                  {"text": "That matters for you.", "kind": "context", "sources": [{"articleId": "a1"}]},
                  {"text": "Have a great day, listener!", "kind": "host"},
                  {"text": "Information, not investment advice.", "kind": "disclosure"}]
        for n, c in enumerate(claims):
            c.update(id=f"c{n}", start=None, end=None, sources=c.get("sources", []), factIds=[])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "briefing.json").write_text("{}", encoding="utf-8")
        return {"claims": claims, "dropped": [{"text": "x", "why": "no source"}], "stories": [{"rank": 1}]}

    def fake_speak(parts, mp3_path, lang="en", tags=None):
        log["speak"].append((list(parts), list(tags or [])))
        mp3_path.write_bytes(mp3(10 * len(parts)))  # 10 frames per line
        return [(round(i * 10 * FRAME_SECONDS, 2), round((i + 1) * 10 * FRAME_SECONDS - 0.05, 2))
                for i in range(len(parts))]

    def fake_ask(step, system, user, schema, **kw):
        log["ask"].append(user)
        return {"segment": "crypto" if "crypto" in user.lower() else "markets-fx"}
    monkeypatch.setattr(editions, "build_briefing", fake_build)
    monkeypatch.setattr(editions, "speak", fake_speak)
    monkeypatch.setattr(editions, "ask_json", fake_ask)
    return day, log


def listener(name, **kw):
    return {"name": name, "language": "en", "seconds": 90, "depth": "medium",
            "description": f"{name} likes central banks and FX.", **kw}


def test_two_listeners_share_one_body(fake):
    day, log = fake
    a = editions.build_listener(day, listener("Anna"), day / "briefings" / "anna", [], [], audio=True)
    b = editions.build_listener(day, listener("Ben", seconds=100), day / "briefings" / "ben", [], [], audio=True)
    assert len(log["build"]) == 1  # one script for both
    bodies = [p for p, _ in log["speak"] if len(p) > 1]
    assert len(bodies) == 1 and "Morning, listener!" not in bodies[0]  # body spoken once, without the greeting
    assert [p for p, _ in log["speak"] if len(p) == 1] == [["Good morning, Anna! Your news: markets and currencies."],
                                                           ["Good morning, Ben! Your news: markets and currencies."]]
    assert a["editionKey"] == b["editionKey"] == "en-90s-medium-markets-fx"
    assert editions.listener_count(day, a["editionKey"]) == 2
    assert [c["text"] for c in a["claims"][1:]] == [c["text"] for c in b["claims"][1:]]
    assert a["mode"] == "edition" and a["stories"] == [{"rank": 1}] and a["dropped"]


def test_edition_profile_and_sign_off(fake):
    day, log = fake
    r = editions.build_listener(day, listener("Anna"), day / "briefings" / "anna", [], [], audio=False)
    edition_profile = log["build"][0]
    assert edition_profile["description"] == editions.SEGMENTS["markets-fx"][0]
    assert edition_profile["seconds"] == 90 and edition_profile["depth"] == "medium"
    texts = [c["text"] for c in r["claims"]]
    assert texts[0].startswith("Good morning, Anna!")
    assert "That's your briefing." in texts and not any("listener" in t for t in texts)  # sign-off to "listener" replaced
    assert [c["id"] for c in r["claims"]] == [f"c{n}" for n in range(len(texts))]
    assert all(c["start"] is None for c in r["claims"]) and r["audioPath"] is None and log["speak"] == []


def test_body_tags_like_build_briefing(fake):
    day, log = fake
    editions.build_listener(day, listener("Anna"), day / "briefings" / "anna", [], [], audio=True)
    body_tags = next(t for p, t in log["speak"] if len(p) > 1)
    # disclosure, first claim of the story, second claim, context, sign-off, closing
    assert body_tags == ["", "excited", "", "", "cheerful", ""]
    assert next(t for p, t in log["speak"] if len(p) == 1) == ["excited"]


def test_joined_audio_and_shifted_timestamps(fake):
    day, _ = fake
    out = day / "briefings" / "anna"
    r = editions.build_listener(day, listener("Anna"), out, [], [], audio=True)
    data = (out / "briefing.mp3").read_bytes()
    assert b"Info" not in data and data[:2] == b"\xff\xfb"  # no header frame: the browser sees the full length
    greeting_s = 10 * FRAME_SECONDS
    assert editions.mp3_frames(data)[1] == pytest.approx(greeting_s + 60 * FRAME_SECONDS)  # 1 + 6 lines
    body = json.loads((day / "editions" / r["editionKey"] / "briefing.json").read_text(encoding="utf-8"))
    for mine, shared in zip(r["claims"][1:], body["claims"]):
        assert mine["start"] == pytest.approx(shared["start"] + greeting_s, abs=0.011)
    assert r["claims"][0]["start"] == 0.0 and r["claims"][0]["end"] < r["claims"][1]["start"]
    starts = [c["start"] for c in r["claims"]]
    assert starts == sorted(starts)


def test_text_first_then_audio_does_not_write_again(fake):
    day, log = fake
    editions.build_listener(day, listener("Anna"), day / "briefings" / "a1", [], [], audio=False)
    editions.build_listener(day, listener("Anna"), day / "briefings" / "a2", [], [], audio=True)
    assert len(log["build"]) == 1 and len(log["ask"]) == 1  # script and segment reused
    assert editions.listener_count(day, "en-90s-medium-markets-fx") == 1  # same profile counted once


def test_same_greeting_text_is_spoken_once(fake):
    day, log = fake
    editions.build_listener(day, listener("Anna"), day / "briefings" / "a1", [], [], audio=True)
    editions.build_listener(day, listener("Anna", seconds=95), day / "briefings" / "a2", [], [], audio=True)
    assert len([p for p, _ in log["speak"] if len(p) == 1]) == 1


def test_other_segment_other_edition(fake):
    day, log = fake
    a = editions.build_listener(day, listener("Anna"), day / "briefings" / "a", [], [], audio=False)
    c = editions.build_listener(day, listener("Cem", description="Only crypto, please."), day / "briefings" / "c",
                                [], [], audio=False)
    assert a["editionKey"] != c["editionKey"] == "en-90s-medium-crypto" and len(log["build"]) == 2
    info = editions.info(day, c["editionKey"])
    assert info == {"key": "en-90s-medium-crypto", "segment": "crypto", "language": "en", "seconds": 90,
                    "depth": "medium", "label": "crypto", "listeners": 1}
