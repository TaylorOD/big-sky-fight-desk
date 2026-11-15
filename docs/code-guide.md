# Code guide

The public site and local studio share a visual style. Only the studio talks to the production backend.

| File | What it does |
| --- | --- |
| `desk/models.py` | Defines briefs, facts, scripts and review responses |
| `desk/provider.py` | Holds prompts and calls the OpenAI models |
| `desk/sources.py` | Reads bounded page excerpts from permitted domains |
| `desk/production.py` | Runs the steps, saves progress and invalidates stale media |
| `desk/storage.py` | Saves episode JSON and reserves usage in SQLite |
| `desk/server.py` | Serves the local studio and starts background work |
| `desk/publishing.py` | Exports approved episodes and builds the site and feed |
| `desk/__main__.py` | Provides the command line entry points |
| `web/studio.html` | Local studio layout |
| `web/studio/studio.js` | Editor, production buttons and status updates |
| `web/shared/` | Shared styles, icon and public player code |
| `public/` | Approved files that can be published |

## State and recovery

Each step saves its result before the next one starts. Research and evidence are reused if a later step fails. Audio and cover files are written to working files, checked, then renamed. A hash ties the review, approval and media to the exact script.

Saving a script edit clears review and media validity. Old files may remain in the private folder, but the studio will not serve or export them as the new version. Export checks the current review, approval hash and both media hashes.

The model review is an advisory quality check, not a proof of accuracy. Publication still needs a person to inspect the sources and output. The check uses only the sources cited by the proposed script, with explicit fact IDs, so unrelated search results do not create false failures.

## Local access

The server binds to `127.0.0.1`. It checks the Host header, requires a random per process token for changes and rejects foreign origins. It does not enable CORS. Browser output escapes text from prompts and model responses.

Source retrieval accepts only selected HTTPS domains and checks each redirect. Reads have time and size limits. Failed source reads remain visible and cannot support a fact. The source text is treated as untrusted evidence in every model prompt.

Only one background operation can be scheduled at once. SQLite transactions prevent concurrent allowance reservations from going over the configured app allowance. Failed calls remain counted. There are no automatic retries or hidden publish operations.

## Command line

```sh
python -m desk new "Preview a confirmed Montana Fusion card" --as-of 2026-11-14 --minutes 4
python -m desk draft EPISODE_ID
python -m desk revise EPISODE_ID
python -m desk review EPISODE_ID
python -m desk media EPISODE_ID
# Read the sources and inspect the output before approving.
python -m desk approve EPISODE_ID
python -m desk export EPISODE_ID
python -m desk build
```

The date above is an example. Use the actual date for a new dispatch. The CLI prints an episode ID when an action finishes.
