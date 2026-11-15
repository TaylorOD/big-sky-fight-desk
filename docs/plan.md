# Big Sky Fight Desk

A short podcast about real Montana MMA. One host, plain language and sources you can check.

## What we are shipping

1. A local studio that researches a topic and makes a script.
2. A source list and a second model pass that checks each script against the research.
3. An MP3 with a disclosed AI voice and an original PNG cover.
4. A public listening page with episodes, transcripts, sources and an RSS feed.
5. A real first episode, automated tests, browser checks and setup instructions.

## Coverage

Fusion Fight League is the starting point. KillEagle Promotions, Mountain Force and other promoters belong here when there is a confirmed Montana event. FightForce and ICF can appear in historical coverage. An old listing does not prove a promotion is active now.

Keep MMA, boxing, kickboxing and bare knuckle clearly labeled. Cover Montana fighters elsewhere only when the Montana connection is sourced. Do not invent results, records, quotes or upcoming bouts. Do not describe fight action without footage or reporting that supports it.

## Episode flow

Research comes first, then a draft, then a separate evidence check. The studio saves each step and can resume after a failure. Media comes after a passing check. A person reviews the script and sources before approving an export. Export creates public files locally. A separate GitHub PR publishes them.

The workflow is bounded in code. Research uses a web search tool. Drafting and review use structured responses. Speech and image generation are tools called only at the right stage. No model gets shell access, arbitrary file paths or publishing credentials.

## Cost and privacy

The studio binds to this computer only. The public website has no generation endpoint and no API key. Calls reserve a fixed allowance before starting, with daily and monthly limits stored in SQLite. Failed calls retain their reservations because a provider may have processed them. These allowances limit app activity but are not a guarantee of the provider invoice.

## Completion checks

1. Fresh research includes real source URLs and a checked date.
2. The first script is reviewed against the linked pages.
3. The first MP3 decodes and plays in a browser.
4. The cover is opened and inspected.
5. Tests cover limits, source validation, edit invalidation, exports and local access.
6. Desktop and narrow browser views are inspected and screenshots are included in the PR.
7. The PR is merged and the public episode is checked after deployment.

## Later

Multiple hosts, automatic schedules and podcast directory submissions are outside this first release. No automatic posting to course channels or social accounts.
