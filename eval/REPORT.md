# Evaluation against our own answer key

Measured on 20 Nov 2026, 17:45, with `output/2026-11-18/stories.json` (17:19), `facts.json` (17:23) and the ten briefings in `output/2026-11-18/briefings/` (17:40 to 17:43). Re-run any time, offline and free:

```
.venv/Scripts/python eval/evaluate.py            # table
.venv/Scripts/python eval/evaluate.py --json     # everything, machine-readable
```

The key (`eval/answer_key.json`) was built by hand, not by a model: headlines, leads and article text of 13 to 18 Nov were read, and every event lists all its articles across outlets and languages (German and Dutch Invezz versions checked by headline). It holds 29 events with 143 articles (18 events with two or more articles, 11 single-article events that must stay apart), 46 facts and 51 spoken claims, each checked against the article text. Articles where reasonable editors could disagree are marked `ambiguous` and left out of the scoring. No article text is stored: ids, headlines, numbers and at most the first eight words of a quote.

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
| E06 Anthropic IPO | 5 + 1 missing | 9 of 20 in s2; IPO preview, index inclusion, "beat SpaceX", O'Leary are separate. "Anthropic receives its first 'Buy' rating" is in no story: the advice filter (`'buy' rating`) drops news about a rating |
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

Also found: German and Dutch translations of round-ups escape the round-up filter, because the filter runs on the English headline before translations are attached ("5 Dinge vor Handelsbeginn", "5 dingen om te weten" are stories s354 and s355, both selected for facts).

## Fact errors (3 of 46, all minor, no wrong number)

| Fact (id when checked) | Claim | Why wrong | Could it have been noticed? |
|---|---|---|---|
| s2-f1 | "Anthropic has priced its IPO at $83 per share." | The article says the price comes from CNBC/Bloomberg sources and was not yet locked in a prospectus; stated as confirmed | Only by reading on: the hedge is two sentences after the quote |
| s29-f1 | "The Federal Reserve is expected to raise ... by 25 basis points" | The article says markets price it at about 98 %; the claim drops "markets" and uses the exact phrasing the fact prompt forbids | Yes, by code: `unattributed` looks for named people only, not for "is expected to" |
| s29-f3 | "Core CPI increased 0.3% ... in October" | Country missing (US); on a day with UK, Canada and Eurozone CPI this is ambiguous | Yes: a claim about CPI, GDP or rates without a country name |

## Claim errors (8 of 48 spoken claims)

| Briefing, claim | Spoken | Why wrong | Could it have been noticed? |
|---|---|---|---|
| jamal c9, mark c9, sofia c9 (and belegger c6 in Dutch) | "Anthropic maintained its proposed IPO price range of $70 to $78 per share." | **Stale.** True on 17 Nov, but Anthropic priced at $83 on 18 Nov, the day before the briefing. Both facts are in `facts.json` (s32-f4 and s2-f1); the script picked the old one | Not by the number check: the numbers are in the quote. A rule "for the same company and metric, speak only the newest fact" would catch it |
| privatanleger c2 | "Nvidia-Aktien stiegen im nachbörslichen Handel um 1,6 Prozent" | After hours on 17 Nov Nvidia rose 2.47 % (article 7J3EQV); the 1.6 % was regular trading on 18 Nov (GG1XRT). The word "nachbörslich" was added | Not by the number check (1.6 is in the quote). A content check of time qualifiers (after hours, premarket, yesterday) against the quote would |
| world-news c7 | "Optimizely traced about $7,040 in cryptocurrency ..." | In the article "It traced" follows Report URI's finding, so the tracer is most likely Report URI (the article is not fully explicit) | Hardly: the quote starts with "It" and the model resolved the pronoun. Rule: a quote that starts with a pronoun needs the sentence before it |
| world-news c8 | "Air traffic resumed at 8:15 p.m. ET after the system stabilised." | True, but which event (the FAA ground stop) and which day (13 Nov) are never said | Yes: a claim with a time and no date or no named subject |
| fx-trader c8 | "Waller wants more hikes, and markets still price a 25 bp December move with about 98% probability." | Unsupported: the only source is the Williams article, which never mentions Waller; the 98 % followed Williams' remarks | Yes, by code: a person named in the claim must be named in one of its quotes |

All 8 pass our current checker, because every number is in its quote. The remaining errors are about time, entity and attribution, not numbers. That is the honest headline: numbers are solid, context is where it breaks.

## Slide-ready sentences

1. "We hand-checked 46 extracted facts and 48 spoken claims against the source articles: not one number was wrong, and 83 % of spoken claims were right in every detail."
2. "Every error we found was context, not a figure: a stale IPO range, 'after hours' instead of regular trading, a missing country or speaker. So our next checker tests time, entity and attribution, not just numbers."
3. "On 143 hand-labelled articles our story grouping is 98 % precise but finds only half of the duplicates: we would rather tell a story twice than mix two stories into one."

## Limits

- One person built the key in about two hours. Event borders (is the House probe part of the Huang story?) are a judgment, noted per event in `note`; borderline articles are `ambiguous`.
- Facts were sampled: the first fact of the top 22 stories, 10 random facts (seed 7) and every fact a briefing used.
- Claim ids and story ids change with every run. The key matches facts by article id and quote start, claims by briefing name and exact text; new sentences show up as "unchecked" and need a hand verdict.
