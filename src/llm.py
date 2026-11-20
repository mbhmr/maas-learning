"""The only place that talks to OpenAI. Every call is logged to output/usage.jsonl."""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
OUTPUT = Path(__file__).resolve().parent.parent / "output"
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# USD per million tokens (input, output). Reference list prices, check before the pitch.
PRICES = {"gpt-4.1-mini": (0.40, 1.60), "gpt-4.1-nano": (0.10, 0.40), "gpt-4o-mini": (0.15, 0.60)}

_client = None


def _get_client():
    global _client
    if _client is None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is missing. Copy .env.example to .env and fill it in.")
        _client = OpenAI()
    return _client


def log_usage(entry):
    OUTPUT.mkdir(exist_ok=True)
    entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), **entry}
    with (OUTPUT / "usage.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def ask_json(step, system, user, schema):
    """One chat call with a strict JSON schema. Returns the parsed object."""
    resp = _get_client().chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": step, "strict": True, "schema": schema}},
    )
    u = resp.usage
    price_in, price_out = PRICES.get(MODEL, (None, None))
    cost = None if price_in is None else (u.prompt_tokens * price_in + u.completion_tokens * price_out) / 1e6
    log_usage({"service": "openai", "step": step, "model": MODEL,
               "input_tokens": u.prompt_tokens, "output_tokens": u.completion_tokens, "usd": cost})
    return json.loads(resp.choices[0].message.content)
