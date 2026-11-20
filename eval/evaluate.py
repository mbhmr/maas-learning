"""Measure our outputs against the hand-built answer key (eval/answer_key.json). Offline, no API calls.

  .venv/Scripts/python eval/evaluate.py                     # output/2026-11-18
  .venv/Scripts/python eval/evaluate.py --day output/2026-11-18 --json

What it measures
- Merging: for every pair of key articles, should they share a story (same key event) and do they?
  precision = of the pairs we put together, how many belong together; recall = of the pairs that belong
  together, how many we put together. German and Dutch translations count as members of their story.
- Per key event: split (its articles sit in more than one story), mixed (its main story also holds articles of
  another key event), missing (an article is in no story, e.g. dropped as a round-up), and the rank of its main story.
- Facts and claims: the share the key marks correct, among those still present in the current outputs.
Articles the key marks 'ambiguous' are left out of the pair counts.
"""
import argparse
import glob
import json
import os
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\w%$.,]+", " ", text.lower().replace("’", "'"))).strip()


def story_map(stories):
    """{article_id: story_id}, translations included."""
    out = {}
    for s in stories:
        for i in s["article_ids"]:
            out[i] = s["id"]
        for langs in s.get("translations", {}).values():
            for i in langs.values():
                out[i] = s["id"]
    return out


def pairwise(events, amap):
    """Pair counts over the key's core articles that are in some story."""
    gold = {a["id"]: e["id"] for e in events for a in e["articles"]}
    ids = sorted(i for i in gold if i in amap)
    tp = fp = fn = 0
    for x, y in combinations(ids, 2):
        same_gold, same_pred = gold[x] == gold[y], amap[x] == amap[y]
        tp += same_gold and same_pred
        fp += same_pred and not same_gold
        fn += same_gold and not same_pred
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"articles": len(ids), "true_pairs": tp, "false_pairs": fp, "missed_pairs": fn,
            "precision": precision, "recall": recall, "f1": f1}


def event_report(events, stories, amap):
    by_id = {s["id"]: s for s in stories}
    gold = {a["id"]: e["id"] for e in events for a in e["articles"]}
    members = {}
    for i, sid in amap.items():
        members.setdefault(sid, []).append(i)
    rows = []
    for e in events:
        ids = [a["id"] for a in e["articles"]]
        present = [i for i in ids if i in amap]
        counts = Counter(amap[i] for i in present)
        main = min(counts, key=lambda sid: (-counts[sid], by_id[sid]["rank"])) if counts else None
        mixed_with, unkeyed = [], 0
        if main:
            own = set(ids) | set(e.get("ambiguous", []))
            for i in members[main]:
                if i in own:
                    continue
                if i in gold:
                    mixed_with.append(gold[i])
                else:
                    unkeyed += 1
        status = []
        if len(counts) > 1:
            status.append("split")
        if mixed_with:
            status.append("mixed")
        if len(present) < len(ids):
            status.append("missing")
        rows.append({
            "event": e["id"], "key": e["key"], "importance": e["importance"], "articles": len(ids),
            "stories": len(counts), "in_main": counts[main] if main else 0, "missing": len(ids) - len(present),
            "main_story": main, "rank": by_id[main]["rank"] if main else None,
            "main_title": by_id[main]["title"] if main else None,
            "split_into": [{"story": sid, "rank": by_id[sid]["rank"], "n": n} for sid, n in counts.most_common()],
            "mixed_with": sorted(set(mixed_with)), "unkeyed_in_main": unkeyed,
            "status": "+".join(status) or "ok",
        })
    return rows


def _match_fact(kf, facts):
    start = norm(kf["quote_start"])
    for f in facts:
        for s in f["sources"]:
            if s["article_id"] == kf["article_id"] and norm(s["quote"]).startswith(start):
                return f
    return None


def fact_report(key_facts, facts):
    rows = []
    for kf in key_facts:
        f = _match_fact(kf, facts)
        rows.append({**kf, "current_id": f["id"] if f else None, "present": f is not None})
    return rows


def load_briefings(day):
    out = {}
    for p in sorted(glob.glob(os.path.join(day, "briefings", "*", "briefing.json"))):
        try:
            out[Path(p).parent.name] = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # being rewritten right now
    return out


def briefing_name(folder):
    return folder.rsplit("-", 1)[0]  # "fx-trader-2fb44037" -> "fx-trader"


def claim_report(key_claims, briefings):
    current = [(briefing_name(folder), c) for folder, b in briefings.items() for c in b["claims"] if c.get("kind") == "claim"]
    index = {(k["briefing"], norm(k["text"])): k for k in key_claims}
    checked, unchecked = [], []
    for name, c in current:
        k = index.get((name, norm(c["text"])))
        (checked if k else unchecked).append({"briefing": name, "id": c["id"], "text": c["text"],
                                              **({"verdict": k["verdict"], "reason": k["reason"]} if k else {})})
    return checked, unchecked


def share(rows, field="verdict", good="correct"):
    n = len(rows)
    return (sum(r[field] == good for r in rows) / n) if n else None


def evaluate(key, day):
    stories = json.loads(Path(day, "stories.json").read_text(encoding="utf-8"))
    facts = json.loads(Path(day, "facts.json").read_text(encoding="utf-8"))["facts"]
    amap = story_map(stories)
    events = key["events"]
    rows = event_report(events, stories, amap)
    multi = [r for r in rows if r["articles"] > 1]
    frows = fact_report(key["facts"], facts)
    present = [r for r in frows if r["present"]]
    checked, unchecked = claim_report(key.get("claims", []), load_briefings(day))
    tier_a = [r for r in rows if r["importance"] == "A"]
    return {
        "day": str(day), "stories": len(stories),
        "pairs": pairwise(events, amap),
        "events": rows,
        "events_multi": len(multi),
        "events_split": sum("split" in r["status"] for r in multi),
        "events_mixed": sum("mixed" in r["status"] for r in rows),
        "events_wrong": sum(r["status"] not in ("ok", "missing") for r in rows),
        "tier_a_in_top10": sum(r["rank"] is not None and r["rank"] <= 10 for r in tier_a), "tier_a": len(tier_a),
        "facts": frows, "facts_present": len(present), "fact_accuracy": share(present),
        "fact_accuracy_all_checked": share(frows),
        "claims_checked": checked, "claims_unchecked": unchecked, "claim_accuracy": share(checked),
        # several listener profiles get the same generated sentence; count each sentence once as well
        "claims_unique": len({norm(c["text"]) for c in checked}),
        "claim_accuracy_unique": share(list({norm(c["text"]): c for c in checked}.values())),
    }


def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f} %"


def print_report(r):
    p = r["pairs"]
    print(f"Day {r['day']}: {r['stories']} stories")
    print(f"\nMERGING over {p['articles']} key articles: precision {pct(p['precision'])}, recall {pct(p['recall'])}, "
          f"F1 {pct(p['f1'])}  ({p['true_pairs']} right pairs, {p['false_pairs']} wrongly joined, "
          f"{p['missed_pairs']} missed)")
    print(f"  multi-article events split: {r['events_split']} of {r['events_multi']}; "
          f"events mixed with another key event: {r['events_mixed']} of {len(r['events'])}")
    print(f"  importance A events in the top 10: {r['tier_a_in_top10']} of {r['tier_a']}")
    print(f"\n{'event':<4} {'key':<28} {'imp':<3} {'art':>3} {'stor':>4} {'rank':>5}  status")
    for e in r["events"]:
        extra = ""
        if e["stories"] > 1:
            extra += " split " + ", ".join(f"{x['story']}#{x['rank']}({x['n']})" for x in e["split_into"])
        if e["mixed_with"]:
            extra += " with " + ",".join(e["mixed_with"])
        if e["missing"]:
            extra += f" missing {e['missing']}"
        if e["unkeyed_in_main"]:
            extra += f" (+{e['unkeyed_in_main']} unkeyed in main)"
        print(f"{e['event']:<4} {e['key'][:28]:<28} {e['importance']:<3} {e['articles']:>3} {e['stories']:>4} "
              f"{str(e['rank']):>5}  {e['status']}{extra}")
    print(f"\nFACTS: {r['facts_present']} of {len(r['facts'])} key facts still in facts.json, "
          f"accuracy {pct(r['fact_accuracy'])} (all checked: {pct(r['fact_accuracy_all_checked'])})")
    for f in r["facts"]:
        if f["verdict"] != "correct":
            print(f"  {f['verdict'].upper()} {f.get('current_id') or f['checked_as']}: {f['claim'][:90]}\n      why: {f['reason']}")
    print(f"\nCLAIMS: {len(r['claims_checked'])} spoken claims checked by hand, accuracy {pct(r['claim_accuracy'])} "
          f"({r['claims_unique']} distinct sentences: {pct(r['claim_accuracy_unique'])}); "
          f"{len(r['claims_unchecked'])} current claims not in the key yet")
    for c in r["claims_checked"]:
        if c["verdict"] != "correct":
            print(f"  {c['verdict'].upper()} {c['briefing']} {c['id']}: {c['text'][:100]}\n      why: {c['reason']}")
    for c in r["claims_unchecked"]:
        print(f"  unchecked {c['briefing']} {c['id']}: {c['text'][:100]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=str(ROOT / "output" / "2026-11-18"))
    ap.add_argument("--key", default=str(ROOT / "eval" / "answer_key.json"))
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = ap.parse_args()
    key = json.loads(Path(args.key).read_text(encoding="utf-8"))
    result = evaluate(key, args.day)
    if args.json:
        print(json.dumps(result, indent=1, ensure_ascii=False))
    else:
        print_report(result)


if __name__ == "__main__":
    main()
