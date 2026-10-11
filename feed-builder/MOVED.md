# Where this runs

This folder is the HomeCircle meeting feed builder. It was moved here on 12 Oct 2026
from the private Origin draft repo (luke-endrody/tmp-bbbf1840f3866e8f), where
GitHub Actions never ran, so the feed had been frozen since 6 Oct 2026.

- Workflow: `.github/workflows/daily-feed.yml` at the repo root (daily 16:00 UTC = 02:00 Brisbane, plus manual "Run workflow").
- Output: pushed to the `gh-pages` branch, served at
  - `https://lendrody28-spec.github.io/homecircle/feed/au/index.json` (+ state files, same paths and schema as before)
  - `https://lendrody28-spec.github.io/homecircle/feed/feed-items.json` (approved curated cards)
  - `https://lendrody28-spec.github.io/homecircle/feed/status/au/coverage.json` and `changes-latest.json` (run report)
- Previous snapshot: each run rebuilds `dist/au/meetings.json` from the published files (`python -m homecircle_feed seed`), so `dist/` is not committed.
- Safety guard: if a source returns fewer than 50% of its previous meeting count (and had at least 20 last time), its previous rows are kept and it is listed under `stale_sources` with status `kept_previous`. Tune per country with `"guard": {"min_keep_ratio": 0.5, "min_previous": 20}` in `sources/registry.json`.
