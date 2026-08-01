# AI Trend Bot

RSS와 Threads에서 AI 관련 정보를 모아 한국어로 요약하고 텔레그램으로 보내는 개인용 봇입니다.

## 확정된 운영 기준

- 발송: 매일 08:17, 14:17, 20:17 (Asia/Seoul)
- 회차별 최대: 8개, 6개, 6개
- 하루 최대: 20개
- 우선순위: 지정 Threads 계정 → 공식 발표 → 키워드 Threads → 연구·커뮤니티
- 중복 게시물은 다시 보내지 않음
- 현재 운영 모드: RSS 뉴스 중심, Threads는 권한 검수 전까지 비활성화

## 사용자가 마무리할 것

1. 자동 실행 전에 비공개 GitHub 저장소를 준비합니다.
2. `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`를 GitHub Actions Secrets에 등록합니다.
3. Threads를 다시 켤 때 장기 토큰과 `threads_profile_discovery` 권한을 준비합니다.

발급받은 키를 채팅이나 저장소에 직접 올리지 마세요. 로컬에서는 `.env.example`을 `.env`로 복사한 뒤 값을 입력합니다.

## 초기 설정 확인

```bash
uv sync
uv run ai-trend-bot check-config
uv run ai-trend-bot run --dry-run --limit 3
```

관심 계정과 키워드는 `config/sources.toml`에서 관리합니다.

실제 텔레그램 발송은 다음 명령으로 확인합니다.

```bash
uv run ai-trend-bot run --send --limit 3
```

## 현재 구현 상태

- [x] 프로젝트 및 엄격한 Python 검사 환경
- [x] 출처·관심 계정·발송량 설정 모델
- [x] 설정 검증 명령
- [x] RSS 수집
- [x] Threads 관심 계정·자기 답글·키워드 수집
- [x] Gemini 한국어 번역·요약
- [x] Gemini 관련도 판정 및 저품질 소식 제외
- [x] 텔레그램 회차별 묶음 발송
- [x] SQLite 중복 기록
- [x] GitHub Actions 3회 예약 실행
