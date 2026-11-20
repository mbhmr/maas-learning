"""Write a listener-specific script from verified facts, then check every line.

A line is kept only if it cites facts and every number it speaks appears in
those facts (value, period, claim or the verified quote). Fixed opening and
closing lines disclose the synthetic voice and rule out investment advice.
"""
import re

from .facts import numbers
from .llm import ask_json

OPENING = {
    "en": "This is your personal news briefing, read by an AI voice. Every figure links to its source in the transcript.",
    "de": "Das ist dein persönliches Nachrichten-Briefing, gesprochen von einer KI-Stimme. Jede Zahl ist im Transkript mit ihrer Quelle verlinkt.",
    "nl": "Dit is je persoonlijke nieuwsbriefing, voorgelezen door een AI-stem. Elk cijfer linkt in het transcript naar de bron.",
}
CLOSING = {
    "en": "That's your briefing. This is information, not investment advice.",
    "de": "Das war dein Briefing. Das ist eine Information, keine Anlageberatung.",
    "nl": "Dat was je briefing. Dit is informatie, geen beleggingsadvies.",
}
WORDS_PER_SECOND = {"en": 2.5, "de": 2.1, "nl": 2.2}
LANG_NAME = {"en": "English", "de": "German", "nl": "Dutch"}

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["lines"],
    "properties": {"lines": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["text", "fact_ids"],
        "properties": {"text": {"type": "string"}, "fact_ids": {"type": "array", "items": {"type": "string"}}}}}},
}


def system_prompt(profile):
    lang = profile["language"]
    words = int(profile["seconds"] * WORDS_PER_SECOND[lang])
    return f"""You write a spoken news briefing in {LANG_NAME[lang]} for this listener:
{profile['description']}
Depth: {profile['depth']}.
Rules:
- About {words} words in total. Stories in the given order, most important first. Leave out stories
  and facts that do not matter to this listener.
- One short spoken sentence per line. Every line lists the fact_ids it relies on in the fact_ids field,
  never in the text. No line without facts.
- Use only the given facts. Every number you say must appear in one of the quoted source sentences
  ("... says:"); numbers that only appear in the fact summary are NOT allowed. At most two numbers per line.
  Say dates the way the quote says them ("on Thursday"), never turn them into a calendar date yourself.
  Never compare or compute
  numbers yourself (no "doubled", "a quarter", "three times"). Write numbers as digits
  with the unit written out (e.g. "0.3 percent" / "0,3 Prozent"), always with the period it refers to.
- If a fact is marked CONFLICT, say that the sources differ and name each source with its value.
- Name the outlet when it helps trust ("according to ActionForex").
- Neutral tone. No recommendations, no buy or sell, no predictions of your own.
- Do not add a greeting or a closing, those are added separately."""


def facts_prompt(stories, facts):
    parts = []
    for st in stories:
        parts.append(f"STORY {st['rank']}: {st['title']}")
        for f in (f for f in facts if f["story_id"] == st["id"]):
            flag = " CONFLICT" if f["conflict"] else ""
            parts.append(f"- [{f['id']}]{flag} {f['claim']} ({f['period']})")
            for s in f["sources"]:
                parts.append(f"    {s['publisher']} says: \"{s['quote']}\"")
    return "\n".join(parts)


def allowed_numbers(fact):
    """Only what the code has verified: the quotes, plus day and year of the article dates.

    The model's own summary (claim, period) does not count, it was never checked.
    """
    nums = set()
    for s in fact["sources"]:
        nums |= numbers(s["quote"])
        y, _, d = s["date"][:10].split("-")
        nums |= {float(y), float(d)}  # "October 2026", "on 13 November"
    return nums


def write_script(profile, stories, facts):
    """Returns (lines, dropped). Each line: {'text', 'fact_ids'}."""
    raw = ask_json("script", system_prompt(profile), facts_prompt(stories, facts), SCHEMA)["lines"]
    return check_script(raw, facts, profile["language"])


FACT_ID = re.compile(r"\s*[\[(]?\bs\d+-f\d+\b[\])]?[.,;]?")


def check_script(raw_lines, facts, lang):
    by_id = {f["id"]: f for f in facts}
    kept, dropped = [], []
    for line in raw_lines:
        line = {**line, "text": FACT_ID.sub("", line["text"]).strip()}  # ids belong in fact_ids, never in speech
        ids = [i for i in line["fact_ids"] if i in by_id]
        spoken = numbers(line["text"], lang)
        if not ids:
            if spoken or len(line["text"].split()) > 8:
                dropped.append({**line, "why": "no source"})
            else:
                kept.append({"text": line["text"], "fact_ids": []})  # short transition, no claim
            continue
        allowed = set().union(*(allowed_numbers(by_id[i]) for i in ids))
        missing = spoken - allowed
        if missing:
            dropped.append({**line, "why": f"numbers not in sources: {sorted(missing)}"})
            continue
        kept.append({"text": line["text"], "fact_ids": ids})
    return kept, dropped
