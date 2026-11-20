"""The checker teaches the writer: the most frequent reasons lines were blocked become "avoid" rules.

Every briefing.json keeps the lines the checker blocked and why. learn() counts those reasons over earlier
briefings, keeps the ones the writer can avoid (not "over the requested length": that is the length cut, not a
writing mistake), and stores the top ones with two real blocked lines each in output/lessons.json.
prompt_block() turns that file into a short section at the END of the writer's prompt (the start stays the same,
so the provider's prompt cache still matches).

    .venv/Scripts/python -m src.lessons output/2026-11-18 output/pregen/2026-11-18-flex    learn from these folders

Whether the block is used is decided by a measurement (eval/ab_lessons.py, README), not by default: ENABLED.
"""
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "output"
LESSONS = OUTPUT / "lessons.json"
ENABLED = os.getenv("LESSONS", "0") == "1"  # switched on only after the A/B measurement says it helps
TOP = 5
EXAMPLES = 2

# category -> the rule the writer gets. Only reasons a better first draft avoids.
RULES = {
    "content check": "A second fact checker rejected these lines for saying more than their quotes "
                     "(direction, cause, a link between facts, an unnamed opinion). Its reasons:",
    "numbers not in sources": "Only numbers that stand in the quotes of the cited facts, exactly as written there: "
                              "no rounding, no converting, no sums, no dates or years the quotes lack.",
    "context line with a figure": "Context lines contain no digit at all, not a year, not a date, not a rank.",
    "repeats an earlier line": "Never tell the same fact or figure twice, and never start two lines with the same "
                               "five words.",
    "person not in its quotes": "Name a person only in a line whose cited quotes name that person.",
    "relative date": "Never say today, yesterday, tonight, this week or a weekday: say the date.",
    "superlative not in sources": "Record, highest, first time and similar words only if the quote has them.",
    "greeting does not call the listener by their name": "The greeting calls the listener by their profile name, "
                                                         "exactly as given.",
    "second context line for one story": "One context line per story, never two.",
    "too long for the ear": "Every line under 40 words.",
    "starts with a bare number": "Never start a line with a number.",
    "English words in a non-English line": "In German and Dutch briefings every word is German or Dutch, only "
                                           "names stay.",
    "context sounds like advice": "Context lines never say what the listener could or should do with money.",
    "no source": "Every line cites at least one fact id.",
}


def category(why):
    """'context line with a figure (rewrite tried)' -> 'context line with a figure'; None if not a writing error."""
    why = re.sub(r"^rewrite blocked: ", "", why or "")
    why = re.sub(r"\s*\(rewrite tried\)$", "", why)
    for cat in RULES:
        if why.startswith(cat):
            return cat
    return None


def detail(why):
    """The part after the category, e.g. the judge's own reason."""
    why = re.sub(r"\s*\(rewrite tried\)$", "", re.sub(r"^rewrite blocked: ", "", why or ""))
    cat = category(why)
    return why[len(cat):].lstrip(" :").strip() if cat else why


def learn(paths):
    """Counts blocked-line reasons over briefing.json files. Returns the lessons dict (not written)."""
    counts, examples, files = Counter(), {}, 0
    for path in paths:
        try:
            dropped = json.loads(Path(path).read_text(encoding="utf-8")).get("dropped") or []
        except (OSError, ValueError):
            continue
        files += 1
        for d in dropped:
            cat = category(d.get("why"))
            if not cat:
                continue
            counts[cat] += 1
            ex = examples.setdefault(cat, [])
            if len(ex) < EXAMPLES and d.get("text") and all(e["text"] != d["text"] for e in ex):
                ex.append({"text": d["text"], "why": detail(d.get("why"))})
    top = [{"reason": cat, "count": n, "rule": RULES[cat], "examples": examples.get(cat, [])}
           for cat, n in counts.most_common(TOP)]
    return {"briefings": files, "blocked": sum(counts.values()), "lessons": top}


def briefing_files(*folders):
    """Every briefing.json below these folders (a day's briefings and editions, an overnight run)."""
    return sorted(p for folder in folders for p in Path(folder).glob("**/briefing.json"))


def prompt_block(lessons=None, force=False):
    """The section appended to the writer's prompt, or "" when switched off or nothing was learned."""
    if not (ENABLED or force):
        return ""
    if lessons is None:
        try:
            lessons = json.loads(LESSONS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
    items = lessons.get("lessons") or []
    if not items:
        return ""
    out = ["", "", f"Lessons from {lessons.get('briefings', 0)} earlier briefings: the checker blocked these "
                  "mistakes most often. Avoid them in the first draft:"]
    for item in items:
        out.append(f"- {item['rule']}")
        for ex in item["examples"]:
            reason = f" (checker: {ex['why'][:120]})" if ex["why"] else ""
            out.append(f'    blocked: "{ex["text"][:160]}"{reason}')
    return "\n".join(out)


if __name__ == "__main__":
    result = {"learned_from": sys.argv[1:], **learn(briefing_files(*sys.argv[1:]))}
    LESSONS.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "lessons"}),
          [(x["reason"], x["count"]) for x in result["lessons"]])
