"""api.py with FastAPI TestClient. build_briefing is replaced, no model and no ElevenLabs."""
import asyncio
import json
import time
from collections import deque

import httpx

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
    monkeypatch.setattr(api, "_inflight", {})
    monkeypatch.setattr(api, "_started", deque())
    calls = []

    def fake_build(profile, stories, facts, out_dir, audio=True):
        calls.append(profile)
        if profile["description"].startswith("SLOW"):
            time.sleep(0.4)  # like a model call: long enough for other requests to arrive meanwhile
        if profile["description"].startswith("FAIL"):
            raise RuntimeError("model down")
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


# ---------------------------------------------------------------- many listeners at once

def gather(*bodies):
    """Sends all requests at the same time against the app (one event loop, like uvicorn) and returns
    [(status, json, seconds)]."""
    async def run():
        transport = httpx.ASGITransport(app=api.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            async def one(body):
                t = time.perf_counter()
                r = await c.post("/api/briefing", json=body)
                return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json")
                                       else None), time.perf_counter() - t, r.headers
            return await asyncio.gather(*(one(b) for b in bodies))
    return asyncio.run(run())


def body(audio=False, **profile):
    return {"day": "2026-11-18", "audio": audio, "profile": {**PROFILE, **profile}}


def test_same_new_listener_at_once_is_built_once(env):
    _, calls, _ = env
    results = gather(*[body(description="SLOW same listener, likes chips.")] * 6)
    assert [r[0] for r in results] == [200] * 6
    assert len(calls) == 1  # five requests waited for the first instead of paying again


def test_cached_listener_not_blocked_by_a_build(env):
    client, calls, _ = env
    post(client, audio=False)  # Anna is now cached
    results = gather(body(description="SLOW new listener, wants crypto."), body())
    (s_new, _, t_new, _), (s_cached, _, t_cached, _) = results
    assert s_new == s_cached == 200 and t_new >= 0.4
    assert t_cached < 0.3  # served while the other one was still being written


def test_concurrency_cap_returns_429(env, monkeypatch):
    _, calls, _ = env
    monkeypatch.setattr(api, "MAX_CONCURRENT_NEW", 2)
    results = gather(*[body(description=f"SLOW distinct listener number {i}.") for i in range(4)])
    codes = sorted(r[0] for r in results)
    assert codes == [200, 200, 429, 429] and len(calls) == 2
    assert all(r[3].get("retry-after") for r in results if r[0] == 429)


def test_hourly_cap_spares_cached_listeners(env, monkeypatch):
    client, calls, _ = env
    monkeypatch.setattr(api, "MAX_NEW_PER_HOUR", 2)
    assert post(client, audio=False).status_code == 200
    assert post(client, audio=False, description="Second listener, wants oil.").status_code == 200
    r = post(client, audio=False, description="Third listener, wants gold.")
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 3000
    assert post(client, audio=False).status_code == 200  # cached: no limit
    assert len(calls) == 2


def test_failed_build_reaches_waiters_and_frees_the_slot(env):
    _, calls, _ = env
    results = gather(*[body(description="FAIL listener whose build breaks.")] * 3)
    assert all(r[0] == 500 for r in results)
    assert api._inflight == {}  # nothing stuck: the next try builds again
    gather(body(description="FAIL listener whose build breaks."))
    assert len(calls) == 2


def test_audio_request_waits_for_text_build_then_builds_audio(env):
    _, calls, tmp = env
    desc = "SLOW listener, first text, then audio."
    results = gather(body(audio=False, description=desc), body(audio=True, description=desc))
    assert [r[0] for r in results] == [200, 200]
    assert len(calls) == 2 and results[1][1]["audioUrl"].endswith(".mp3") and results[0][1]["audioUrl"] is None
