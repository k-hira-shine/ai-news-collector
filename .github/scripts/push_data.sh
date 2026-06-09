#!/usr/bin/env bash
# main への push（競合時は merge。data/logs/*.jsonl は行をマージ）
set -euo pipefail

COMMIT_MSG="${1:?commit message required}"
shift
ADD_PATHS=("$@")

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"

abort_in_progress_git() {
  git rebase --abort 2>/dev/null || true
  git merge --abort 2>/dev/null || true
}

commit_if_needed() {
  git add "${ADD_PATHS[@]}"
  if ! git diff --staged --quiet; then
    git commit -m "$COMMIT_MSG"
  fi
}

refresh_cost_tracking() {
  local path
  for path in "${ADD_PATHS[@]}"; do
    if [[ "$path" == "data/" || "$path" == "data/logs/" || "$path" == "data/cost_tracking.json" ]]; then
      python3 check_cost.py --record --quiet
      git add data/cost_tracking.json
      return
    fi
  done
}

fix_jsonl_conflicts() {
  local f
  for f in data/logs/*.jsonl; do
    [[ -f "$f" ]] || continue
    grep -q '^<<<<<<< ' "$f" || continue
    python3 - "$f" <<'PY'
import sys
path = sys.argv[1]
seen: set[str] = set()
out: list[str] = []
for raw in open(path, encoding="utf-8"):
    line = raw.rstrip("\n")
    if line.startswith(("<<<<<<<", "=======", ">>>>>>>")):
        continue
    if line not in seen:
        seen.add(line)
        out.append(line)
with open(path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out) + ("\n" if out else ""))
PY
    git add "$f"
  done
}

fix_buzz_html() {
  [[ "${REBUILD_BUZZ:-}" == "true" ]] || return 0
  [[ -f docs/buzz.html ]] || return 0
  grep -q '^<<<<<<< ' docs/buzz.html || return 0
  if [[ -f data/buzz.json ]]; then
    python build_buzz.py
    git add docs/buzz.html
  else
    git checkout --theirs docs/buzz.html 2>/dev/null \
      || git checkout --ours docs/buzz.html 2>/dev/null || true
    git add docs/buzz.html
  fi
}

fix_run_status() {
  [[ -f docs/run_status.json ]] || return 0
  grep -q '^<<<<<<< ' docs/run_status.json || return 0
  python3 .github/scripts/merge_run_status.py docs/run_status.json
  git add docs/run_status.json data/logs/
}

resolve_merge_conflicts() {
  fix_jsonl_conflicts
  fix_buzz_html
  fix_run_status
  local f
  while IFS= read -r f; do
    [[ -n "$f" ]] || continue
    case "$f" in
      data/logs/*.jsonl) fix_jsonl_conflicts ;;
      docs/buzz.html) fix_buzz_html ;;
      docs/run_status.json) fix_run_status ;;
      *)
        git checkout --theirs "$f" 2>/dev/null \
          || git checkout --ours "$f" 2>/dev/null || true
        git add "$f" 2>/dev/null || true
        ;;
    esac
  done < <(git diff --name-only --diff-filter=U 2>/dev/null || true)
}

merge_origin_main() {
  local attempt="$1"
  abort_in_progress_git
  git fetch origin main
  if git merge origin/main -m "${COMMIT_MSG} (merge attempt ${attempt})"; then
    refresh_cost_tracking
    commit_if_needed
    return 0
  fi
  resolve_merge_conflicts
  refresh_cost_tracking
  if ! git diff --cached --quiet || ! git diff --quiet; then
    git commit -m "${COMMIT_MSG} (merge attempt ${attempt})"
  fi
}

commit_if_needed

for attempt in 1 2 3; do
  if git push origin HEAD:main; then
    echo "Push OK (attempt ${attempt})"
    exit 0
  fi
  echo "Push failed (attempt ${attempt}), merging origin/main..."
  merge_origin_main "$attempt"
  if [[ "${REBUILD_BUZZ:-}" == "true" ]] && [[ -f data/buzz.json ]]; then
    python build_buzz.py 2>/dev/null && git add docs/buzz.html || true
    commit_if_needed
  fi
  sleep "$((attempt * 3))"
done

echo "::error::Push failed after 3 attempts"
exit 1
