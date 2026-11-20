"""Text to speech with the ElevenLabs REST API (no SDK: its file paths break on Windows).

Uses the /with-timestamps endpoint: one call returns the audio AND the start time of every
character, so the player can highlight the sentence being spoken and jump to a claim.
"""
import base64
import os
import re

import httpx
from dotenv import load_dotenv

from .llm import ENV, log_usage

# "George", a premade ElevenLabs voice. Override with ELEVENLABS_VOICE_ID.
DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"

# Only for the ear: the transcript keeps the written form, the voice gets the spoken one.
SPOKEN = {
    "en": [(r"\bUSD/JPY\b", "dollar yen"), (r"\bEUR/USD\b", "euro dollar"), (r"\bGBP/USD\b", "pound dollar"),
           (r"\b(m/m|MoM)\b", "month on month"), (r"\b(y/y|YoY)\b", "year on year"), (r"\bbps\b", "basis points"),
           (r"\bQ1\b", "first quarter"), (r"\bQ2\b", "second quarter"), (r"\bQ3\b", "third quarter"),
           (r"\bQ4\b", "fourth quarter"), (r"%", " percent"), (r"\bCEO\b", "C E O")],
    "de": [(r"\bUSD/JPY\b", "Dollar Yen"), (r"\bEUR/USD\b", "Euro Dollar"), (r"\bbps\b", "Basispunkte"),
           (r"\bQ([1-4])\b", r"\1. Quartal"), (r"%", " Prozent"), (r"\bggü\.", "gegenüber")],
    "nl": [(r"\bUSD/JPY\b", "dollar yen"), (r"\bEUR/USD\b", "euro dollar"), (r"\bbps\b", "basispunten"),
           (r"\bQ([1-4])\b", r"kwartaal \1"), (r"%", " procent")],
}


def spoken_form(text, lang):
    for pattern, repl in SPOKEN.get(lang, []):
        text = re.sub(pattern, repl, text)
    return re.sub(r"\s{2,}", " ", text)


def speak(parts, mp3_path, lang="en"):
    """Speaks the parts (one per transcript line) as one MP3. Returns [(start_s, end_s)] per part."""
    load_dotenv(ENV)
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is missing in .env.")
    voice = os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE
    model = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
    spoken = [spoken_form(p, lang) for p in parts]
    text, spans, pos = "", [], 0
    for i, p in enumerate(spoken):
        sep = "\n\n" if i else ""  # a paragraph break gives the voice a short pause between lines
        text += sep + p
        pos += len(sep)
        spans.append((pos, pos + len(p)))
        pos += len(p)
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key},
        # Very energetic delivery (team decision 20.11.): low stability = lively intonation, high style, a bit faster.
        # Only the VOICE is excited; the words stay neutral and checked, so no claim sounds bigger than its source.
        json={"text": text, "model_id": model,
              "voice_settings": {"stability": 0.25, "similarity_boost": 0.75, "style": 0.85,
                                 "use_speaker_boost": True, "speed": 1.12}},
        timeout=180,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs error {r.status_code}: {r.text[:300]}")
    data = r.json()
    mp3_path.write_bytes(base64.b64decode(data["audio_base64"]))
    log_usage({"service": "elevenlabs", "step": "tts", "model": model, "characters": len(text)})
    al = data.get("alignment") or {}
    starts, ends = al.get("character_start_times_seconds", []), al.get("character_end_times_seconds", [])
    if len(starts) != len(text):
        return [None] * len(parts)  # timing not usable: the player still works, just without highlighting
    return [(round(starts[a], 2), round(ends[b - 1], 2)) if b > a else None for a, b in spans]
