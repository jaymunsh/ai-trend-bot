# AI Trend Bot

AI 관련 소식을 모아 한국어로 요약하고 텔레그램으로 보내는 개인용 봇입니다.

설계 배경과 결정 근거는
[`docs/superpowers/specs/2026-08-03-digest-quality-overhaul-design.md`](docs/superpowers/specs/2026-08-03-digest-quality-overhaul-design.md)에 있습니다.

## 운영 기준

- 발송: 매일 07:30, 13:30, 19:30 (Asia/Seoul)
- 중복 게시물은 다시 보내지 않음
- 현재 운영 모드: RSS 뉴스 중심
- 발송 개수는 **가변**입니다. 편집 기준을 통과한 것만 보내며, 통과분이 없으면 보내지 않습니다.
  `--limit`(기본 30, 최대 40)은 목표치가 아니라 폭주 방지선입니다.

GitHub Actions의 예약 실행은 부하에 따라 5~15분 지연되는 것이 정상입니다.

## 데이터 저장

발송한 항목은 **`data/sent.jsonl`에 한 줄씩 기록하고 저장소에 커밋합니다.**
매 실행 후 Actions가 자동으로 커밋·푸시하므로 이 파일은 절대 수동으로 편집하지 마세요.

```jsonc
{"key": "<URL의 sha256>", "title": "...", "url": "...", "source": "...", "sent_at": "..."}
```

- `key`가 재발송 차단의 기준입니다. 파일이 사라지면 **이미 보낸 항목이 전부 재발송됩니다.**
- 기록은 텔레그램 메시지 하나가 실제로 전달된 뒤에만 남습니다. 여러 메시지로 쪼개져 나가다
  중간에 실패해도, 이미 도착한 것은 다시 오지 않습니다.
- 이전에는 SQLite 파일을 GitHub Actions 캐시에 두었으나, 캐시는 7일 미사용·용량 초과로
  evict되며 그때마다 대량 재발송이 발생합니다. 그래서 git으로 옮겼습니다.
- 용량은 연 2MB 수준입니다. 커지면 오래된 줄부터 잘라내면 됩니다.

탈락 항목과 그 사유는 저장소에 커밋하지 않습니다. 드라이런에서 터미널로 확인하세요
(`--show-dropped`, 기본 켜짐).

## 설정

수집처는 `config/sources.toml`에서 관리합니다.

```bash
uv sync
uv run ai-trend-bot check-config
uv run ai-trend-bot run --dry-run --limit 30   # 발송 없이 결과만 확인
uv run ai-trend-bot run --send --limit 30      # 실제 발송
```

`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`를 GitHub Actions Secrets에
등록해야 자동 실행이 동작합니다. 로컬에서는 `.env.example`을 `.env`로 복사해 값을 넣습니다.
**발급받은 키를 채팅이나 저장소에 직접 올리지 마세요.**

Actions가 `data/sent.jsonl`을 푸시해야 하므로 워크플로에 `contents: write` 권한이 필요합니다.

## 파이프라인

```
① 수집  collect   27개 소스 → 후보 300건 안팎         feeds.py
② 선별  triage    1차 배치 심사 → 2차 전역 재심사     triage.py, gemini.triage()
③ 심화  enrich    통과분만 원문 본문 fetch            enrich.py
④ 전달  deliver   렌더링 → 텔레그램 → 기록 커밋       telegram.py, store.py
```

**②가 핵심입니다.** 항목마다 종류를 매기고(`모델·제품 출시`, `연구 결과`, `정책·산업·자금`,
`도구·오픈소스`, `튜토리얼·사용법`, `홍보·사례소개`, `기타`) 뒤 세 종류는 코드에서 강제로
버립니다. 0~100 점수에 임계값을 걸지 않는 이유는, 모델의 절대 점수가 좁은 구간에 몰려서
어디를 자르든 자의적이 되기 때문입니다. 순위도 절대 평가가 아니라 후보끼리 비교해 매깁니다.

**③이 요약 품질을 좌우합니다.** 예전에는 RSS의 두세 문장짜리 티저를 요약해서 "요약본의
요약"이 나왔습니다. 이제 통과한 소수만 원문 본문을 받아옵니다. 추출에 실패하면 티저로
폴백하므로 그 항목만 얕아지고 발송은 정상 진행됩니다.

**②는 두 번 돌립니다.** 무료 티어 Gemini는 후보 300건대를 한 요청으로 받으면 503을
반환합니다. 그래서 1차는 100건씩 배치로 심사합니다. 다만 배치만 나누면 같은 사건을
다룬 두 매체가 서로 다른 배치에 떨어져 둘 다 살아남습니다. 그래서 1차 생존자
수십 건을 다시 한 번에 놓고 중복 병합과 순위를 다시 매깁니다.

실측 (2026-08-03 저녁): **후보 322건 → 발송 7건.** 1차 배치 심사만으로는 40건이
남았는데, 2차 전역 재심사에서 중복과 약체가 걸러져 7건이 됐습니다. 상한에 걸리지 않고
기준이 스스로 멈춘 결과입니다.

## 편집 기준 고치기

브리핑이 마음에 안 들면 **코드가 아니라 [`config/editorial.md`](config/editorial.md)를
고치세요.** 한국어 산문으로 쓰인 편집 방침이고, 그대로 선별 프롬프트에 들어갑니다.

```bash
# 고친 뒤 무엇이 왜 걸러졌는지 확인
uv run ai-trend-bot run --dry-run
```

기준이 느슨하다고 느끼면 "반드시 걸러낼 것"에 항목을 추가하고, 중요한 걸 놓치면
"반드시 통과시킬 것"에 추가합니다.

## 현재 구현 상태

- [x] 프로젝트 및 엄격한 Python 검사 환경 (ruff ALL, basedpyright all)
- [x] 출처·발송량 설정 모델과 검증 명령
- [x] RSS 수집
- [x] Gemini 한국어 번역·요약
- [x] 텔레그램 발송 (HTML, 회차별 헤더, 출처 하이퍼링크)
- [x] 발송 기록을 저장소에 커밋 (`data/sent.jsonl`)
- [x] GitHub Actions 3회 예약 실행
- [x] 선별 계층 (분류·사건 병합·후속 판정·순위)
- [x] 원문 본문 추출 후 심층 요약
- [x] 수집처 27개 (벤더 공식·테크 미디어·큐레이터·HN·Hugging Face·arXiv·국내·Threads)

## Threads 지원 상태

`@choi.openai` 같은 **타인 계정은 공식 Threads API로 수집할 수 없습니다.**
`threads_profile_discovery` 권한이 필요한데, Standard Access로는 `@meta`, `@threads`,
`@instagram`, `@facebook` 네 개만 조회되고, 그 외에는 Meta 앱 심사(2~4주, 실제 서비스의
사용자 플로우 스크린캐스트 제출)를 통과해야 합니다. 개인용 봇은 제출할 사용자 플로우가
없어 사실상 불가능합니다.

따라서 **RSSHub `/threads/:user` 라우트를 경유**해 RSS로 받습니다 (현재
`rsshub.rssforever.com`). 토큰도 60일 갱신도 심사도 필요 없는 대신, 공용 인스턴스라
자주 타임아웃됩니다. 실패해도 그날 해당 소스만 빠지고 브리핑은 정상 발송됩니다.
안정성이 필요하면 RSSHub를 직접 띄우세요.

`ai_trend_bot/threads.py`는 본인 계정 조회(`threads_basic`만으로 동작)를 위해 남겨두었으나
현재 파이프라인에서는 호출하지 않습니다.

## 프로젝트 한눈에 보기

구현 구조와 수집처는 [`docs/how-it-works.html`](docs/how-it-works.html)에 한국어 다이어그램
문서로 정리되어 있습니다. (개편 반영 전 내용이라 일부 낡았습니다.)
