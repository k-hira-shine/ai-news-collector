# 2026-07-05 single public URL decision

## Decision

Use one canonical public URL:

https://k-hira-shine.github.io/ai-news-collector/

The old mirror URL remains only as a backward-compatible redirect:

https://k-hira-shine.github.io/ai-news-dashboard/

## Why

`ai-news-dashboard` was a separate static mirror repository. Collection workflows force-pushed the generated `docs/` directory there using `PAGES_DEPLOY_KEY`.

That created two independently deployed public surfaces:

- `ai-news-collector`: the source repository's Pages site
- `ai-news-dashboard`: a generated static mirror

This split caused the 2026-07-05 incident where one URL was current and the other was stale. A mirror only helps when it is the sole public surface. Once the source repo Pages site was restored with `Deploy Static Pages`, keeping both copies increased operational risk without adding user value.

## Changes

- Removed SSH mirror deploy steps from:
  - `.github/workflows/collect.yml`
  - `.github/workflows/money-collect.yml`
- Updated news email links to the canonical `ai-news-collector` URL.
- Reduced `daily_check.py` freshness monitoring to the canonical URL.
- Converted `k-hira-shine/ai-news-dashboard` into a redirect-only repository.

## Rule

Do not reintroduce generated dashboard deployment to `ai-news-dashboard`.

If a backup publication target is needed later, make it an explicit failover with a separate health model, not a silent second copy.
