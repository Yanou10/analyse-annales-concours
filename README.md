# exam-corpus-pipeline

Maps a corpus of past exam papers onto an official syllabus and outputs a revision priority ranking based on measured topic frequency.

Instead of guessing what to revise, you get an ordering built from what the examiners actually asked, over every paper in the corpus.

## What it does

The pipeline runs in five stages. Each stage writes its output to object storage, so any stage can be re-run on its own without redoing the ones before it.

| Stage | Input | Output |
|---|---|---|
| 0 — Reference | Official syllabus (`.md`) | Reference of **182 typed concepts**, with a rule registry (severity levels), typed cross-references, and a check of the corpus against the reference |
| 1 — Extraction | Raw exam papers (`.md`) | **338 exercises, 2,199 questions** — segmented by heading, deduplicated by content hash |
| 3 — Labelling | Questions + reference | Each question tagged with the concepts it tests, under a frozen and verified prompt protocol, run through the Anthropic Batch API |
| 4 — Measurement | Labels | Frequency breakdowns and a standalone HTML dashboard |
| 5 — Storage | Results | PostgreSQL import via the HTTP service |

## Why the labels can be trusted

An LLM labelling 2,199 questions will be confidently wrong somewhere. Three things guard against that:

- **Frozen prompt protocol.** The labelling prompt is versioned and fixed, so two runs are comparable and a change in output means a change in input, not in wording.
- **Scored against a verified sample.** Labels are checked against answers verified by hand, and the score is reported rather than assumed.
- **Batch API.** Grouping requests roughly halved the cost and the wall-clock time, which is what made a verification pass affordable in the first place.

## Architecture

```
MinIO  ──(s3:ObjectCreated)──►  n8n  ──HTTP──►  FastAPI service
  ▲                                                   │
  │                                          /build /extract
  └──────────── results, dashboards ◄──────  /label /measure /import
                                                      │
                                                      ▼
                                                 PostgreSQL
```

Dropping a syllabus or a paper into MinIO triggers the whole chain. The FastAPI service runs the long stages as background tasks with progress tracking, so an HTTP call returns immediately and the caller polls for state.

## Stack

Python · FastAPI · PostgreSQL · MinIO · n8n · Docker · Caddy (HTTPS) · Anthropic Batch API · pytest

## Running it

```bash
cp .env.example .env        # ANTHROPIC_API_KEY, MinIO and Postgres credentials
docker compose up -d        # five services behind HTTPS
```

Import the two workflows in `n8n/` and point them at the service.

Each stage is also runnable on its own from the CLI, which is how you re-label a corpus after editing the reference without re-extracting anything.

## Tests

```bash
pytest                      # 121 tests
```

The suite covers segmentation, deduplication, the rule registry, and the measurement stage. No network calls: labelling is exercised against recorded fixtures.

## Reliability notes

- Long jobs resume after an interruption instead of restarting from zero.
- Stage outputs are content-addressed, so re-running a stage on unchanged input is a no-op.
- Errors surface in the job state rather than being swallowed.

## Licence

MIT
