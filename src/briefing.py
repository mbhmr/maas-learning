"""From verified facts to one finished briefing: checked script, MP3 and transcript JSON."""
import json
import re
from pathlib import Path
from urllib.parse import quote as urlquote

from .script import CLOSING, OPENING, write_script
from .tts import speak


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "listener"


def evidence_url(url, quote):
    """Link that opens the original article and highlights the quote (text fragment, Chrome/Edge/Safari).

    We never show the article itself (licence), only the short verified quote and this link.
    """
    return f"{url}#:~:text={urlquote(quote.strip().rstrip('.'), safe='')}"


def build_briefing(profile, stories, facts, out_dir, audio=True):
    """Writes briefing.json (and briefing.mp3) to out_dir and returns the briefing dict.

    The transcript and the speech come from the same checked lines, so what you
    hear is exactly what you can click through.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lang = profile["language"]
    lines, dropped, chosen = write_script(profile, stories, facts)
    by_id = {f["id"]: f for f in facts}

    claims = [{"text": OPENING[lang], "sources": [], "kind": "disclosure"}]
    for line in lines:
        sources, seen = [], set()
        for fid in line["fact_ids"]:
            f = by_id[fid]
            for s in f["sources"]:
                if s["article_id"] in seen:
                    continue
                seen.add(s["article_id"])
                sources.append({"articleId": s["article_id"], "publisher": s["publisher"], "url": s["url"], "date": s["date"][:10],
                                "value": s["value_in_source"], "conflict": f["conflict"],
                                "quote": s["quote"], "evidenceUrl": evidence_url(s["url"], s["quote"]),
                                "translations": s.get("translations", {})})
        claims.append({"text": line["text"], "sources": sources, "kind": "claim" if sources else "transition"})
    claims.append({"text": CLOSING[lang], "sources": [], "kind": "disclosure"})

    briefing = {"profile": profile, "audioPath": None, "claims": claims, "dropped": dropped,
                "stories": [{"rank": s["rank"], "title": s["title"], "articles": len(s["article_ids"])} for s in chosen]}
    for n, c in enumerate(claims):
        c["id"], c["start"], c["end"] = f"c{n}", None, None
    if audio:
        mp3 = out_dir / "briefing.mp3"
        for c, t in zip(claims, speak([c["text"] for c in claims], mp3, lang)):
            if t:
                c["start"], c["end"] = t  # seconds into the MP3, for highlighting and seeking
        briefing["audioPath"] = str(mp3)
    (out_dir / "briefing.json").write_text(json.dumps(briefing, indent=2, ensure_ascii=False), encoding="utf-8")
    return briefing
