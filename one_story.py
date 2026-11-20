"""First end-to-end test: ONE event from two sources (US producer prices, October 2026).

Run: .venv/Scripts/python one_story.py
Writes output/one_story/ (facts.json, briefing.json, briefing.mp3).
"""
import json
import sys
from pathlib import Path

from src.articles import load_articles
from src.briefing import build_briefing
from src.facts import extract_facts

OUT = Path("output/one_story")
STORY = {
    "id": "s1", "rank": 1, "title": "US producer prices for October 2026",
    "article_ids": ["INVZ-10009737-01M7AMS30JH9CG20KPB7WFHP1P",   # Invezz
                    "ACTI-10010414-01M7AP8WCVYF7JHMQF5AF5PSKQ"],  # ActionForex
}
PROFILE = {
    "name": "FX trader", "language": "en", "seconds": 40, "depth": "dense, numbers with period",
    "description": "A currency trader who wants the key figures, expectations and what they mean for the Fed.",
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    articles = load_articles(["invezz_en", "actionforex"])
    facts, rejected = extract_facts(STORY, articles)
    (OUT / "facts.json").write_text(json.dumps({"facts": facts, "rejected": rejected}, indent=2, ensure_ascii=False),
                                    encoding="utf-8")
    print(f"{len(facts)} facts verified, {len(rejected)} sources rejected")
    for f in facts:
        print(" ", "CONFLICT" if f["conflict"] else "ok      ", f["claim"], [s["publisher"] for s in f["sources"]])
    for r in rejected:
        print("  rejected:", r)
    briefing = build_briefing(PROFILE, [STORY], facts, OUT, audio="--no-audio" not in sys.argv)
    print("\nSCRIPT")
    for c in briefing["claims"]:
        print(" ", c["text"], [s["publisher"] for s in c["sources"]])
    for d in briefing["dropped"]:
        print("  dropped:", d)
    print("audio:", briefing["audioPath"])
