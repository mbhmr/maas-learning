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


def numbers(text, lang="en"):
    """All numbers in a text as floats. '6.5%' -> 6.5, German '6,5 %' -> 6.5, '1,000' -> 1000."""
    if lang == "de":
        text = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", text).replace(",", ".")
    else:
        text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)}


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
- Skip opinions, forecasts by the outlet and anything that sounds like investment advice."""


def extract_facts(story, articles):
    """story = {'id', 'title', 'article_ids'}; returns (verified_facts, rejected)."""
    docs = "\n\n".join(
        f"<article id=\"{a['id']}\" publisher=\"{a['publisher']}\" date=\"{a['date'][:10]}\">\n"
        f"{a['headline']}\n{a['text'][:MAX_CHARS]}\n</article>"
        for a in (articles[i] for i in story["article_ids"]))
    raw = ask_json("facts", SYSTEM, f"Story: {story['title']}\n\n{docs}", SCHEMA)["facts"]
    return verify_facts(story, raw, articles)


def verify_facts(story, raw_facts, articles):
    verified, rejected = [], []
    for n, f in enumerate(raw_facts):
        good = []
        for s in f["sources"]:
            art = articles.get(s["article_id"])
            if art is None or s["article_id"] not in story["article_ids"]:
                rejected.append({"fact": f["claim"], "why": f"unknown article {s['article_id']}"})
                continue
            if norm(s["quote"]) not in norm(art["text"]):
                rejected.append({"fact": f["claim"], "why": f"quote not found in {art['publisher']}"})
                continue
            if not numbers(s["value_in_source"]) <= numbers(s["quote"]):
                rejected.append({"fact": f["claim"], "why": f"value {s['value_in_source']} not in quote"})
                continue
            good.append({**s, "publisher": art["publisher"], "url": art["url"], "date": art["date"]})
        if not good:
            continue
        verified.append({
            "id": f"{story['id']}-f{n + 1}", "story_id": story["id"], "metric": f["metric"],
            "claim": f["claim"], "value": f["value"], "unit": f["unit"], "period": f["period"],
            "importance": f["importance"], "sources": good,
            "conflict": len({frozenset(numbers(s["value_in_source"])) for s in good}) > 1,
        })
    return verified, rejected
