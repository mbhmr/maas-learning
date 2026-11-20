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
python prepare.py --day 2026-11-13        # prepare one news day (about 16 model calls)
python prepare.py --day 2026-11-13 --stories-only   # grouping and ranking only, free
streamlit run app.py                      # the app: describe a listener, get the briefing
```

## Working together

- One branch per person (`daten`, `audio`, `ui`), small commits, pull before push, merge into `main` with a pull request.
- Never commit `.env`, `data/` or `output/` (already in `.gitignore`).
