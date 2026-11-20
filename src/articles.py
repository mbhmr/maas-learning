"""Load the Newstex JSONL feeds into one flat, uniform list of articles."""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
FEEDS = ["actionforex", "ibtimes_uk", "invezz_en", "invezz_de", "invezz_nl", "zacks"]


def load_articles(feeds=FEEDS):
    """Return {article_id: article}. Skips articles without link or text."""
    out = {}
    for feed in feeds:
        path = DATA / f"{feed}.jsonl"
        for line in path.open(encoding="utf-8"):
            a = json.loads(line)
            text = (a.get("text_content") or "").strip()
            url = a.get("permalink")
            if not text or not url:
                continue
            out[a["$id"]] = {
                "id": a["$id"],
                "feed": feed,
                "publisher": a["publication"]["name"],
                "language": a.get("language", "en"),
                "author": a.get("source"),
                "date": a["date"],
                "headline": a["headline"].strip(),
                "excerpt": (a.get("excerpt") or "").strip(),
                "url": url,
                "text": text,
                "sections": a.get("provider_categories") or [],
            }
    return out
