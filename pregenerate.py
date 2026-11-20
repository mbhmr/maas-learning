"""Overnight: write and check every shared edition of a news day before anyone listens.

    .venv/Scripts/python pregenerate.py 2026-11-18                     all 324 editions, into output/pregen/<day>/
    .venv/Scripts/python pregenerate.py 2026-11-18 --only en-90s --workers 8
    .venv/Scripts/python pregenerate.py 2026-11-18 --tier default     full price, to compare with flex
    .venv/Scripts/python pregenerate.py 2026-11-18 --live             into output/<day>/editions (the API reads it)

An edition is language x length x depth x segment (3 x 6 x 3 x 6 = 324). Each one is the normal pipeline
(select, script, code checks, judge, repair, top-up), text only: the voice is paid when the first listener of that
edition presses play, so an edition nobody hears costs no voice. The writer runs on OpenAI's flex tier (half price,
answers later when busy; nobody is waiting at night). Afterwards a new listener needs one cached segment call and
no writer model.

Writes output/pregen-<day>[-<tier>].json: wall time, USD per edition, failures, lines spoken, characters the voice
would cost if every edition were heard.
"""
import argparse
import json
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "output"
VOICE_USD_PER_1000_CHARS = 0.08  # ElevenLabs v3/v4 list price, read 20.11. (kosten-und-produkt.md)


def all_keys():
    from src.editions import DEPTHS, LENGTHS, SEGMENTS
    return [(f"{lang}-{sec}s-{depth}-{seg}", {"language": lang, "seconds": sec, "depth": depth, "segment": seg})
            for lang in ("en", "de", "nl") for sec in LENGTHS for depth in DEPTHS for seg in SEGMENTS]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("day")
    ap.add_argument("--only", default="", help="only keys starting with this, e.g. en-90s")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--tier", default="flex", choices=("flex", "default"))
    ap.add_argument("--live", action="store_true", help="write into output/<day>/editions, which the API serves")
    ap.add_argument("--name", default="", help="a name for this run's folder and report, e.g. after-fix")
    args = ap.parse_args(argv)

    os.environ["OPENAI_SERVICE_TIER"] = "" if args.tier == "default" else args.tier
    from src import editions, llm
    llm.SERVICE_TIER = os.environ["OPENAI_SERVICE_TIER"] or None

    source = OUTPUT / args.day
    stories = json.loads((source / "stories.json").read_text(encoding="utf-8"))
    facts = json.loads((source / "facts.json").read_text(encoding="utf-8"))["facts"]
    if args.live:
        folder = source
    else:  # a separate day folder, so a measurement never touches what the demo serves
        folder = OUTPUT / "pregen" / f"{args.day}-{args.tier}{'-' + args.name if args.name else ''}"
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("stories.json", "facts.json"):
            shutil.copy2(source / name, folder / name)

    # count every call of this run per edition, on top of the normal usage.jsonl line
    local, spent, lock = threading.local(), {}, threading.Lock()
    write_line = llm.log_usage

    def counting(entry):
        write_line(entry)
        with lock:
            row = spent.setdefault(getattr(local, "key", "?"), {"usd": 0.0, "calls": 0, "flex": 0})
            row["usd"] += entry.get("usd") or 0
            row["calls"] += 1
            row["flex"] += entry.get("tier") == "flex"
    llm.log_usage = counting

    keys = [(k, p) for k, p in all_keys() if k.startswith(args.only)]
    done, failed = {}, {}

    def one(key, parts):
        local.key = key
        t0 = time.time()
        for attempt in (1, 2):  # one retry: a timeout or a refused call should not leave an edition empty
            try:
                body = editions.edition(folder, key, parts, stories, facts, audio=False)
                return key, body, time.time() - t0, None
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)[:200]}"
        return key, None, time.time() - t0, err

    start = time.time()
    with ThreadPoolExecutor(args.workers) as pool:
        for fut in as_completed([pool.submit(one, k, p) for k, p in keys]):
            key, body, secs, err = fut.result()
            if err:
                failed[key] = err
            else:
                news = [c for c in body["claims"] if c["kind"] in ("claim", "context")]
                words = sum(len(c["text"].split()) for c in body["claims"])
                done[key] = {"seconds": round(secs, 1), "lines": len(news), "words": words,
                             "unsourced": sum(1 for c in news if not c["sources"]),
                             "characters": sum(len(c["text"]) for c in body["claims"]),
                             "requested_seconds": body["seconds"], "language": body["language"]}
            print(f"{len(done) + len(failed)}/{len(keys)} {key} {'FAILED ' + err if err else f'{secs:.0f}s'}",
                  flush=True)
    wall = time.time() - start

    usd = sum(r["usd"] for r in spent.values())
    calls = sum(r["calls"] for r in spent.values())
    chars = sum(d["characters"] for d in done.values())
    report = {
        "day": args.day, "tier": args.tier, "workers": args.workers, "folder": str(folder),
        "editions": len(keys), "built": len(done), "failed": failed,
        "wall_seconds": round(wall), "openai_usd": round(usd, 4), "openai_calls": calls,
        "flex_calls": sum(r["flex"] for r in spent.values()),
        "usd_per_edition": round(usd / max(len(done), 1), 5),
        "lines_without_source": sum(d["unsourced"] for d in done.values()),
        "empty_editions": sorted(k for k, d in done.items() if d["lines"] == 0),
        "voice_characters_if_all_heard": chars,
        "voice_usd_if_all_heard": round(chars / 1000 * VOICE_USD_PER_1000_CHARS, 2),
        "per_edition": {k: {**d, "usd": round(spent.get(k, {}).get("usd", 0), 5)} for k, d in sorted(done.items())},
    }
    suffix = ("" if args.tier == "flex" else f"-{args.tier}") + (f"-{args.name}" if args.name else "")
    out = OUTPUT / f"pregen-{args.day}{('-' + args.only) if args.only else ''}{suffix}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "per_edition"}, indent=2))
    print(f"report: {out}")
    return report


if __name__ == "__main__":
    sys.exit(0 if main()["failed"] == {} else 1)
