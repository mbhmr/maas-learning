"""A/B test of the learning loop: does the writer make fewer blocked first drafts with the lessons block?

    .venv/Scripts/python eval/ab_lessons.py --days 2026-11-13 2026-11-18 --reps 10 --workers 6

Both arms get the same stories (the story choice is made once per preset and day and reused), the same facts and
the same checks; the only difference is the lessons section at the end of the writer prompt (src/lessons.py,
output/lessons.json). Runs alternate between the arms. Nothing is written to the briefing folders.

Measured per run: lines in the first draft, how many of them the code checks and the judge blocked, whether a
repair call was needed, lines finally spoken, words against the requested length, figures per 100 spoken words (a
guard: fewer blocks bought with vaguer lines would show here) and USD. Result: output/ab-lessons-<stamp>.json.
"""
import argparse
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import lessons, llm, script  # noqa: E402
from src.facts import numbers  # noqa: E402

# The four presets of the player (web/src/App.jsx), copied so the test does not depend on the UI.
PRESETS = {
    "trader": {"name": "FX trader", "language": "en", "seconds": 180, "depth": "dense, every figure with its period",
               "description": "A currency trader. Wants central banks, inflation and macro data, FX moves and the "
                              "biggest market-moving company news. Numbers first, no background explanations."},
    "investor": {"name": "Privatanleger", "language": "de", "seconds": 120,
                 "depth": "simple, explain terms in a few words",
                 "description": "A private investor in Germany with little time. Wants the big stories of the day in "
                                "plain language, what happened and why it matters, few numbers."},
    "world": {"name": "World news", "language": "en", "seconds": 150, "depth": "simple, explain terms in a few words",
              "description": "Someone who just wants to know what happened in the world: politics, world events, big "
                             "business and tech stories, crime and culture. Not an investor, no market jargon, at "
                             "most one number per story."},
    "belegger": {"name": "Belegger", "language": "nl", "seconds": 150, "depth": "medium",
                 "description": "A Dutch retail investor who holds tech stocks and some crypto. Wants stocks, AI "
                                "companies, crypto and the big macro numbers that move them, with the key figure per "
                                "story and why it matters."},
}

local = threading.local()
_select_lock = threading.Lock()
_select_memo = {}
_orig = {"system_prompt": script.system_prompt, "check_script": script.check_script, "judge": script.judge,
         "select_stories": script.select_stories, "log_usage": llm.log_usage}


def _system_prompt(profile, day=None):
    text = _orig["system_prompt"](profile, day)
    return text + lessons.prompt_block(force=True) if getattr(local, "arm", "off") == "on" else text


def _check_script(raw_lines, facts, lang):
    kept, dropped = _orig["check_script"](raw_lines, facts, lang)
    run = local.run
    if run["draft_lines"] is None:  # the first call is the writer's first draft
        run["draft_lines"] = len(raw_lines)
        run["draft_code_blocked"] = len(dropped)
        run["draft_reasons"] = [lessons.category(d["why"]) or d["why"][:40] for d in dropped]
    return kept, dropped


def _judge(lines, facts):
    kept, bad = _orig["judge"](lines, facts)
    run = local.run
    if run["draft_judge_blocked"] is None:
        run["draft_judge_blocked"] = sum(1 for b in bad if b.get("kind") != "host")
    return kept, bad


def _select_stories(profile, stories, facts):
    key = (json.dumps(profile, sort_keys=True), tuple(s["id"] for s in stories), local.day)
    with _select_lock:  # same stories for both arms: computed once, then reused
        if key not in _select_memo:
            _select_memo[key] = _orig["select_stories"](profile, stories, facts)
        return _select_memo[key]


def _log_usage(entry):
    _orig["log_usage"](entry)
    run = getattr(local, "run", None)
    if run is not None:
        run["usd"] += entry.get("usd") or 0
        run["repair_calls"] += entry.get("step") == "repair"


def install():
    script.system_prompt, script.check_script, script.judge = _system_prompt, _check_script, _judge
    script.select_stories, llm.log_usage = _select_stories, _log_usage


def one(day, preset, rep, arm, data):
    stories, facts = data[day]
    profile = PRESETS[preset]
    local.arm, local.day = arm, day
    local.run = run = {"day": day, "preset": preset, "rep": rep, "arm": arm, "draft_lines": None,
                       "draft_code_blocked": 0, "draft_judge_blocked": None, "draft_reasons": [],
                       "repair_calls": 0, "usd": 0.0}
    try:
        kept, dropped, chosen, frame = script.write_script(profile, stories, facts)
    except Exception as e:
        return {**run, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    lang = profile["language"]
    spoken = [k["text"] for k in kept if k.get("kind") in ("claim", "context")]
    words = sum(len(t.split()) for t in spoken)
    figures = sum(len(numbers(t, lang)) for t in spoken)
    run.update(spoken_lines=len(spoken), words=words,
               requested_words=round(profile["seconds"] * script.WORDS_PER_SECOND[lang]),
               figures_per_100_words=round(100 * figures / max(words, 1), 2),
               draft_judge_blocked=run["draft_judge_blocked"] or 0)
    run["draft_blocked"] = run["draft_code_blocked"] + run["draft_judge_blocked"]
    run["draft_block_rate"] = round(run["draft_blocked"] / max(run["draft_lines"] or 0, 1), 4)
    return run


def paired_diff(runs, field):
    """Mean (on - off) over pairs with the same day, preset and rep, and a 95 % bootstrap interval."""
    by = {}
    for r in runs:
        if "error" not in r:
            by.setdefault((r["day"], r["preset"], r["rep"]), {})[r["arm"]] = r[field]
    diffs = [v["on"] - v["off"] for v in by.values() if "on" in v and "off" in v]
    if not diffs:
        return None
    rng = random.Random(0)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(4000))
    return {"pairs": len(diffs), "mean_diff": round(sum(diffs) / len(diffs), 4),
            "ci95": [round(means[100], 4), round(means[3899], 4)]}


def summary(runs):
    out = {}
    for arm in ("off", "on"):
        rs = [r for r in runs if r["arm"] == arm and "error" not in r]
        n = max(len(rs), 1)
        lines = sum(r["draft_lines"] or 0 for r in rs)
        out[arm] = {"runs": len(rs), "errors": sum(1 for r in runs if r["arm"] == arm and "error" in r),
                    "draft_lines": lines,
                    "draft_block_rate_pooled": round(sum(r["draft_blocked"] for r in rs) / max(lines, 1), 4),
                    "runs_with_repair": round(sum(r["repair_calls"] > 0 for r in rs) / n, 3),
                    "spoken_lines": round(sum(r["spoken_lines"] for r in rs) / n, 2),
                    "words_of_requested": round(sum(r["words"] / r["requested_words"] for r in rs) / n, 3),
                    "figures_per_100_words": round(sum(r["figures_per_100_words"] for r in rs) / n, 2),
                    "usd_per_briefing": round(sum(r["usd"] for r in rs) / n, 5)}
    out["paired"] = {f: paired_diff(runs, f) for f in ("draft_block_rate", "usd", "spoken_lines",
                                                       "figures_per_100_words")}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="+", required=True)
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--presets", nargs="+", default=list(PRESETS))
    args = ap.parse_args()
    if not lessons.prompt_block(force=True):
        sys.exit("no lessons: run  python -m src.lessons <folders>  first")
    data = {}
    for day in args.days:
        folder = ROOT / "output" / day
        data[day] = (json.loads((folder / "stories.json").read_text(encoding="utf-8")),
                     json.loads((folder / "facts.json").read_text(encoding="utf-8"))["facts"])
    install()
    # alternate the arms: off/on in one rep, on/off in the next, so drift over the run hits both
    jobs = [(d, p, rep, arm) for d in args.days for p in args.presets for rep in range(args.reps)
            for arm in (("off", "on") if rep % 2 == 0 else ("on", "off"))]
    start = time.time()
    with ThreadPoolExecutor(args.workers) as pool:
        runs = list(pool.map(lambda j: one(*j, data), jobs))
    result = {"days": args.days, "reps": args.reps, "lessons": json.loads(lessons.LESSONS.read_text(encoding="utf-8")),
              "wall_seconds": round(time.time() - start), "summary": summary(runs),
              "by_day": {d: summary([r for r in runs if r["day"] == d]) for d in args.days}, "runs": runs}
    out = ROOT / "output" / f"ab-lessons-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"summary": result["summary"], "by_day": result["by_day"]}, indent=2))
    print(f"report: {out}")


if __name__ == "__main__":
    main()
