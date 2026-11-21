# Evaluation against our own answer key

Measured on 20 Nov 2026, 17:45, with `output/2026-11-18/stories.json` (17:19), `facts.json` (17:23) and the ten briefings in `output/2026-11-18/briefings/` (17:40 to 17:43). Re-run any time, offline and free (note: every new `prepare.py` run changes story ids and grouping, so a re-run gives different numbers than the ones below, and the hand-checked fact and claim verdicts no longer match; the key itself, matched by article id, stays valid for the grouping scores):

```
.venv/Scripts/python eval/evaluate.py            # table
.venv/Scripts/python eval/evaluate.py --json     # everything, machine-readable
```

The key (`eval/answer_key.json`) was built by hand, not by a model: headlines, leads and article text of 13 to 18 Nov were read, and every event lists all its articles across outlets and languages (German and Dutch Invezz versions checked by headline). It holds 29 events with 144 articles (18 events with two or more articles, 11 single-article events that must stay apart), 46 facts and 51 spoken claims, each checked against the article text. Articles where reasonable editors could disagree are marked `ambiguous` and left out of the scoring. No article text is stored: ids, headlines, numbers and at most the first eight words of a quote.

## Jury benchmark (21 Nov)

`eval/benchmark.py` scores every finished briefing on what the Sourcera jury checks, offline and free:

```
.venv/Scripts/python eval/benchmark.py                                                 # the demo presets of 18 Nov
.venv/Scripts/python eval/benchmark.py --folder output/pregen/2026-11-18-flex-fix7     # all 324 shared editions
```

What each check means is in the file's docstring. The rule while fixing: never loosen a check to reach 100 %, fix the pipeline. Where the benchmark itself was wrong (a false alarm), it was corrected and the case is listed below. Two fresh reviews read the benchmark without knowing the plan; the second one found five ways it passed things it should fail, all closed (an invented article id skipped the quote check, figures in context lines were not checked, a merged story hid repeats, small whole figures were ignored, "producer" in an earlier clause excused a bare "annual inflation").

**The four demo presets** (fx-trader, privatanleger, belegger, world-news; 18 Nov, with audio): **every check at 100 %**, audio check included (the speech recogniser heard every figure as written).

**All 324 shared editions of 18 Nov**, each run scored with today's benchmark:

| Run (night of 21 Nov) | figures | language | length | must_hear | wording | verbatim | others |
|---|---|---|---|---|---|---|---|
| run 1, before the fixes | 88.9 % | 99.1 % | 80.6 % | 63.9 % | 94.8 % | 74.7 % | sourced 99.7 % (one empty edition) |
| fix3 | 92.9 % | 99.4 % | 90.4 % | 65.4 % | 94.4 % | 77.8 % | 100 % |
| fix4 (quotes read in their own language) | 100 % | 99.4 % | 89.8 % | 66.0 % | 92.0 % | 76.8 % | 100 % |
| **fix7 (all fixes)** | **100 %** | **100 %** | **92.9 %** | **95.1 %** | **100 %** | 38.0 % (see below) | **100 %** |

"Others" are sourced, dates, disclosure, no_advice and no_repeats. Audio is not applicable to text-only editions. fix7 wrote all 324 in 674 s for 3.12 USD, 0 failures, 0 empty editions, 0 lines without a source.

**What the benchmark found in the pipeline, all fixed in code:**
- English decimal points in German and Dutch lines: "6.077 Millionen ETH" is 6,077 million to a German ear, 1000x wrong. The old checker let it through on purpose.
- German and Dutch quotes read as English: "351.000 Barrel" became 351, and the line was "corrected" to 351,000.
- English sentences in Dutch and German lines.
- The writer rule kept "indices" in English, so 33 editions said "US Producer Price Index".
- One empty 30 s edition, and too short editions.
- The top story of the day had nothing to speak: facts needed a number, so Huang's statement was never a fact. Every line about it was rightly blocked by the content check.
- Two quotes not word for word in their article: a control character instead of "£", and a quotation mark the model added.
- The October retail sales as two stories (Zacks and ActionForex).
- "rose 0.3 percent in October on 13 November".
- "annual inflation" for the PPI rate.

**Where the benchmark was wrong and was corrected** (false alarms, each checked by hand):
- Date ranges ("8 en 9 december"), and "a December 25 basis points hike" read as a date.
- Dutch "verkopen", and words shared by two languages (in, is, die, je).
- A year inside a date ("November 18, 2026", "Q3 2026").
- "Take-Two" read as the figure 2.
- "wholesale inflation", which does name the PPI.
- Shared editions were measured without the greeting the player puts in front of them.

**Why fix7 is not 100 % everywhere, and why that is honest:**
- **verbatim 38 %:** all 201 failures are one quote. It is Huang's statement with the leading quotation mark the model added, fixed in `facts.json` and in `src/facts.py` (`exact_quote`) after fix7 had loaded the facts. All 362 quotes of 18 Nov now stand word for word in their article, and the demo presets pass. A new run would show it; we did not pay for a fifth full run.
- **length 92.9 %:** 23 editions are more than 25 % short, mostly "world" and "simple" ones. After the checker there is not enough checked material for them; we keep a short checked briefing rather than fill it with unchecked lines. Without audio, length is words divided by the pipeline's own measured speaking rate, so it checks the word budget, not the clock.
- **must_hear 95.1 %:** a soft proxy (the highest-ranked must-hear story of the listener's topics). 10 of the 16 misses are the merged retail story, now ranked #3, in editions that picked other macro news; 4 are Huang.
- **Known gap:** `no_repeats` does not flag one shared figure across two different stories. The PPI 6.5 % also appears in a gold story. One figure alone across stories is too often chance (0.3 % for CPI and PPI).
- **Shared building blocks:** the benchmark uses the pipeline's number reader, must-hear definition and greeting text, but none of its allowances. `verbatim`, `dates` and `language` are independent of the pipeline.

**Changed in place on 21 Nov, about 01:30 to 02:00:** `output/2026-11-18/stories.json` and `facts.json`. This covers the retail merge (`prepare.py --remerge`), the "£" quote, the Huang fact `s1-f6` and its quote. Backups are in `output/_papierkorb/2026-11-18-vor-remerge/`. `facts.json` keeps its old modification time on purpose, because the API keys its briefing cache by it; restart the API so its pipeline numbers re-read the file.

## Status after the fixes (20 Nov evening)

Re-measured merging at 20:40 on the new prepare run (with the safer merge rule): pairwise precision **99.9 %** (was 97.7 %), recall **59.6 %** (was 52.4 %), events mixed with another key event **2 of 29** (was 4 stories), multi-article events split 7 of 18 (was 10). Importance-A events in the top 10 fell to 3 of 8 (was 5): ranking is the open weak spot. Facts and spoken claims were not re-judged by hand.

Everything below was measured at 17:45, before commit 2377ab9 and the commits after it. Several listed gaps are now closed by code (the numbers below are the 17:45 state):

- A person named in a spoken line must be named in one of its quotes (catches the unsupported Waller claim).
- Time qualifiers in a line (after hours, premarket, "nachbörslich" and the like) must appear in one of its quotes (catches "after hours" vs regular trading).
- Only the newest fact per entity and metric goes to the writer (catches the stale Anthropic price range).
- At fact extraction, "is expected to" without who expects it, and macro figures without a country, are rejected (catches s29-f1 and s29-f3).
- The `'buy' rating` advice filter no longer drops news about a rating.
- Translated round-ups are filtered.
- Headlines that share only a weak name (a country, a data series) no longer merge (targets the mixed stories s5, s17, s18, s26).

Ranking after the latest prepare run (21:52, new rank score): 6 of 8 importance-A events in the top 10 (was 3), precision 99.9 %, recall 59.0 %, 2 of 29 events mixed. Known limit: the speculation penalty also hits real news written as a question ("Why is there a nationwide ground stop today?", "Is Chase Bank down?") and "beat forecast"; a narrower rule moved Waller out of the top 10 in an offline check, so the measured rule stays. Story titles: a story that ran over several days now takes the headline of a quoted article when its own headline is more than a day older ("Nasdaq opens 1.5% lower" on the 16th stood above "gained 0.35%" from the 18th).

Still open: pronoun-led quotes (Optimizely), a time with no date or event (world-news c8), and the split stories (recall).

## The numbers

| What | Result |
|---|---|
| Merging, pairwise precision | **97.7 %** (603 right pairs, 14 pairs of different events wrongly joined) |
| Merging, pairwise recall | **52.4 %** (548 pairs that belong together are in different stories) |
| Multi-article events split over several stories | **10 of 18** |
| Stories that glue different key events together | **4 stories, holding 10 key events** |
| Importance-A events in the top 10 | 5 of 8 (PPI is #23, US retail sales #43, Waller #14) |
| Facts in `facts.json` correct | **43 of 46 = 93.5 %**; 0 wrong numbers, 3 wrong context (all minor) |
| Spoken claims correct | **40 of 48 = 83.3 %** (28 distinct sentences: 22 = 78.6 %); 7 wrong, 1 unsupported |

Pairwise recall is dominated by the Huang story (40 articles, 780 of the 1,151 gold pairs). Per event, the picture is the 10 of 18 split events. Precision is measured only among key articles; the 4 mixed stories below also contain unrelated articles outside the key.

## Merge errors

Split (the same event in several stories):

| Event | Stories | What went wrong |
|---|---|---|
| E03 Jensen Huang exit | 6 | s1 holds 31 of 40; "Nvidia stock outlook after Huang's exit" (+DE/NL), "Why is Nvidia falling over 2% on Wednesday" (+DE/NL, its lead is the House probe of Huang), Lori Huang's fortune, Denny's plaque, "185,000 demand his return" are on their own |
| E06 Anthropic IPO | 5 + 1 missing | 9 of 20 in s2; IPO preview, index inclusion, "beat SpaceX", O'Leary are separate. "Anthropic receives its first 'Buy' rating" is in no story: the advice filter (`'buy' rating`) dropped news about a rating (now fixed) |
| E05 Microsoft outage | 5 | no two outlets merged; main story only rank 132 |
| E04 FAA ground stop | 6 | 8 of 13 together, 5 IBTimes follow-ups alone |
| E07 Nvidia Q3 results | 2 | "investors still need answers" (+DE/NL) apart from the results story |
| E08 Deutsche Bank leak | 2 | Invezz (+DE/NL) and IBTimes UK never merged although both name Deutsche Bank and Epstein |
| E10 Pattinson as Bond | 3 | 6 of 8 together |
| E11 US retail sales | 2 | ActionForex and Zacks apart; the Zacks headline shares few words |
| E12 Oil, API inventory build | 2 | the English article sits in an older Brent outlook story (s8, with 16 and 17 Nov analyses); the German and Dutch versions form their own story (s25) because their author differs from the English one, so `link_translations` fails |
| E09 Apple outage | 2 | one of three IBTimes articles alone |

Mixed (different events in one story). These are worse: they look like one story and the briefing speaks them under one headline.

| Story | Glued together | Effect |
|---|---|---|
| s5 "Canada CPI holds at 3.1%" | Canada CPI (E18), Eurozone HICP (E19), UK CPI (E20) | three releases from three days under one title; the FX briefing's Eurozone sentence cites story s5 |
| s17 "Kalshi buys FB Securities" | Kalshi buys broker (E21), CFTC sues Louisiana (E13, +DE/NL), Kalshi GTA job ad (E22) | three unrelated Kalshi stories |
| s18 "Trump tapping his leg in China" | Trump leg tapping (E26) and China industrial output (E25) | the China data fact s18-f1 is filed under a Trump gossip story |
| s26 "Wall Street's next big test ... shopping trolley" | Walmart/Target preview (E27) and an Illinois murder suspect named Captain America (E28) | they share only the word "America" |

Seen outside the key, same pattern: s69 silver plus an EUR/USD forecast, s56 two different Trump politics stories.

How it could have been noticed: none of this is visible in the briefing itself. A mixed story looks like a normal story with several sources; it shows up only when someone reads the headline list of a story, which is what this key does. Cheap guard: flag every merged story whose headlines share no proper name (Canada/Eurozone/UK, Kalshi/CFTC, Trump/China), and treat the same-author rule for translations as a hint, not a condition (E12).

Also found (now fixed, translated round-ups are filtered): German and Dutch translations of round-ups escaped the round-up filter, because the filter ran on the English headline before translations were attached ("5 Dinge vor Handelsbeginn", "5 dingen om te weten" are stories s354 and s355, both selected for facts).

## Fact errors (3 of 46, all minor, no wrong number)

| Fact (id when checked) | Claim | Why wrong | Could it have been noticed? |
|---|---|---|---|
| s2-f1 | "Anthropic has priced its IPO at $83 per share." | The article says the price comes from CNBC/Bloomberg sources and was not yet locked in a prospectus; stated as confirmed | Only by reading on: the hedge is two sentences after the quote |
| s29-f1 | "The Federal Reserve is expected to raise ... by 25 basis points" | The article says markets price it at about 98 %; the claim drops "markets" and uses the exact phrasing the fact prompt forbids | Yes, by code: `unattributed` looks for named people only, not for "is expected to". **Now caught:** rejected at extraction |
| s29-f3 | "Core CPI increased 0.3% ... in October" | Country missing (US); on a day with UK, Canada and Eurozone CPI this is ambiguous | Yes: a claim about CPI, GDP or rates without a country name. **Now caught:** rejected at extraction |

## Claim errors (8 of 48 spoken claims)

| Briefing, claim | Spoken | Why wrong | Could it have been noticed? |
|---|---|---|---|
| jamal c9, mark c9, sofia c9 (and belegger c6 in Dutch) | "Anthropic maintained its proposed IPO price range of $70 to $78 per share." | **Stale.** True on 17 Nov, but Anthropic priced at $83 on 18 Nov, the day before the briefing. Both facts are in `facts.json` (s32-f4 and s2-f1); the script picked the old one | Not by the number check: the numbers are in the quote. A rule "for the same company and metric, speak only the newest fact" would catch it. **Now caught:** only the newest fact per entity and metric reaches the writer |
| privatanleger c2 | "Nvidia-Aktien stiegen im nachbörslichen Handel um 1,6 Prozent" | After hours on 17 Nov Nvidia rose 2.47 % (article 7J3EQV); the 1.6 % was regular trading on 18 Nov (GG1XRT). The word "nachbörslich" was added | Not by the number check (1.6 is in the quote). A content check of time qualifiers (after hours, premarket, yesterday) against the quote would. **Now caught:** a time qualifier must be in a quote |
| world-news c7 | "Optimizely traced about $7,040 in cryptocurrency ..." | In the article "It traced" follows Report URI's finding, so the tracer is most likely Report URI (the article is not fully explicit) | Hardly: the quote starts with "It" and the model resolved the pronoun. Rule: a quote that starts with a pronoun needs the sentence before it |
| world-news c8 | "Air traffic resumed at 8:15 p.m. ET after the system stabilised." | True, but which event (the FAA ground stop) and which day (13 Nov) are never said | Yes: a claim with a time and no date or no named subject |
| fx-trader c8 | "Waller wants more hikes, and markets still price a 25 bp December move with about 98% probability." | Unsupported: the only source is the Williams article, which never mentions Waller; the 98 % followed Williams' remarks | Yes, by code: a person named in the claim must be named in one of its quotes. **Now caught** |

All 8 passed the checker as it was at measurement time (17:45), because every number is in its quote. The fixes listed at the top now catch three of the five claim rows (stale range, after hours, the Waller claim) and both fact rows; the pronoun row and the time-without-date row are still open. The remaining errors are about time, entity and attribution, not numbers. That is the honest headline: numbers are solid, context is where it breaks.

## Slide-ready sentences

1. "We hand-checked 46 extracted facts and 48 spoken claims against the source articles: not one number was wrong, and 83 % of spoken claims were right in every detail."
2. "Every error we found was context, not a figure: a stale IPO range, 'after hours' instead of regular trading, a missing country or speaker. So our next checker tests time, entity and attribution, not just numbers."
3. "On 144 hand-labelled articles our story grouping is 98 % precise but finds only half of the duplicates: we would rather tell a story twice than mix two stories into one."

## Limits

- One person built the key in about two hours. Event borders (is the House probe part of the Huang story?) are a judgment, noted per event in `note`; borderline articles are `ambiguous`.
- Facts were sampled: the first fact of the top 22 stories, 10 random facts (seed 7) and every fact a briefing used.
- Claim ids and story ids change with every run. The key matches facts by article id and quote start, claims by briefing name and exact text; new sentences show up as "unchecked" and need a hand verdict.
