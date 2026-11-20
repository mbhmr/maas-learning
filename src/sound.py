"""Sound for the player, all from ElevenLabs (REST via httpx, like tts.py).

  make_jingle   Music API: a 5 second instrumental intro, played before the briefing (product feel)
  make_chimes   Sound Effects API: "verified" after each checked claim, "conflict" where sources disagree
  speak_quote   Text to speech: reads the original source quote aloud on click (trust), cached per quote

Jingle and chimes are made once (python -m src.sound) and then served as files. Every paid call is logged
to output/usage.jsonl.
"""
import hashlib
import os

import httpx
from dotenv import load_dotenv
from mutagen.mp3 import MP3

from .llm import ENV, OUTPUT, log_usage

API = "https://api.elevenlabs.io/v1"
SOUND = OUTPUT / "sound"
QUOTE_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # George, a premade voice
QUOTE_MODEL = "eleven_flash_v2_5"     # the cheapest model, enough for one calm sentence
# Calm and plain: the quote is evidence, not a show. Higher stability = steadier voice, style 0 = no acting.
QUOTE_SETTINGS = {"stability": 0.7, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True, "speed": 0.95}

# Licence (music terms, Exhibit A, as of 09.10.2026, read 20.11.): every plan allows online and offline commercial
# use except film, TV, radio and studio games, so a demo or pitch video is fine. Free plan: credit required
# ("Created in collaboration with ElevenLabs") and no Music API; paid plans: no credit required.
JINGLE_PROMPT = ("Short energetic modern morning news intro jingle, upbeat electronic pop, bright synth stabs, "
                 "punchy drums, rising build, confident ending on a clean final hit. Instrumental, no vocals.")
CHIMES = {
    "verified": ("Soft short positive confirmation chime, single bright bell tone, gentle, clean, "
                 "user interface success sound", 0.6),
    "conflict": ("Neutral two-note attention tone, a calm mid pitched note followed by a slightly lower note, "
                 "soft marimba, clean user interface notification, not alarming", 1.0),
}


def _key():
    load_dotenv(ENV)
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is missing in .env.")
    return key


def _post(path, body, timeout=120):
    r = httpx.post(f"{API}{path}", params={"output_format": "mp3_44100_128"},
                   headers={"xi-api-key": _key()}, json=body, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs error {r.status_code} on {path}: {r.text[:300]}")
    return r.content


def duration(path):
    """Real length of an MP3 in seconds, read from the file."""
    return round(MP3(str(path)).info.length, 2)


def make_jingle(path=SOUND / "jingle.mp3", seconds=5):
    """Instrumental intro via the Music API. Returns its measured duration in seconds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # music_length_ms must be 3000 to 600000; force_instrumental guarantees no vocals (docs checked 20.11.)
    audio = _post("/music", {"prompt": JINGLE_PROMPT, "music_length_ms": int(seconds * 1000),
                             "force_instrumental": True, "model_id": "music_v1"}, timeout=300)
    path.write_bytes(audio)
    real = duration(path)
    log_usage({"service": "elevenlabs", "step": "jingle", "model": "music_v1", "seconds": real})
    return real


def make_chimes(folder=SOUND):
    """verified.mp3 and conflict.mp3 via Sound Effects. Returns {name: measured seconds}."""
    folder.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, (prompt, seconds) in CHIMES.items():
        # duration_seconds must be 0.5 to 30; higher prompt_influence = closer to the prompt (docs checked 20.11.)
        audio = _post("/sound-generation", {"text": prompt, "duration_seconds": seconds, "prompt_influence": 0.6,
                                            "model_id": "eleven_text_to_sound_v2"})
        path = folder / f"{name}.mp3"
        path.write_bytes(audio)
        result[name] = duration(path)
        log_usage({"service": "elevenlabs", "step": "sfx", "model": "eleven_text_to_sound_v2",
                   "name": name, "seconds": result[name]})
    return result


def speak_quote(quote, lang="en"):
    """MP3 of the verbatim quote in a calm voice. Same quote and language = same file, no second cost."""
    folder = SOUND / "quotes"
    path = folder / f"{hashlib.sha1(f'{lang}|{quote}'.encode('utf-8')).hexdigest()}.mp3"
    if path.exists():
        return path
    folder.mkdir(parents=True, exist_ok=True)
    audio = _post(f"/text-to-speech/{QUOTE_VOICE}", {"text": quote, "model_id": QUOTE_MODEL,
                                                     "language_code": lang, "voice_settings": QUOTE_SETTINGS})
    path.write_bytes(audio)
    log_usage({"service": "elevenlabs", "step": "quote", "model": QUOTE_MODEL, "characters": len(quote)})
    return path


if __name__ == "__main__":
    # python -m src.sound  makes jingle and chimes (3 paid calls) if they are missing; delete a file to remake it
    if not (SOUND / "jingle.mp3").exists():
        print("jingle", make_jingle(), "s")
    if not all((SOUND / f"{n}.mp3").exists() for n in CHIMES):
        print(make_chimes())
    for f in sorted(SOUND.glob("*.mp3")):
        print(f.name, duration(f), "s")
