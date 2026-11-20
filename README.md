# The Liquid Briefing · Maas Learning

MAIN Summit Hackathon 2026, Sourcera track. One news day from Newstex, a personal audio briefing for any listener,
and every spoken fact links to the article it came from.

## How it works

| Step | File | Cost |
|---|---|---|
| Load the six feeds, skip articles without text or link | `src/articles.py` | code |
| Attach German and Dutch Invezz translations to their English original | `src/cluster.py` | code |
| Drop buy/sell pitches, group articles about the same event (TF-IDF), rank stories | `src/cluster.py` | code |
| Extract 3 to 6 facts per selected story, each with article ID and a verbatim quote | `src/facts.py` | small model |
| Check every fact: quote must be in the article, value must be in the quote, mark conflicting sources | `src/facts.py` | code |
| Write the script for one listener from the checked facts | `src/script.py` | small model |
| Check every line: it must cite facts, and every spoken number must be in them, otherwise it is removed | `src/script.py` | code |
| Fixed opening (AI voice disclosure) and closing (not investment advice) | `src/script.py` | code |
| Speech from exactly the checked transcript | `src/tts.py` | ElevenLabs |

`prepare.py` runs once per news day, the app reuses its facts for every listener. Every model and voice call is
logged to `output/usage.jsonl` (tokens, characters, USD) for the cost estimate.

## Setup (Windows, macOS, Linux)

Python 3.12 or newer. On Windows on ARM use the x64 Python from python.org, Streamlit's `pyarrow` has no ARM build.

```
git clone https://github.com/mbhmr/maas-learning.git
cd maas-learning
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

1. **Data:** download the Sourcera dataset yourself and put the six `.jsonl` files into `data/`.
   The data is never committed (licence: no republishing, no sharing, delete after the event).
2. **Keys:** copy `.env.example` to `.env` and fill it in. Keys come through the private team chat, never through Git.

## Run

```
python one_story.py                       # first end-to-end test: US producer prices, two sources
python prepare.py                         # prepare 13 to 18 Nov once (about 70 small-model calls, ~0.20 USD)
python prepare.py --stories-only          # grouping only, free
uvicorn api:app --port 8000               # API for the React player in web/
streamlit run app.py                      # fallback app: describe a listener, get the briefing
```

## API (for the player)

`POST /api/briefing` with `{"day": "2026-11-18", "profile": {"name", "language": "en|de|nl", "seconds", "depth", "description"}}`
returns the briefing. Same profile again = served from cache, no new cost.

```
{ "audioUrl": "/api/audio/2026-11-18/<key>.mp3",
  "claims": [ { "id": "c3", "text": "spoken sentence", "kind": "claim|transition|disclosure",
                "start": 12.4, "end": 16.9,            // seconds in the MP3; null if no audio or no timing
                "sources": [ { "articleId", "publisher", "date", "url", "quote", "evidenceUrl", "value", "conflict",
                               "translations": {"de": {"url", "publisher"}} } ] } ],
  "profile": {...}, "stories": [...], "dropped": [ { "text", "why" } ] }
```
`evidenceUrl` opens the original article with the quote highlighted (text fragment). Open it in a new tab so the
audio keeps playing. `dropped` lists lines the checker removed, worth showing ("what we did not say").

## Sound (for the player)

Three fixed sounds, made once with `python -m src.sound` (ElevenLabs Music and Sound Effects), served by
`GET /api/sound/{name}.mp3`: play `jingle` once before the briefing starts, `verified` at the `end` of each claim
with `kind: "claim"`, and `conflict` instead when one of its sources has `conflict: true`. Any other name is 404.
To let the listener hear the original wording, `POST /api/quote-audio` with `{"quote": source.quote, "lang": "en|de|nl"}`
returns an MP3 of that quote in a calm voice. Send the `quote` exactly as it came in the briefing: only quotes of
checked facts are read aloud, anything else is 404, and each quote is generated once and then served from cache.

### Audio check

`src/audiocheck.py` listens back to the finished MP3: it sends it to ElevenLabs Speech-to-Text (Scribe, word timestamps)
and compares every number heard in a claim's time window with the numbers in its checked text.
`check_audio(mp3_path, claims, lang)` returns `{"checked", "ok", "mismatches": [{"claim_id", "text", "expected", "heard", "spoken"}]}` (`spoken` = the recognised words).
Names from the claims go in as keyterms, the numbers never do, so the recogniser is not told what it should hear.
The ElevenLabs key needs the Speech to Text permission. Not yet run on real audio (20.11.), only on simulated transcripts.

## Working together

- One branch per person (`daten`, `audio`, `ui`), small commits, pull before push, merge into `main` with a pull request.
- Never commit `.env`, `data/` or `output/` (already in `.gitignore`).
