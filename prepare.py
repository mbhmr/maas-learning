"""Prepare the news ONCE, reused by every listener.

  load -> group (code) -> merge ongoing stories and rate importance (one small-model call on headlines, checked
  by code) -> pick stories (code) -> facts per story (small model, checked by code)

Run:  .venv/Scripts/python prepare.py                       (13 to 18 November, briefing for the 19th)
      .venv/Scripts/python prepare.py --stories-only        (grouping by code only, no model calls, free)
Writes output/<end>/stories.json and output/<end>/facts.json.
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.articles import load_articles
from src.cluster import cluster, merge_and_rate
from src.facts import extract_facts
from src.llm import ask_json

WITH_FACTS = 40        # strongest stories get facts: enough for a wildcard listener with unusual interests
PER_TOPIC = 3          # plus the best stories of every topic, so no kind of listener goes empty
ARTICLES_PER_STORY = 4  # newest article per outlet, at most this many, sent to the model


def pick(stories):
    chosen = stories[:WITH_FACTS]
    for topic in {s.get("topic") for s in stories}:
        chosen += [s for s in stories if s.get("topic") == topic and s not in chosen][:PER_TOPIC]
    return sorted(chosen, key=lambda s: s["rank"])


def evidence_articles(story, articles):
    """Newest article of each outlet, so several voices are heard without sending 30 articles."""
    newest = {}
    for i in sorted(story["article_ids"], key=lambda i: articles[i]["date"], reverse=True):
        newest.setdefault(articles[i]["publisher"], i)
    return list(newest.values())[:ARTICLES_PER_STORY]


def add_translations(facts, story, articles):
    """German and Dutch Invezz versions of a cited English article, for listeners in that language."""
    for f in facts:
        for s in f["sources"]:
            s["translations"] = {lang: {"url": articles[tid]["url"], "publisher": articles[tid]["publisher"]}
                                 for lang, tid in story["translations"].get(s["article_id"], {}).items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-11-13", help="first UTC day, YYYY-MM-DD")
    ap.add_argument("--end", default="2026-11-18", help="last UTC day; the briefing is for the morning after")
    ap.add_argument("--stories-only", action="store_true", help="group by code only, no model calls")
    args = ap.parse_args()

    out = Path("output") / args.end
    out.mkdir(parents=True, exist_ok=True)
    articles = load_articles()
    window = [a for a in articles.values() if args.start <= a["date"][:10] <= args.end]
    stories = cluster(window, list(articles.values()))
    print(f"{len(window)} articles {args.start} to {args.end} -> {len(stories)} stories by code")
    if args.stories_only:
        for s in stories[:20]:
            print(f"  {s['rank']:>3}. {s['title'][:80]}  [{len(s['article_ids'])}]")
        return

    stories, info = merge_and_rate(stories, articles, ask_json, args.end)
    print(f"merged {info['merges']} stories into others, refused {len(info['refused'])} merges without a shared name"
          f" -> {len(stories)} stories")
    chosen = pick(stories)
    for s in stories:
        s["headlines"] = [{"id": i, "publisher": articles[i]["publisher"], "headline": articles[i]["headline"],
                           "date": articles[i]["date"], "url": articles[i]["url"]} for i in s["article_ids"]]
        s["selected"] = s in chosen
        s["fact_article_ids"] = evidence_articles(s, articles)
        s.pop("all_headlines", None)
    (out / "stories.json").write_text(json.dumps(stories, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "merge_log.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    for s in chosen[:15]:
        print(f"  {s['rank']:>3}. [{s['importance']}] {s['title'][:70]}  ({len(s['article_ids'])} art., "
              f"{len(s['publishers'])} outlets, {s['topic']})")

    def work(story):
        try:
            facts, rejected = extract_facts(story, articles)
        except Exception as e:  # one broken call must not stop the whole day: skip this story, say why
            return [], [{"fact": story["title"], "why": f"fact call failed: {e}"[:300]}]
        add_translations(facts, story, articles)
        return facts, rejected

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, chosen))
    facts = [f for fs, _ in results for f in fs]
    rejected = [r for _, rs in results for r in rs]
    (out / "facts.json").write_text(json.dumps({"start": args.start, "end": args.end, "facts": facts,
                                                "rejected": rejected}, indent=2, ensure_ascii=False), encoding="utf-8")
    conflicts = sum(f["conflict"] for f in facts)
    print(f"{len(chosen)} stories with facts: {len(facts)} facts verified ({conflicts} with conflicting sources), "
          f"{len(rejected)} sources rejected")


if __name__ == "__main__":
    main()
