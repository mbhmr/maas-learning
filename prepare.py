"""Prepare one news day ONCE, reused by every listener.

  load -> group into stories (code) -> pick top stories (code) -> facts per story (small model, checked by code)

Run:  .venv/Scripts/python prepare.py --day 2026-11-13
      .venv/Scripts/python prepare.py --day 2026-11-13 --stories-only   (no model calls, free)
Writes output/<day>/stories.json and output/<day>/facts.json.
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.articles import load_articles
from src.cluster import cluster
from src.facts import extract_facts

TOP_OVERALL = 8   # strongest stories of the day, whatever the outlet
PER_FEED = 2      # plus the best stories of each feed, so every kind of listener has material


def pick(stories, articles):
    chosen = stories[:TOP_OVERALL]
    for feed in ("actionforex", "invezz_en", "ibtimes_uk", "zacks"):
        own = [s for s in stories if s not in chosen and articles[s["article_ids"][0]]["feed"] == feed]
        chosen += own[:PER_FEED]
    return sorted(chosen, key=lambda s: s["rank"])


def add_translations(facts, story, articles):
    """German and Dutch Invezz versions of a cited English article, for listeners in that language."""
    for f in facts:
        for s in f["sources"]:
            s["translations"] = {lang: {"url": articles[tid]["url"], "publisher": articles[tid]["publisher"]}
                                 for lang, tid in story["translations"].get(s["article_id"], {}).items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-11-13", help="UTC calendar day, YYYY-MM-DD")
    ap.add_argument("--stories-only", action="store_true", help="group and rank only, no model calls")
    args = ap.parse_args()

    out = Path("output") / args.day
    out.mkdir(parents=True, exist_ok=True)
    articles = load_articles()
    day = [a for a in articles.values() if a["date"][:10] == args.day]
    if not day:
        raise SystemExit(f"No articles on {args.day}.")
    stories = cluster(day, list(articles.values()))
    chosen = pick(stories, articles)
    for s in stories:
        s["headlines"] = [{"id": i, "publisher": articles[i]["publisher"], "headline": articles[i]["headline"],
                           "url": articles[i]["url"]} for i in s["article_ids"]]
        s["selected"] = s in chosen
    (out / "stories.json").write_text(json.dumps(stories, indent=2, ensure_ascii=False), encoding="utf-8")
    multi = sum(len(s["article_ids"]) > 1 for s in stories)
    print(f"{len(day)} articles -> {len(stories)} stories ({multi} with several articles), {len(chosen)} selected")
    for s in chosen:
        print(f"  {s['rank']:>3}. {s['title'][:80]}  [{', '.join(s['publishers'])}]")
    if args.stories_only:
        return

    def work(story):
        facts, rejected = extract_facts(story, articles)
        add_translations(facts, story, articles)
        return facts, rejected

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(work, chosen))
    facts = [f for fs, _ in results for f in fs]
    rejected = [r for _, rs in results for r in rs]
    (out / "facts.json").write_text(json.dumps({"day": args.day, "facts": facts, "rejected": rejected},
                                               indent=2, ensure_ascii=False), encoding="utf-8")
    conflicts = sum(f["conflict"] for f in facts)
    print(f"{len(facts)} facts verified ({conflicts} with conflicting sources), {len(rejected)} sources rejected")


if __name__ == "__main__":
    main()
