"""api.py with FastAPI TestClient. build_briefing is replaced, no model and no ElevenLabs."""
import json

import pytest
from fastapi.testclient import TestClient

import api

PROFILE = {"name": "Anna", "language": "en", "seconds": 90, "depth": "medium",
           "description": "Likes central banks and chips."}


@pytest.fixture
def env(tmp_path, monkeypatch):
    day = tmp_path / "2026-11-18"
    day.mkdir()
    (day / "stories.json").write_text("[]", encoding="utf-8")
    (day / "facts.json").write_text(json.dumps({"facts": []}), encoding="utf-8")
    monkeypatch.setattr(api, "OUTPUT", tmp_path)
    calls = []

    def fake_build(profile, stories, facts, out_dir, audio=True):
        calls.append(profile)
        out_dir.mkdir(parents=True, exist_ok=True)
        result = {"lines": [], "audioPath": str(out_dir / "briefing.mp3")}
        (out_dir / "briefing.json").write_text(json.dumps(result), encoding="utf-8")
        if audio:
            (out_dir / "briefing.mp3").write_bytes(b"ID3fake")
        return dict(result)
    monkeypatch.setattr(api, "build_briefing", fake_build)
    return TestClient(api.app), calls, tmp_path


def post(client, day="2026-11-18", audio=True, **profile):
    return client.post("/api/briefing", json={"day": day, "audio": audio, "profile": {**PROFILE, **profile}})


def test_days_lists_prepared_days(env):
    client, _, _ = env
    assert client.get("/api/days").json() == ["2026-11-18"]


@pytest.mark.parametrize("day", ["../etc", "2026-11-1", "abc", "2026-11-18/../x", "2026-11-99x"])
def test_invalid_day_is_404(env, day):
    client, calls, _ = env
    assert post(client, day=day).status_code == 404 and calls == []


def test_unprepared_day_is_404(env):
    client, calls, _ = env
    assert post(client, day="2026-01-01").status_code == 404 and calls == []


@pytest.mark.parametrize("bad", [{"language": "fr"}, {"seconds": 19}, {"seconds": 301}, {"language": "EN"}])
def test_language_and_seconds_validation(env, bad):
    client, calls, _ = env
    assert post(client, **bad).status_code == 422 and calls == []


@pytest.mark.parametrize("ok", [{"seconds": 20}, {"seconds": 300}, {"language": "de"}, {"language": "nl"}])
def test_valid_edges_pass(env, ok):
    client, calls, _ = env
    assert post(client, **ok).status_code == 200 and len(calls) == 1


def test_description_too_long_and_too_short(env):
    client, calls, _ = env
    assert post(client, description="x" * 1001).status_code == 422
    assert post(client, description="short").status_code == 422
    assert calls == []


def test_name_too_long(env):
    client, _, _ = env
    assert post(client, name="n" * 61).status_code == 422


def test_cache_hit_without_new_build(env):
    client, calls, _ = env
    r1 = post(client)
    assert r1.status_code == 200 and len(calls) == 1
    r2 = post(client)
    assert r2.status_code == 200 and len(calls) == 1
    assert r2.json()["audioUrl"] == r1.json()["audioUrl"] and r1.json()["audioUrl"].endswith(".mp3")


def test_other_profile_builds_again(env):
    client, calls, _ = env
    post(client)
    post(client, description="Totally different interests, mostly crypto.")
    assert len(calls) == 2


def test_audio_path_not_leaked(env):
    client, _, _ = env
    assert "audioPath" not in post(client).json()


def test_cached_without_mp3_rebuilds_when_audio_wanted(env):
    client, calls, _ = env
    post(client, audio=False)
    assert len(calls) == 1
    r = post(client, audio=False)  # text only: cache is enough
    assert len(calls) == 1 and r.json()["audioUrl"] is None
    post(client, audio=True)       # audio wanted, mp3 missing: build again
    assert len(calls) == 2


def test_audio_served(env):
    client, _, _ = env
    url = post(client).json()["audioUrl"]
    r = client.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == b"ID3fake"


@pytest.mark.parametrize("key", ["..%2F..%2Ffacts", "..%5C..%5Cfacts", "ABC", "a.b", "%2e%2e", "x" * 61])
def test_audio_bad_key_is_404(env, key):
    client, _, _ = env
    assert client.get(f"/api/audio/2026-11-18/{key}.mp3").status_code == 404


def test_audio_unknown_key_and_bad_day(env):
    client, _, _ = env
    assert client.get("/api/audio/2026-11-18/nothing-here.mp3").status_code == 404
    assert client.get("/api/audio/not-a-day/anna-12345678.mp3").status_code == 404
