# The Liquid Briefing · Maas Learning

MAIN Summit Hackathon 2026, Sourcera track. One news day from Newstex, a personal audio briefing for any listener,
and every spoken fact links to the article it came from.

## For the jury

- **What it does:** one news day from six Newstex feeds becomes a personal audio briefing for any listener (language, length, depth, interests), in English, German or Dutch.
- **Why you can trust it:** every spoken sentence with a figure links to the verbatim quote it rests on. A checker blocks any line whose number, name, time or claim is not in its quote, and after recording, speech recognition listens to the audio and checks every figure again.
- **Measured:** against an answer key we built by hand (see `eval/REPORT.md`): no wrong number in 46 facts, and 6 of 8 must-hear events in the top 10 of the ranking.
- **Demo outputs are not in this repo:** the Newstex licence forbids republishing article text, so `data/` and `output/` stay local. The pitch video shows the app; to run it yourself, follow Setup and Run below with the event dataset.

## How it works

| Step | File | Cost |
|---|---|---|
| Load the six feeds, skip articles without text or link | `src/articles.py` | code |
| Attach German and Dutch Invezz translations to their English original | `src/cluster.py` | code |
| Drop buy/sell pitches, group articles about the same event (TF-IDF; a place or data series alone never joins two stories), rank stories (importance, number of outlets, freshness, a bonus for macro and currency news, a penalty for speculative headlines) | `src/cluster.py` | code |
| Extract 3 to 6 facts per selected story, each with article ID and a verbatim quote | `src/facts.py` | small model |
| Check every fact: quote must be in the article, value must be in the quote, mark conflicting sources | `src/facts.py` | code |
| Write the script for one listener from the checked facts | `src/script.py` | small model |
| Check every line in three stages: code (every number, superlative and source must be in the cited quotes; no relative dates, no repeats, no overlong sentences), a judge model (does the quote really say this?), then the length budget. A final pass drops repeats across the whole briefing; if it ends up under 80 % of the asked length, one more round writes lines from unused stories | `src/script.py` | code + small model |
| Repair round: blocked lines go back to the writer once, with the reason, and are checked again from the start | `src/script.py` | small model |
| Greeting and sign-off call the listener by name; short AI voice disclosure and "not investment advice" | `src/script.py` | code |
| Speech from exactly the checked transcript, with word timestamps for the live highlight | `src/tts.py` | ElevenLabs v4 (voice Danielle) |
| Listen back: Speech-to-Text on the finished MP3, every number of every claim must be heard in its time window (`audioCheck` in the briefing) | `src/audiocheck.py` | ElevenLabs Scribe |
| Shared editions: listeners with the same language, length, depth and interest segment share one recorded body, only the greeting is personal | `src/editions.py` | code + small model |

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
python prepare.py                         # prepare 13 to 18 Nov once (picks up to 120 stories, macro and multi-outlet stories always; last run 20 Nov evening: 94 small-model calls, about 0.18 USD, 93 stories with facts)
python prepare.py --stories-only          # grouping only, free
uvicorn api:app --port 8000               # API for the React player
cd web && npm install && npm run dev      # the player, http://localhost:5173 (proxies /api to port 8000)
streamlit run app.py                      # fallback app: describe a listener, get the briefing
python eval/evaluate.py                   # score against our hand-built answer key (needs eval/answer_key.json, kept local)
```

The player has two views: **Briefing** (four preset listeners and "your own listener" with an optional shared-edition
switch; player with speed and volume; the transcript with the word being spoken marked and a footnote number per
sourced sentence; the quotes of the selected sentence beside it, on phones as a sheet from below; and one folded
section "How this briefing was made" with the pipeline numbers, the stories, the blocked lines and the optional chime)
and **Today's ranking** (every story of the day in rank order with a one-line reason, the stories this listener hears
marked, and each story's articles one click away; a story's optional `reason` field replaces the computed line).

## API (for the player)

`POST /api/briefing` with `{"day": "2026-11-18", "profile": {"name", "language": "en|de|nl", "seconds", "depth", "description"}, "mode": "personal|edition"}`
returns the briefing. Same profile again = served from cache, no new cost. `personal` (default) chooses stories and
writes a script for this one listener; `edition` reuses the shared body of the listener's segment and adds a personal
greeting, the response then carries `edition: {key, segment, label, language, seconds, depth, listeners}`.
At most 4 briefings are built at once and 60 per hour; beyond that the API answers 429 with `Retry-After`.
`GET /api/stories/{day}` lists every story of the day, ranked, with its articles (headline, outlet, link, no article text).

```
{ "audioUrl": "/api/audio/2026-11-18/<key>.mp3",
  "claims": [ { "id": "c3", "text": "spoken sentence", "kind": "host|disclosure|claim|context|transition",
                "start": 12.4, "end": 16.9,            // seconds in the MP3; null if no audio or no timing
                "words": [[12.4, 12.7, 0, 5], ...],    // per written word: start s, end s, char start, char end in text
                "sources": [ { "articleId", "publisher", "date", "url", "quote", "evidenceUrl", "value", "conflict",
                               "translations": {"de": {"url", "publisher"}} } ] } ],
  "profile": {...}, "stories": [...], "dropped": [ { "text", "why" } ] }
```
`evidenceUrl` opens the original article with the quote highlighted (text fragment). Open it in a new tab so the
audio keeps playing. `dropped` lists lines the checker removed, worth showing ("what we did not say").

## Sound (for the player)

Three fixed sounds, made once with `python -m src.sound` (ElevenLabs Music and Sound Effects), served by
`GET /api/sound/{name}.mp3`. The player plays the `jingle` once before the briefing starts. `verified` and `conflict` are an opt-in chime
(switch in "How this briefing was made"): `verified` at the `end` of each claim with `kind: "claim"`, and `conflict`
instead when one of its sources has `conflict: true`. Any other name is 404.
To let the listener hear the original wording, `POST /api/quote-audio` with `{"quote": source.quote, "lang": "en|de|nl"}`
returns an MP3 of that quote in a calm voice. Send the `quote` exactly as it came in the briefing: only quotes of
checked facts are read aloud, anything else is 404, and each quote is generated once and then served from cache.

### Audio check

`src/audiocheck.py` listens back to the finished MP3: it sends it to ElevenLabs Speech-to-Text (Scribe, word timestamps)
and compares every number heard in a claim's time window with the numbers in its checked text.
`check_audio(mp3_path, claims, lang)` returns `{"checked", "ok", "mismatches": [{"claim_id", "text", "expected", "heard", "spoken"}]}` (`spoken` = the recognised words).
Names from the claims go in as keyterms, the numbers never do, so the recogniser is not told what it should hear.
The ElevenLabs key needs the Speech to Text permission. It runs after every briefing is recorded; the result is `audioCheck` in the briefing response, shown in the app. Spelled-out numbers ("zero point three", "one and a half", "dreiundachtzig", "anderhalf") are turned into digits before comparing; a missed figure is shown as a flag, never hidden. On the four demo briefings of 20.11. evening it heard every figure in 14 of 14 spoken lines with figures. If the check fails (no key permission, network), the briefing is still delivered with `audioCheck.error` set.

## Evaluation

`eval/REPORT.md` measures the pipeline against an answer key we built by hand (29 events, 144 articles, 46 facts,
48 spoken claims): no wrong number found, 83 % of spoken claims right in every detail, the rest were context errors
(stale figure, missing country or speaker). The key quotes headlines of the event data, so it stays out of Git.

## Working together

- One branch per person (`daten`, `audio`, `ui`), small commits, pull before push, merge into `main` with a pull request.
- Never commit `.env`, `data/` or `output/` (already in `.gitignore`).
