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


_UNITS = {w: n for n, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                     "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_UNITS.update({w: n for n, w in enumerate("_ first second third fourth fifth sixth seventh eighth ninth tenth eleventh "
                                          "twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth "
                                          "nineteenth".split()) if n})
_TENS = {w: 10 * n for n, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if n > 1}
_TENS.update({"twentieth": 20, "thirtieth": 30})


def _word_value(w):
    parts = w.lower().split("-")
    if len(parts) <= 2 and all(p in _UNITS or p in _TENS for p in parts):
        return sum(_UNITS.get(p, 0) + _TENS.get(p, 0) for p in parts)
    return None


def spelled_to_digits(text):
    """English speech recognition writes "zero point three percent", "one hundred and thirty billion",
    "twenty twenty-two": number words become digits so the figures can be compared. Scale words above a
    thousand (million, billion, trillion) stay words; the number parser reads them as it does in the script."""
    tokens = re.findall(r"\d+(?:[.,]\d+)*[A-Za-z]*|[A-Za-z]+(?:-[A-Za-z]+)*|\S", text)  # "16th", "4.0" stay whole
    out, i = [], 0
    while i < len(tokens):
        v = _word_value(tokens[i])
        if v is None:
            out.append(tokens[i])
            i += 1
            continue
        total, current = 0, v
        i += 1
        while i < len(tokens):
            w, nxt = tokens[i].lower(), _word_value(tokens[i])
            if w == "hundred" and 0 < current < 10:
                current *= 100
            elif w == "thousand" and current:
                total, current = total + current * 1000, 0
            elif w == "and" and i + 1 < len(tokens) and _word_value(tokens[i + 1]) is not None and current >= 100:
                pass
            elif nxt is not None and (
                    (current % 100 == 0 and (current or total)) or               # "one hundred | thirty"
                    (nxt < 10 and current % 100 >= 20 and current % 10 == 0)):  # "twenty | five" (not "twenty | twenty-two")
                current += nxt
            else:
                break
            i += 1
        value = str(total + current)
        if i + 1 < len(tokens) and tokens[i].lower() == "point" and _word_value(tokens[i + 1]) is not None:
            i += 1
            digits = ""
            while i < len(tokens) and _word_value(tokens[i]) is not None and _word_value(tokens[i]) < 10:
                digits += str(_word_value(tokens[i]))
                i += 1
            value += "." + digits
        out.append(value)
    return " ".join(out)


# German and Dutch write numbers as one compound word: "dreiundachtzig", "achthundertfünfundzwanzig",
# "drieëntachtig", "achthonderdvijfentwintig"; decimals as "null Komma drei", "nul komma drie".
_SMALL = {
    "de": dict(zip("null ein eins eine zwei drei vier fünf sechs sieben acht neun zehn elf zwölf dreizehn vierzehn "
                   "fünfzehn sechzehn siebzehn achtzehn neunzehn".split(),
                   [0, 1, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19])),
    "nl": dict(zip("nul een één twee drie vier vijf zes zeven acht negen tien elf twaalf dertien veertien vijftien "
                   "zestien zeventien achttien negentien".split(), list(range(0, 2)) + list(range(1, 20)))),
}
_TENS_WORDS = {
    "de": dict(zip("zwanzig dreißig dreissig vierzig fünfzig sechzig siebzig achtzig neunzig".split(),
                   [20, 30, 30, 40, 50, 60, 70, 80, 90])),
    "nl": dict(zip("twintig dertig veertig vijftig zestig zeventig tachtig negentig".split(), range(20, 100, 10))),
}
_GLUE = {"de": ("hundert", "tausend", "und", "komma"), "nl": ("honderd", "duizend", "en", "komma")}
_HALF = {"de": {"anderthalb": "1,5", "eineinhalb": "1,5"}, "nl": {"anderhalf": "1,5", "anderhalve": "1,5"}}


def _compound(w, lang):
    """Value of one German or Dutch number word, or None."""
    small, tens = _SMALL[lang], _TENS_WORDS[lang]
    hundred, thousand, und, _ = _GLUE[lang]
    w = w.lower().replace("ë", "e")
    if not w:
        return 0
    if w in small:
        return small[w]
    if w in tens:
        return tens[w]
    for scale, mult in ((thousand, 1000), (hundred, 100)):
        if scale in w:
            left, right = w.split(scale, 1)
            lv = _compound(left, lang) if left else 1
            rv = _compound(right, lang)
            return None if lv is None or rv is None else lv * mult + rv
    if und in w:
        left, right = w.rsplit(und, 1)
        lv, rv = _compound(left, lang), _compound(right, lang)
        if lv is not None and rv is not None and lv < 10 and rv in tens.values():
            return lv + rv
    return None


def compound_to_digits(text, lang):
    for word, value in _HALF[lang].items():
        text = re.sub(rf"\b{word}\b", value, text, flags=re.I)
    tokens = re.findall(r"\d+(?:[.,]\d+)*|\w+|\S", text)  # "4,0" stays one number
    out, i = [], 0
    while i < len(tokens):
        v = _compound(tokens[i], lang) if tokens[i].isalpha() else None
        if v is None:
            out.append(tokens[i])
            i += 1
            continue
        value = str(v)
        i += 1
        if i + 1 < len(tokens) and tokens[i].lower() == "komma":
            digits = ""
            i += 1
            while i < len(tokens) and tokens[i].isalpha() and (_compound(tokens[i], lang) if _compound(tokens[i], lang)
                                                               is not None else 99) < 10:  # "null" is a digit too
                digits += str(_compound(tokens[i], lang))
                i += 1
            value += "," + digits if digits else ""
        out.append(value)
    return " ".join(out)


def _heard_numbers(text, lang):
    if lang == "en":
        # "twenty-twenty-two" is a year said as two numbers
        text = re.sub(r"\b([a-z]+ty)-([a-z]+ty-[a-z]+)\b", r"\1 \2", text, flags=re.I)
        text = re.sub(r"\ba (hundred|thousand)\b", r"one \1", text, flags=re.I)  # "a hundred and twenty"
        text = re.sub(r"\b([a-z-]+|\d+) and a half\b",  # "one and a half percent" is 1.5
                      lambda m: f"{(_word_value(m[1]) if not m[1].isdigit() else int(m[1]))}.5"
                      if m[1].isdigit() or _word_value(m[1]) is not None else m[0], text, flags=re.I)
        text = spelled_to_digits(text)
    elif lang in _SMALL:
        text = compound_to_digits(text, lang)
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
