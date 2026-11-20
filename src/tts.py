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

# "Danielle", a premade ElevenLabs voice (Matthias, 20.11.: a woman's voice, the same as in the pitch video).
# Override with ELEVENLABS_VOICE_ID.
DEFAULT_VOICE = "FVQMzxJGPUBtfz1Azdoy"  # Danielle, Matthias' pick for the pitch video (20.11.); before: Jessica cgSgspJ2msm6clMCkdW9
# eleven_v3 knows three stability steps: 0.0 Creative, 0.5 Natural, 1.0 Robust. Creative sounded unstable,
# Natural keeps the voice steady and still follows the audio tags.
VOICE_SETTINGS = {"eleven_v3": {"stability": 0.5, "similarity_boost": 0.75},
                  # v4 knows only these two; lower stability sounds livelier (tested for the pitch video, 20.11.)
                  "eleven_v4": {"stability": 0.35, "similarity_boost": 0.8},
                  "other": {"stability": 0.25, "similarity_boost": 0.75, "style": 0.85, "use_speaker_boost": True,
                            "speed": 1.12}}
# eleven_v3 audio tags: how a line is said, never words. They go into the speech only, not into the transcript.
TAG = {"excited": "[excited]", "cheerful": "[cheerfully]", "": ""}

# Only for the ear: the transcript keeps the written form, the voice gets the spoken one.
SPOKEN = {
    "en": [(r"\bUSD/JPY\b", "dollar yen"), (r"\bEUR/USD\b", "euro dollar"), (r"\bGBP/USD\b", "pound dollar"),
           (r"\b(m/m|MoM)\b", "month on month"), (r"\b(y/y|YoY)\b", "year on year"), (r"\bbps?\b", "basis points"),
           (r"\bQ1\b", "first quarter"), (r"\bQ2\b", "second quarter"), (r"\bQ3\b", "third quarter"),
           (r"\bQ4\b", "fourth quarter"), (r"%", " percent"), (r"\bCEO\b", "C E O")],
    "de": [(r"\bUSD/JPY\b", "Dollar Yen"), (r"\bEUR/USD\b", "Euro Dollar"), (r"\bbps?\b", "Basispunkte"),
           (r"\bQ([1-4])\b", r"\1. Quartal"), (r"%", " Prozent"), (r"\bggü\.", "gegenüber")],
    "nl": [(r"\bUSD/JPY\b", "dollar yen"), (r"\bEUR/USD\b", "euro dollar"), (r"\bbps?\b", "basispunten"),
           (r"\bQ([1-4])\b", r"kwartaal \1"), (r"%", " procent")],
}


def spoken_form(text, lang):
    for pattern, repl in SPOKEN.get(lang, []):
        text = re.sub(pattern, repl, text)
    return re.sub(r"\s{2,}", " ", text)


def _spoken_words(text, lang):
    """The spoken form built word by word, so every written word knows where it sits in the speech.

    Returns (spoken text, [(spoken_start, spoken_end, written_start, written_end)]). The rules in SPOKEN only touch
    single words ("5%", "USD/JPY", "Q3"), so word by word gives the same speech as the whole line at once.
    """
    spoken, words = "", []
    for m in re.finditer(r"\S+", text):
        w = spoken_form(m.group(), lang).strip()
        if not w:
            continue
        spoken += " " if spoken else ""
        words.append((len(spoken), len(spoken) + len(w), m.start(), m.end()))
        spoken += w
    return spoken, words


def _layout(parts, tags):
    """The text sent to the voice and the (start, end) character span of every part, tags excluded."""
    text, spans = "", []
    for i, (p, tag) in enumerate(zip(parts, tags)):
        text += "\n\n" if i else ""  # a paragraph break gives the voice a short pause between lines
        if tag and p:
            text += tag + " "
        spans.append((len(text), len(text) + len(p)))
        text += p
    return text, spans


def speak(parts, mp3_path, lang="en", tags=None, words=None):
    """Speaks the parts (one per transcript line) as one MP3. Returns [(start_s, end_s)] per part.

    tags: per part a key of TAG ("excited", "cheerful" or ""), the delivery of that line.
    words: an empty list to receive, per part, [[start_s, end_s, char_start, char_end], ...]: when each written
    word of the transcript line is spoken, so the player can highlight the word being read. None if not usable.
    """
    load_dotenv(ENV)
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is missing in .env.")
    voice = os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE
    model = os.getenv("ELEVENLABS_MODEL", "eleven_v4")
    laid = [_spoken_words(p, lang) for p in parts]
    spoken = [sp for sp, _ in laid]
    tags = (list(tags or []) + [""] * len(parts))[:len(parts)]
    tags = [TAG.get(t or "", "") if model in ("eleven_v3", "eleven_v4") else "" for t in tags]
    text, spans = _layout(spoken, tags)
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key},
        json={"text": text, "model_id": model, "voice_settings": VOICE_SETTINGS.get(model, VOICE_SETTINGS["other"])},
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
        # the alignment may leave the tags out: then it matches the text without them
        text, spans = _layout(spoken, [""] * len(spoken))
        if len(starts) != len(text):
            if words is not None:
                words.extend([None] * len(parts))
            return [None] * len(parts)  # timing not usable: the player still works, just without highlighting
    if words is not None:
        for (a, _), (_, ws) in zip(spans, laid):
            words.append([[round(starts[a + s0], 2), round(ends[a + s1 - 1], 2), w0, w1] for s0, s1, w0, w1 in ws])
    return [(round(starts[a], 2), round(ends[b - 1], 2)) if b > a else None for a, b in spans]
