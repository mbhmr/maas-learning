"""Text to speech with the ElevenLabs REST API (no SDK: its file paths break on Windows)."""
import os

import httpx
from dotenv import load_dotenv

from .llm import ENV, log_usage

# "George", a premade ElevenLabs voice. Override with ELEVENLABS_VOICE_ID.
DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"


def speak(text, mp3_path):
    load_dotenv(ENV)
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is missing in .env.")
    voice = os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE
    model = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key},
        json={"text": text, "model_id": model},
        timeout=120,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs error {r.status_code}: {r.text[:300]}")
    mp3_path.write_bytes(r.content)
    log_usage({"service": "elevenlabs", "step": "tts", "model": model, "characters": len(text)})
