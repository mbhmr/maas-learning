"""From verified facts to one finished briefing: checked script, MP3 and transcript JSON."""
import json
import re
from pathlib import Path
from urllib.parse import quote as urlquote

from .script import write_script
from .tts import speak


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "listener"


def evidence_url(url, quote):
    """Link that opens the original article and highlights the quote (text fragment, Chrome/Edge/Safari).

    We never show the article itself (licence), only the short verified quote and this link.
    """
    words = quote.strip().rstrip(".").split()

    def enc(part):  # "-" and "," are syntax inside a text fragment, so they must be encoded
        return urlquote(" ".join(part), safe="").replace("-", "%2D")

    if len(words) <= 10:
        return f"{url}#:~:text={enc(words)}"
    # Long quote: match from its first to its last words. Tolerates small differences in the
    # middle (curly quotes, an edited word on the live page) that make an exact match fail.
    return f"{url}#:~:text={enc(words[:5])},{enc(words[-5:])}"


def _sources(fact_ids, by_id):
    """Every cited fact's quote, once: two facts from one article each keep their own quote."""
    sources, seen = [], set()
    for fid in fact_ids:
        f = by_id[fid]
        for s in f["sources"]:
            if (s["article_id"], s["quote"]) in seen:
                continue
            seen.add((s["article_id"], s["quote"]))
            sources.append({"articleId": s["article_id"], "factId": fid, "publisher": s["publisher"], "url": s["url"],
                            "date": s["date"][:10], "value": s["value_in_source"], "conflict": f["conflict"],
                            "quote": s["quote"], "evidenceUrl": evidence_url(s["url"], s["quote"]),
                            "translations": s.get("translations", {})})
    return sources


def build_briefing(profile, stories, facts, out_dir, audio=True):
    """Writes briefing.json (and briefing.mp3) to out_dir and returns the briefing dict.

    The transcript and the speech come from the same checked lines, so what you
    hear is exactly what you can click through.
    Claim kinds: "host" (greeting, sign-off), "disclosure" (fixed AI-voice and no-advice lines), "claim" (news),
    "context" (why it matters to this listener, our reading; its sources are the story's cited facts),
    "transition" (code text without a source, e.g. "nothing on X today").
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lang = profile["language"]
    lines, dropped, chosen, frame = write_script(profile, stories, facts)
    by_id = {f["id"]: f for f in facts}
    story_of = {f["id"]: f["story_id"] for f in facts}

    def frame_claim(key, kind):
        return [{"text": frame[key], "sources": [], "factIds": [], "kind": kind}] if frame.get(key) else []

    claims = frame_claim("greeting", "host") + frame_claim("opening", "disclosure")
    tags = ["excited"] * len(claims[:1]) + [""] * (len(claims) - 1)
    new_story = True
    for n, line in enumerate(lines):
        ids = list(line["fact_ids"])
        if line.get("kind") == "context":  # it interprets the story: show every fact of it that was spoken
            story = story_of[ids[0]]
            ids += [i for x in lines if x.get("kind") == "claim" for i in x["fact_ids"]
                    if story_of[i] == story and i not in ids]
        sources = _sources(ids, by_id)
        kind = line.get("kind", "claim") if sources else "transition"
        claims.append({"text": line["text"], "sources": sources, "factIds": ids if sources else [], "kind": kind})
        # energy for the first line of each story, plain delivery for the figures after it
        tags.append("excited" if kind == "claim" and new_story else "")
        new_story = kind != "claim"
    for key, kind, tag in (("sign_off", "host", "cheerful"), ("closing", "disclosure", "")):
        extra = frame_claim(key, kind)
        claims += extra
        tags += [tag] * len(extra)

    briefing = {"profile": profile, "audioPath": None, "claims": claims, "dropped": dropped,
                "stories": [{"rank": s["rank"], "title": s["title"], "articles": len(s["article_ids"])} for s in chosen]}
    for n, c in enumerate(claims):
        c["id"], c["start"], c["end"] = f"c{n}", None, None
    if audio:
        mp3 = out_dir / "briefing.mp3"
        for c, t in zip(claims, speak([c["text"] for c in claims], mp3, lang, tags=tags)):
            if t:
                c["start"], c["end"] = t  # seconds into the MP3, for highlighting and seeking
        briefing["audioPath"] = str(mp3)
    (out_dir / "briefing.json").write_text(json.dumps(briefing, indent=2, ensure_ascii=False), encoding="utf-8")
    return briefing
