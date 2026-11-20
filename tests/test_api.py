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


# ---------------------------------------------------------------- shared editions (mode "edition")

@pytest.fixture
def edition_env(env, monkeypatch):
    client, calls, tmp = env
    built = []

    def fake_listener(folder, profile, out, stories, facts, audio=True):
        built.append(profile)
        out.mkdir(parents=True, exist_ok=True)
        key = "en-90s-medium-markets-fx"
        (folder / "editions" / key).mkdir(parents=True, exist_ok=True)
        (folder / "editions" / key / "briefing.json").write_text(json.dumps(
            {"key": key, "language": "en", "seconds": 90, "depth": "medium", "segment": "markets-fx"}),
            encoding="utf-8")
        listeners = folder / "editions" / key / "listeners.json"
        seen = json.loads(listeners.read_text()) if listeners.exists() else []
        listeners.write_text(json.dumps(seen + [profile["name"]]))
        result = {"mode": "edition", "editionKey": key, "claims": [], "audioPath": str(out / "briefing.mp3")}
        (out / "briefing.json").write_text(json.dumps(result), encoding="utf-8")
        if audio:
            (out / "briefing.mp3").write_bytes(b"ID3edition")
        return dict(result)
    monkeypatch.setattr(api.editions, "build_listener", fake_listener)
    return client, calls, built


def test_personal_is_default_and_says_so(env):
    client, _, _ = env
    r = post(client).json()
    assert r["mode"] == "personal" and r["edition"] is None


def test_edition_mode_response(edition_env):
    client, calls, built = edition_env
    r = client.post("/api/briefing", json={"day": "2026-11-18", "mode": "edition", "profile": PROFILE})
    j = r.json()
    assert r.status_code == 200 and calls == [] and len(built) == 1  # the personal build is not used
    assert j["mode"] == "edition" and "editionKey" not in j and "audioPath" not in j
    assert j["edition"] == {"key": "en-90s-medium-markets-fx", "segment": "markets-fx", "language": "en",
                            "seconds": 90, "depth": "medium", "label": "markets and currencies", "listeners": 1}
    assert client.get(j["audioUrl"]).content == b"ID3edition"


def test_edition_listener_count_is_read_fresh_from_cache(edition_env):
    client, _, built = edition_env
    send = lambda **p: client.post("/api/briefing", json={"day": "2026-11-18", "mode": "edition",
                                                          "profile": {**PROFILE, **p}}).json()
    first = send()
    send(name="Ben")
    again = send()  # Anna again: served from cache, but the count includes Ben now
    assert len(built) == 2 and first["edition"]["listeners"] == 1 and again["edition"]["listeners"] == 2


def test_same_profile_personal_and_edition_do_not_share_a_cache(edition_env):
    client, calls, built = edition_env
    p = post(client).json()
    e = client.post("/api/briefing", json={"day": "2026-11-18", "mode": "edition", "profile": PROFILE}).json()
    assert p["audioUrl"] != e["audioUrl"] and len(calls) == 1 and len(built) == 1


def test_unknown_mode_is_422(env):
    client, calls, _ = env
    r = client.post("/api/briefing", json={"day": "2026-11-18", "mode": "shared", "profile": PROFILE})
    assert r.status_code == 422 and calls == []


# ---------------------------------------------------------------- GET /api/stories/{day}

STORIES = [
    {"id": "s2", "rank": 2, "title": "Second", "topic": "markets", "importance": 3, "publishers": ["Zacks"],
     "article_ids": ["z1"], "selected": False, "translations": {}, "latest": "2026-11-17T08:00:00+00:00",
     "headlines": [{"id": "z1", "publisher": "Zacks", "headline": "Z one", "date": "2026-11-17T08:00:00+00:00",
                    "url": "https://z/1"}]},
    {"id": "s1", "rank": 1, "title": "First", "topic": "currencies", "importance": 5,
     "publishers": ["Invezz", "ActionForex"], "article_ids": ["i1", "a1"], "selected": True,
     "translations": {"i1": {"de": "i1de"}}, "latest": "2026-11-18T09:00:00+00:00",
     "headlines": [{"id": "i1", "publisher": "Invezz", "headline": "I one", "date": "2026-11-18T09:00:00+00:00",
                    "url": "https://i/1"},
                   {"id": "a1", "publisher": "ActionForex", "headline": "A one", "url": "https://a/1"}]},
]
META = {"i1": {"publisher": "Invezz", "date": "2026-11-18T09:00:00+00:00", "headline": "I one", "url": "https://i/1",
               "language": "en"},
        "i1de": {"publisher": "Invezz - German", "date": "2026-11-18T09:30:00+00:00", "headline": "I eins",
                 "url": "https://i/de/1", "language": "de"},
        "a1": {"publisher": "ActionForex", "date": "2026-11-18T07:00:00+00:00", "headline": "A one",
               "url": "https://a/1", "language": "en"}}


@pytest.fixture
def stories_env(env, monkeypatch):
    client, _, tmp = env
    (tmp / "2026-11-18" / "stories.json").write_text(json.dumps(STORIES), encoding="utf-8")
    (tmp / "2026-11-18" / "facts.json").write_text(json.dumps({"facts": [{"story_id": "s1"}, {"story_id": "s1"}]}),
                                                   encoding="utf-8")
    monkeypatch.setattr(api, "_article_meta", lambda: META)
    return client, tmp


def test_stories_ranked_with_articles_and_no_text(stories_env):
    client, _ = stories_env
    j = client.get("/api/stories/2026-11-18").json()
    assert j["day"] == "2026-11-18" and [s["id"] for s in j["stories"]] == ["s1", "s2"]
    s1, s2 = j["stories"]
    assert {k: s1[k] for k in ("rank", "title", "topic", "importance", "outlets", "articleCount", "languages",
                               "selected", "hasFacts", "factCount", "latest")} == {
        "rank": 1, "title": "First", "topic": "currencies", "importance": 5, "outlets": ["Invezz", "ActionForex"],
        "articleCount": 2, "languages": ["de", "en"], "selected": True, "hasFacts": True, "factCount": 2,
        "latest": "2026-11-18"}
    assert s1["articles"] == [
        {"id": "i1", "publisher": "Invezz", "date": "2026-11-18", "headline": "I one", "url": "https://i/1",
         "language": "en", "translationOf": None},
        {"id": "i1de", "publisher": "Invezz - German", "date": "2026-11-18", "headline": "I eins",
         "url": "https://i/de/1", "language": "de", "translationOf": "i1"},
        {"id": "a1", "publisher": "ActionForex", "date": "2026-11-18", "headline": "A one", "url": "https://a/1",
         "language": "en", "translationOf": None}]  # date of a1 filled from the data, its headline has none
    assert s2["hasFacts"] is False and s2["factCount"] == 0
    assert "text" not in json.dumps(j).replace("translationOf", "")  # never the article body


def test_stories_without_facts_file_and_without_data(stories_env, monkeypatch):
    client, tmp = stories_env
    (tmp / "2026-11-18" / "facts.json").unlink()
    monkeypatch.setattr(api, "_article_meta", lambda: {})
    j = client.get("/api/stories/2026-11-18").json()
    s1 = j["stories"][0]
    assert not s1["hasFacts"] and s1["languages"] == [] and len(s1["articles"]) == 2  # no translation without data
    assert s1["articles"][1]["date"] is None and s1["articles"][1]["language"] is None


@pytest.mark.parametrize("day", ["2026-01-01", "abc", "..", "2026-11-18x"])
def test_stories_unknown_day_is_404(stories_env, day):
    client, _ = stories_env
    assert client.get(f"/api/stories/{day}").status_code == 404
