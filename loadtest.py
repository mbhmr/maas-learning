"""Many listeners at once against the running API: latency, throughput, errors and the real cost per new listener.

Run:  .venv/Scripts/python loadtest.py --base http://localhost:8001 --k 10 --distinct 6 --sequential 2
      .venv/Scripts/python loadtest.py --phases audio           (ONE new briefing with voice, about 0.11 USD)

Phases (all with audio off unless "audio"):
  cached      K listeners whose briefing already exists                       costs nothing
  identical   K requests for the SAME new listener at the same moment         should cost ONE briefing
  distinct    D different new listeners at the same moment                    D briefings, some may get 429
  sequential  S new listeners one after another, step times from the log      S briefings
  audio       one new listener with voice: TTS time, characters, MP3 size     one briefing with voice
New listeners are named "Loadtest" so their folders are easy to find in output/<day>/briefings/.
Cost comes from output/usage.jsonl (every model call is logged there); results go to output/loadtest-<time>.json.
"""
import argparse
import asyncio
import hashlib
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

import httpx

from src.briefing import slug

OUTPUT = Path(__file__).resolve().parent / "output"
INTERESTS = ["central banks and the dollar", "chip makers and AI", "oil, gold and commodities", "crypto",
             "UK companies and the pound", "Japanese yen and inflation", "big tech earnings", "European stocks",
             "airlines and travel", "banks and interest rates", "energy transition", "retail and consumers"]
LANGS = ["en", "de", "nl"]


def new_profile(run, i, lang="en"):
    a, b = INTERESTS[i % len(INTERESTS)], INTERESTS[(i * 5 + 3) % len(INTERESTS)]
    return {"name": "Loadtest", "language": lang, "seconds": 90, "depth": "medium",
            "description": f"Load test {run} #{i}. Interested in {a} and {b}, short and clear."}


def cache_key(profile):  # same rule as api.py
    full = {"name": "Listener", "language": "en", "seconds": 90, "depth": "medium", **profile}
    return f"{slug(full['name'])}-{hashlib.sha1(json.dumps(full, sort_keys=True).encode()).hexdigest()[:8]}"


def cached_profiles(day):
    """Profiles whose text briefing already exists (folder name = cache key), so asking costs nothing."""
    found = []
    for p in sorted((OUTPUT / day / "briefings").glob("*/briefing.json")):
        prof = json.loads(p.read_text(encoding="utf-8")).get("profile", {})
        if prof and cache_key(prof) == p.parent.name and not prof["name"].startswith("Loadtest"):
            found.append(prof)
    return found


def pct(values, q):
    if not values:
        return None
    v = sorted(values)
    return round(v[min(len(v) - 1, max(0, round(q / 100 * len(v) + 0.5) - 1))], 2)


async def fire(client, day, profiles, audio=False):
    """All requests at the same moment. Returns [(status, seconds, start_wallclock, json_or_text)]."""
    async def one(prof):
        start, t = time.time(), time.perf_counter()
        try:
            r = await client.post("/api/briefing", json={"day": day, "profile": prof, "audio": audio})
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]
            return r.status_code, time.perf_counter() - t, start, body
        except httpx.HTTPError as e:
            return f"error {type(e).__name__}", time.perf_counter() - t, start, None
    return await asyncio.gather(*(one(p) for p in profiles))


def summary(name, results, wall):
    ok = [s for code, s, _, _ in results if code == 200]
    codes = {}
    for code, *_ in results:
        codes[str(code)] = codes.get(str(code), 0) + 1
    return {"phase": name, "requests": len(results), "status": codes, "wall_s": round(wall, 2),
            "p50_s": pct(ok, 50), "p95_s": pct(ok, 95), "max_s": round(max(ok), 2) if ok else None,
            "throughput_per_s": round(len(ok) / wall, 2) if wall else None}


def read_usage(since):
    """Log lines written at or after `since` (local time, whole seconds, like src/llm.py writes them)."""
    path, rows = OUTPUT / "usage.jsonl", []
    if path.exists():
        for line in path.open(encoding="utf-8"):
            row = json.loads(line)
            if datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S").timestamp() >= int(since):
                rows.append(row)
    return rows


def cost_per_listener(rows):
    """One new briefing = one 'select' call. Sums USD per step and divides by the number of briefings."""
    briefings = sum(1 for r in rows if r.get("step") == "select")
    steps = {}
    for r in rows:
        if r.get("step") in ("select", "script", "judge", "tts"):
            s = steps.setdefault(r["step"], {"calls": 0, "usd": 0.0, "in": 0, "out": 0, "chars": 0, "model": r["model"]})
            s["calls"] += 1
            s["usd"] += r.get("usd") or 0.0
            s["in"] += r.get("input_tokens", 0)
            s["out"] += r.get("output_tokens", 0)
            s["chars"] += r.get("characters", 0)
    openai = sum(s["usd"] for k, s in steps.items() if k != "tts")
    per = {k: {"model": s["model"], "calls": s["calls"], "avg_usd": round(s["usd"] / s["calls"], 5),
               "avg_in": round(s["in"] / s["calls"]), "avg_out": round(s["out"] / s["calls"]),
               **({"avg_chars": round(s["chars"] / s["calls"])} if s["chars"] else {})}
           for k, s in steps.items()}
    return {"new_briefings_in_log": briefings, "openai_usd_total": round(openai, 5),
            "openai_usd_per_listener": round(openai / briefings, 5) if briefings else None, "steps": per}


def step_times(rows, starts):
    """Per briefing built one at a time: seconds from request start to each logged call (log has 1 s resolution)."""
    out = []
    for start, end in starts:
        mine = [r for r in rows if int(start) <= datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S").timestamp()
                <= end + 1 and r.get("step") in ("select", "script", "judge", "tts")]
        t, prev, times = None, int(start), {}
        for r in mine:
            t = datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S").timestamp()
            times[r["step"]] = round(t - prev)
            prev = t
        times["total"] = round(end - start, 1)
        out.append(times)
    return out


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    ap.add_argument("--day", help="news day, default: newest prepared")
    ap.add_argument("--k", type=int, default=10, help="requests in the cached and identical phases")
    ap.add_argument("--distinct", type=int, default=6, help="different new listeners at once")
    ap.add_argument("--sequential", type=int, default=2, help="new listeners one after another")
    ap.add_argument("--phases", default="cached,identical,distinct,sequential")
    args = ap.parse_args()
    phases = args.phases.split(",")
    run = time.strftime("%H%M%S")
    began = time.time()
    report = {"run": run, "base": args.base, "phases": [], "notes": []}

    async with httpx.AsyncClient(base_url=args.base, timeout=600,
                                 limits=httpx.Limits(max_connections=200, max_keepalive_connections=200)) as c:
        day = args.day or (await c.get("/api/days")).json()[0]
        report["day"] = day
        n_new = 0

        if "cached" in phases:
            profs = cached_profiles(day)
            if not profs:
                report["notes"].append("no cached profile found, cached phase skipped")
            else:
                t = time.perf_counter()
                res = await fire(c, day, [profs[i % len(profs)] for i in range(args.k)])
                report["phases"].append(summary(f"cached x{args.k}", res, time.perf_counter() - t))

        if "identical" in phases:
            prof = new_profile(run, 0)
            t = time.perf_counter()
            res = await fire(c, day, [prof] * args.k)
            report["phases"].append(summary(f"identical new x{args.k}", res, time.perf_counter() - t))
            n_new += 1

        if "distinct" in phases:
            profs = [new_profile(run, 100 + i, LANGS[i % 3]) for i in range(args.distinct)]
            t = time.perf_counter()
            res = await fire(c, day, profs)
            report["phases"].append(summary(f"distinct new x{args.distinct}", res, time.perf_counter() - t))
            n_new += sum(1 for code, *_ in res if code == 200)
            report["rejected_429"] = [b.get("detail") if isinstance(b, dict) else b for code, _, _, b in res if code == 429][:1]

        seq_windows = []
        if "sequential" in phases:
            await asyncio.sleep(2)  # so log lines of the phase before do not count as step times
            t, res = time.perf_counter(), []
            for i in range(args.sequential):
                r = (await fire(c, day, [new_profile(run, 200 + i)]))[0]
                res.append(r)
                seq_windows.append((r[2], r[2] + r[1]))
                await asyncio.sleep(1.1)  # the log has whole seconds: keep briefings apart
            report["phases"].append(summary(f"sequential new x{args.sequential}", res, time.perf_counter() - t))
            n_new += sum(1 for code, *_ in res if code == 200)

        audio_window = None
        if "audio" in phases:
            t = time.perf_counter()
            r = (await fire(c, day, [new_profile(run, 300)], audio=True))[0]
            report["phases"].append(summary("new with voice x1", [r], time.perf_counter() - t))
            audio_window = (r[2], r[2] + r[1])
            n_new += 1 if r[0] == 200 else 0
            if r[0] == 200 and r[3].get("audioUrl"):
                mp3 = await c.get(r[3]["audioUrl"])
                ends = [cl["end"] for cl in r[3]["claims"] if cl.get("end")]
                report["audio"] = {"mp3_bytes": len(mp3.content), "seconds": max(ends) if ends else None,
                                   "kb_per_s": round(len(mp3.content) / 1000 / max(ends), 1) if ends else None}

    rows = read_usage(began)
    report["expected_new_briefings"] = n_new
    report["cost"] = cost_per_listener(rows)
    if report["cost"]["new_briefings_in_log"] != n_new:
        report["notes"].append("log shows a different number of briefings than this run built: another process "
                               "wrote to usage.jsonl at the same time, cost per listener is still per select call")
    if seq_windows:
        report["sequential_step_seconds"] = step_times(rows, seq_windows)
    if audio_window:
        report["audio_step_seconds"] = step_times(rows, [audio_window])

    out = OUTPUT / f"loadtest-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{'phase':<24}{'req':>5}{'status':>22}{'wall s':>8}{'p50 s':>8}{'p95 s':>8}{'max s':>8}{'ok/s':>7}")
    for p in report["phases"]:
        print(f"{p['phase']:<24}{p['requests']:>5}{json.dumps(p['status']):>22}{p['wall_s']:>8}"
              f"{p['p50_s'] or '-':>8}{p['p95_s'] or '-':>8}{p['max_s'] or '-':>8}{p['throughput_per_s'] or '-':>7}")
    print(json.dumps({k: report[k] for k in report if k not in ("phases",)}, indent=2))
    print(f"saved {out}")


if __name__ == "__main__":
    asyncio.run(main())
