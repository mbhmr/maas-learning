"""Small web API for the React player. Keys stay on this server, never in the browser.

Run:  .venv/Scripts/uvicorn api:app --port 8000
  GET  /api/days                       prepared news days
  POST /api/briefing  {day, profile}   briefing.json for any listener (cached: same profile = no new cost)
  GET  /api/audio/{day}/{key}.mp3      the audio of a briefing
The briefing format is described in README.md (claims with text, start/end seconds and sources).
"""
import hashlib
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.briefing import build_briefing, slug

OUTPUT = Path("output")
app = FastAPI(title="The Liquid Briefing")
# Only the local React dev server may call this. Before any public link: add a login or a rate limit first,
# otherwise anyone could spend the event credits.
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


@app.post("/api/briefing")
def briefing(req: Request):
    folder = _day(req.day)
    profile = req.profile.model_dump()
    if profile["language"] not in ("en", "de", "nl") or not 20 <= profile["seconds"] <= 300:
        raise HTTPException(422, "language must be en, de or nl and seconds between 20 and 300")
    key = f"{slug(profile['name'])}-{hashlib.sha1(json.dumps(profile, sort_keys=True).encode()).hexdigest()[:8]}"
    out = folder / "briefings" / key
    cached = out / "briefing.json"
    if cached.exists() and (not req.audio or (out / "briefing.mp3").exists()):
        result = json.loads(cached.read_text(encoding="utf-8"))
    else:
        stories = json.loads((folder / "stories.json").read_text(encoding="utf-8"))
        facts = json.loads((folder / "facts.json").read_text(encoding="utf-8"))["facts"]
        result = build_briefing(profile, stories, facts, out, audio=req.audio)
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
