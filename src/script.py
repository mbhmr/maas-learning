"""From verified facts to a script for ONE listener, checked line by line.

1. select_stories: the small model picks the stories that fit this listener (code checks the ids
   and caps the number by the requested length). Interests with no story are said out loud.
2. write_script: the small model writes a greeting and a sign-off for this listener and the spoken lines,
   each line a "claim" (news) or a "context" (why it matters to this listener), each citing fact ids.
3. check_script: numbers are put into the listener's language (0,3 Prozent, Milliarden), then a line survives
   only if every number and every superlative it speaks is in a verified quote of the facts it cites.
   A second model judges the content. Then the code cuts the script to the requested length.
Short fixed lines disclose the synthetic voice and rule out investment advice; the greeting and the sign-off
are written by the model, checked by code (no numbers, no advice, short) and fall back to fixed text.
"""
import re
from datetime import date, timedelta

from .facts import numbers
from .lessons import prompt_block
from .llm import SCRIPT_MODEL, ask_json

# Fixed by code, never by the model. Kept short: in a 30 s briefing every second of frame is a second of news.
OPENING = {
    "en": "Read by an AI voice, every figure links to its source.",
    "de": "Gesprochen von einer KI-Stimme, jede Zahl ist mit ihrer Quelle verlinkt.",
    "nl": "Voorgelezen door een AI-stem, elk cijfer linkt naar de bron.",
}
OPENING_SHORT = {"en": "AI voice, every figure sourced.", "de": "KI-Stimme, jede Zahl mit Quelle.",
                 "nl": "AI-stem, elk cijfer met bron."}
CLOSING = {"en": "Information, not investment advice.", "de": "Information, keine Anlageberatung.",
           "nl": "Informatie, geen beleggingsadvies."}
# Used when the model's greeting or sign-off fails a check.
GREETING = {"en": "Good morning!", "de": "Guten Morgen!", "nl": "Goedemorgen!"}
SIGN_OFF = {"en": "That's your briefing.", "de": "Das war dein Briefing.", "nl": "Dat was je briefing."}
SHORT_SECONDS = 60      # below: the short disclosure
NO_SIGN_OFF_SECONDS = 45  # below: no sign-off, the closing alone
NOTHING_ON = {
    "en": "Today's sources have nothing on {}.",
    "de": "Zu {} steht heute nichts in unseren Quellen.",
    "nl": "Over {} staat vandaag niets in onze bronnen.",
}
WORDS_PER_SECOND = {"en": 2.45, "de": 2.25, "nl": 2.2}  # measured 20.11. 22:00 on Danielle/eleven_v4: en 2.41 and 2.49, de 2.24, nl 2.2
LANG_NAME = {"en": "English", "de": "German", "nl": "Dutch"}
# Filler a real host would never say. The model is told so; the code removes what slips through anyway.
STOCK_PHRASES = re.compile(r"^\s*(next up|up next|here'?s a big one|big one coming|moving on|last but not least|"
                           r"and finally|now,? let'?s|weiter geht'?s?( es)?|jetzt wird('s| es) spannend|spannend|"
                           r"interessant|und jetzt|door naar het volgende|nu wordt het spannend)\b[\s!:.,-]*", re.I)
SECONDS_PER_STORY = 20  # 25 left most briefings at half their length once the checker had removed lines
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
    # "nothing in our sources" must be true for the whole day, not only for the stories picked: a topic word that
    # appears in any story title of the day is not missing, the line would be wrong
    titles = " ".join(s["title"] for s in stories).lower()
    missing = [m.strip() for m in out["interests_without_story"]
               if m.strip() and len(m.split()) <= 4 and not re.search(r"\d", m)
               and not any(re.search(rf"\b{re.escape(w)}", titles) for w in m.lower().split() if len(w) >= 2)]
    return chosen, missing[:2]


# ---------------------------------------------------------------- 2. writing

LINE_KINDS = ("claim", "context")
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["greeting", "sign_off", "lines"],
    "properties": {
        "greeting": {"type": "string"}, "sign_off": {"type": "string"},
        "lines": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "kind", "fact_ids"],
            "properties": {"text": {"type": "string"}, "kind": {"type": "string", "enum": list(LINE_KINDS)},
                           "fact_ids": {"type": "array", "items": {"type": "string"}}}}}},
}

NUMBER_STYLE = {
    "en": 'Numbers as digits with the unit written out: "0.3 percent", "$10.5 billion", "25 basis points".',
    "de": 'Numbers the German way: decimal comma ("0,3 Prozent"), "Milliarden" for billion, "Billionen" for '
          'trillion, currency after the number ("10,5 Milliarden Dollar"). Every word is German: translate the '
          'verbs and nouns of the English quotes ("rose" is "stieg", "producer prices" are "Erzeugerpreise"), '
          'only names of companies, people and indices stay. A change is "um" ("stieg um 0,3 Prozent"), a level '
          'is "auf" ("stieg auf 6,5 Prozent"), exactly as the quote has it. Always "du", never "Sie".',
    "nl": 'Numbers the Dutch way: decimal comma ("0,3 procent"), "miljard" for billion, "biljoen" for '
          'trillion, currency after the number ("10,5 miljard dollar"). Every word is Dutch: translate the verbs '
          'and nouns of the English quotes ("rose" is "steeg"), only names of companies, people and indices stay. '
          'A change is "met" ("steeg met 0,3 procent"), a level is "naar" ("steeg naar 6,5 procent"), exactly as '
          'the quote has it. Always "je", never "u".',
}


def host_words(profile):
    """Word cap for greeting and sign-off: 6 in a 30 s briefing, up to 20 in a long one."""
    return max(6, min(20, round(profile["seconds"] / 6)))


def frame_texts(profile):
    """The fixed frame (and fallbacks) for this length: greeting, opening, sign_off, closing."""
    lang = profile["language"]
    return {"greeting": GREETING[lang],
            "opening": (OPENING_SHORT if profile["seconds"] < SHORT_SECONDS else OPENING)[lang],
            "sign_off": SIGN_OFF[lang] if profile["seconds"] >= NO_SIGN_OFF_SECONDS else "",
            "closing": CLOSING[lang]}


def system_prompt(profile, day=None):
    lang = profile["language"]
    hw = host_words(profile)
    frame = len(frame_texts(profile)["opening"].split()) + len(CLOSING[lang].split()) + hw  # hosts rarely use the cap
    words = max(20, int(profile["seconds"] * WORDS_PER_SECOND[lang]) - frame)
    sign_off = (f"- sign_off: at most {hw} words, a warm goodbye in the same spirit, using the same name for the listener as the greeting. No numbers, no facts, no advice."
                if profile["seconds"] >= NO_SIGN_OFF_SECONDS else "- sign_off: empty string (too short for one).")
    published = f" The briefing is published on {day}." if day else ""
    if profile.get("days") and profile["days"] > 1:  # "the week so far": a look back, every story with its date
        published += (f" It covers the last {profile['days']} days of news: a review of those days, the most "
                      "important story first whatever its day, and every claim says its date.")
    return f"""You write a spoken radio news briefing in {LANG_NAME[lang]} for this listener:
{profile['description']}
Depth: {profile['depth']}.{published}

What you return:
- greeting: at most {hw} words, the host's hello to THIS listener, calling them by their profile name exactly as
  given (never a different role word), naming who they are and what this briefing
  is about in general words (e.g. "Morning, trader, central banks are running the show!"). No numbers, no
  company or person names, no events, no claims. Do not say it is a briefing or an AI, the code adds that.
{sign_off}
- lines: the news, one spoken sentence per line, about {words} words in total (use nearly all of them: the
  listener asked for this length, a briefing far under it is a failure; the code cuts anything over), stories in the given order.

Two kinds of lines:
- kind "claim": what happened, only what the quoted source sentences say.
- kind "context": one per story (two related stories told together share one), one sentence after that
  story's claims: why it matters to THIS listener, in plain words ("That keeps intervention risk front and
  centre for a yen trader."). It cites the facts it interprets. It says NO number and repeats no figure, adds
  no fact, no cause and no link between facts that the quotes do not state, no advice, no prediction of prices
  or decisions. Vary the wording from story to story, never the same opening twice.

How a story is told:
- Fewer facts told well beat many facts listed. Short sentences (at most about 25 words, never over 40: longer lines are dropped by code), one story per sentence, written for the ear.
- Open each story with its most important and newest fact as a full sentence that starts with who or what
  ("US producer prices rose 0.3 percent in October"). Never start a line with a number ("0.3 percent, not
  0.4 percent ..." is wrong).
- When stories touch the same subject (two Fed officials, two central banks, a data release and the market
  move), do not tell them one after the other: contrast them in ONE line that names both sides ("Fed
  Governor Waller argues for 50 basis points, New York Fed President Williams for 25."), citing the facts of
  both, then one context line for the pair.
- An opinion, forecast or preference of one person or outlet is always said with its name ("Fed Governor
  Waller wants 50 basis points"), never as a fact and never as what "the Fed" or "the market" leans to.
- Never join two facts with "as", "while", "so", "because", "after", "weil", "während", "terwijl", "omdat"
  unless one quote states that link: use two sentences. No judging words the quote does not use ("sticky",
  "fragile", "hot", "strong").
- Prefer the freshest facts. A story marked OLDER gets its date in the line ("on 14 November").
- You are a wide-awake, genuinely enthusiastic morning host who makes the listener feel smart: talk to them
  ("you"), exclamation marks where a real host would raise the voice. The energy is in HOW you say it, never
  in WHAT happened: keep the source's verbs and size ("rose" stays "rose", never "soared").
- Never use filler or stock radio phrases ("Next up", "Moving on", "Here's a big one", "Weiter geht es",
  "Spannend:"), never label a sentence, never comment on the briefing itself.

Facts and numbers:
- Every line lists the fact_ids it relies on in fact_ids, never in the text.
- Every number you say must appear in one of the quoted source sentences ("... says:"); numbers that only
  appear in the fact summary are NOT allowed. At most two numbers per line. Words like "highest", "record"
  or "first time" only if the quote says so. Never compare or compute numbers yourself (no "doubled").
  Never say today, yesterday, tonight, this week or a weekday: say the date ("on 18 November").
- {NUMBER_STYLE[lang]}
- Name an outlet at most once per story. Always name both when a fact is marked CONFLICT and say they differ.
- No recommendations, no buy or sell, never what listeners can or should do with their money, no predictions
  of your own, no cheering for a stock or market move. Say whose shares moved (the company, not a person).""" + prompt_block()


def _newest(fact):
    return max(s["date"][:10] for s in fact["sources"])


# A story moves on: "Anthropic kept its IPO range at $70 to $78" (17 Nov) was stale once it priced at $83 (18 Nov),
# and the writer picked the old fact. Only the newest fact per entity and metric goes to the writer. Same entity is
# the first word of the metric key ("anthropic_ipo_price_range"); same metric is the same key, or an evolving deal
# word in both keys plus one more shared word ("ipo" + "price"). Older means an older newest-source DAY.
EVOLVING = {"ipo", "offering", "listing", "guidance", "outlook", "forecast", "deal", "bid", "takeover", "acquisition",
            "merger", "buyout"}
_GENERIC_KEY = {"per", "of", "the", "a", "and", "in", "on", "to", "change", "mom", "yoy", "qoq", "total", "value",
                "count", "number", "estimate"}


def _superseded(old, new):
    a, b = old.get("metric", "").lower().split("_"), new.get("metric", "").lower().split("_")
    if not a[0] or a[0] != b[0] or _newest(old) >= _newest(new):
        return False
    shared = (set(a[1:]) & set(b[1:])) - _GENERIC_KEY
    return a == b or (bool(shared & EVOLVING) and len(shared) >= 2)


def current_facts(facts):
    """The facts the writer may use: every fact that a NEWER fact about the same entity and metric replaces is left out,
    also when the newer one sits in another story."""
    by_entity = {}
    for f in facts:
        if f.get("sources"):
            by_entity.setdefault(f.get("metric", "").split("_")[0].lower(), []).append(f)
    return [f for f in facts if not f.get("sources")
            or not any(_superseded(f, g) for g in by_entity.get(f.get("metric", "").split("_")[0].lower(), []))]


def news_day(facts):
    """The day of the briefing: the newest article date among the facts (ISO, '2026-11-18')."""
    return max((_newest(f) for f in facts if f.get("sources")), default=None)


def _age(day, newest):
    return (date.fromisoformat(day) - date.fromisoformat(newest)).days


def facts_prompt(stories, facts, day=None):
    """The facts per story, most important first and, at equal importance, the newest first.

    A story whose newest source is more than 2 days before the briefing day is marked OLDER.
    """
    parts = []
    for st in stories:
        own = sorted((f for f in facts if f["story_id"] == st["id"]), key=_newest, reverse=True)
        own = sorted(own, key=lambda f: -f["importance"])[:FACTS_PER_STORY]  # stable sort keeps newest first
        newest = max((_newest(f) for f in own), default=None)
        older = bool(day and newest) and _age(day, newest) > 2
        parts.append(f"STORY: {st['title']}" + (f" (OLDER: newest source {_day(newest)}, say the date)" if older else ""))
        for f in own:
            flag = " CONFLICT" if f["conflict"] else ""
            parts.append(f"- [{f['id']}]{flag} {f['claim']} ({f['period']})")
            for s in f["sources"]:
                parts.append(f"    {s['publisher']} ({_day(s['date'])}) says: \"{s['quote']}\"")
    return "\n".join(parts)


def _day(iso):
    y, m, d = iso[:10].split("-")
    return f"{int(d)} {MONTHS_EN[int(m) - 1]} {y}"


def with_headlines(facts, stories):
    """Copies of the facts whose sources carry their article's headline (from stories.json), for the person check."""
    heads = {h["id"]: h.get("headline", "") for st in stories for h in st.get("headlines", [])}
    return [{**f, "sources": [{**src, "headline": heads.get(src.get("article_id"), "")} for src in f.get("sources", [])]}
            for f in facts]


def in_span(stories, facts, days):
    """Only stories whose newest article falls in the last `days` days of the news (1 = the last day only).
    None or 0: everything prepare.py put in the window (13 to 18 Nov for the demo day)."""
    end = news_day(facts)
    if not days or not end:
        return stories
    first = (date.fromisoformat(end[:10]) - timedelta(days=days - 1)).isoformat()
    return [s for s in stories if (s.get("latest") or "")[:10] >= first]


def write_script(profile, stories, facts):
    """Returns (lines, dropped, spoken_stories, frame).

    lines: {'text', 'fact_ids', 'kind'} with kind "claim", "context" or "transition".
    frame: {'greeting', 'opening', 'sign_off', 'closing'}. greeting and sign_off are the model's when they pass
    the checks, otherwise the fixed fallback; sign_off is "" in very short briefings.
    """
    lang = profile["language"]
    facts = current_facts(facts)  # stale facts are never offered, so they cannot be cited either
    stories = in_span(stories, facts, profile.get("days"))
    facts = with_headlines(facts, stories)
    chosen, missing = select_stories(profile, stories, facts)
    day = news_day(facts)
    out = ask_json("script", system_prompt(profile, day and _day(day)), facts_prompt(chosen, facts, day), SCHEMA,
                   model=SCRIPT_MODEL)
    kept, dropped = check_script(out["lines"], facts, lang)
    frame = frame_texts(profile)
    hosts = []
    for role in ("greeting", "sign_off"):
        if not frame[role]:
            continue
        text, why = check_host(out.get(role, ""), lang, host_words(profile))
        name = (profile.get("name") or "").strip().lower()
        if role == "greeting" and not why and name and name != "listener" and not calls_by_name(text, name):
            text, why = None, "greeting does not call the listener by their name"
        if why:
            dropped.append({"text": out.get(role, ""), "fact_ids": [], "kind": "host", "why": why})
        else:
            hosts.append({"text": text, "fact_ids": [], "kind": "host", "role": role})
    judged_lines, judged = judge(kept + hosts, facts)
    for line in judged_lines:
        if line.get("role"):
            frame[line["role"]] = line["text"]
    kept = [line for line in judged_lines if not line.get("role")]
    kept, dropped, judged = repair(profile, chosen, facts, day, kept, dropped, judged)
    kept, twice = dedupe(kept, facts, profile["language"])
    dropped += twice
    reserved = sum(len(t.split()) for t in frame.values())
    for _ in range(TOP_UP_ROUNDS):  # each round adds stories only while the briefing is under 80 % of its length
        chosen, kept, more_dropped = top_up(profile, stories, facts, day, chosen, kept, reserved)
        dropped += more_dropped
    kept, cut = fit_length(kept, profile, reserved)
    kept, orphans = arrange(kept, facts)
    if missing:
        kept.append({"text": NOTHING_ON[lang].format(", ".join(missing)), "fact_ids": [], "kind": "transition"})
    story_of = {f["id"]: f["story_id"] for f in facts}
    spoken = {story_of[i] for line in kept for i in line["fact_ids"]}
    frame = {k: tidy(v) for k, v in frame.items()}
    return kept, dropped + judged + cut + orphans, [s for s in chosen if s["id"] in spoken], frame


REPAIRABLE = ("content check", "numbers not in sources", "too long for the ear", "starts with a bare number",
              "superlative not in sources", "English words", "context line with a figure",
              "person not in its quotes", "time qualifier not in its quotes")  # a rewrite can drop the name or the qualifier
REPAIR_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["lines"],
                 "properties": {"lines": SCHEMA["properties"]["lines"]}}


def repair(profile, chosen, facts, day, kept, dropped, judged):
    """One second chance: blocked lines go back to the writer with the checker's reason, and the rewrite
    passes every check again. What still fails stays blocked. Lines that were dropped for good stay dropped.
    """
    blocked = [d for d in dropped + judged if d.get("kind", "claim") in LINE_KINDS
               and any(str(d.get("why", "")).startswith(r) or r in str(d.get("why", "")) for r in REPAIRABLE)]
    if not blocked:
        return kept, dropped, judged
    lang = profile["language"]
    todo = "\n".join(f'- [{d.get("kind", "claim")}] "{d["text"]}" facts {d.get("fact_ids", [])}: blocked because '
                     f'{d["why"]}' for d in blocked)
    user = (facts_prompt(chosen, facts, day) + "\n\nThe checker blocked these lines. Rewrite each one so it passes: "
            "one short sentence (at most 30 words), only what its quotes say, the same fact ids, no figure in a "
            "context line. Leave out a line you cannot fix fully.\n" + todo)
    try:
        out = ask_json("repair", system_prompt(profile, day and _day(day)), user, REPAIR_SCHEMA, model=SCRIPT_MODEL)
    except Exception:  # the briefing is still valid without the repair
        return kept, dropped, judged
    fixed, still = check_script(out.get("lines", []), facts, lang)
    fixed, still_judged = judge(fixed, facts)
    blocked_ids = {id(d) for d in blocked}
    for d in blocked:
        d["why"] = f'{d["why"]} (rewrite tried)'
    order = {s["id"]: n for n, s in enumerate(chosen)}
    story_of = {f["id"]: f["story_id"] for f in facts}
    lines = sorted(kept + fixed, key=lambda x: (order.get(story_of.get((x.get("fact_ids") or [""])[0]), 99),
                                               x.get("kind") == "context"))
    # the original wording stays visible as blocked, the rewrite (if it passed) is spoken
    return lines, dropped + [{**x, "why": f'rewrite blocked: {x["why"]}'} for x in still], judged + still_judged


RELATIVE_TIME = re.compile(r"\b(yesterday|today|tonight|tomorrow|last week|this week|next week|last night|"
                           r"gestern|heute|morgen früh|letzte woche|vorige woche|diese woche|nächste woche|"
                           r"gisteren|vandaag|(?<!am )(?<!guten )morgen|vorige week|deze week|volgende week|afgelopen week|"
                           # a weekday is relative too: the listener hears it on another day than the article's
                           r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|montag|dienstag|mittwoch|"
                           r"donnerstag|freitag|samstag|sonntag|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|"
                           r"zondag)\b", re.I)


def calls_by_name(text, name):
    """The greeting uses the listener's name or a clear part of it ("trader" for "FX trader",
    "Anleger" for "Privatanleger")."""
    low = text.lower()
    parts = [w for w in re.findall(r"\w+", name.lower()) if len(w) >= 2]
    return any(re.search(rf"\b{re.escape(w)}", low) for w in parts) or any(len(w) >= 5 and w in name.lower() for w in re.findall(r"\w+", low))


def tidy(text):
    """No space before punctuation, no dash as a pause (it reads badly on screen and in speech)."""
    text = re.sub(r"\s*[—–]\s*(?=\D)", ", ", text or "")
    return re.sub(r"\s+([!?.,;:])", r"\1", text).strip()


UNNAMED_START = re.compile(r"^(it|its|they|their|he|she|his|her|this|these|that|those|the (outage|company|firm|bank|"
                           r"agency|group|stock|shares|deal|index|report|move|decision|disruption|incident|attack|"
                           r"probe)|er|sie|es|dies|der (konzern|ausfall|vorfall|angriff|bericht)|"
                           r"die (bank|störung|firma|aktie|behörde)|das (unternehmen|papier)|zij|hij|dit|deze|dat|"
                           r"het (bedrijf|aandeel|incident)|de (bank|storing|aanval))\b"
                           # "The Bank of England", "This week's CPI" do name their subject
                           r"(?!\s+of\b|\s+week|\s+month|\s+year|\s+quarter|\s+morning)", re.I)
TOP_UP_BELOW = 0.8  # a briefing under 80 % of its requested length gets one more round of stories
TOP_UP_ROUNDS = 2   # one round left 95 of 324 editions under 80 % (eval/benchmark.py, 21.11.): the checker blocks
                    # lines of the new stories too


def top_up(profile, stories, facts, day, chosen, kept, reserved):
    """The checker removes lines, so a briefing can end far under the length the listener asked for. Then the
    next fitting stories are written in one more call and go through the same checks. Returns
    (chosen, kept, dropped)."""
    lang = profile["language"]
    budget = profile["seconds"] * WORDS_PER_SECOND[lang] - reserved
    used = sum(len(line["text"].split()) for line in kept)
    if used >= TOP_UP_BELOW * budget:
        return chosen, kept, []
    with_facts = {f["story_id"] for f in facts}
    taken = {s["id"] for s in chosen}
    pool = [s for s in stories if s["id"] in with_facts and s["id"] not in taken]
    if not pool:
        return chosen, kept, []
    rest = {**profile, "seconds": max(20, (budget - used) / WORDS_PER_SECOND[lang])}
    try:
        more, _ = select_stories(rest, pool, facts)
        out = ask_json("script", system_prompt(rest, day and _day(day)),
                       facts_prompt(more, facts, day) + "\n\nThe listener has already heard other stories: write only "
                       "the lines for these, no greeting and no sign-off.", SCHEMA, model=SCRIPT_MODEL)
    except Exception:  # the briefing is valid without the extra stories
        return chosen, kept, []
    new, dropped = check_script(out["lines"], facts, lang)
    new, judged = judge(new, facts)
    new, orphans = arrange(new, facts)
    kept, twice = dedupe(kept + new, facts, lang)
    return chosen + more, kept, dropped + judged + orphans + twice


def _telling(figures):
    """Figures that identify a piece of news: not a day of the month and not a year."""
    return {n for n in figures if not (n.is_integer() and (1 <= n <= 31 or 1900 <= n <= 2099))
            and n not in (1e3, 1e6, 1e9, 1e12)}  # "billion" alone is a scale, not a figure


def dedupe(lines, facts, lang):
    """The last word on repeats, over the whole briefing: rewrites from the repair round were only checked among
    themselves. A claim is a repeat when an earlier claim of the same story shares one of its figures."""
    story_of = {f["id"]: f["story_id"] for f in facts}
    kept, dropped = [], []
    told = set()  # stories that already have their "why it matters" line
    opened = set()  # stories that already have a claim
    for line in lines:
        stories = {story_of.get(i) for i in line["fact_ids"]}
        # the first claim of a story must say who or what it is about: "The outage hit 430 million people" alone
        # leaves the listener guessing which outage
        if line.get("kind", "claim") == "claim" and not stories & opened and UNNAMED_START.match(line["text"]):
            dropped.append({**line, "why": "does not name what the story is about"})
            continue
        if line.get("kind") == "context":
            if stories & told:
                dropped.append({**line, "why": "second context line for one story"})
                continue
            told |= stories
        if line.get("kind", "claim") == "claim":
            figures = numbers(line["text"], lang)
            if figures and any(k.get("kind", "claim") == "claim" and (
                    stories & {story_of.get(i) for i in k["fact_ids"]} and figures & numbers(k["text"], lang)
                    # the same event can sit in two stories (retail sales from two outlets): two shared figures
                    # that are not a day or a year are the same news told twice
                    or len(_telling(figures & numbers(k["text"], lang))) >= 2) for k in kept):
                dropped.append({**line, "why": "repeats an earlier line"})
                continue
            opened |= stories
        kept.append(line)
    return kept, dropped


def arrange(lines, facts):
    """A context line only stays if a claim of its story is spoken, and it goes right after that story's claims."""
    story_of = {f["id"]: f["story_id"] for f in facts}
    claims_of = {}
    for line in lines:
        if line.get("kind", "claim") == "claim":
            claims_of.setdefault(story_of[line["fact_ids"][0]], []).append(line)
    out, orphans = [], []
    for line in lines:
        line = {**line, "text": tidy(line["text"])}
        if line.get("kind") != "context":
            out.append(line)
            continue
        story = story_of[line["fact_ids"][0]]
        if story not in claims_of:
            orphans.append({**line, "why": "context for a story whose news was not spoken"})
            continue
        last = max(n for n, x in enumerate(out) if x.get("kind", "claim") == "claim"
                   and story_of[x["fact_ids"][0]] == story) if any(
            x.get("kind", "claim") == "claim" and story_of[x["fact_ids"][0]] == story for x in out) else None
        if last is None:  # the story's claims come later: hold the line until they are placed
            claims_of[story].append(None)
            out.append({**line, "_wait": story})
        else:
            out.insert(last + 1, line)
    # place held context lines after their story's last claim
    held = [x for x in out if x.get("_wait")]
    out = [x for x in out if not x.get("_wait")]
    for line in held:
        story = line.pop("_wait")
        last = max(n for n, x in enumerate(out) if x.get("kind", "claim") == "claim"
                   and story_of[x["fact_ids"][0]] == story)
        out.insert(last + 1, line)
    return out, orphans


def fit_length(lines, profile, reserved=None):
    """Hard cap by code: the model is told the length, the code makes sure of it.

    reserved: words of greeting, disclosure, sign-off and closing (default: the fixed opening and closing).
    """
    lang = profile["language"]
    if reserved is None:
        reserved = len(OPENING[lang].split()) + len(CLOSING[lang].split())
    budget = profile["seconds"] * WORDS_PER_SECOND[lang] * 1.1 - reserved
    kept, used = [], 0
    for n, line in enumerate(lines):
        used += len(line["text"].split())
        if used > budget and kept:  # cut the END, never a line in the middle of a story
            return kept, [{**x, "why": "over the requested length"} for x in lines[n:]]
        if used > budget:  # the first line alone is over: a few seconds long beats an empty briefing (nl 30 s, 21.11.)
            return [line], [{**x, "why": "over the requested length"} for x in lines[n + 1:]]
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
    dated = date_numbers(text)
    for s in fact["sources"]:
        nums |= numbers(s["quote"], s.get("language", "en"))  # "351.000 Barrel" in a German quote is 351000
        y, _, d = s["date"][:10].split("-")
        nums |= {float(y), float(d)} & dated
    return nums


def date_numbers(text):
    """Day and year numbers that stand right next to a month name: "18 November 2026", "November 18", "Nov. 2026"."""
    m = MONTH_WORDS.pattern[3:-3]  # the alternation without its \b( )\b
    found = set()
    for hit in re.finditer(rf"\b(\d{{1,2}})\.?\s+(?:{m})\b\.?(?:,?\s+(\d{{4}}))?|\b(?:{m})\b\.?\s+(\d{{1,4}})\b(?:,?\s+(\d{{4}}))?",
                           text, re.I):
        found |= {float(g) for g in hit.groups() if g}
    return found


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

# ---- numbers in the listener's language. Runs BEFORE the checks, so transcript, speech and check see one text.
_EN_NUMBER = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+)(?![\d]|[.,]\d)")
_CURRENCY = {"de": {"$": "Dollar", "€": "Euro", "¥": "Yen", "£": "Pfund"},
             "nl": {"$": "dollar", "€": "euro", "¥": "yen", "£": "pond"}}
_SCALE = {  # (English word or abbreviation after a digit, local word); case-sensitive: "Billion" is German
    "de": [(r"\btrillions?\b", "Billionen"), (r"\bbillions?\b|\bbillionen\b", "Milliarden"),
           (r"\bmillions?\b|\bmillionen\b", "Millionen"), (r"\bmilliarden\b", "Milliarden"),
           (r"(?<=\d)\s?(?:tn|T)\b", " Billionen"), (r"(?<=\d)\s?(?:bn|B)\b", " Milliarden"),
           (r"(?<=\d)\s?(?:mn|M)\b", " Millionen"),
           (r"\b(?:per ?cent|percent)\b", "Prozent"), (r"\bbasis points?\b", "Basispunkte")],
    "nl": [(r"\btrillions?\b", "biljoen"), (r"\bbillions?\b", "miljard"), (r"\bmillions?\b", "miljoen"),
           (r"(?<=\d)\s?(?:tn|T)\b", " biljoen"), (r"(?<=\d)\s?(?:bn|B)\b", " miljard"),
           (r"(?<=\d)\s?(?:mn|M)\b", " miljoen"),
           (r"\b(?:per ?cent|percent)\b", "procent"), (r"\bbasis points?\b", "basispunten")],
}
_SINGULAR = {"de": [(r"(?<![\d.,])\b1 Milliarden\b", "1 Milliarde"), (r"(?<![\d.,])\b1 Millionen\b", "1 Million"),
                    (r"(?<![\d.,])\b1 Billionen\b", "1 Billion")]}
# English words that give away an untranslated German or Dutch line ("US-Producer-Prices rose im Oktober").
# Also a whole untranslated sentence (found by eval/benchmark.py in Dutch editions, 21.11.): English function words
# that German and Dutch never use ("with no evidence it is", "could still access their accounts").
ENGLISH_GIVEAWAY = re.compile(r"\b(rose|fell|rises|jumped|climbed|slipped|gained|said|says|than|while|prices|shares|"
                              r"the(?!\s+(?-i:[A-Z])))\b"  # "The Gentlemen" is a name
                              # function words in lower case only: "After-Hours-Handel", "This Is Money" are German
                              # usage or names; "these" is Dutch for thesis, "of" Dutch for or
                              r"|(?-i:\b(with|could|their|because|which|would|about|from|those|that|you|your|"
                              r"as much as|plus or minus|called for|potentially|larger|revenue|interest rate)\b)"
                              r"|\bon \d{1,2} [a-z]", re.I)


def german_decimals(text, allowed):
    """'1.155' or '6.077' in a German or Dutch line is a thousand-dot number (1155), but when only the English decimal
    (1.155) is in the quotes, the writer kept the English decimal point: it becomes '1,155'. Until 21.11. the checker
    accepted such a line and the listener heard 6.077 million ETH as six thousand million (eval/benchmark.py)."""
    def fix(m):
        tok = m.group(0)
        return tok.replace(".", ",") if float(tok.replace(".", "")) not in allowed and float(tok) in allowed else tok
    return re.sub(r"(?<![\d.,])\d{1,3}\.\d{3}(?![\d]|[.,]\d)", fix, text)


def _swap_number(m):
    num = m.group(1)
    if "," in num:  # 1,234.5 -> 1.234,5
        return num.replace(",", "\0").replace(".", ",").replace("\0", ".")
    whole, frac = num.split(".")
    return num if len(frac) == 3 else f"{whole},{frac}"  # "1.000" is already German for a thousand


def localise(text, lang):
    """English number style in a German or Dutch line becomes local: 0.3 percent -> 0,3 Prozent,
    $10.5 billion -> 10,5 Milliarden Dollar. For transcript and speech alike; English text stays as it is."""
    if lang not in _SCALE:
        return text
    text = _EN_NUMBER.sub(_swap_number, text)
    for sym, name in _CURRENCY[lang].items():
        text = re.sub(rf"(?:US)?{re.escape(sym)}\s?(\d+(?:[.,]\d+)*(?:\s?(?:trillions?|billions?|millions?|tn|bn|mn|[TBM])\b)?)",
                      rf"\1 {name}", text)
    for pattern, repl in _SCALE[lang] + _SINGULAR.get(lang, []):
        text = re.sub(pattern, repl, text)
    return re.sub(r"\s{2,}", " ", text)


# A person named in a line must be named in one of its quotes: "Waller wants more hikes" once cited only the Williams
# article (fx-trader c8). The people come from the fact claims, where the fact prompt puts a title before the name
# ("Fed Governor Christopher Waller", "BoJ board member Hajime Takata"); the surname is what is checked.
_TITLED = re.compile(r"\b(?i:governor|president|chair(?:man|woman)?|ceo|minister|secretary|senator|commissioner|"
                     r"director|board member|member|economist|analyst|strategist|founder|chief executive)\s+"
                     r"((?:[A-Z][a-zA-Z'’-]+\s+){0,2}[A-Z][a-zA-Z'’-]+)")


def people(facts):
    """Surnames of the people the facts name with a title: {'Waller', 'Hammack', 'Ueda', ...}."""
    return {m.group(1).split()[-1] for f in facts for m in _TITLED.finditer(f.get("claim", ""))}


def unquoted_people(text, quotes, names, headlines=()):
    """The names spoken in `text` that none of its quotes contains ("Wallers" in German counts as Waller).

    A quote often says "the 63-year-old" or "he" where its own article's headline names the person ("Jensen Huang
    keeps door open ..."): that headline backs the name, but only when the quote names no other person, so a quote
    about Williams in an article headlined "Waller ..." still cannot carry Waller (on 18 Nov every Huang line was
    blocked for this, eval/benchmark.py must_hear)."""
    src = " ".join(quotes).lower()
    # the headline only stands in for a quote that names nobody ("The 63-year-old resigned"): no titled person, no
    # "First Last" name, and the line does not put words or a view in the person's mouth ("Huang said ...")
    nobody = not any(n.lower() in src for n in names) and not PERSON_NAME.search(" ".join(quotes))
    heads = " ".join(headlines).lower() if nobody and not ATTRIBUTION.search(text) else ""
    return sorted(n for n in names if re.search(rf"\b{re.escape(n)}", text) and n.lower() not in src
                  and n.lower() not in heads)


PERSON_NAME = re.compile(r"\b[A-Z][a-z]+ (?:[A-Z]\. )?[A-Z][a-z]{2,}\b")  # "John Williams", "Jerome H. Powell"
ATTRIBUTION = re.compile(r"\b(said|says|told|argues?|argued|wants?|wanted|calls? for|called for|warns?|warned|"
                         r"expects?|expected|believes?|thinks?|sees|saw|predicts?|sagte|sagt|fordert|warnt|erwartet|"
                         r"meint|zei|zegt|wil|waarschuwt|verwacht)\b", re.I)


# "after hours", "premarket" and their German and Dutch words say WHEN a move happened. "Nvidia rose 1.6 percent in
# after-hours trading" was wrong although 1.6 is in the quote: the 1.6 % was regular trading (privatanleger c2).
# Each pair: the words in a spoken line, and the words in a quote (any language) that back them.
SESSIONS = [
    (re.compile(r"\b(after[- ]?hours|extended trading|post-?market|nachbörs|nabeurs)", re.I),
     re.compile(r"\b(after[- ]?hours|extended trading|post-?market|after the (bell|close)|late trading|nachbörs|"
                r"nach (handels|börsen)schluss|nabeurs|na (de )?(sluiting|slotbel))", re.I)),
    (re.compile(r"\b(pre-?market|vorbörs|voorbeurs)", re.I),
     re.compile(r"\b(pre-?market|before the (bell|open)|ahead of the (bell|open)|vorbörs|vor (handels|börsen)beginn|"
                r"vor (der )?börseneröffnung|voorbeurs|voor (de )?(opening|openingsbel))", re.I)),
]


def unsupported_session(text, quotes):
    """The time qualifier a line speaks ("nachbörslich") if no quote says the same, else None."""
    src = " ".join(quotes)
    for spoken, backed in SESSIONS:
        m = spoken.search(text)
        if m and not backed.search(src):
            return m.group(0)
    return None


ADVICE = re.compile(r"\b(buy|buying|sell(?!-)|selling|invest(ing)?|you should|time to|kauf\w*|verkauf\w*|investier\w*|"
                    r"solltest|lohnt sich|koop\w*|kopen|verkoop\w*|verkopen|investeer\w*|zou je moeten)\b", re.I)
BARE_NUMBER_START = re.compile(r"^\W*\d")
DASH = re.compile(r"(?<!\d)\s+[—–-]\s+|\s+[—–-]\s+(?!\d)")  # a pause, not a range "3.75 - 4.00": comma


def check_host(text, lang, max_words):
    """Greeting or sign-off by the model: returns (text, None) or (None, why). Free text in speech, so strict."""
    text = DASH.sub(", ", re.sub(r"\s+", " ", FACT_ID.sub("", text or ""))).strip()
    if not text:
        return None, "host line empty"
    if re.search(r"\d", text) or numbers(text, lang):
        return None, "host line has a number"
    if len(text.split()) > max_words:
        return None, f"host line longer than {max_words} words"
    if ADVICE.search(text):
        return None, "host line sounds like advice"
    if unsupported_superlatives(text, []):
        return None, "host line has a superlative"
    if lang != "en" and ENGLISH_GIVEAWAY.search(text):
        return None, "host line not in the listener's language"
    return text, None


def check_script(raw_lines, facts, lang):
    """Each raw line: {'text', 'fact_ids', 'kind'} (kind "claim" if missing). Returns (kept, dropped)."""
    by_id = {f["id"]: f for f in facts}
    names = people(facts)
    kept, dropped, context_for = [], [], set()
    for line in raw_lines:
        kind = line.get("kind") if line.get("kind") in LINE_KINDS else "claim"
        text = FACT_ID.sub("", line["text"]).strip()  # ids belong in fact_ids, never in speech
        text = STOCK_PHRASES.sub("", text).strip()    # filler at the start goes, the sentence stays
        text = localise(DASH.sub(", ", text), lang)   # what is checked is exactly what is shown and spoken
        if not text:
            continue
        line = {**line, "text": text[0].upper() + text[1:], "kind": kind}
        ids = [i for i in line["fact_ids"] if i in by_id]
        if not ids:  # every spoken line needs a verified source, also a "harmless" short one
            dropped.append({**line, "why": "no source"})
            continue
        allowed = set().union(*(allowed_numbers(by_id[i], line["text"]) for i in ids))
        if lang != "en":  # "6.077 million" from an English quote said as "6.077 Millionen" is 6,077 million in German
            line["text"] = german_decimals(line["text"], allowed)
        spoken = numbers(line["text"], lang)
        missing = spoken - allowed
        if missing:
            dropped.append({**line, "why": f"numbers not in sources: {sorted(missing)}"})
            continue
        quotes = [s["quote"] for i in ids for s in by_id[i]["sources"]]
        sup = unsupported_superlatives(line["text"], quotes)
        if sup:
            dropped.append({**line, "why": f"superlative not in sources: {sup}"})
            continue
        who = unquoted_people(line["text"], quotes, names,
                              [s.get("headline", "") for i in ids for s in by_id[i]["sources"]])
        if who:
            dropped.append({**line, "why": f"person not in its quotes: {', '.join(who)}"})
            continue
        when = unsupported_session(line["text"], quotes)
        if when:
            dropped.append({**line, "why": f"time qualifier not in its quotes: {when}"})
            continue
        if BARE_NUMBER_START.match(line["text"]):
            dropped.append({**line, "why": "starts with a bare number"})
            continue
        if len(line["text"].split()) > 45:  # one sentence, one story: a listener cannot scroll back
            dropped.append({**line, "why": "too long for the ear (over 45 words)"})
            continue
        if RELATIVE_TIME.search(line["text"]):  # the briefing is heard on another day than the article was written
            dropped.append({**line, "why": "relative date (say the date instead)"})
            continue
        opening = " ".join(line["text"].lower().split()[:5])
        # the same figures again (two or more) is the same news, however it is worded
        # the same fact told again with one of its figures is a repeat too ("rose 0.2 percent" twice)
        if any(" ".join(k["text"].lower().split()[:5]) == opening
               or (len(spoken) >= 2 and numbers(k["text"], lang) >= spoken)
               or (spoken & numbers(k["text"], lang) and set(ids) & set(k["fact_ids"])) for k in kept):
            dropped.append({**line, "why": "repeats an earlier line"})
            continue
        if lang != "en" and ENGLISH_GIVEAWAY.search(line["text"]):
            dropped.append({**line, "why": "English words in a non-English line"})
            continue
        if kind == "context":
            story = by_id[ids[0]]["story_id"]
            if ADVICE.search(line["text"]):
                dropped.append({**line, "why": "context sounds like advice"})
                continue
            if re.search(r"\d", line["text"]):  # a reading, not a repeat of the figures
                dropped.append({**line, "why": "context line with a figure"})
                continue
            if story in context_for:
                dropped.append({**line, "why": "second context line for one story"})
                continue
            context_for.add(story)
        kept.append({"text": line["text"], "fact_ids": ids, "kind": kind})
    return kept, dropped


# A second, independent look by a cheap model: does each line say only what its quotes say?
# The code checks numbers and words; this catches wrong direction, invented causes, advice and relative dates.
JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["verdicts"],
    "properties": {"verdicts": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["n", "supported", "why"],
        "properties": {"n": {"type": "integer"}, "supported": {"type": "boolean"}, "why": {"type": "string"}}}}},
}
JUDGE_SYSTEM = """You are a strict fact checker for a radio news script. Each numbered line has a KIND and the
quoted source sentences it cites. Mark a line supported=false if it breaks a rule of its kind.

KIND claim (news) is unsupported if:
- it states something the quotes do not say: another subject, direction up or down, size, time, company or
  person, or a cause or consequence the quotes do not state; a change said as a level or a level as a change
  ("rose 0.3%" is not "rose to 0.3%", German "um" is not "auf", Dutch "met" is not "naar");
- it links two facts with "as", "while", "so", "because", "after", "amid", "weil", "während", "nachdem",
  "terwijl", "omdat", "doordat" or a similar link that no quote states;
- it gives one person's or one outlet's opinion, forecast or preference as a fact or as a consensus without
  naming whose view it is (e.g. "25 bp is the lean for the Fed meeting" when the quote is one official's
  remarks; the official must be named);
- it uses a judging word the quotes do not have and do not mean ("sticky", "fragile", "hot", "solid", "strong").
KIND context (the host's reading of why a story matters to THIS listener) is allowed interpretation: saying
why it matters, what it is relevant to, or how such news works in general is its job, do NOT reject it for
that. It is unsupported only if it adds a new fact, number, event, person or cause about this story that the
quotes do not have, links two facts as cause and effect or as depending on each other when no quote does,
or predicts a price, a rate decision or a market move.
KIND host (greeting or sign-off) is unsupported if it states any fact, event, number, name or prediction;
naming the topics in general words is fine.
EVERY kind is unsupported if it tells listeners what to do with money (what they can or should buy, sell or
hold), or if it uses yesterday, tonight, this week or a weekday (claim and context lines: also "today").
Enthusiasm, exclamation marks, addressing the listener and a plain explanation of a term are fine.
Return one verdict per line, with a short reason when unsupported."""


def judge(lines, facts):
    if not lines:
        return lines, []
    by_id = {f["id"]: f for f in facts}
    listing = []
    for n, line in enumerate(lines):
        quotes = " | ".join(f"{s['publisher']} ({_day(s['date'])}): \"{s['quote']}\""
                            for i in line["fact_ids"] for s in by_id[i]["sources"])
        listing.append(f"{n}. KIND: {line.get('kind', 'claim')}\n   LINE: {line['text']}\n   QUOTES: {quotes or '(none)'}")
    verdicts = ask_json("judge", JUDGE_SYSTEM, "\n".join(listing), JUDGE_SCHEMA)["verdicts"]
    bad = {v["n"]: v["why"] for v in verdicts if not v["supported"] and 0 <= v["n"] < len(lines)}
    seen = {v["n"] for v in verdicts}
    # fail closed: a line the judge did not rule on is not spoken
    bad.update({n: "no verdict for this line" for n in range(len(lines)) if n not in seen})
    kept = [line for n, line in enumerate(lines) if n not in bad]
    return kept, [{**lines[n], "why": f"content check: {why}"} for n, why in bad.items()]
