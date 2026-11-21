# The Liquid Briefing · Maas Learning

MAIN Summit Hackathon 2026, Sourcera track. One news day from Newstex, a personal audio briefing for any listener,
and every spoken fact links to the article it came from.

## For the jury

- **What it does:** one news day from six Newstex feeds becomes a personal audio briefing for any listener (language, length, depth, interests), in English, German or Dutch.
- **Why you can trust it:** every spoken sentence with a figure links to the verbatim quote it rests on. A checker blocks any line whose number, name, time or claim is not in its quote, and after recording, speech recognition listens to the audio and checks every figure again.
- **Measured:** against an answer key we built by hand (see `eval/REPORT.md`): no wrong number in 46 facts, and 6 of 8 must-hear events in the top 10 of the ranking (the rank score was tuned on this same key, so read it as a fit, not a blind test).
- **Run it with your own keys and data, in four steps:**
  1. **Install** (Python 3.12+, Node 20+): see Setup below.
  2. **Keys:** copy `.env.example` to `.env` in the repo root and fill in two lines:
     - `OPENAI_API_KEY=` for writing and checking.
     - `ELEVENLABS_API_KEY=` for the voice and the audio check; it needs the Text to Speech and Speech to Text permissions.

     Leave the other lines empty to use the defaults (gpt-4.1-mini, voice Danielle on eleven_v4).
  3. **Data:** put your Newstex `.jsonl` export in any folder, then run `python prepare.py --data <that folder>`. This groups, ranks and fact-checks the last 6 days of the data, about 0.1 to 0.2 USD per run. See "Use your own data".
  4. **Start:** run `uvicorn api:app --port 8000`, then `cd web && npm install && npm run dev`, and open http://localhost:5173. Pick the day, describe a listener and press create. The tab **Today's ranking** shows how every story was ranked and why.
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
python prepare.py --start 2026-11-13 --end 2026-11-18   # the demo day: prepare 13 to 18 Nov once (picks up to 120 stories, macro and multi-outlet stories always; last run 20 Nov evening: 94 small-model calls, about 0.18 USD, 93 stories with facts; the run behind the demo briefings of 21 Nov kept 81 stories with 347 facts)
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

## Use your own data

One command turns any Newstex export into a news day the player can open:

```
python prepare.py --data path/to/your/newstex
```

- **Folder:** any folder with Newstex `.jsonl` files, one article per line, any file names (`export-zacks.jsonl`, `day1.jsonl` ...). Fields used: `$id`, `headline`, `date`, `language`, `text_content`, `permalink`, `publication.name`, `source` (author), `excerpt`, `provider_categories`. Articles without text or link are skipped.
- **Window:** by default the last 6 days of the data, ending on the newest full day (a day with at least 10 % of the busiest day's articles, so a few stragglers of the next morning do not become the news day); choose it with `--start 2026-11-13 --end 2026-11-18`.
- **Output:** `output/<end>/stories.json` and `facts.json`; the API and the player list that day at once. `--out somewhere` writes elsewhere (for a trial run the player should not see).
- **Checked end to end (21 Nov):** the 190 articles of 17 Nov copied into a new folder under other file names, `prepare.py --data` on it: 66 stories with facts, 273 checked facts, about 0.1 USD; one trader briefing from it passed every check of `eval/benchmark.py`. That run found and fixed one trap: German and Dutch Invezz translations were linked by file name, now by the publisher in the record.

## Several days in one briefing

A profile may carry `days`: `1` = only stories whose newest article is from the last day, `3` = the last three days, unset = the whole prepared window (6 days). With more than one day the writer is told it is a review of those days and every claim says its date. On 18 Nov: 38 stories with facts for `days: 1`, 72 for `3`, 82 for the whole week (`src/script.py`, `in_span`).

## What makes it scale and learn

Measured on 21 Nov, numbers from our own runs; reports in `output/` (local, not in Git).

| What | How | Measured |
|---|---|---|
| **The whole day is written before anyone wakes up** | `pregenerate.py <day> --live` writes and checks all 324 shared editions into `output/<day>/editions`, which the API serves (without `--live` it is a measured trial run in its own folder; the demo day ships without them) (3 languages x 6 lengths x 3 depths x 6 interest segments), 8 in parallel. A listener then needs one cached segment call, no writer model; the voice is paid only when the first listener of an edition presses play | all 324 in **11.2 min** for **3.12 USD** (0.96 ct per edition, run fix7), 0 failures, 0 empty editions, **0 lines without a source**. Voice for all 324 if every one were heard: 597,458 characters, about 48 USD at 0.08 USD per 1,000 characters |
| **Half price at night** | The night run uses OpenAI's flex tier (slower, half price; nobody is waiting). A busy refusal falls back to the normal price (not yet seen live). Only the gpt-5 calls (writer, repair) take flex; gpt-4.1-mini refuses it | per writer call **0.26 ct** on flex vs **0.49 ct** at normal price (-46 %). Per edition 0.85 vs 1.43 ct (-41 %), but the two 18-edition runs made a different number of calls (109 vs 123), so the per-call figure is the clean one; flex took 60 s vs 49 s |
| **Honest cost log** | Every call logs cached input tokens, reasoning tokens and the tier, and the price counts them (`src/llm.py`, `cost_usd`) | story selection gets cache hits from the provider (110k cached tokens in an 18-edition run), writer and judge prompts are too short for it. The cache discount shares are from the price list, not checked against an invoice |
| **Our own jury benchmark** | `eval/benchmark.py` scores every briefing on what the jury checks: figures with scale in the quotes (each quote read in its own language), quotes word for word in the article, dates, sources, disclosure, no advice, language, length, audio check, no repeated news, wording, must-hear story. It uses the pipeline's number reader but none of its allowances | the four demo presets pass every check (100 %). All 324 editions (fix7): figures, language, wording, dates, sources, no repeats 100 %, length 92.9 %, must-hear 95.1 %; why not all 100 % in [`eval/REPORT.md`](eval/REPORT.md#jury-benchmark-21-nov). It found real faults that are now fixed in the pipeline: English decimal points in German and Dutch lines ("6.077 Millionen ETH", 1000x wrong), German quotes read as English ("351.000 Barrel" as 351), English sentences in Dutch and German lines, an empty 30 s edition, too short editions, every line on the day's lead story blocked by the person check, a quote with a control character instead of "£", the October retail sales as two stories, "in October on 13 November", "annual inflation" for the PPI rate |
| **The checker teaches the writer (experimental, off)** | `src/lessons.py` counts why lines were blocked over earlier briefings and adds the five most frequent reasons, each with two real blocked lines, to the end of the writer prompt. `eval/ab_lessons.py` tests it: same stories, same checks, with and without | 160 runs: on the day it learned from, blocked first-draft lines **28.3 % -> 22.9 %** (paired difference -5.4 points, 95 % interval -10.2 to -0.7). On an unseen day **no effect** (-0.9, interval -5.7 to +3.9), and lines carried slightly fewer figures. So it stays switched off (`LESSONS=1` turns it on) until it helps on new days too |

What still runs in the cloud at listen time: nothing for a listener whose edition exists (segment call cached, body and greeting audio cached); for a new edition the writer and checker models and the voice. Nothing runs on the listener's device.

## API (for the player)

`POST /api/briefing` with `{"day": "2026-11-18", "profile": {"name", "language": "en|de|nl", "seconds", "depth", "description", "days"}, "mode": "personal|edition"}`
(`days` is optional: 1 = the last day, 3 = the last three days, left out = the whole prepared window)
returns the briefing. Same profile again = served from cache, no new cost. `personal` (default) chooses stories and
writes a script for this one listener; `edition` reuses the shared body of the listener's segment and adds a personal
greeting, the response then carries `edition: {key, segment, label, language, seconds, depth, listeners}`.
At most 4 briefings are built at once and 60 per hour; beyond that the API answers 429 with `Retry-After`.
`GET /api/stories/{day}` lists every story of the day, ranked, with its articles (headline, outlet, link, no article text)
and `why`, the parts of its rank score.

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
The ElevenLabs key needs the Speech to Text permission. It runs after every briefing is recorded; the result is `audioCheck` in the briefing response, shown in the app. Spelled-out numbers ("zero point three", "one and a half", "dreiundachtzig", "anderhalf") are turned into digits before comparing; a missed figure is shown as a flag, never hidden. On the four demo briefings of 21.11. night it heard every figure in 44 of 44 spoken lines with figures (12 + 16 + 7 + 9). If the check fails (no key permission, network), the briefing is still delivered with `audioCheck.error` set.

## Evaluation

`eval/REPORT.md` measures the pipeline against an answer key we built by hand (29 events, 144 articles, 46 facts,
48 spoken claims): no wrong number found, 83 % of spoken claims right in every detail, the rest were context errors
(stale figure, missing country or speaker). The key quotes headlines of the event data, so it stays out of Git.

## Working together

- One branch per person (`daten`, `audio`, `ui`), small commits, pull before push, merge into `main` with a pull request.
- Never commit `.env`, `data/` or `output/` (already in `.gitignore`).
