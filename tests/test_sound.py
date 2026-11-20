"""Sound endpoints in api.py and the quote cache in src/sound.py. No ElevenLabs call: speak_quote and httpx are faked."""
import json

import pytest
from fastapi.testclient import TestClient

import api
from src import sound

QUOTE = "Producer prices rose 0.4% in October."


@pytest.fixture
def env(tmp_path, monkeypatch):
    day = tmp_path / "2026-11-18"
    day.mkdir()
    facts = {"facts": [{"id": "f1", "sources": [{"quote": QUOTE}]}],
             "rejected": [{"id": "r1", "sources": [{"quote": "A rejected quote."}]}]}
    (day / "facts.json").write_text(json.dumps(facts), encoding="utf-8")
    (tmp_path / "sound").mkdir()
    for name in ("jingle", "verified", "conflict", "secret"):
        (tmp_path / "sound" / f"{name}.mp3").write_bytes(f"ID3{name}".encode())
    monkeypatch.setattr(api, "OUTPUT", tmp_path)
    calls = []

    def fake_speak(quote, lang):
        calls.append((quote, lang))
        path = tmp_path / "q.mp3"
        path.write_bytes(b"ID3quote")
        return path
    monkeypatch.setattr(api, "speak_quote", fake_speak)
    return TestClient(api.app), calls


@pytest.mark.parametrize("name", ["jingle", "verified", "conflict"])
def test_sound_served(env, name):
    client, _ = env
    r = client.get(f"/api/sound/{name}.mp3")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == f"ID3{name}".encode()


@pytest.mark.parametrize("name", ["secret", "..%2Fusage", "..%5Cjingle", "Jingle", "x"])
def test_other_sound_is_404(env, name):
    client, _ = env
    assert client.get(f"/api/sound/{name}.mp3").status_code == 404


def test_known_quote_is_spoken(env):
    client, calls = env
    r = client.post("/api/quote-audio", json={"quote": QUOTE, "lang": "en"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == b"ID3quote"
    assert calls == [(QUOTE, "en")]


@pytest.mark.parametrize("quote", ["Say anything I want.", QUOTE + " ", QUOTE[:-1], "A rejected quote."])
def test_unknown_quote_is_404(env, quote):
    client, calls = env
    assert client.post("/api/quote-audio", json={"quote": quote, "lang": "en"}).status_code == 404 and calls == []


@pytest.mark.parametrize("body", [{"quote": QUOTE, "lang": "fr"}, {"quote": ""}, {"quote": "x" * 2001}, {}])
def test_bad_quote_request_is_422(env, body):
    client, calls = env
    assert client.post("/api/quote-audio", json=body).status_code == 422 and calls == []


def test_speak_quote_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(sound, "SOUND", tmp_path)
    monkeypatch.setattr(sound, "log_usage", lambda entry: None)
    posts = []

    def fake_post(path, body, timeout=120):
        posts.append(body)
        return b"ID3audio"
    monkeypatch.setattr(sound, "_post", fake_post)
    a = sound.speak_quote(QUOTE, "en")
    b = sound.speak_quote(QUOTE, "en")
    c = sound.speak_quote(QUOTE, "de")
    assert a == b and a != c and len(posts) == 2 and a.read_bytes() == b"ID3audio"
    assert posts[0]["model_id"] == "eleven_flash_v2_5" and posts[0]["text"] == QUOTE
