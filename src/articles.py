"""Load the Newstex JSONL feeds into one flat, uniform list of articles."""
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
FEEDS = ["actionforex", "ibtimes_uk", "invezz_en", "invezz_de", "invezz_nl", "zacks"]


def feed_of(stem, record):
    """The feed name the pipeline keys on (Invezz translations are linked by "invezz_de"/"invezz_nl"). A file with
    one of our feed names keeps it; any other file name (a jury export) gets it from the record itself."""
    if stem in FEEDS:
        return stem
    name = (record.get("publication") or {}).get("name", "")
    if name.lower().startswith("invezz"):
        return f"invezz_{record.get('language', 'en')}"
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or stem


def load_articles(feeds=None, data=None):
    """Return {article_id: article}. Skips articles without link or text.

    data: a folder of Newstex JSONL files, one article per line (default data/). feeds: file names without .jsonl;
    default every *.jsonl in the folder, so your own export works under any file names.
    """
    folder = Path(data) if data else DATA
    paths = [folder / f"{f}.jsonl" for f in feeds] if feeds else sorted(folder.glob("*.jsonl"))
    if not paths:
        raise FileNotFoundError(f"no .jsonl files in {folder}")
    out = {}
    for path in paths:
        stem = path.stem
        for line in path.open(encoding="utf-8"):
            if not line.strip():
                continue
            a = json.loads(line)
            text = (a.get("text_content") or "").strip()
            url = a.get("permalink")
            if not text or not url:
                continue
            out[a["$id"]] = {
                "id": a["$id"],
                "feed": feed_of(stem, a),
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
