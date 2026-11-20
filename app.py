"""The Liquid Briefing, Maas Learning. Run: streamlit run app.py

Pick a prepared news day, describe any listener, get a briefing: audio, and a
transcript where every factual line links to the article it came from.
"""
import hashlib
import json
from pathlib import Path

import streamlit as st

from src.briefing import build_briefing, slug

OUTPUT = Path("output")
PRESETS = {
    "FX trader (EN)": {
        "name": "FX trader", "language": "en", "seconds": 120, "depth": "dense, every figure with its period",
        "description": "A currency trader. Wants central banks, inflation and macro data, FX moves and the biggest "
                       "market-moving company news. Numbers first, no background explanations.",
    },
    "Privatanleger (DE)": {
        "name": "Privatanleger", "language": "de", "seconds": 75, "depth": "simple, explain terms in a few words",
        "description": "A private investor in Germany with little time. Wants the big stories of the day in plain "
                       "language, what happened and why it matters, few numbers.",
    },
    "Custom listener": {
        "name": "", "language": "en", "seconds": 90, "depth": "medium",
        "description": "",
    },
}
LANGS = {"en": "English", "de": "Deutsch", "nl": "Nederlands"}
DEPTHS = ["dense, every figure with its period", "medium", "simple, explain terms in a few words"]

st.set_page_config(page_title="The Liquid Briefing", page_icon="🎧", layout="centered")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def prepared_days():
    return sorted((p.parent.name for p in OUTPUT.glob("*/facts.json") if (p.parent / "stories.json").exists()),
                  reverse=True)


def usage_summary():
    path = OUTPUT / "usage.jsonl"
    if not path.exists():
        return None
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    steps = {}
    for r in rows:
        s = steps.setdefault(r["step"], {"calls": 0, "input_tokens": 0, "output_tokens": 0, "characters": 0, "usd": 0.0})
        s["calls"] += 1
        for k in ("input_tokens", "output_tokens", "characters"):
            s[k] += r.get(k) or 0
        s["usd"] += r.get("usd") or 0.0
    return steps


def show_briefing(b):
    p = b["profile"]
    st.subheader(f"{p['name'] or 'Listener'} · {LANGS[p['language']]} · about {p['seconds']} s")
    if b.get("audioPath") and Path(b["audioPath"]).exists():
        st.audio(b["audioPath"], format="audio/mp3")
        st.caption("Synthetic voice (ElevenLabs). The audio is generated from exactly the transcript below.")
    else:
        st.info("No audio for this run (transcript only).")

    st.markdown("#### Transcript")
    for c in b["claims"]:
        if c["kind"] == "disclosure":
            st.markdown(f"*{c['text']}*")
            continue
        links, quotes = [], []
        for s in c["sources"]:
            mark = " ⚠️" if s.get("conflict") else ""
            target = s.get("evidenceUrl") or s["url"]  # opens the original and highlights the passage
            label = f"{s['publisher']}: {s['value']}{mark}" if s["value"] else s["publisher"]
            links.append(f"[{label}]({target})")
            if s.get("quote"):
                quotes.append(f"> “{s['quote']}” ({s['publisher']}, [open at this passage]({target}))")
            for lang, t in (s.get("translations") or {}).items():
                if lang == p["language"]:
                    links.append(f"[{t['publisher']}]({t['url']})")
        conflict = any(s.get("conflict") for s in c["sources"])
        line = f"{c['text']}"
        if links:
            line += "  \n<small>" + " · ".join(links) + "</small>"
        if conflict:
            line += "  \n<small>⚠️ Sources give different values. Both are named.</small>"
        st.markdown(line, unsafe_allow_html=True)
        if quotes:
            with st.expander("Evidence"):
                st.markdown("\n\n".join(quotes))

    with st.expander("How this briefing was made"):
        st.markdown("**Stories, most important first** (several outlets on one event are merged into one story):")
        for s in b["stories"]:
            st.markdown(f"{s['rank']}. {s['title']} ({s['articles']} article{'s' if s['articles'] > 1 else ''})")
        if b["dropped"]:
            st.markdown("**Lines removed by the checker before speech** (number or source not found):")
            for d in b["dropped"]:
                st.markdown(f"- ~~{d['text']}~~ ({d['why']})")
        else:
            st.markdown("The checker removed no line.")


st.title("🎧 The Liquid Briefing")
st.caption("Same news day, a different briefing for every listener. Every spoken fact links to its source.")

days = prepared_days()
if not days:
    st.error("No prepared news day yet. Run `python prepare.py --day 2026-11-13` first.")
    st.stop()

with st.sidebar:
    day = st.selectbox("News day", days)
    preset = st.radio("Listener", list(PRESETS), index=0)
    base = PRESETS[preset]
    name = st.text_input("Name", base["name"], key=f"name-{preset}")
    language = st.selectbox("Language", list(LANGS), index=list(LANGS).index(base["language"]),
                            format_func=LANGS.get, key=f"lang-{preset}")
    seconds = st.slider("Length (seconds)", 30, 180, base["seconds"], step=15, key=f"sec-{preset}")
    depth = st.selectbox("Depth", DEPTHS, index=DEPTHS.index(base["depth"]), key=f"depth-{preset}")
    description = st.text_area("Who is listening, what do they care about?", base["description"], height=140,
                               key=f"desc-{preset}")
    audio = st.checkbox("Generate audio", value=True)
    go = st.button("Generate briefing", type="primary", use_container_width=True)

profile = {"name": name.strip(), "language": language, "seconds": seconds, "depth": depth,
           "description": description.strip()}
key = hashlib.sha1(json.dumps(profile, sort_keys=True).encode()).hexdigest()[:8]
out_dir = OUTPUT / day / "briefings" / f"{slug(name)}-{key}"
cached = out_dir / "briefing.json"

if go:
    if not profile["description"]:
        st.warning("Describe the listener first.")
        st.stop()
    if cached.exists() and (not audio or load_json(cached).get("audioPath")):
        st.success("This listener was generated before. Playing the saved briefing.")
    else:
        stories = [s for s in load_json(OUTPUT / day / "stories.json") if s["selected"]]
        facts = load_json(OUTPUT / day / "facts.json")["facts"]
        with st.spinner("Writing and checking the script" + (", then recording" if audio else "") + " ..."):
            try:
                build_briefing(profile, stories, facts, out_dir, audio=audio)
            except Exception as e:  # show a readable message instead of a stack trace
                st.error(f"Could not build the briefing: {e}")
                st.stop()

if cached.exists():
    show_briefing(load_json(cached))
else:
    st.info("Describe a listener on the left and press **Generate briefing**.")

steps = usage_summary()
if steps:
    with st.expander("Cost so far (all runs, from output/usage.jsonl)"):
        st.table([{"step": k, **v, "usd": round(v["usd"], 4)} for k, v in steps.items()])
