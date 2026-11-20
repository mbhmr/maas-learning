"""The only place that talks to OpenAI. Every call is logged to output/usage.jsonl."""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV)
OUTPUT = Path(__file__).resolve().parent.parent / "output"
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")            # bulk work: merging, facts (many calls)
SCRIPT_MODEL = os.getenv("OPENAI_SCRIPT_MODEL", "gpt-5.4-mini")  # one call per listener: writing has to sound good

# USD per million tokens (input, output). Reference list prices, check before the pitch.
PRICES = {"gpt-4.1-mini": (0.40, 1.60), "gpt-5.4-mini": (0.75, 4.50), "gpt-5.4-nano": (0.20, 1.25)}  # checked 20.11.
# Cached input (the provider repeats a prompt start of 1,024+ tokens it saw minutes ago): 10 % of the input price on
# gpt-5.4, 25 % on gpt-4.1 (checked 21.11.). Flex (slower, may be refused when busy): half price on gpt-5 models;
# gpt-4.1-mini refuses flex (400, tested 21.11.).
CACHED_SHARE = {"gpt-4.1-mini": 0.25, "gpt-5.4-mini": 0.10, "gpt-5.4-nano": 0.10}
FLEX_SHARE = 0.5
# "flex" for work nobody waits for (the overnight run of all editions). Unset: the default tier.
SERVICE_TIER = os.getenv("OPENAI_SERVICE_TIER") or None

_client = None


def _get_client():
    global _client
    if _client is None:
        load_dotenv(ENV)  # read again: keys may have been added while the app was running
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is missing. Copy .env.example to .env and fill it in.")
        _client = OpenAI(timeout=60, max_retries=2)  # a hung call must not block a listener for minutes
    return _client


def log_usage(entry):
    OUTPUT.mkdir(exist_ok=True)
    entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), **entry}
    with (OUTPUT / "usage.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def cost_usd(model, input_tokens, output_tokens, cached_tokens=0, tier=None):
    """What one call costs at list price: cached input at its share, flex at half. None for an unknown model."""
    if model not in PRICES:
        return None
    price_in, price_out = PRICES[model]
    fresh = input_tokens - cached_tokens
    usd = (fresh * price_in + cached_tokens * price_in * CACHED_SHARE.get(model, 1) + output_tokens * price_out) / 1e6
    return usd * (FLEX_SHARE if tier == "flex" else 1)


def ask_json(step, system, user, schema, max_tokens=4000, model=None, timeout=None):
    """One chat call with a strict JSON schema. Returns the parsed object.

    max_tokens stops a call that loops (once a fact call wrote 66,000 characters of repeated JSON).
    """
    model = model or MODEL
    # GPT-5 models reason first: they take no temperature and count their thinking in the token limit
    extra = ({"reasoning_effort": "low", "max_completion_tokens": max_tokens + 4000} if model.startswith("gpt-5")
             else {"temperature": 0, "max_tokens": max_tokens})
    tier = SERVICE_TIER if model.startswith("gpt-5") else None
    if tier:
        extra["service_tier"] = tier
        timeout = timeout or 900  # flex answers later when the provider is busy; nobody is waiting
    client = _get_client() if timeout is None else _get_client().with_options(timeout=timeout)
    request = dict(model=model, **extra,
                   messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                   response_format={"type": "json_schema", "json_schema": {"name": step, "strict": True,
                                                                           "schema": schema}})
    try:
        resp = client.chat.completions.create(**request)
    except Exception as e:  # flex may be refused when busy (429 resource unavailable): pay full price instead
        if not tier or getattr(e, "status_code", None) != 429:
            raise
        request.pop("service_tier")
        resp = client.chat.completions.create(**request)
    u = resp.usage
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", None) or 0
    reasoning = getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", None) or 0
    served = getattr(resp, "service_tier", None)
    cost = cost_usd(model, u.prompt_tokens, u.completion_tokens, cached, served)
    log_usage({"service": "openai", "step": step, "model": model,
               "input_tokens": u.prompt_tokens, "output_tokens": u.completion_tokens, "usd": cost,
               "cached_tokens": cached, "reasoning_tokens": reasoning, "tier": served})
    if resp.choices[0].finish_reason == "length":
        raise RuntimeError(f"{step}: answer cut off at {max_tokens} tokens")
    return json.loads(resp.choices[0].message.content)
