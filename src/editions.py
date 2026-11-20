"""Shared editions: many listeners, one news body.

A listener profile maps to an edition key: language, length bucket, depth bucket and one interest segment.
Every listener with the same key gets the same checked news body (claims, context, sources, body audio); only the
greeting with their name is made per listener. So at 100,000 listeners the expensive part (story selection,
script, content check, about 1,000 characters of voice) is paid once per edition, not once per listener.

The segment comes from a small model with a fixed list as output (temperature 0, cached per description):
wildcard descriptions arrive in English, German or Dutch and in any wording, keyword rules would miss most of them.

Files, per news day:
  output/<day>/editions/<key>/briefing.json   the edition body (claims with sources, start/end inside body.mp3)
  output/<day>/editions/<key>/body.mp3        the body audio, made once
  output/<day>/editions/<key>/listeners.json  hashes of the profiles that mapped to this edition (the count)
  output/greetings/<hash>.mp3 and .json       a spoken greeting, same text = same file
  output/segments.json                        description hash -> segment
A listener's own briefing.mp3 is greeting + body, MP3 frames joined, body timestamps shifted by the greeting.
"""
import hashlib
import json
import threading
from pathlib import Path

from .briefing import build_briefing
from .llm import ask_json
from .script import GREETING, SIGN_OFF, check_host
from .tts import speak

# segment -> (who the edition is written for, label per language for the greeting)
SEGMENTS = {
    "markets-fx": ("A markets listener: central banks, interest rates, inflation and macro data, currency moves, and "
                   "the biggest market-moving company news.",
                   {"en": "markets and currencies", "de": "Märkte und Währungen", "nl": "markten en valuta"}),
    "stocks-tech": ("A stock-market listener: company earnings and deals, tech and AI companies, chipmakers, big "
                    "share moves, and the macro numbers that move stocks.",
                    {"en": "stocks and tech", "de": "Aktien und Tech", "nl": "aandelen en tech"}),
    "crypto": ("A crypto listener: bitcoin and other crypto assets, crypto companies and regulation, and the macro "
               "numbers that move them.",
               {"en": "crypto", "de": "Krypto", "nl": "crypto"}),
    "energy-commodities": ("A commodities listener: oil, gas, gold and energy prices, energy companies and the "
                           "geopolitics behind supply.",
                           {"en": "energy and commodities", "de": "Energie und Rohstoffe",
                            "nl": "energie en grondstoffen"}),
    "personal-finance": ("A private investor with little time: the big economic and market stories of the day in "
                         "plain language, what happened and why it matters, few numbers.",
                         {"en": "the big money stories", "de": "die großen Geldthemen", "nl": "de grote geldverhalen"}),
    "world": ("Someone who just wants to know what happened in the world: politics, world events, big business and "
              "tech stories, crime and culture. Not an investor, no market jargon, at most one number per story.",
              {"en": "world news", "de": "Weltgeschehen", "nl": "wereldnieuws"}),
}
LENGTHS = (30, 60, 90, 120, 180, 300)  # seconds; a request goes to the nearest, a tie to the shorter
DEPTHS = {"dense": "dense, every figure with its period", "medium": "medium",
          "simple": "simple, explain terms in a few words"}  # the three choices of the player
DENSE_WORDS = ("dense", "every figure", "expert", "detail", "deep", "dicht", "ausführlich", "experte", "gedetailleerd")
SIMPLE_WORDS = ("simple", "explain", "plain", "beginner", "easy", "einfach", "erklär", "eenvoudig", "uitleg")
EDITION_NAME = {"en": "listener", "de": "Hörer", "nl": "luisteraar"}  # the address the edition script is written to
GREET = {"en": ("Good morning, {}!", "Your news: {}."), "de": ("Guten Morgen, {}!", "Deine Nachrichten: {}."),
         "nl": ("Goedemorgen, {}!", "Je nieuws: {}.")}
GREETING_WORDS = 14

_lock = threading.Lock()  # small file updates (segments.json, listeners.json)
_edition_locks = {}       # edition folder -> lock: one edition is written once, other listeners wait for it


def _hash(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- profile -> edition key

SEGMENT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["segment"],
                  "properties": {"segment": {"type": "string", "enum": list(SEGMENTS)}}}
SEGMENT_SYSTEM = "Assign the listener described by the user to exactly ONE news edition, the one they would " \
                 "want most. The description may be in any language. Editions:\n" + \
                 "\n".join(f"- {k}: {d}" for k, (d, _) in SEGMENTS.items())


def classify(description, cache_path):
    """The interest segment of a listener description. One small-model call per new description, then cached."""
    h = _hash(" ".join(description.lower().split()))
    with _lock:
        cache = _read(cache_path, {})
    if h in cache:
        return cache[h]
    segment = ask_json("edition-segment", SEGMENT_SYSTEM, description, SEGMENT_SCHEMA, max_tokens=50)["segment"]
    if segment not in SEGMENTS:  # the schema forbids it, the code makes sure
        raise RuntimeError(f"unknown segment {segment!r}")
    with _lock:
        cache = _read(cache_path, {})
        cache[h] = segment
        _write(cache_path, cache)
    return segment


def length_bucket(seconds):
    return min(LENGTHS, key=lambda b: (abs(b - seconds), b))


def depth_bucket(depth):
    low = (depth or "").lower()
    if any(w in low for w in DENSE_WORDS):
        return "dense"
    if any(w in low for w in SIMPLE_WORDS):
        return "simple"
    return "medium"


def edition_key(profile, segment):
    """('en-90s-medium-markets-fx', parts). Same key = same news body."""
    parts = {"language": profile["language"], "seconds": length_bucket(profile["seconds"]),
             "depth": depth_bucket(profile["depth"]), "segment": segment}
    return f"{parts['language']}-{parts['seconds']}s-{parts['depth']}-{segment}", parts


# ---------------------------------------------------------------- MP3 frames

_BITRATES = {1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
             2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}  # by version bits


def _frame(data, i):
    """(length, samples, sample_rate) of the MPEG layer III frame at i, or None."""
    if i + 4 > len(data) or data[i] != 0xFF or data[i + 1] & 0xE0 != 0xE0:
        return None
    version, layer = (data[i + 1] >> 3) & 3, (data[i + 1] >> 1) & 3
    br_idx, sr_idx, pad = data[i + 2] >> 4, (data[i + 2] >> 2) & 3, (data[i + 2] >> 1) & 1
    if version == 1 or layer != 1 or br_idx in (0, 15) or sr_idx == 3:
        return None
    rate = _RATES[version][sr_idx]
    kbps = _BITRATES[1 if version == 3 else 2][br_idx]
    if version == 3:
        return 144000 * kbps // rate + pad, 1152, rate
    return 72000 * kbps // rate + pad, 576, rate


def mp3_frames(data):
    """The audio frames of an MP3 without ID3 tags and without the Xing/Info header frame, and their length in
    seconds. Joined files must not carry an Info frame: a browser would read the total length from the first one."""
    start = 0
    if data[:3] == b"ID3":
        size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
        start = 10 + size + (10 if data[5] & 0x10 else 0)
    end = len(data) - 128 if data[-128:-125] == b"TAG" else len(data)
    data = data[start:end]
    i, out, seconds = 0, [], 0.0
    while (f := _frame(data, i)) is not None:
        length, samples, rate = f
        frame = data[i:i + length]
        if i == 0 and (b"Xing" in frame[:64] or b"Info" in frame[:64]):
            i += length
            continue
        if len(frame) < length:
            break  # cut-off last frame
        out.append(frame)
        seconds += samples / rate
        i += length
    if not out:
        raise ValueError("no MP3 audio frames found")
    return b"".join(out), seconds


# ---------------------------------------------------------------- the edition body, once per key

def _tags(claims):
    """Delivery per line, as build_briefing does it: energy on the first line of a story, cheerful sign-off."""
    tags, prev = [], None
    for c in claims:
        tags.append("excited" if c["kind"] == "claim" and prev != "claim" else "cheerful" if c["kind"] == "host"
                    else "")
        prev = c["kind"]
    return tags


def edition(day_folder, key, parts, stories, facts, audio):
    """The edition body for this key: written on first use (one script, one content check), its audio spoken on the
    first listener who wants audio. Later listeners only read it."""
    folder = Path(day_folder) / "editions" / key
    with _lock:
        lock = _edition_locks.setdefault(str(folder), threading.Lock())
    with lock:
        path = folder / "briefing.json"
        body = _read(path, None)
        if body is None:
            lang = parts["language"]
            profile = {"name": EDITION_NAME[lang], "language": lang, "seconds": parts["seconds"],
                       "depth": DEPTHS[parts["depth"]], "description": SEGMENTS[parts["segment"]][0]}
            built = build_briefing(profile, stories, facts, folder, audio=False)
            claims = [c for c in built["claims"] if c["text"]]
            if claims and claims[0]["kind"] == "host":
                claims = claims[1:]  # the greeting is per listener
            for c in claims:  # the model's sign-off was written to "listener": keep it only if it does not say so
                if c["kind"] == "host" and EDITION_NAME[lang].lower() in c["text"].lower():
                    c["text"] = SIGN_OFF[lang]
            for n, c in enumerate(claims):
                c["id"], c["start"], c["end"] = f"c{n}", None, None
            body = {"key": key, **parts, "profile": profile, "claims": claims, "dropped": built["dropped"],
                    "stories": built["stories"], "audio": None}
            _write(path, body)
        if audio and not (folder / "body.mp3").exists():
            times = speak([c["text"] for c in body["claims"]], folder / "body.mp3", parts["language"],
                          tags=_tags(body["claims"]))
            for c, t in zip(body["claims"], times):
                c["start"], c["end"] = t if t else (None, None)
            body["audio"] = "body.mp3"
            _write(path, body)
        return body


def listener_count(day_folder, key):
    return len(_read(Path(day_folder) / "editions" / key / "listeners.json", []))


def _register(day_folder, key, profile):
    path = Path(day_folder) / "editions" / key / "listeners.json"
    with _lock:
        seen = _read(path, [])
        h = _hash(profile)[:16]
        if h not in seen:
            seen.append(h)
            _write(path, seen)
        return len(seen)


# ---------------------------------------------------------------- per listener: greeting + body

def greeting_text(profile, segment):
    """'Good morning, Anna! Your news: markets and currencies.' Fixed words around the name, checked like any
    host line; a name that fails the check (digits, too long) is left out."""
    lang = profile["language"]
    hello, topic = GREET[lang]
    label = SEGMENTS[segment][1][lang]
    name = profile["name"].strip()
    named = [f"{hello.format(name)} {topic.format(label)}"] if name and name.lower() != "listener" else []
    for text in named + [f"{GREETING[lang]} {topic.format(label)}"]:
        ok, _ = check_host(text, lang, GREETING_WORDS)
        if ok:
            return ok
    return GREETING[lang]


def _greeting_audio(cache_dir, text, lang):
    """(mp3 frames, seconds, (start, end)) of a spoken greeting. Same text and language = same file, paid once."""
    mp3 = Path(cache_dir) / f"{_hash([lang, text])[:20]}.mp3"
    meta = mp3.with_suffix(".json")
    if not mp3.exists() or not meta.exists():
        mp3.parent.mkdir(parents=True, exist_ok=True)
        (t,) = speak([text], mp3, lang, tags=["excited"])
        _write(meta, {"text": text, "lang": lang, "timing": t})
    frames, seconds = mp3_frames(mp3.read_bytes())
    return frames, seconds, _read(meta, {}).get("timing")


def build_listener(day_folder, profile, out_dir, stories, facts, audio=True):
    """Writes the listener's briefing.json (and briefing.mp3 = greeting + edition body) and returns it."""
    day_folder, out_dir = Path(day_folder), Path(out_dir)
    segment = classify(profile["description"], day_folder.parent / "segments.json")
    key, parts = edition_key(profile, segment)
    body = edition(day_folder, key, parts, stories, facts, audio)
    _register(day_folder, key, profile)
    greeting = {"text": greeting_text(profile, segment), "sources": [], "factIds": [], "kind": "host",
                "start": None, "end": None}
    claims = [greeting] + [dict(c) for c in body["claims"]]
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {"profile": profile, "mode": "edition", "editionKey": key, "audioPath": None, "claims": claims,
              "dropped": body["dropped"], "stories": body["stories"]}
    if audio:
        frames, offset, timing = _greeting_audio(day_folder.parent / "greetings", greeting["text"],
                                                 profile["language"])
        body_frames, _ = mp3_frames((day_folder / "editions" / key / "body.mp3").read_bytes())
        if timing:
            greeting["start"], greeting["end"] = timing
        for c in claims[1:]:
            if c["start"] is not None:
                c["start"], c["end"] = round(c["start"] + offset, 2), round(c["end"] + offset, 2)
        (out_dir / "briefing.mp3").write_bytes(frames + body_frames)
        result["audioPath"] = str(out_dir / "briefing.mp3")
    for n, c in enumerate(claims):
        c["id"] = f"c{n}"
    _write(out_dir / "briefing.json", result)
    return result


def info(day_folder, key):
    """What the player shows: 'shared edition, markets and currencies, 1,234 listeners'."""
    body = _read(Path(day_folder) / "editions" / key / "briefing.json", {})
    return {"key": key, "segment": body.get("segment"), "language": body.get("language"),
            "seconds": body.get("seconds"), "depth": body.get("depth"),
            "label": SEGMENTS.get(body.get("segment"), (None, {}))[1].get(body.get("language")),
            "listeners": listener_count(day_folder, key)}
