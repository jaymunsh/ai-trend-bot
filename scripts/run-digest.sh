#!/usr/bin/env bash
# miniPC cron에서 하루 세 번 호출한다. 설치 위치는 ~/bin/run-digest.sh 다.
set -euo pipefail

REPO="$HOME/apps/ai-trend-bot"
UV="$HOME/.local/bin/uv"
export AI_TREND_BOT_SENT_LOG="$HOME/.local/state/ai-trend-bot/sent.jsonl"

# 준비부터 발송까지 동일 프로세스를 유지한다. 수동/중복 cron 실행은 겹치지 않게 한다.
mkdir -p "$(dirname "$AI_TREND_BOT_SENT_LOG")"
exec 9>"$(dirname "$AI_TREND_BOT_SENT_LOG")/run.lock"
flock -n 9 || exit 0

# 시크릿은 저장소 밖에 둔다. set -a 로 읽는 값 전부를 자식 프로세스에 넘긴다.
set -a
# shellcheck source=/dev/null
source "$HOME/.config/ai-trend-bot.env"
set +a

# config/sources.toml 과 config/editorial.md 를 CWD 상대 경로로 연다. cd 없이는 못 찾는다.
cd "$REPO"

# 코드를 못 당겨도 기존 코드로 보내는 편이 낫다.
git pull --ff-only --quiet || echo "$(date -Is) git pull 실패, 기존 코드로 진행"

"$UV" sync --frozen --quiet
"$UV" run ai-trend-bot run --send --scheduled --limit 50 --min-gap-hours 3
echo "$(date -Is) done"
