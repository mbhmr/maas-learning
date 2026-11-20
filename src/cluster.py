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
# Buy/sell pitches are dropped up front: the briefing must not give investment advice.
ADVICE = re.compile(r"\b(stocks? to buy|buy now|should you (invest|buy)|investing radar|strong buy|top-ranked)\b", re.I)
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
    arts = [a for a in arts if not ADVICE.search(a["headline"])]
    originals, translations = link_translations(arts)
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
