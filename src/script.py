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
from .llm import SCRIPT_MODEL, ask_json

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
# Filler a real host would never say. The model is told so; the code removes what slips through anyway.
STOCK_PHRASES = re.compile(r"^\s*(next up|up next|here'?s a big one|big one coming|moving on|last but not least|"
                           r"and finally|now,? let'?s|weiter geht'?s?( es)?|jetzt wird('s| es) spannend|spannend|"
                           r"interessant|und jetzt|door naar het volgende|nu wordt het spannend)\b[\s!:.,-]*", re.I)
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
    # free model text goes into speech here, so only short plain topic names pass ("Tesla", "Solarenergie")
    missing = [m.strip() for m in out["interests_without_story"]
               if m.strip() and len(m.split()) <= 4 and not re.search(r"\d", m)]
    return chosen, missing[:2]


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
- Written for the ear: short sentences, one per line.
- You are a wide-awake, genuinely enthusiastic morning host who loves this stuff and makes the listener feel
  smart. Real energy, not filler: start each story with a hook that is itself news (the most surprising
  fact first, with its fact_ids), talk to the listener ("you"), tell them in one plain sentence why it matters
  for someone like them, use exclamation marks where a real host would raise their voice. Link stories by
  their content when they connect, otherwise just start the next one with its hook.
- Never use filler or stock radio phrases ("Next up", "Moving on", "Here's a big one", "Weiter geht es",
  "Spannend:", "Interessant:"), never label a sentence, never comment on the briefing itself.
- The energy is in HOW you say it, never in WHAT happened: keep the source's verbs and size ("rose" stays
  "rose", never "soared" or "exploded"), no drama the quote does not have.
- Every line lists the fact_ids it relies on in the fact_ids field, never in the text. Every sentence about
  the news needs fact_ids. Only a sentence that says nothing factual may go without.
- Every number you say must appear in one of the quoted source sentences ("... says:"); numbers that only
  appear in the fact summary are NOT allowed. At most two numbers per line. Words like "highest", "record"
  or "first time" only if the quote says so. Never compare or compute numbers yourself (no "doubled",
  "three times"). Never say today, yesterday, tonight, this week or a weekday: the listener hears this later,
  so say the date from the source line instead ("on 18 November").
- Write numbers as digits with the unit written out ("0.3 percent" / "0,3 Prozent") and with the period.
- Name an outlet at most once per story. Always name both when a fact is marked CONFLICT and say they differ.
- No recommendations, no buy or sell, never what listeners can or should do with their money, no predictions
  of your own, no cheering for a stock or market move. Say whose shares moved (the company, not a person).
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
                parts.append(f"    {s['publisher']} ({_day(s['date'])}) says: \"{s['quote']}\"")
    return "\n".join(parts)


def _day(date):
    y, m, d = date[:10].split("-")
    return f"{int(d)} {MONTHS_EN[int(m) - 1]} {y}"


def write_script(profile, stories, facts):
    """Returns (lines, dropped, spoken_stories). Each line: {'text', 'fact_ids'}."""
    chosen, missing = select_stories(profile, stories, facts)
    raw = ask_json("script", system_prompt(profile), facts_prompt(chosen, facts), SCHEMA, model=SCRIPT_MODEL)["lines"]
    kept, dropped = check_script(raw, facts, profile["language"])
    kept, judged = judge(kept, facts)
    kept, cut = fit_length(kept, profile)
    lang = profile["language"]
    if missing:
        kept.append({"text": NOTHING_ON[lang].format(", ".join(missing)), "fact_ids": []})
    story_of = {f["id"]: f["story_id"] for f in facts}
    spoken = {story_of[i] for line in kept for i in line["fact_ids"]}
    return kept, dropped + judged + cut, [s for s in chosen if s["id"] in spoken]


def fit_length(lines, profile):
    """Hard cap by code: the model is told the length, the code makes sure of it."""
    budget = profile["seconds"] * WORDS_PER_SECOND[profile["language"]] * 1.1
    budget -= len(OPENING[profile["language"]].split()) + len(CLOSING[profile["language"]].split())
    kept, used = [], 0
    for n, line in enumerate(lines):
        used += len(line["text"].split())
        if used > budget:  # cut the END, never a line in the middle of a story
            return kept, [{**x, "why": "over the requested length"} for x in lines[n:]]
        kept.append(line)
    return kept, []


# ---------------------------------------------------------------- 3. checking

MONTHS_EN = "January February March April May June July August September October November December".split()
MONTH_WORDS = re.compile(r"\b(january|february|march|april|may|june|july|august|september|october|november|"
                         r"december|januar|februar|märz|mai|juni|juli|oktober|dezember|januari|februari|maart|"
                         r"mei|augustus|oktober|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|okt|nov|dec|dez)\b", re.I)


def allowed_numbers(fact, text=""):
    """Only what the code has verified: the quotes, plus day and year of the article dates.

    Day and year count only next to a month name ("on 18 November 2026"), so "rose 18 percent" cannot hide
    behind the date. The model's own summary (claim, period) does not count, it was never checked.
    """
    nums = set()
    for s in fact["sources"]:
        nums |= numbers(s["quote"])
        if MONTH_WORDS.search(text):
            y, _, d = s["date"][:10].split("-")
            nums |= {float(y), float(d)}
    return nums


# A superlative or a dramatic verb in speech needs the same idea in an (English) source quote.
SUPERLATIVES = {
    "highest": "highest", "höchst": "highest", "hoogst": "highest",
    "lowest": "lowest", "niedrigst": "lowest", "tiefst": "lowest", "laagst": "lowest",
    "record(?!ed)": "record", "rekord": "record", "massive": "massive|huge|record", "tank": "tank|plung|crash",
    "spik": "spik|soar|surg|jump", "absturz": "plung|crash|tumbl|slump", "abgestürzt": "plung|crash|tumbl|slump",
    "biggest": "biggest|largest", "largest": "biggest|largest", "größt": "biggest|largest", "grootst": "biggest|largest",
    "smallest": "smallest", "kleinst": "smallest",
    "first time": "first time|first-ever|for the first", "erstmals": "first time|first-ever|for the first",
    "zum ersten mal": "first time|first-ever|for the first", "voor het eerst": "first time|first-ever|for the first",
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
    return [w for w, en in SUPERLATIVES.items() if re.search(r"\b" + w, low) and not re.search(en, src)]


FACT_ID = re.compile(r"\s*[\[(]?\bs\d+-f\d+\b[\])]?[.,;]?")


def check_script(raw_lines, facts, lang):
    by_id = {f["id"]: f for f in facts}
    kept, dropped = [], []
    for line in raw_lines:
        text = FACT_ID.sub("", line["text"]).strip()  # ids belong in fact_ids, never in speech
        text = STOCK_PHRASES.sub("", text).strip()    # filler at the start goes, the sentence stays
        if not text:
            continue
        line = {**line, "text": text[0].upper() + text[1:]}
        ids = [i for i in line["fact_ids"] if i in by_id]
        if not ids:  # every spoken line needs a verified source, also a "harmless" short one
            dropped.append({**line, "why": "no source"})
            continue
        spoken = numbers(line["text"], lang)
        missing = spoken - set().union(*(allowed_numbers(by_id[i], line["text"]) for i in ids))
        if missing:
            dropped.append({**line, "why": f"numbers not in sources: {sorted(missing)}"})
            continue
        sup = unsupported_superlatives(line["text"], [s["quote"] for i in ids for s in by_id[i]["sources"]])
        if sup:
            dropped.append({**line, "why": f"superlative not in sources: {sup}"})
            continue
        kept.append({"text": line["text"], "fact_ids": ids})
    return kept, dropped


# A second, independent look by a cheap model: does each line say only what its quotes say?
# The code checks numbers and words; this catches wrong direction, invented causes, advice and relative dates.
JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["verdicts"],
    "properties": {"verdicts": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["n", "supported", "why"],
        "properties": {"n": {"type": "integer"}, "supported": {"type": "boolean"}, "why": {"type": "string"}}}}},
}
JUDGE_SYSTEM = """You are a strict fact checker for a radio news script. Each numbered line comes with the quoted
source sentences it cites. Mark a line supported=false if ANY of this is true:
- it states something the quotes do not say (another subject, another direction up or down, another size,
  another time, a cause or consequence the quotes do not state, a different company or person);
- it tells listeners what to do with money, or what they can or should buy or sell, or predicts the future;
- it uses today, yesterday, tonight, this week or a weekday (the listener hears it on a later day).
Enthusiasm, exclamation marks, addressing the listener and a plain explanation of a term are fine.
A sentence saying why such news matters in general is fine if it adds no new fact about this event.
Return one verdict per line, with a short reason when unsupported."""


def judge(lines, facts):
    if not lines:
        return lines, []
    by_id = {f["id"]: f for f in facts}
    listing = []
    for n, line in enumerate(lines):
        quotes = " | ".join(f"{s['publisher']} ({_day(s['date'])}): \"{s['quote']}\""
                            for i in line["fact_ids"] for s in by_id[i]["sources"])
        listing.append(f"{n}. LINE: {line['text']}\n   QUOTES: {quotes}")
    verdicts = ask_json("judge", JUDGE_SYSTEM, "\n".join(listing), JUDGE_SCHEMA)["verdicts"]
    bad = {v["n"]: v["why"] for v in verdicts if not v["supported"] and 0 <= v["n"] < len(lines)}
    kept = [line for n, line in enumerate(lines) if n not in bad]
    return kept, [{**lines[n], "why": f"content check: {why}"} for n, why in bad.items()]
