"""Group articles about the same event into stories, in plain code (no model, no cost).

1. Invezz German and Dutch articles are translations of an English one (same
   author, within 15 minutes). They are attached to it, not clustered.
2. The rest is compared by TF-IDF word overlap of headline and the first
   1,000 characters (cosine similarity). Word weights come from the whole
   dataset, so template phrases ("since last earnings report") count little.
   An article joins the story whose members are, on average, similar enough.
3. Buy/sell pitches are dropped, different tickers never merge.
4. Stories are ranked: more independent outlets first, then more articles,
   then macro and market sections, then recency.
"""
import math
import re
from collections import Counter
from datetime import datetime

STOP = set("""the a an and or of to in on for with at by from as is are was were be been it its this that these those
has have had not but than then into over after before about after says said say will would could can may might new
more most up down out off why what how who when here there their they you your our we he she his her them which also
just amid ahead still after week day today monday tuesday wednesday thursday friday saturday sunday
stock stocks shares share price prices market markets news report us usd per cent percent""".split())

SIMILAR = 0.27  # tuned on known pairs: same event 0.28 to 0.44, different events up to 0.24
LEAD = 1000
TRANSLATION_MINUTES = 15
# Buy/sell pitches are dropped up front: the briefing must not give investment advice. News ABOUT a rating
# ("Anthropic receives its first 'Buy' rating") is news and stays, so there is no "buy rating" pattern.
ADVICE = re.compile(r"\b(stocks? to buy|buy now|should you (invest|buy)|investing radar|strong buy|top-ranked|"
                    r"(a|good) (stock to )?buy\b|buy or sell|time to buy|worth buying|bull of the day|bear of the day)", re.I)
# Round-ups cover many events at once; mixing them into one story would glue unrelated news together.
ROUNDUP = re.compile(r"\b(evening digest|morning (digest|brief)|things to know|what to watch|week ahead|"
                     r"weekly (recap|wrap)|market wrap|stocks? to watch|abendbericht|morgenbericht|wochenausblick|avondbericht|ochtendbericht|avondoverzicht|ochtendoverzicht|abend-update|morgen-update|"
                     r"abend-report|morgen-report|\d+ dinge|\d+ dingen|dingen om te weten|dinge vor handelsbeginn)\b", re.I)
PRIORITY_SECTIONS = {"fed", "ecb", "boj", "boe", "inflation", "central banks", "economy", "united states",
                     "stock market", "earnings", "world", "politics", "business"}


def _ts(a):
    return datetime.fromisoformat(a["date"])


def link_translations(arts):
    """Return (originals, {original_id: {lang: translated_id}})."""
    en = [a for a in arts if a["feed"] == "invezz_en"]
    links, originals = {}, []
    for a in arts:
        if a["feed"] not in ("invezz_de", "invezz_nl"):
            originals.append(a)
            continue
        match = min((e for e in en if e.get("author") == a.get("author")),
                    key=lambda e: abs((_ts(e) - _ts(a)).total_seconds()), default=None)
        if match and abs((_ts(match) - _ts(a)).total_seconds()) <= TRANSLATION_MINUTES * 60:
            links.setdefault(match["id"], {})[a["language"]] = a["id"]
        else:
            originals.append(a)  # no English twin: treat as its own article
    return originals, links


def _tokens(a):
    text = f"{a['headline']} {a['headline']} {a['excerpt']} {a['text'][:LEAD]}".lower()
    return [w for w in re.findall(r"[a-z][a-z0-9\-]{2,}", text) if w not in STOP]


def idf_table(corpus):
    """Inverse document frequency over a large set of articles (the whole dataset)."""
    df = Counter(w for a in corpus for w in set(_tokens(a)))
    n = len(corpus)
    return {w: math.log(n / c) for w, c in df.items()}, math.log(n)


def _vector(a, idf):
    table, default = idf
    v = {w: (1 + math.log(c)) * table.get(w, default) for w, c in Counter(_tokens(a)).items()}
    norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return {w: x / norm for w, x in v.items()}


def _cos(u, v):
    if len(u) > len(v):
        u, v = v, u
    return sum(x * v.get(w, 0.0) for w, x in u.items())


def cluster(arts, corpus):
    """Group arts (one news day) into ranked stories. corpus: all articles, for word weights.

    Returns [{'id', 'rank', 'title', 'article_ids', 'publishers', 'score', 'translations'}].
    """
    # translations are linked FIRST, so a dropped English round-up or pitch takes its German and Dutch twins with it
    # ("5 Dinge vor Handelsbeginn" survived as its own story while only the English headline was filtered)
    originals, translations = link_translations(arts)
    originals = [a for a in originals if not ADVICE.search(a["headline"]) and not ROUNDUP.search(a["headline"])]
    originals.sort(key=_ts)
    tickers = [set(re.findall(r"\(([A-Z]{1,5})\)", a["headline"])) for a in originals]
    idf = idf_table([a for a in corpus if a["feed"] not in ("invezz_de", "invezz_nl")])
    vecs = [_vector(a, idf) for a in originals]
    groups = []  # lists of indices into originals
    for i, v in enumerate(vecs):
        best, best_sim = None, SIMILAR
        for g in groups:
            if tickers[i] and any(tickers[j] and not tickers[i] & tickers[j] for j in g):
                continue  # different companies, e.g. two Zacks earnings templates
            sim = sum(_cos(v, vecs[j]) for j in g) / len(g)  # average link: no chaining
            if sim >= best_sim:
                best, best_sim = g, sim
        if best is None:
            groups.append([i])
        else:
            best.append(i)

    stories = []
    for g in groups:
        members = [originals[i] for i in g]
        publishers = sorted({a["publisher"] for a in members})
        sections = {s.lower() for a in members for s in a["sections"]}
        latest = max(_ts(a) for a in members)
        score = (3.0 * len(publishers) + 1.0 * len(members)
                 + (1.5 if sections & PRIORITY_SECTIONS else 0.0) + latest.hour / 100)
        # title from the most central article: the one closest to all others
        lead = originals[max(g, key=lambda i: sum(_cos(vecs[i], vecs[j]) for j in g))]
        stories.append({
            "title": lead["headline"], "article_ids": [a["id"] for a in members],
            "publishers": publishers, "score": round(score, 2),
            "translations": {a["id"]: translations[a["id"]] for a in members if a["id"] in translations},
        })
    stories.sort(key=lambda s: -s["score"])
    for n, s in enumerate(stories, 1):
        s["rank"], s["id"] = n, f"s{n}"
    return stories


# ---------------------------------------------------------------------------
# Step 2: one cheap model call over the story TITLES only (no article text),
# checked by code. Merges what TF-IDF split (an ongoing story told over days)
# and rates how much each story matters to a financial newsroom.
# ---------------------------------------------------------------------------

MERGE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["merge", "importance"],
    "properties": {
        "merge": {"type": "array", "description": "groups of story ids that are the same event or ongoing story",
                  "items": {"type": "array", "items": {"type": "string"}}},
        "importance": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "score", "topic"],
            "properties": {"id": {"type": "string"}, "score": {"type": "integer", "description": "1 to 5"},
                           "topic": {"type": "string", "enum": ["central banks and macro", "currencies", "markets",
                                                                "companies and tech", "crypto", "energy and commodities",
                                                                "politics and world", "entertainment and lifestyle",
                                                                "crime and accidents", "other"]}}}},
    },
}

MERGE_SYSTEM = """You are the editor of a financial newsroom. You get a list of story ids with their headlines.
1. merge: list groups of ids that report the SAME event or the same ongoing story (same company or institution
   and the same development, e.g. a CEO resigning and the fallout in the following days). Do not merge stories
   that merely share a sector or a company. Leave everything else out.
2. importance: for EVERY id, a score from 5 (moves markets or affects many people: central bank decisions,
   major data releases, very large companies) to 1 (gossip, minor single-company notes), and one topic."""

_NAME = re.compile(r"\b[A-Z][a-zA-Z&\-]{2,}\b(?!')")  # not "Don" from "Don't"
_NOT_NAME = {"The", "Why", "What", "How", "Is", "Are", "Can", "Will", "This", "These", "After", "Before", "Here",
             "New", "Stock", "Stocks", "Shares", "Price", "Today", "US", "Its", "From", "With", "For", "And"}


COMMON = set("""his her him she who was did you now just out over says said claims calls reveals report reports
warns amid about could down not while during former family man woman after before into first last next big top
why what how when where new could should would year years day days week weeks time back
ceo cfo coo cto ipo etf etfs wall street january february march april may june july august september october
november december""".split())  # job titles, instruments and months are written in capitals but name no event
# Names that are a place or a data series, not the subject of one event: alone they never join two stories.
# Seen gluing: "Canada CPI" + "Eurozone ... Core CPI" + "UK ... Core CPI", "Trump ... in China" + "China Industrial
# Output", "America's shopping trolley" + "Captain America". A second shared name ("Huang" next to "China") still joins.
WEAK = set("""cpi ppi gdp hicp pmi pce core inflation retail sales output industrial jobs payrolls yields treasury
america american china chinese japan japanese canada canadian europe european eurozone britain british germany
german france french india russia ukraine israel iran texas california illinois florida washington london beijing
tokyo""".split())
RARE_SHARE = 0.05    # a shared name only counts if at most 5 % of stories carry it ("Huang" yes, "Trump" no)
FRESH = 5.0           # score bonus for a story whose newest article is from the last hours of the window
HALF_LIFE_HOURS = 24  # ... halved every 24 hours: 5 just now, 2.5 a day old, 1.25 two days old, 0.16 five days old


def _names(story):
    words = {w.lower() for h in story["all_headlines"] for w in _NAME.findall(h) if w not in _NOT_NAME}
    return words - STOP - COMMON


def _core_names(story):
    """Names of the title plus names in at least half of the story's own headlines.

    "NVIDIA Leadership Crisis ... ETFs in Focus" names no person, its second headline says "Jensen Huang saga":
    the title alone misses that. A name in one of 23 headlines does not count, so a big story stays its own
    topic and cannot reach out to everything ("outage" once pulled a bank outage into a flight ground stop).
    """
    heads = story["all_headlines"]
    count = Counter(n for h in heads for n in _names({"all_headlines": [h]}))
    return _names({"all_headlines": [story["title"]]}) | {n for n, c in count.items() if 2 * c >= len(heads)}


def proper_names(articles):
    """Words that are written with a capital letter in running text too: 'Huang', 'FAA', not 'Stop' or 'Know'.

    Headlines are in Title Case, so a capital letter there proves nothing; the article bodies decide.
    """
    cap, low, first = Counter(), Counter(), Counter()
    for a in articles:
        # mid-sentence words only; `nxt` tells whether another capitalised word follows ("Donald Trump")
        for w, nxt in re.findall(r"(?<=[a-z,;] )([A-Za-z][a-zA-Z&\-]{2,})(?= ([A-Z])?)", a["text"]):
            (cap if w[0].isupper() else low)[w.lower()] += 1
            if w[0].isupper() and nxt:
                first[w.lower()] += 1
    # first names ("Donald", "Robert") glue unrelated people together: only surnames and other names count
    return {w for w, c in cap.items() if c >= 2 and c >= 4 * low[w] and first[w] < 0.6 * c}


# A question or a forecast in the headline is opinion about the news, not the news ("will oil crash below $90?",
# "analyst sees upside", "Play the dollar's gain with these ETFs"): it should not outrank a data release.
SPECULATION = re.compile(r"\?|\b(analysis|forecast|outlook|prediction|what's next|could|should you|is it time|"
                         r"price target|sees upside|to buy|buy now|play|etfs? in focus|top picks?)\b", re.I)
MACRO_TOPICS = {"central banks and macro", "currencies"}


def rank_score(story, n_articles, fresh):
    """Importance leads (5 per point), then outlets, size and freshness. Measured on the answer key (20.11.):
    with 3 per point and no macro bonus 3 of 8 must-hear events were in the top 10, with this 6 of 8."""
    return round(5 * story["importance"] + 2 * len(story["publishers"]) + math.log2(1 + n_articles) + fresh
                 + (4 if story["topic"] in MACRO_TOPICS else 0) - (6 if SPECULATION.search(story["title"]) else 0), 2)


def freshness(latest, end):
    """The briefing is for the morning after `end`: news of the last 24 to 48 hours counts clearly more.

    Measured from the story's NEWEST article, so a big story that ran all week and is still reported stays fresh.
    """
    hours = max(0.0, (end - latest).total_seconds() / 3600)
    return FRESH * 0.5 ** (hours / HALF_LIFE_HOURS)


def merge_and_rate(stories, articles, ask_json, end_day):
    """Returns re-ranked stories. The model only proposes; a merge needs a shared name in the headlines."""
    for s in stories:
        s["all_headlines"] = [articles[i]["headline"] for i in s["article_ids"]]
    listing = "\n".join(f"{s['id']}: " + " | ".join(s["all_headlines"][:3]) for s in stories)
    # 8,000 output tokens take about two minutes: the 60 s listener timeout would kill this once-a-day call
    out = ask_json("merge", MERGE_SYSTEM, listing, MERGE_SCHEMA, max_tokens=20000, timeout=600)
    by_id = {s["id"]: s for s in stories}

    # names are fixed BEFORE merging, so a growing story cannot collect ever more names and swallow everything
    # ("outage", "flight" in one of 23 headlines once pulled in a bank outage). The seed (bigger story) offers
    # only the names of its TITLE. The joining story matches with its own title, or with names from its other
    # headlines (_core_names) only if TWO names agree: "Jensen Huang saga" + "NVIDIA" joins the Huang story,
    # a lone "Bitcoin" in one of two Solana headlines does not join the Bitcoin story.
    proper = proper_names([articles[i] for s in stories for i in s["article_ids"]])
    title_names = {s["id"]: _names({"all_headlines": [s["title"]]}) & proper for s in stories}
    names = {s["id"]: _core_names(s) & proper for s in stories}
    df = Counter(n for s in stories for n in _names(s))  # rarity over ALL headlines: "Trump", "Nvidia" are common
    rare = {n for n, c in df.items() if c <= max(3, RARE_SHARE * len(stories))} - WEAK

    def joins(i, h):
        shared = names[i] & title_names[h]
        return bool(title_names[i] & title_names[h] & rare) or (bool(shared & rare) and len(shared) >= 2)
    merged_into, merges, refused = {}, 0, []
    for group in out["merge"]:
        ids = [i for i in dict.fromkeys(group) if i in by_id and i not in merged_into]
        if len(ids) < 2:
            continue
        # split the proposal by code: biggest story first, every other story joins the first seed that shares
        # a rare proper name with it (names fixed above), otherwise it stays on its own
        seeds = []
        for i in sorted(ids, key=lambda i: -len(by_id[i]["article_ids"])):
            head = next((h for h in seeds if joins(i, h)), None)
            if head is None:
                seeds.append(i)
                continue
            h, o = by_id[head], by_id[i]
            h["article_ids"] += o["article_ids"]
            h["all_headlines"] += o["all_headlines"]
            h["translations"].update(o["translations"])
            merged_into[i] = head
            merges += 1
        if len(seeds) > 1:
            refused.append((f"{len(seeds) - 1} of {len(ids)} proposed stories kept apart, no shared name",
                            by_id[seeds[0]]["title"]))

    rating = {r["id"]: r for r in out["importance"] if r["id"] in by_id}
    end = datetime.fromisoformat(end_day + "T23:59:59+00:00")
    result = []
    for s in stories:
        if s["id"] in merged_into:
            continue
        members = [articles[i] for i in s["article_ids"]]
        s["publishers"] = sorted({a["publisher"] for a in members})
        r = rating.get(s["id"], {"score": 2, "topic": "other"})
        s["importance"], s["topic"] = max(1, min(5, r["score"])), r["topic"]
        s["latest"] = max(a["date"] for a in members)
        s["score"] = rank_score(s, len(members), freshness(max(_ts(a) for a in members), end))
        result.append(s)
    result.sort(key=lambda s: -s["score"])
    for n, s in enumerate(result, 1):
        s["rank"], s["id"] = n, f"s{n}"
    return result, {"merges": merges, "refused": refused, "proposed": out["merge"]}
