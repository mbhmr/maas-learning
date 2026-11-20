"""Listening back: the finished MP3 goes through ElevenLabs Speech-to-Text, every spoken number is compared.

The transcript is checked against the articles before speech is generated. This closes the last gap:
did the voice actually say those numbers? A claim passes when every number in its checked text is
also heard in its time window of the audio.
"""
import os
import re

import httpx
from dotenv import load_dotenv

from .facts import numbers
from .llm import ENV, log_usage

MODEL = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v2")
PAD = 0.3  # seconds around a claim, word timings of the two models differ slightly


def _transcribe(mp3_path, lang, keyterms):
    load_dotenv(ENV)
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is missing in .env.")
    data = {"model_id": MODEL, "language_code": lang, "timestamps_granularity": "word",
            "tag_audio_events": "false", "diarize": "false"}
    with open(mp3_path, "rb") as f:
        r = httpx.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": key},
            data={**data, "keyterms": keyterms} if keyterms else data,
            files={"file": (os.path.basename(mp3_path), f, "audio/mpeg")},
            timeout=300,
        )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs STT error {r.status_code}: {r.text[:300]}")
    return r.json()


def _keyterms(claims):
    """Names only (capitalised words), never the numbers: feeding the expected numbers to the recogniser
    would push it to hear them, and the check would confirm itself."""
    text = " ".join(c.get("text") or "" for c in claims if c.get("sources"))  # sourced claims, not the jingle lines
    lower = set(re.findall(r"\b[a-z]+\b", text))
    terms = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        for m in re.finditer(r"\b[A-Z][A-Za-z&]{2,}\b", sentence):
            w = m.group()
            # at the start of a sentence every word is capitalised: "The" counts only if it never appears as "the"
            if (m.start() or w.lower() not in lower) and w not in terms and len(terms) < 50:
                terms.append(w)
    return terms


def _heard_numbers(text, lang):
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text)  # "December 8th" means 8, the facts parser drops ordinals
    return numbers(text, lang)


def _missing(expected, heard):
    """Expected numbers not heard. A year may come back as one number (2026) or as two (20 26)."""
    out = []
    for n in sorted(expected):
        if n in heard:
            continue
        if n.is_integer() and 1900 <= n <= 2099 and {n // 100, n % 100} <= heard:
            continue
        out.append(n)
    return out


def check_audio(mp3_path, claims, lang="en"):
    """Returns {"checked": n, "ok": n, "mismatches": [{"claim_id", "text", "expected", "heard"}]}.

    Only claims with timing and at least one number are checked.
    """
    todo = [c for c in claims if c.get("start") is not None and c.get("end") is not None and numbers(c["text"], lang)]
    if not todo:
        return {"checked": 0, "ok": 0, "mismatches": []}
    result = _transcribe(mp3_path, lang, _keyterms(claims))
    words = [w for w in result.get("words", []) if w.get("type") == "word" and w.get("start") is not None]
    seconds = result.get("audio_duration_secs") or (words[-1]["end"] if words else 0)
    log_usage({"service": "elevenlabs", "step": "audiocheck", "model": MODEL, "seconds": round(seconds, 2)})

    ok, mismatches = 0, []
    for c in todo:
        spoken = " ".join(w["text"] for w in words if c["start"] - PAD <= w["start"] and w["end"] <= c["end"] + PAD)
        expected, heard = numbers(c["text"], lang), _heard_numbers(spoken, lang)
        if _missing(expected, heard):
            mismatches.append({"claim_id": c["id"], "text": c["text"], "expected": sorted(expected),
                               "heard": sorted(heard), "spoken": spoken})
        else:
            ok += 1
    return {"checked": len(todo), "ok": ok, "mismatches": mismatches}
