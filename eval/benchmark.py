"""Our own jury benchmark: every briefing scored on what the Sourcera jury checks. Offline except --fit.

    .venv/Scripts/python eval/benchmark.py                                   cached demo briefings of 2026-11-18
    .venv/Scripts/python eval/benchmark.py --day 2026-11-18 --folder output/pregen/2026-11-18-flex
    .venv/Scripts/python eval/benchmark.py --fit                             plus a model's listener-fit verdict

Checks per briefing (a briefing passes a check only if every line passes it):
  sourced       every news line (claim, context) has a source with a link and a quote
  figures       every figure a claim speaks is in one of its quotes (own number reading, not the pipeline's)
  dates         every date a line speaks ("18 November") is the date of one of its sources or in a quote
  disclosure    the AI-voice line and the "not investment advice" line are there
  no_advice     no buy/sell/should-invest words in any spoken line
  language      every line with enough function words reads as the listener's language
  length        spoken length within 25 % of the request (audio timing if there is audio, else words / rate)
  audio         the speech-recognition re-check heard every figure as written (briefings with audio only)
  must_hear     the briefing speaks the most important story of the day it can: the highest-ranked must-hear
                story (central banks, macro, or two or more outlets) among the stories its listener was offered
  fit           (--fit) a small model rates how well the spoken stories fit the listener description, 1 to 5;
                passes at 4 or 5
A check that does not apply (no audio) counts as not applicable, not as passed.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.facts import numbers  # noqa: E402

MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
          "september": 9, "october": 10, "november": 11, "december": 12, "januar": 1, "februar": 2, "märz": 3,
          "mai": 5, "juni": 6, "juli": 7, "oktober": 10, "dezember": 12, "januari": 1, "februari": 2, "maart": 3,
          "mei": 5, "augustus": 8}
DATE = re.compile(r"\b(\d{1,2})\.?\s+(" + "|".join(MONTHS) + r")\b|\b("
                  + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
DAY_FIRST = re.compile(r"\b(\d{1,2})\.?\s+(" + "|".join(MONTHS) + r")\b", re.I)  # de, nl: "im November 5 Prozent"
SCALES = {1e3, 1e6, 1e9, 1e12}
# words that exist in two of the languages ("in", "is") are left out
STOP = {"en": {"the", "and", "of", "to", "for", "that", "with", "on", "its", "was", "has", "are", "your"},
        "de": {"der", "das", "und", "ist", "mit", "für", "auf", "von", "den", "dem", "nicht", "sich", "dein"},
        "nl": {"de", "het", "een", "en", "van", "met", "voor", "op", "dat", "niet", "zijn", "je", "naar"}}
# Advice is a sentence telling the listener what to do, not a word: "verkopen" is also Dutch for "sales", "sell-off"
# and "buy rating" are news. So: the listener as the one who buys, sells or invests, or an imperative to do so.
ADVICE = re.compile(r"\b(you (should|could|might want to|may want to|need to) (buy|sell|invest|hold|get in)|"
                    r"(buy|sell) (now|the dip|before)|(now is a|good) time to (buy|sell|invest|get in)|"
                    r"solltest( du)? (\w+ )?(kaufen|verkaufen|investieren|einsteigen)|"
                    r"jetzt (kaufen|verkaufen|einsteigen)|lohnt sich (der kauf|ein einstieg)|zou je moeten|"
                    r"moet je (\w+ )?(kopen|verkopen|beleggen)|(nu|snel) (kopen|verkopen|instappen))\b", re.I)
# "8 and 9 December" (the 8 is a date too) and "December 8-9" (so is the 9)
RANGE_BEFORE = re.compile(r"\b(\d{1,2})\.?\s*(?:-|–|to|and|en|und|bis|tot)\s*(?=\d{1,2}\.?\s+(" + "|".join(MONTHS)
                          + r")\b)", re.I)
RANGE_AFTER = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+\d{1,2}\s*(?:-|–|to|and)\s*(\d{1,2})\b", re.I)
WPS = {"en": 2.45, "de": 2.25, "nl": 2.2}
AI_WORDS = {"en": "ai voice", "de": "ki-stimme", "nl": "ai-stem"}
NO_ADVICE = {"en": "not investment advice", "de": "keine anlageberatung", "nl": "geen beleggingsadvies"}
NEWS = ("claim", "context")


def dates_in(text, lang="en"):
    """{(month, day)}; month first ("November 18") only in English. A range gives both days."""
    out = set()
    for m in (DATE if lang == "en" else DAY_FIRST).finditer(text):
        day, month = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        out.add((MONTHS[month.lower()], int(day)))
    for m in RANGE_BEFORE.finditer(text):
        out.add((MONTHS[m.group(2).lower()], int(m.group(1))))
    for m in RANGE_AFTER.finditer(text) if lang == "en" else ():
        out.add((MONTHS[m.group(1).lower()], int(m.group(2))))
    return out


def strip_dates(text, lang="en"):
    text = RANGE_BEFORE.sub(" ", text)
    if lang == "en":
        text = RANGE_AFTER.sub(" ", text)
    return (DATE if lang == "en" else DAY_FIRST).sub(" ", text)


def line_figures(text, lang):
    return {x for x in numbers(strip_dates(text, lang), lang) if x not in SCALES}


def quote_figures(quotes):
    """A quote may be English or the source's own language: read it both ways, and allow the scale-free form
    ("1.5 trillion" spoken as "1,5 Billionen" is 1.5 and 1e12 on both sides)."""
    found = set()
    for q in quotes:
        found |= numbers(q, "en") | numbers(q, "de")
    return {x for x in found if x not in SCALES}


def language_of(text):
    words = re.findall(r"[a-zäöüß]+", text.lower())
    hits = {lang: sum(w in stop for w in words) for lang, stop in STOP.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] >= 2 and list(hits.values()).count(hits[best]) == 1 else None


def check(briefing, stories=None):
    """{check: (passed True/False/None, [problems])} for one briefing dict."""
    lang = briefing["profile"]["language"]
    claims = [c for c in briefing["claims"] if c.get("text")]
    news = [c for c in claims if c["kind"] in NEWS]
    res = {}

    bad = [c["text"] for c in news if not c["sources"] or not all(s.get("url") and s.get("quote") for s in c["sources"])]
    res["sourced"] = (not bad and bool(news), bad or ([] if news else ["no news line"]))

    bad = []
    for c in news:
        if c["kind"] != "claim":
            continue
        years = {float(s["date"][:4]) for s in c["sources"] if s.get("date")}  # "October 2026" is a date
        missing = line_figures(c["text"], lang) - quote_figures([s["quote"] for s in c["sources"]]) - years
        if missing:
            bad.append(f"{sorted(missing)} in: {c['text']}")
    res["figures"] = (not bad, bad)

    bad = []
    for c in news:
        said = dates_in(c["text"], lang)
        if not said:
            continue
        known = {(int(s["date"][5:7]), int(s["date"][8:10])) for s in c["sources"] if s.get("date")}
        for s in c["sources"]:
            known |= dates_in(s["quote"])
        if said - known:
            bad.append(f"{sorted(said - known)} in: {c['text']}")
    res["dates"] = (not bad, bad)

    low = " ".join(c["text"].lower() for c in claims if c["kind"] == "disclosure")
    bad = [w for w in (AI_WORDS[lang], NO_ADVICE[lang]) if w not in low]
    res["disclosure"] = (not bad, bad)

    bad = [c["text"] for c in claims if c["kind"] != "disclosure" and ADVICE.search(c["text"])]
    res["no_advice"] = (not bad, bad)

    bad = [f"{language_of(c['text'])}: {c['text']}" for c in claims
           if language_of(c["text"]) not in (None, lang)]
    res["language"] = (not bad, bad)

    want = briefing["profile"]["seconds"]
    timed = [c for c in claims if c.get("end") is not None]
    spoken = timed[-1]["end"] if timed and briefing.get("audioPath") else \
        sum(len(c["text"].split()) for c in claims) / WPS[lang]
    res["length"] = (abs(spoken - want) <= 0.25 * want, [f"{spoken:.0f} s spoken, {want} s asked"])

    ac = briefing.get("audioCheck")
    if not briefing.get("audioPath") or ac is None:
        res["audio"] = (None, ["no audio"])
    else:
        problems = [f"{m.get('expected')} heard as {m.get('heard')}" for m in ac.get("mismatches", [])]
        if ac.get("error"):
            problems.append(f"check failed: {ac['error']}")
        res["audio"] = (not problems and ac.get("ok") == ac.get("checked"), problems)

    if stories is not None:
        res["must_hear"] = must_hear(briefing, stories)
    return res


def must_have(story):
    from prepare import must_have as rule  # the same definition the preparation uses
    return rule(story)


def must_hear(briefing, stories):
    """The listener was offered the stories in briefing['stories'] (the selection plus top-up) by title. A must-hear
    story the listener's topics cover should be spoken: we take the highest-ranked must-hear story whose topic
    one of the spoken stories shares, and ask that it is among the spoken stories."""
    spoken_titles = {s["title"] for s in briefing.get("stories", [])}
    spoken = [s for s in stories if s["title"] in spoken_titles]
    if not spoken:
        return (False, ["no story spoken"])
    topics = {s.get("topic") for s in spoken}
    with_facts = [s for s in stories if s.get("selected")]
    candidates = sorted((s for s in with_facts if must_have(s) and s.get("topic") in topics), key=lambda s: s["rank"])
    if not candidates:
        return (None, ["no must-hear story in this listener's topics"])
    top = candidates[0]
    return (top["title"] in spoken_titles, [f"top must-hear for these topics: #{top['rank']} {top['title']}"])


FIT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["score", "why"],
              "properties": {"score": {"type": "integer"}, "why": {"type": "string"}}}


def fit(briefing):
    from src.llm import ask_json
    p = briefing["profile"]
    lines = "\n".join(c["text"] for c in briefing["claims"] if c["kind"] in NEWS)
    out = ask_json("bench-fit", "You judge a personal news briefing for its listener. Score 1 to 5 how well the "
                   "choice of stories and the depth fit the listener description (5 = exactly what they asked for, "
                   "3 = half of it is off, 1 = wrong listener). Judge the selection and depth, not the writing.",
                   f"Listener: {p['description']}\nDepth asked: {p['depth']}\nLength asked: {p['seconds']} s\n\n"
                   f"Spoken lines:\n{lines}", FIT_SCHEMA, max_tokens=200)
    return (out["score"] >= 4, [f"{out['score']}/5: {out['why']}"])


def run(paths, stories, with_fit=False):
    rows = []
    for path in paths:
        b = json.loads(Path(path).read_text(encoding="utf-8"))
        if "profile" not in b or "claims" not in b:
            continue
        res = check(b, stories)
        if with_fit:
            res["fit"] = fit(b)
        rows.append({"path": str(path), "name": b["profile"].get("name"), "checks": res})
    names = sorted({k for r in rows for k in r["checks"]})
    table = {}
    for k in names:
        vals = [r["checks"][k][0] for r in rows if k in r["checks"]]
        applicable = [v for v in vals if v is not None]
        table[k] = {"passed": sum(applicable), "applicable": len(applicable),
                    "rate": round(sum(applicable) / len(applicable), 4) if applicable else None}
    return rows, table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-11-18")
    ap.add_argument("--folder", action="append", help="where the briefing.json files are (default: the day's "
                                                      "briefings and editions)")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    day = ROOT / "output" / args.day
    folders = [Path(f) for f in args.folder] if args.folder else [day / "briefings", day / "editions"]
    paths = sorted(p for f in folders for p in f.glob("**/briefing.json"))
    stories = json.loads((day / "stories.json").read_text(encoding="utf-8"))
    rows, table = run(paths, stories, args.fit)
    if args.json:
        print(json.dumps({"table": table, "rows": rows}, indent=2, ensure_ascii=False))
        return
    print(f"{len(rows)} briefings from {', '.join(str(f) for f in folders)}\n")
    print(f"{'check':<12} {'passed':>8}  rate")
    for k, v in table.items():
        rate = "n/a" if v["rate"] is None else f"{100 * v['rate']:.1f} %"
        print(f"{k:<12} {v['passed']:>3}/{v['applicable']:<4}  {rate}")
    for r in rows:
        for k, (ok, problems) in r["checks"].items():
            if ok is False:
                print(f"\nFAIL {k} {r['name']} ({Path(r['path']).parent.name}):")
                for p in problems[:4]:
                    print(f"   {p}")


if __name__ == "__main__":
    main()
