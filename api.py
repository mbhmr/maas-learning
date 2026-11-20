"""Small web API for the React player. Keys stay on this server, never in the browser.

Run:  .venv/Scripts/uvicorn api:app --port 8000
  GET  /api/days                       prepared news days
  POST /api/briefing  {day, profile, mode}  briefing.json for any listener (cached: same profile = no new cost)
                                       mode "personal" (default): own story choice and script for this listener;
                                       mode "edition": shared edition body, only the greeting is personal
  GET  /api/audio/{day}/{key}.mp3      the audio of a briefing
  GET  /api/stories/{day}              every story of the day, ranked, with its article list (no article text)
The briefing format is described in README.md (claims with text, start/end seconds and sources).

Many listeners at once: a new briefing is built in a worker thread, so cached listeners are served while others
wait for the model. The same listener twice at the same time is built once, the second request waits for the
first. At most MAX_CONCURRENT_NEW new briefings run at once and MAX_NEW_PER_HOUR start per hour, beyond that 429:
so a shared link cannot burn the event credits. Cached briefings are never limited.
"""
import asyncio
import hashlib
import json
import os
import re
import time
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src import editions
from src.briefing import build_briefing, slug

OUTPUT = Path("output")
app = FastAPI(title="The Liquid Briefing")
# Only the local React dev server may call this. The limits below cap the spend; before a public link still add a
# login, because the limits are for everyone together, so one visitor could use up the hour for all.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


class Profile(BaseModel):
    name: str = Field("Listener", max_length=60)
    language: str = "en"
    seconds: int = 90
    depth: str = Field("medium", max_length=80)
    description: str = Field(..., min_length=10, max_length=1000)


class Request(BaseModel):
    day: str
    profile: Profile
    audio: bool = True
    # personal stays the default: the demo presets keep their own story choice and the model's greeting. edition is
    # the path for many listeners (src/editions.py): same news body for everyone with the same edition key.
    mode: Literal["personal", "edition"] = "personal"


def _day(day):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise HTTPException(404, "day must look like 2026-11-18")
    folder = OUTPUT / day
    if not (folder / "facts.json").exists() or not (folder / "stories.json").exists():
        raise HTTPException(404, f"day {day} is not prepared")
    return folder


@app.get("/api/days")
def days():
    return sorted((p.parent.name for p in OUTPUT.glob("*/facts.json") if (p.parent / "stories.json").exists()),
                  reverse=True)


# Credit guard (measured 20.11.: a new text briefing about 0.01 USD, with voice about 0.11 USD).
MAX_CONCURRENT_NEW = int(os.getenv("BRIEFING_MAX_CONCURRENT", "4"))
MAX_NEW_PER_HOUR = int(os.getenv("BRIEFING_MAX_PER_HOUR", "60"))
_inflight = {}      # cache key -> task that is building this briefing right now
_started = deque()  # start times (monotonic seconds) of new briefings in the last hour


def _admit():
    """Raises 429 if a new briefing would exceed the limits, otherwise books its start."""
    now = time.monotonic()
    while _started and now - _started[0] > 3600:
        _started.popleft()
    if len(_inflight) >= MAX_CONCURRENT_NEW:
        raise HTTPException(429, f"{MAX_CONCURRENT_NEW} new briefings are being written right now, try again in a "
                                 "few seconds", headers={"Retry-After": "15"})
    if len(_started) >= MAX_NEW_PER_HOUR:
        wait = int(3600 - (now - _started[0])) + 1
        raise HTTPException(429, f"limit of {MAX_NEW_PER_HOUR} new briefings per hour reached",
                            headers={"Retry-After": str(wait)})
    _started.append(now)


def _build(folder, profile, out, audio):
    """The slow part (three model calls, optionally the voice). Runs in a worker thread."""
    stories = json.loads((folder / "stories.json").read_text(encoding="utf-8"))
    facts = json.loads((folder / "facts.json").read_text(encoding="utf-8"))["facts"]
    return build_briefing(profile, stories, facts, out, audio=audio)


def _build_edition(folder, profile, out, audio):
    """A listener of a shared edition: segment call (cached), the edition once, then greeting + body."""
    stories = json.loads((folder / "stories.json").read_text(encoding="utf-8"))
    facts = json.loads((folder / "facts.json").read_text(encoding="utf-8"))["facts"]
    return editions.build_listener(folder, profile, out, stories, facts, audio=audio)


@app.post("/api/briefing")
async def briefing(req: Request):
    folder = _day(req.day)
    profile = req.profile.model_dump()
    if profile["language"] not in ("en", "de", "nl") or not 20 <= profile["seconds"] <= 300:
        raise HTTPException(422, "language must be en, de or nl and seconds between 20 and 300")
    hashed = profile if req.mode == "personal" else {**profile, "mode": req.mode}  # personal keys stay as they were
    key = f"{slug(profile['name'])}-{hashlib.sha1(json.dumps(hashed, sort_keys=True).encode()).hexdigest()[:8]}"
    out = folder / "briefings" / key
    cached = out / "briefing.json"
    while True:
        if cached.exists() and (not req.audio or (out / "briefing.mp3").exists()):
            result = json.loads(cached.read_text(encoding="utf-8"))
            break
        task = _inflight.get(key)
        if task is not None:
            # the same listener is being built right now: wait for it instead of paying twice, then look again
            # (a text-only build does not answer a request that wants audio)
            await asyncio.shield(task)
            continue
        _admit()
        build = _build if req.mode == "personal" else _build_edition
        task = asyncio.ensure_future(run_in_threadpool(build, folder, profile, out, req.audio))
        _inflight[key] = task
        task.add_done_callback(lambda _t, k=key: _inflight.pop(k, None))
        result = await asyncio.shield(task)  # shield: a listener who closes the tab does not abort a paid build
        break
    result = dict(result)
    result["audioUrl"] = f"/api/audio/{req.day}/{key}.mp3" if (out / "briefing.mp3").exists() else None
    result.pop("audioPath", None)  # local file path, not for the browser
    result["mode"] = req.mode
    edition_key = result.pop("editionKey", None)
    result["edition"] = editions.info(folder, edition_key) if edition_key else None  # count is read fresh
    return result


@app.get("/api/audio/{day}/{key}.mp3")
def audio(day: str, key: str):
    if not re.fullmatch(r"[a-z0-9-]{1,60}", key):  # no path tricks like ../
        raise HTTPException(404, "no audio")
    path = _day(day) / "briefings" / key / "briefing.mp3"
    if not path.exists():
        raise HTTPException(404, "no audio")
    return FileResponse(path, media_type="audio/mpeg")


# Sound (src/sound.py): jingle and chimes as fixed files, and the original quote read aloud on click.
from src.sound import speak_quote  # noqa: E402

SOUNDS = ("jingle", "verified", "conflict")


@app.get("/api/sound/{name}.mp3")
def sound(name: str):
    path = OUTPUT / "sound" / f"{name}.mp3"
    if name not in SOUNDS or not path.exists():
        raise HTTPException(404, "no such sound")
    return FileResponse(path, media_type="audio/mpeg")


class QuoteRequest(BaseModel):
    quote: str = Field(..., min_length=1, max_length=2000)
    lang: str = "en"


def _known_quotes():
    """Every verbatim quote of a checked fact. Only these may be read aloud, so nobody spends our credits on
    arbitrary text."""
    quotes = set()
    for p in OUTPUT.glob("*/facts.json"):
        for fact in json.loads(p.read_text(encoding="utf-8")).get("facts", []):
            quotes.update(s["quote"] for s in fact.get("sources", []) if s.get("quote"))
    return quotes


@app.post("/api/quote-audio")
def quote_audio(req: QuoteRequest):
    if req.lang not in ("en", "de", "nl"):
        raise HTTPException(422, "lang must be en, de or nl")
    if req.quote not in _known_quotes():
        raise HTTPException(404, "not a quote from our checked facts")
    return FileResponse(speak_quote(req.quote, req.lang), media_type="audio/mpeg")


# ---------------------------------------------------------------- the stories of a day, for the newsroom view

@lru_cache(maxsize=1)
def _article_meta():
    """Language, headline and link of every article in data/ (never the text). Empty if the data is not here."""
    from src.articles import load_articles
    try:
        return {i: {k: a[k] for k in ("publisher", "date", "headline", "url", "language")}
                for i, a in load_articles().items()}
    except FileNotFoundError:
        return {}


@app.get("/api/stories/{day}")
def stories_of_day(day: str):
    """All stories prepare.py grouped for this day, most important first. Metadata and links only, no article
    body (licence). language is null when data/ is missing on this machine."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or not (OUTPUT / day / "stories.json").exists():
        raise HTTPException(404, f"day {day} is not prepared")
    stories = json.loads((OUTPUT / day / "stories.json").read_text(encoding="utf-8"))
    facts_path = OUTPUT / day / "facts.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8"))["facts"] if facts_path.exists() else []
    fact_count = {}
    for f in facts:
        fact_count[f["story_id"]] = fact_count.get(f["story_id"], 0) + 1
    meta = _article_meta()
    out = []
    for s in sorted(stories, key=lambda s: s["rank"]):
        articles = []
        headlines = {h["id"]: h for h in s.get("headlines", [])}
        for aid in s["article_ids"]:
            h = {**meta.get(aid, {}), **headlines.get(aid, {})}  # older days have no date in their headlines
            articles.append({"id": aid, "publisher": h.get("publisher"), "date": (h.get("date") or "")[:10] or None,
                             "headline": h.get("headline"), "url": h.get("url"), "language": h.get("language"),
                             "translationOf": None})
            for lang, tid in s.get("translations", {}).get(aid, {}).items():
                t = meta.get(tid)
                if t:
                    articles.append({"id": tid, "publisher": t["publisher"], "date": t["date"][:10],
                                     "headline": t["headline"], "url": t["url"], "language": lang,
                                     "translationOf": aid})
        out.append({"rank": s["rank"], "id": s["id"], "title": s["title"], "topic": s.get("topic"),
                    "importance": s.get("importance"), "outlets": s.get("publishers", []),
                    "articleCount": len(s["article_ids"]),
                    "languages": sorted({a["language"] for a in articles if a["language"]}),
                    "selected": bool(s.get("selected")), "hasFacts": s["id"] in fact_count,
                    "factCount": fact_count.get(s["id"], 0), "latest": (s.get("latest") or "")[:10] or None,
                    "articles": articles})
    return {"day": day, "stories": out}
