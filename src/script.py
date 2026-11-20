"""From verified facts to a script for ONE listener, checked line by line.

1. select_stories: the small model picks the stories that fit this listener (code checks the ids
   and caps the number by the requested length). Interests with no story are said out loud.
2. write_script: the small model writes spoken lines, each citing fact ids.
3. check_script: a line survives only if every number and every superlative it speaks is in a
   verified quote of the facts it cites. Then the code cuts the script to the requested length.
Fixed opening and closing lines disclose the synthetic voice and rule out investment advice.
"""
import re

from .facts import numbers
from .llm import ask_json

OPENING = {
    "en": "Good morning! This is your personal news briefing, read by an AI voice. Every figure links to its source in the transcript. Let's go!",
    "de": "Guten Morgen! Das ist dein persönliches Nachrichten-Briefing, gesprochen von einer KI-Stimme. Jede Zahl ist im Transkript mit ihrer Quelle verlinkt. Los geht's!",
    "nl": "Goedemorgen! Dit is je persoonlijke nieuwsbriefing, voorgelezen door een AI-stem. Elk cijfer linkt in het transcript naar de bron. Daar gaan we!",
}
CLOSING = {
    "en": "That's your briefing, have a great day! This is information, not investment advice.",
    "de": "Das war dein Briefing, hab einen starken Tag! Das ist eine Information, keine Anlageberatung.",
    "nl": "Dat was je briefing, maak er een topdag van! Dit is informatie, geen beleggingsadvies.",
}
NOTHING_ON = {
    "en": "Today's sources have nothing on {}.",
    "de": "Zu {} steht heute nichts in unseren Quellen.",
    "nl": "Over {} staat vandaag niets in onze bronnen.",
}
WORDS_PER_SECOND = {"en": 2.1, "de": 1.9, "nl": 2.0}  # measured: 127 words in 62 s (EN), a little slower for DE/NL
LANG_NAME = {"en": "English", "de": "German", "nl": "Dutch"}
SECONDS_PER_STORY = 25
FACTS_PER_STORY = 4

# ---------------------------------------------------------------- 1. selection

SELECT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["story_ids", "interests_without_story"],
    "properties": {
        "story_ids": {"type": "array", "items": {"type": "string"}},
        "interests_without_story": {"type": "array", "items": {"type": "string"},
                                    "description": "listener interests no story covers, in the listener's language"},
    },
}


def select_stories(profile, stories, facts):
    """Returns (stories in listening order, interests nothing covers)."""
    k = max(2, round(profile["seconds"] / SECONDS_PER_STORY))
    with_facts = {f["story_id"] for f in facts}
    pool = [s for s in stories if s["id"] in with_facts]
    listing = "\n".join(f"{s['id']}: {s['title']} (topic {s.get('topic', '?')}, importance {s.get('importance', '?')}/5,"
                        f" {len(s['publishers'])} outlets)" for s in pool)
    system = f"""You are the editor choosing stories for ONE listener:
{profile['description']}
Pick up to {k} story ids that this listener would want, in the order they should hear them: the most important
story that fits them first. Prefer importance and stories covered by several outlets. If the listener names
interests that no story covers, list those interests (in {LANG_NAME[profile['language']]}, short)."""
    out = ask_json("select", system, listing, SELECT_SCHEMA)
    by_id = {s["id"]: s for s in pool}
    chosen = [by_id[i] for i in dict.fromkeys(out["story_ids"]) if i in by_id][:k]
    if not chosen:
        chosen = pool[:k]  # never an empty briefing: fall back to the top stories
    return chosen, out["interests_without_story"][:2]


# ---------------------------------------------------------------- 2. writing

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["lines"],
    "properties": {"lines": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["text", "fact_ids"],
        "properties": {"text": {"type": "string"}, "fact_ids": {"type": "array", "items": {"type": "string"}}}}}},
}


def system_prompt(profile):
    lang = profile["language"]
    words = int(profile["seconds"] * WORDS_PER_SECOND[lang])
    return f"""You write a spoken radio news briefing in {LANG_NAME[lang]} for this listener:
{profile['description']}
Depth: {profile['depth']}.
Rules:
- At most {words} words in total. Stories in the given order. Fewer facts told well beat many facts listed.
- Written for the ear: short sentences, one per line, a punchy transition when a new story starts.
- Sound like a very happy, wide-awake morning radio host full of energy, so nobody falls asleep even on dry
  topics: upbeat transitions ("Next up!", "Here's a big one!"), exclamation marks, talk directly to the
  listener, explain why a story matters for them in plain words, without advice.
- The energy is in HOW you say it, never in WHAT happened: keep the source's verbs and size ("rose" stays
  "rose", never "soared" or "exploded"), no drama the quote does not have.
- Every line lists the fact_ids it relies on in the fact_ids field, never in the text.
  A line without fact_ids may only be a short transition of at most 8 words without any number.
- Every number you say must appear in one of the quoted source sentences ("... says:"); numbers that only
  appear in the fact summary are NOT allowed. At most two numbers per line. Words like "highest", "record"
  or "first time" only if the quote says so. Never compare or compute numbers yourself (no "doubled",
  "three times"). Say dates the way the quote says them ("on Thursday").
- Write numbers as digits with the unit written out ("0.3 percent" / "0,3 Prozent") and with the period.
- Name an outlet at most once per story. Always name both when a fact is marked CONFLICT and say they differ.
- No recommendations, no buy or sell, no predictions of your own, no cheering for a stock or market move.
- No greeting and no closing, those are added separately."""


def facts_prompt(stories, facts):
    parts = []
    for st in stories:
        parts.append(f"STORY: {st['title']}")
        own = sorted((f for f in facts if f["story_id"] == st["id"]), key=lambda f: -f["importance"])
        for f in own[:FACTS_PER_STORY]:
            flag = " CONFLICT" if f["conflict"] else ""
            parts.append(f"- [{f['id']}]{flag} {f['claim']} ({f['period']})")
            for s in f["sources"]:
                parts.append(f"    {s['publisher']} says: \"{s['quote']}\"")
    return "\n".join(parts)


def write_script(profile, stories, facts):
    """Returns (lines, dropped, chosen_stories). Each line: {'text', 'fact_ids'}."""
    chosen, missing = select_stories(profile, stories, facts)
    raw = ask_json("script", system_prompt(profile), facts_prompt(chosen, facts), SCHEMA)["lines"]
    kept, dropped = check_script(raw, facts, profile["language"])
    kept, cut = fit_length(kept, profile)
    lang = profile["language"]
    if missing:
        kept.append({"text": NOTHING_ON[lang].format(", ".join(missing)), "fact_ids": []})
    return kept, dropped + cut, chosen


def fit_length(lines, profile):
    """Hard cap by code: the model is told the length, the code makes sure of it."""
    budget = profile["seconds"] * WORDS_PER_SECOND[profile["language"]] * 1.1
    budget -= len(OPENING[profile["language"]].split()) + len(CLOSING[profile["language"]].split())
    kept, cut, used = [], [], 0
    for line in lines:
        n = len(line["text"].split())
        if used + n > budget:
            cut.append({**line, "why": "over the requested length"})
            continue
        kept.append(line)
        used += n
    while kept and not kept[-1]["fact_ids"]:  # never end on a transition into nothing
        cut.append({**kept.pop(), "why": "transition without a following story"})
    return kept, cut


# ---------------------------------------------------------------- 3. checking

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


# A superlative or a dramatic verb in speech needs the same idea in an (English) source quote.
SUPERLATIVES = {
    "highest": "highest", "höchst": "highest", "hoogst": "highest",
    "lowest": "lowest", "niedrigst": "lowest", "tiefst": "lowest", "laagst": "lowest",
    "record": "record", "rekord": "record",
    "biggest": "biggest|largest", "largest": "biggest|largest", "größt": "biggest|largest", "grootst": "biggest|largest",
    "smallest": "smallest", "kleinst": "smallest",
    "first time": "first", "erstmals": "first", "zum ersten mal": "first", "voor het eerst": "first",
    "all-time": "all-time|record", "allzeit": "all-time|record",
    # dramatic verbs: an upbeat host must not make a move sound bigger than the source says
    "soar": "soar|surg|skyrocket|rocket", "skyrocket": "soar|surg|skyrocket|rocket", "rocket": "soar|surg|skyrocket|rocket",
    "surg": "soar|surg|skyrocket|rocket|jump", "explod": "soar|surg|skyrocket|explod", "explodier": "soar|surg|skyrocket|explod",
    "schießt": "soar|surg|skyrocket|jump", "schiet omhoog": "soar|surg|skyrocket|jump",
    "plung": "plung|crash|tumbl|collaps|slump", "crash": "plung|crash|tumbl|collaps", "collaps": "plung|crash|collaps",
    "tumbl": "plung|crash|tumbl|slump", "stürz": "plung|crash|tumbl|slump", "bricht ein": "plung|crash|tumbl|slump",
    "einbruch": "plung|crash|tumbl|slump", "kelder": "plung|crash|tumbl|slump", "historic": "historic|record",
}


def unsupported_superlatives(text, quotes):
    low, src = text.lower(), " ".join(quotes).lower()
    return [w for w, en in SUPERLATIVES.items() if w in low and not re.search(en, src)]


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
        missing = spoken - set().union(*(allowed_numbers(by_id[i]) for i in ids))
        if missing:
            dropped.append({**line, "why": f"numbers not in sources: {sorted(missing)}"})
            continue
        sup = unsupported_superlatives(line["text"], [s["quote"] for i in ids for s in by_id[i]["sources"]])
        if sup:
            dropped.append({**line, "why": f"superlative not in sources: {sup}"})
            continue
        kept.append({"text": line["text"], "fact_ids": ids})
    return kept, dropped
