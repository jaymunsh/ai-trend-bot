#!/usr/bin/env bash
# miniPC cron에서 하루 세 번 호출한다. 설치 위치는 ~/bin/run-digest.sh 다.
set -euo pipefail

# 기존 운영 환경의 별도 오류 알림을 유지한다. 알림 실패는 원래 종료 코드를 바꾸지 않는다.
STAGE="초기화"
alert_on_error() {
  local code=$? cmd=$BASH_COMMAND stage=$STAGE
  if [[ -n "${TELEGRAM_ALERT_CHAT_ID:-}" && -n "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    local err_line esc_err esc_cmd
    err_line=$(tail -n 5 "$HOME/logs/ai-trend-bot.log" 2>/dev/null | sed '/^[[:space:]]*$/d' | tail -n 1 | cut -c1-400 || true)
    esc_err=$(printf '%s' "$err_line" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')
    esc_cmd=$(printf '%s' "${cmd/#$HOME/\~}" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')
    curl -fsS -m 10 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TELEGRAM_ALERT_CHAT_ID}" \
      --data-urlencode "parse_mode=HTML" \
      --data-urlencode "text=<b>[ai-trend-bot] 회차 실패</b>
시각: $(date '+%F %T %Z') · $(hostname)
단계: ${stage}
원인: <code>${esc_err}</code>
명령: <code>${esc_cmd}</code>" >/dev/null 2>&1 || true
  fi
  exit "$code"
}
trap alert_on_error ERR

REPO="$HOME/apps/ai-trend-bot"
UV="$HOME/.local/bin/uv"
RUN_MODE="${1:---scheduled}"
export AI_TREND_BOT_SENT_LOG="$HOME/.local/state/ai-trend-bot/sent.jsonl"

# 준비부터 발송까지 동일 프로세스를 유지한다. 수동/중복 cron 실행은 겹치지 않게 한다.
mkdir -p "$(dirname "$AI_TREND_BOT_SENT_LOG")"
exec 9>"$(dirname "$AI_TREND_BOT_SENT_LOG")/run.lock"
flock -n 9 || exit 0

# 시크릿은 저장소 밖에 둔다. set -a 로 읽는 값 전부를 자식 프로세스에 넘긴다.
STAGE="환경 변수 로드"
set -a
# shellcheck source=/dev/null
source "$HOME/.config/ai-trend-bot.env"
set +a

# config/sources.toml 과 config/editorial.md 를 CWD 상대 경로로 연다. cd 없이는 못 찾는다.
STAGE="저장소 이동"
cd "$REPO"

# 코드를 못 당겨도 기존 코드로 보내는 편이 낫다.
git pull --ff-only --quiet || echo "$(date -Is) git pull 실패, 기존 코드로 진행"

STAGE="의존성 동기화 (uv sync)"
"$UV" sync --frozen --quiet
STAGE="수집·요약·발송 (ai-trend-bot run)"
"$UV" run ai-trend-bot run --send "$RUN_MODE" --limit 30 --min-gap-hours 3
echo "$(date -Is) done"
