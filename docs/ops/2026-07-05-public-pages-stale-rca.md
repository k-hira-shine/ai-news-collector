# 2026-07-05 public Pages stale RCA

## Summary

2026-07-05 JST, the news data and generated `docs/` files were current, but the user-facing URL `https://k-hira-shine.github.io/ai-news-collector/` still showed `2026-07-04 朝便`.

The mirror URL `https://k-hira-shine.github.io/ai-news-dashboard/` had already been updated to `2026-07-05 朝便`, which initially made the issue look like a browser cache problem. The actual issue was split-brain between the two public Pages URLs.

## Impact

- Stale URL: `https://k-hira-shine.github.io/ai-news-collector/`
- Stale key shown: `2026-07-04-morning`
- Current key expected: `2026-07-05-morning`
- News collection itself was not stopped.
- Email delivery was separately restored in `05e6281`.

## Root Cause

The collection workflows update `data/` and `docs/` from inside GitHub Actions via `.github/scripts/push_data.sh`.

Those commits are pushed by the workflow's `GITHUB_TOKEN`. GitHub Actions intentionally does not trigger most new workflow runs, nor Pages builds, from events caused by `GITHUB_TOKEN` pushes. Therefore:

1. `AI News Collector` generated and pushed fresh `docs/index.html`.
2. `Deploy Static Pages` was configured mainly as a `push` workflow on `docs/**`.
3. The automated `docs/**` push did not trigger that `push` workflow.
4. The repo Pages URL remained on the previous deployed artifact.
5. The separate `ai-news-dashboard` mirror was still updated by the SSH deploy step, so only one of the two public URLs was fresh.

Reference: GitHub documents that events caused by `GITHUB_TOKEN` do not create new workflow runs except for selected exceptions, and that commits pushed by Actions using `GITHUB_TOKEN` do not trigger a GitHub Pages build.

## Fix

Commit `c73c2d0` made `Deploy Static Pages` run after the data-producing workflows complete:

- `AI News Collector`
- `AI Money Cases Collector`
- `Buzz Ranking Collector`
- `Rebuild Reviews Page`

Follow-up hardening in this RCA session:

- The `workflow_run` trigger is restricted to `main`.
- The deploy job no longer requires the upstream workflow conclusion to be `success`.
  - Reason: `docs/` may already have been pushed even if a later mirror deploy or notification step fails.
  - Deploying the current `main/docs` artifact is harmless and keeps the repo Pages URL current.
- `daily_check.py` now checks public HTML freshness for both public URLs by comparing each page's `ai-news-latest-key` against the newest `data/analysis/*.json` key.

## Verification

After redeploy, direct HTML and browser checks for `https://k-hira-shine.github.io/ai-news-collector/` showed:

- `latest_key=2026-07-05-morning`
- `Last updated: 2026-07-05 01:19 JST`
- latest diagram button: `2026-07-05 朝便`
- first archive item: `2026-07-05 朝便`
- active tab: `07-05 朝便 最新`

## Regression Guard

Daily ops check now fails if either public URL is stale or unreachable:

- `collector`: `https://k-hira-shine.github.io/ai-news-collector/`
- `dashboard`: `https://k-hira-shine.github.io/ai-news-dashboard/`

The regression test `PublicPagesTests.test_stale_collector_page_fails` reproduces the exact failure mode: collector stale while dashboard is current.
