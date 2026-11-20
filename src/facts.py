"""Facts per story: the model proposes them, the code checks them against the articles.

A fact survives only if its quote is really in the cited article and the number
is really in the quote. If two sources give different values, the fact is
marked as a conflict instead of silently picking one.
"""
import re

from .llm import ask_json

MAX_CHARS = 6000  # per article sent to the model; key facts sit near the top


def norm(text):
    """Lowercase, unify quotes and dashes, keep letters, digits and . , % $ ' - only."""
    text = text.lower()
    for a, b in (("’", "'"), ("‘", "'"), ("–", "-"), ("—", "-"), ("“", '"'), ("”", '"')):
        text = text.replace(a, b)
    text = re.sub(r"[^\w%$.,'-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Numbers spoken as words also count, so "doubled" or "a quarter" cannot slip past the checker.
# "one"/"ein" are left out on purpose: they are mostly articles ("one of the", "ein Anstieg").
_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    # scale words: "23 million" vs "23 billion" must not pass as the same figure
    "thousand": 1e3, "million": 1e6, "millions": 1e6, "billion": 1e9, "billions": 1e9, "trillion": 1e12,
    "tausend": 1e3, "million": 1e6, "millionen": 1e6, "milliarde": 1e9, "milliarden": 1e9, "billion": 1e9,
    "elf": 11, "dreizehn": 13, "fünfzehn": 15, "dreißig": 30, "vierzig": 40, "fünfzig": 50,
    "half": 0.5, "halved": 0.5, "twice": 2, "double": 2, "doubled": 2,
    "triple": 3, "tripled": 3, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7,
    "acht": 8, "neun": 9, "zehn": 10, "zwölf": 12, "zwanzig": 20, "hundert": 100, "halb": 0.5,
    "halbiert": 0.5, "hälfte": 0.5, "doppelt": 2, "verdoppelt": 2,
    "verdreifacht": 3, "twee": 2, "drie": 3, "vier": 4, "tien": 10, "helft": 0.5, "verdubbeld": 2,
    # written scale abbreviations: "5,28 Mio. Barrel", "3 Mrd. Euro", "12 mln", "4 mld" (nl), "milliard" from "3bn"
    "mio": 1e6, "mrd": 1e9, "tsd": 1e3, "miljoen": 1e6, "miljoenen": 1e6, "miljard": 1e9, "miljarden": 1e9,
    "mln": 1e6, "mld": 1e9, "duizend": 1e3, "milliard": 1e9,
}
# German and Dutch "Billion"/"biljoen" is 10^12, the English billion is 10^9
_WORDS_DE_NL = {**_WORDS, "billion": 1e12, "billionen": 1e12, "bio": 1e12, "biljoen": 1e12, "biljoenen": 1e12}


# Fractions only as fractions, not "third quarter" (a period) or "Viertel" in "Stadtviertel".
_FRACTIONS = [(r"\b(a|one) quarter of\b", 0.25), (r"\b(a|one) third of\b", 1 / 3), (r"\bein viertel\b", 0.25),
              (r"\bein drittel\b", 1 / 3), (r"\btwo thirds\b", 2 / 3), (r"\bzwei drittel\b", 2 / 3)]
# Numbers that are part of a name, never a figure: S&P 500, Nasdaq 100, Q3, G7, Nikkei 225 ...
_NAMES = re.compile(r"\b(s&p\s?500|nasdaq(\s?100)?|ftse\s?\d+|dax\s?\d+|stoxx\s?\d+|nikkei\s?225|russell\s?\d+|"
                    r"cac\s?40|ibex\s?35|aex|q[1-4]|h[12]|g\d{1,2}|covid-19|f-\d+|\d+(st|nd|rd|th))\b", re.I)


def numbers(text, lang="en"):
    """All numbers in a text as floats. '6.5%' -> 6.5, '1,000' -> 1000, 'doubled' -> 2.

    lang is the language of the TEXT: German and Dutch write a decimal comma and a thousands dot,
    so '5,28 Mio.' -> {5.28, 1e6} and '1.000' -> 1000; read as English, '5,28' would be 5 and 28.
    """
    text = _NAMES.sub(" ", text)
    # "$7.5B", "¥15.4T", "€3bn", "430M" -> the same scale word as when it is spoken out
    # ("milliard", not "billion": in German and Dutch text "billion" means 10^12)
    for short, word in (("tn|t", "trillion"), ("bn|b", "milliard"), ("mn|m", "million"), ("k", "thousand")):
        text = re.sub(rf"(?<=\d)\s?(?:{short})\b", f" {word}", text, flags=re.I)
    if lang in ("de", "nl"):  # decimal comma: "6,5 %"
        text = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", text).replace(",", ".")
    else:
        text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    found = {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)}
    low = text.lower()
    words = _WORDS_DE_NL if lang in ("de", "nl") else _WORDS
    found |= {float(words[w]) for w in re.findall(r"[a-zäöüß]+", low) if w in words}
    found |= {v for pattern, v in _FRACTIONS if re.search(pattern, low)}
    return found


SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["facts"],
    "properties": {"facts": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["metric", "claim", "value", "unit", "period", "importance", "sources"],
        "properties": {
            "metric": {"type": "string", "description": "short stable key, e.g. 'us_ppi_mom'"},
            "claim": {"type": "string", "description": "one neutral English sentence in your own words"},
            "value": {"type": "string"}, "unit": {"type": "string"}, "period": {"type": "string"},
            "importance": {"type": "integer", "description": "3 = headline, 1 = detail"},
            "sources": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["article_id", "value_in_source", "quote"],
                "properties": {"article_id": {"type": "string"}, "value_in_source": {"type": "string"},
                               "quote": {"type": "string"}}}},
        }}}},
}

SYSTEM = """You extract checkable facts from financial news for an audio briefing.
Rules:
- Return the 3 to 6 most important facts about the story, the headline fact first.
- Each fact has one value with unit and period (e.g. value '0.3', unit '% month on month', period 'October 2026').
- For every article that states the fact, add a source with its article_id, the value as that article gives it,
  and a quote copied character for character from that article (one sentence or less, max 35 words) containing the value.
- If articles give different values for the same metric, keep ONE fact and list each article with its own value.
- Never compute, round or convert numbers. Never use knowledge outside the articles.
- Keep attribution. If the quote reports what a person, institution or analyst said, expects, supports or
  thinks, the claim names who, as the article does: "Fed Governor Waller said he supports a 25 basis point
  hike", never "The Fed is expected to hike". One official's view is never the institution's decision,
  and a forecast is never stated as a fact.
- Skip opinions, forecasts by the outlet and anything that sounds like investment advice."""


def extract_facts(story, articles):
    """story = {'id', 'title', 'article_ids'}; returns (verified_facts, rejected)."""
    docs = "\n\n".join(
        f"<article id=\"{a['id']}\" publisher=\"{a['publisher']}\" date=\"{a['date'][:10]}\">\n"
        f"{a['headline']}\n{a['text'][:MAX_CHARS]}\n</article>"
        for a in (articles[i] for i in story.get("fact_article_ids", story["article_ids"])))
    raw = ask_json("facts", SYSTEM, f"Story: {story['title']}\n\n{docs}", SCHEMA)["facts"]
    return verify_facts(story, raw, articles)


def verify_facts(story, raw_facts, articles):
    verified, rejected = [], []
    for n, f in enumerate(raw_facts):
        good = []
        for s in f["sources"]:
            art = articles.get(s["article_id"])
            lang = (art or {}).get("language", "en")  # the quote is in the article's language
            if art is None or s["article_id"] not in story["article_ids"]:
                rejected.append({"fact": f["claim"], "why": f"unknown article {s['article_id']}"})
                continue
            if norm(s["quote"]) not in norm(art["text"]):
                rejected.append({"fact": f["claim"], "why": f"quote not found in {art['publisher']}"})
                continue
            if not numbers(s["value_in_source"], lang) <= numbers(s["quote"], lang):
                rejected.append({"fact": f["claim"], "why": f"value {s['value_in_source']} not in quote"})
                continue
            speaker = unattributed(f["claim"], s["quote"])
            if speaker:
                rejected.append({"fact": f["claim"], "why": f"view of {speaker} stated as a fact"})
                continue
            good.append({**s, "publisher": art["publisher"], "url": art["url"], "date": art["date"], "language": lang})
        good = _one_per_article(good, f["value"])
        if not good:
            continue
        verified.append({
            "id": f"{story['id']}-f{n + 1}", "story_id": story["id"], "metric": f["metric"],
            "claim": f["claim"], "value": f["value"], "unit": f["unit"], "period": f["period"],
            "importance": f["importance"], "sources": good, "conflict": _conflict(good),
        })
    return verified, rejected


# "Hammack also argued that ...", "Waller, speaking on Monday, warned ...": a named person's VIEW. Plain "said" is
# left out on purpose: "the Labor Department said" carries data, not an opinion.
_VIEW = re.compile(r"\b([A-Z][a-zA-Z'’-]+)(?:,[^,]{1,60},)? (?:also |further |again )?(?:argued|argues|believes|"
                   r"thinks|warned|warns|expects|prefers|favou?rs|supports|called for|calls for|urged|urges|"
                   r"suggested|suggests|signall?ed|reiterated)\b")
_PRONOUNS = {"He", "She", "They", "It", "We", "I", "This", "That", "Analysts", "Investors", "Markets", "Traders",
             "Economists", "Officials", "Some", "Many", "Others"}


def unattributed(claim, quote):
    """The speaker if the quote is a named person's view and the claim drops the name, else None."""
    for m in _VIEW.finditer(quote):
        who = m.group(1)
        if who not in _PRONOUNS and who.lower() not in claim.lower():
            return who
    return None


def _one_per_article(sources, value):
    """One article cannot disagree with itself: keep its source that carries the fact's value."""
    keep, target = {}, numbers(value)  # the fact's value is in English, like the claim
    for s in sources:
        old = keep.get(s["article_id"])
        if old is None or (target <= _source_numbers(s) and not target <= _source_numbers(old)):
            keep[s["article_id"]] = s
    return list(keep.values())


def _source_numbers(source):
    return numbers(source["value_in_source"], source.get("language", "en"))


_SCALES = {1e3, 1e6, 1e9, 1e12}


_THREE_AFTER_SEPARATOR = re.compile(r"(?<![\d.,])(\d{1,3})[.,](\d{3})(?![\d.,])")
TOLERANCE = 0.0025  # 0.25 %: "$25.9 billion" is "$25.95 billion" shortened, 6.8 % and 6.9 % still disagree


def _figures(source):
    """The value as whole figures: '5.28 million' -> {5280000}, so a shared scale word alone is no agreement.

    Without this, '5.28 million' and '5.82 million' would share 1e6 and pass as the same figure.
    '27,945' and '27.945' are read both ways: a translation often keeps the English separator
    (Invezz German wrote the Nasdaq 100 at "27,945", the Dutch version "27.945").
    """
    found = _source_numbers(source)
    for a, b in _THREE_AFTER_SEPARATOR.findall(source["value_in_source"]):
        found |= {float(a + b), float(f"{a}.{b}")}
    base, scales = found - _SCALES, found & _SCALES
    if not base or not scales:
        return found
    return {round(b * s, 3) for b in base for s in scales}


def _conflict(sources):
    """Different outlets disagree only if no figure is shared: '6.3% to 6.5%' and '6.5%' agree, 6.9% and 6.8% do not.

    Each value is read in its own article's language, so '5,28 Mio. Barrel' (de) agrees with '5.28 million barrels',
    and '23 million' disagrees with '23 billion'. Figures within 0.25 % count as the same (rounding).
    """
    sets = [_figures(s) for s in sources]
    sets = [s for s in sets if s]
    if len(sets) < 2:
        return False
    close = lambda x, y: abs(x - y) <= TOLERANCE * max(abs(x), abs(y))
    return not any(all(any(close(x, y) for y in other) for other in sets[1:]) for x in sets[0])
