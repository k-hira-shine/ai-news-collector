#!/bin/bash
# GitHub Actions ワークフロートリガースクリプト
# gh CLI不要 / PATはGitリモートURLから自動取得
# 使い方:
#   ./run_workflow.sh collect      → collect.yml (full)
#   ./run_workflow.sh collect analyze-only
#   ALLOW_LEGACY_COSTS=true ./run_workflow.sh money        → money-collect.yml (legacy/manual)
#   ALLOW_LEGACY_COSTS=true ./run_workflow.sh buzz         → buzz-collect.yml (legacy/manual)

set -euo pipefail

REPO="k-hira-shine/ai-news-collector"
WORKFLOW="${1:-}"
MODE="${2:-full}"

case "$WORKFLOW" in
  collect)
    YML="collect.yml"
    PAYLOAD="{\"ref\":\"main\",\"inputs\":{\"mode\":\"${MODE}\"}}"
    ;;
  money)
    if [ "${ALLOW_LEGACY_COSTS:-}" != "true" ]; then
      echo "❌ money はLegacy課金workflowのため既定では起動しません"
      echo "   明示的に実行する場合だけ: ALLOW_LEGACY_COSTS=true $0 money ${MODE}"
      exit 1
    fi
    YML="money-collect.yml"
    PAYLOAD="{\"ref\":\"main\",\"inputs\":{\"mode\":\"${MODE}\",\"allow_costs\":\"true\"}}"
    ;;
  buzz)
    if [ "${ALLOW_LEGACY_COSTS:-}" != "true" ]; then
      echo "❌ buzz はLegacy課金workflowのため既定では起動しません"
      echo "   明示的に実行する場合だけ: ALLOW_LEGACY_COSTS=true $0 buzz ${MODE}"
      exit 1
    fi
    YML="buzz-collect.yml"
    PAYLOAD="{\"ref\":\"main\",\"inputs\":{\"profile\":\"${MODE}\",\"allow_costs\":\"true\"}}"
    ;;
  *)
    echo "使い方: $0 [collect|money|buzz] [mode]"
    echo "  collect → collect.yml"
    echo "  money   → money-collect.yml (legacy/manual; ALLOW_LEGACY_COSTS=true が必要)"
    echo "  buzz    → buzz-collect.yml (legacy/manual; ALLOW_LEGACY_COSTS=true が必要)"
    exit 1
    ;;
esac

echo "🚀 トリガー: $YML (mode=$MODE)"

# GitリモートURLからPATを自動取得 (https://user:PAT@github.com/... 形式)
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
PAT=$(echo "$REMOTE_URL" | sed -n 's|https://[^:]*:\([^@]*\)@.*|\1|p')
if [ -z "$PAT" ]; then
  echo "❌ PATをGitリモートURLから取得できませんでした"
  echo "   git remote set-url origin https://USERNAME:PAT@github.com/REPO.git"
  exit 1
fi

HTTP_STATUS=$(curl -s -o /tmp/gh_trigger_resp.txt -w "%{http_code}" \
  -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $PAT" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/${REPO}/actions/workflows/${YML}/dispatches" \
  -d "$PAYLOAD")

if [ "$HTTP_STATUS" = "204" ]; then
  JST_NOW=$(TZ=Asia/Tokyo date '+%Y-%m-%d %H:%M JST')
  echo "✅ 起動成功 ($JST_NOW)"
  echo "   確認: https://github.com/${REPO}/actions"
else
  echo "❌ 失敗 (HTTP $HTTP_STATUS)"
  cat /tmp/gh_trigger_resp.txt
  exit 1
fi
