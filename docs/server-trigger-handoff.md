# 서버 인수인계 — AI 트렌드 봇 트리거

이 문서는 **다른 서버 프로젝트에서 작업하는 사람/에이전트**를 위한 것입니다.
해야 할 일은 crontab에 줄 세 개를 추가하는 것뿐입니다. 이 저장소의 코드를 서버에
배포하거나, 컨테이너를 만들거나, DB를 붙일 일은 없습니다.

## 1. 무엇을 해결하려는가

AI 트렌드 봇은 GitHub Actions에서 하루 세 번 실행되어 텔레그램으로 브리핑을 보냅니다.
실행 자체는 정상입니다. **문제는 GitHub의 예약(`schedule`)이 실행을 통째로 버린다는
것입니다.**

`schedule`은 보장이 아니라 best-effort 큐입니다. 부하가 높으면 지연되고, 지연이 다음
슬롯까지 밀리면 실행하지 않고 폐기합니다. 무료 티어 + 비공개 저장소는 우선순위가 낮습니다.

관측된 사례:

| 예정 (UTC) | 결과 |
| --- | --- |
| 2026-08-03 22:30 | +63분 지연 |
| 2026-08-04 04:30 | **폐기** |
| 2026-08-04 12:20 | +119분 지연 |
| 2026-08-05 04:23 | **폐기** |

낮 회차(04:xx UTC)는 이틀 연속 폐기됐습니다.

**`workflow_dispatch`는 이 큐를 타지 않습니다.** 수동 실행은 항상 즉시 돌았습니다.
그래서 서버가 정시에 `workflow_dispatch`를 호출해 주면 이 문제가 사라집니다.

## 2. 하지 말아야 할 것

작업 범위를 좁게 유지해 주세요. 아래는 **전부 불필요**합니다.

- **봇 코드를 서버에 배포하지 마세요.** 실행은 계속 GitHub Actions에서 합니다.
- **Docker / Kubernetes 불필요.** 상시 실행되는 프로세스가 없습니다. 서버에 올라가는
  것은 crontab 항목뿐이라 격리할 대상이 없습니다.
- **DB 불필요.** 이 프로젝트에는 데이터베이스가 없습니다. 상태는 저장소 안의 텍스트
  파일(`data/sent.jsonl`) 하나이고, GitHub Actions가 매 실행 후 커밋합니다.
- **웹 프레임워크(FastAPI 등) 불필요.** 호출할 엔드포인트가 필요 없습니다.
- **배치 프레임워크(Spring Batch 등) 불필요.** 재시작·청크·스텝 관리가 필요한 작업이
  아닙니다. 2분 만에 끝나는 CLI 한 번 호출입니다.

## 3. 해야 할 일

### 3.1 PAT 발급

GitHub에서 Personal Access Token을 발급합니다.

- 저장소: `jaymunsh/ai-trend-bot` (**비공개**)
- 필요한 권한: classic PAT이면 `repo` 스코프. fine-grained PAT이면 해당 저장소에 대해
  **Actions: Read and write**
- 만료일을 설정했다면 갱신 일정을 남겨두세요. 만료되면 조용히 실패합니다.

토큰은 crontab에 직접 쓰지 말고 파일로 분리해 권한을 좁히세요.

```bash
install -m 600 /dev/null ~/.config/ai-trend-bot.env
echo 'GH_PAT=ghp_xxxxxxxxxxxx' > ~/.config/ai-trend-bot.env
```

### 3.2 트리거 스크립트

```bash
install -m 755 /dev/null ~/bin/trigger-ai-trend-bot.sh
cat > ~/bin/trigger-ai-trend-bot.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
source ~/.config/ai-trend-bot.env
curl -sS -X POST \
  -H "Authorization: Bearer ${GH_PAT}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  --fail-with-body \
  https://api.github.com/repos/jaymunsh/ai-trend-bot/actions/workflows/digest.yml/dispatches \
  -d '{"ref":"main"}'
SH
```

성공 시 HTTP 204와 빈 본문을 반환합니다. 출력이 없는 것이 정상입니다.

### 3.3 crontab 등록

**먼저 서버 타임존을 확인하세요.** `timedatectl` 또는 `date`로 봅니다.

발송 목표 시각은 **Asia/Seoul 기준 07:23 / 13:23 / 19:23**입니다.
GitHub 예약보다 3분 앞선 07:20 / 13:20 / 19:20에 호출해 서버가 항상 먼저 이기게 합니다.

```bash
# 서버가 KST인 경우
20 7,13,19 * * * ~/bin/trigger-ai-trend-bot.sh >> ~/logs/ai-trend-bot.log 2>&1

# 서버가 UTC인 경우 (KST = UTC+9)
20 22,4,10 * * * ~/bin/trigger-ai-trend-bot.sh >> ~/logs/ai-trend-bot.log 2>&1
```

systemd timer를 쓰는 환경이라면 `OnCalendar=*-*-* 07,13,19:20:00 Asia/Seoul`로 잡아도
됩니다. 둘 중 그 서버의 기존 관례를 따르세요.

### 3.4 기존 GitHub 예약은 그대로 둡니다

저장소의 cron은 지우지 마세요. **서버가 죽었을 때의 백업으로 남깁니다.**

중복 걱정은 없습니다. 워크플로가 `--min-gap-hours 3`으로 실행되어, **최근 3시간 안에
발송한 기록이 있으면 수집조차 하지 않고 종료합니다.** 서버가 07:20에 트리거해 발송이
끝나면, 뒤늦게 도착하는 GitHub 예약분은 자동으로 건너뜁니다. 트리거가 겹쳐도
안전합니다.

## 4. 검증

```bash
# 1. 수동 실행
~/bin/trigger-ai-trend-bot.sh; echo "exit=$?"

# 2. 실행이 걸렸는지 확인 (gh CLI가 있는 경우)
gh run list --repo jaymunsh/ai-trend-bot --workflow digest.yml -L 3
```

- 텔레그램에 브리핑이 도착하면 성공입니다. 실행에 2~3분 걸립니다.
- 방금 발송한 직후 다시 트리거하면 **"최근 3시간 안에 발송한 기록이 있어
  건너뜁니다"** 가 로그에 남고 아무것도 오지 않습니다. 이것도 정상 동작입니다.

## 5. 실패했을 때

| 증상 | 원인 |
| --- | --- |
| HTTP 401 | PAT가 잘못됐거나 만료 |
| HTTP 403 | PAT 스코프 부족. `repo` 또는 Actions write 필요 |
| HTTP 404 | 저장소명·워크플로 파일명 오타. 비공개 저장소인데 PAT에 접근 권한이 없어도 404가 납니다 |
| 204인데 아무 일 없음 | `ref`가 잘못된 브랜치. 기본 브랜치는 `main` |
| 실행은 됐는데 텔레그램 조용함 | 정상일 수 있습니다. 편집 기준을 통과한 항목이 0건이면 보내지 않습니다. Actions 로그에 "기준을 통과한 항목이 없습니다"가 남습니다 |

크론이 도는데 로그가 비어 있으면 cron 환경의 `PATH`를 의심하세요. `curl` 절대 경로
(`/usr/bin/curl`)를 쓰면 대부분 해결됩니다.

## 6. 참고

- 저장소: `https://github.com/jaymunsh/ai-trend-bot` (비공개)
- 워크플로: `.github/workflows/digest.yml`
- 프로젝트 개요: 같은 저장소의 `README.md`
- 예약 실행이 왜 신뢰할 수 없는지에 대한 상세: `docs/superpowers/specs/2026-08-03-digest-quality-overhaul-design.md` 18장
