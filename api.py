"""Small web API for the React player. Keys stay on this server, never in the browser.

Run:  .venv/Scripts/uvicorn api:app --port 8000
  GET  /api/days                       prepared news days
  POST /api/briefing  {day, profile}   briefing.json for any listener (cached: same profile = no new cost)
  GET  /api/audio/{day}/{key}.mp3      the audio of a briefing
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
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

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


@app.post("/api/briefing")
async def briefing(req: Request):
    folder = _day(req.day)
    profile = req.profile.model_dump()
    if profile["language"] not in ("en", "de", "nl") or not 20 <= profile["seconds"] <= 300:
        raise HTTPException(422, "language must be en, de or nl and seconds between 20 and 300")
    key = f"{slug(profile['name'])}-{hashlib.sha1(json.dumps(profile, sort_keys=True).encode()).hexdigest()[:8]}"
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
        task = asyncio.ensure_future(run_in_threadpool(_build, folder, profile, out, req.audio))
        _inflight[key] = task
        task.add_done_callback(lambda _t, k=key: _inflight.pop(k, None))
        result = await asyncio.shield(task)  # shield: a listener who closes the tab does not abort a paid build
        break
    result = dict(result)
    result["audioUrl"] = f"/api/audio/{req.day}/{key}.mp3" if (out / "briefing.mp3").exists() else None
    result.pop("audioPath", None)  # local file path, not for the browser
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
