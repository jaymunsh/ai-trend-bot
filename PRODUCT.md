# AI Trend Bot

<!-- impeccable:product-schema 1 -->

## Platform

web

The public-facing artifact is a static HTML explanation of a Python Telegram bot.

## Stack

Existing static HTML, CSS and JavaScript in `docs/`. The bot uses Python 3.13,
Gemini, RSS/public APIs and Telegram. GitHub Pages is the user's intended future
destination for the introduction page; deployment is not part of this redesign.

## Users

The current bot serves its owner, who follows AI tools, industry developments,
writing material and important announcements. The introduction explains the
project to future visitors. Whether visitors will be able to subscribe remains
undecided; do not invent signup or public subscription functionality.

## Product Purpose

Collect AI news, select worthwhile developments, summarize article content in
Korean and send a scheduled Telegram briefing. Help readers identify new facts
without reading every source article.

## Operating Context

The documented regular runner is miniPC cron at 07:15, 13:15 and 19:15 Asia/Seoul, preparing deliveries for 07:30, 13:30 and 19:30.
GitHub supplies code updates; Actions is a manual fallback. Delivery is variable,
with no message when nothing qualifies, and an operational cap of 50 items.

## Capabilities and Constraints

- 30 configured sources: 9 official, 16 community/media and 5 research.
- Nine of those are news outlets. The sum of configured candidate caps is 435;
  it is not the number of fresh articles received per run.
- URL deduplication, batched Gemini selection, event comparison against the
  previous 14 days, article-body extraction, Korean summaries and Telegram HTML.
- Source failures are isolated; failed body extraction falls back to the teaser.
- Successful message deliveries are recorded in an external current-month JSONL file and permanent monthly archives on miniPC.
- Recent 48-hour unsent filtering happens before source caps. Unknown dates stay explicitly uncertain.
- Summaries target two or three mobile lines, with a bold title and one representative link plus a distinct-outlet count. Other URLs remain in delivery history. Prepared digests stay in memory until delivery.
- Candidate persistence and rejected-item caching are intentionally absent.
- Git updates alone do not replace the installed miniPC runner or cron; refresh both during operational rollout.
- The user does not want additional company-specific newsroom collection.

## Evidence on Hand

`README.md`, `config/sources.toml`, `config/editorial.md`, `scripts/run-digest.sh`,
the implementation in `ai_trend_bot/`, and user-supplied Telegram examples.
The owner supplied the representative robot image, now stored in
`docs/assets/ai-news-robot.png` for the introduction and README.
`docs/digest-preview.html` remains an independent earlier format prototype; the
introduction no longer links to it or offers format comparison.
There are no supplied subscriber counts, customer testimonials or live uptime
measurements. Do not fabricate these or claim zero missed articles.

## Product Principles

- Facts and meaningful changes take priority over volume.
- Preserve source attribution and distinguish facts from interpretation.
- Explain implemented behavior separately from proposed improvements.
- Keep the presentation understandable before introducing code details.

## Open Decisions

Public subscription scope remains undecided. Collection changes were approved on 2026-10-04.
