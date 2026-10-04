# Briefing Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 승인된 수집/요약/정시 발송과 삭제 없는 월별 발송 기록을 구현한다.
**Architecture:** 기존 Python 파이프라인을 확장한다. 단일 실행이 준비·대기를 담당하고 JSONL 활성파일/월별 아카이브를 읽는다.
**Tech Stack:** Python3.13, anyio/httpx2/Pydantic, pytest, static HTML/CSS/JS.
**Spec:** docs/superpowers/specs/2026-10-04-briefing-refresh-design.md

## Global Constraints
- 발송 07:30·13:30·19:30 KST; 준비15분 전; 상한50.
- 삭제 없음, 추가 서버/후보 저장 없음, 기존 Threads 실패 격리 유지.
- 기존 디자인과 사용자 이미지 변경 유지. 새 의존성 추가 없음.

## Review Focus
- UTC 월 경계와 한국 월 경계가 다른 기록의 분류.
- 아카이브 쓰기 후 활성파일 교체 실패 시 재실행의 무손실·멱등성.
- 신규 기사가 피드 상한 밖에 있거나 같은URL이 여러출처에서 나온 경우.
- 1차 병합, 새 사실이 있는 후속 보도, 최종 생존0건/상한 잘림.
- 준비 지연, 월말 정시 대기, 50건 요약/부분 전송 실패.

### Task1 월별 기록
Files: ai_trend_bot/store.py, tests/test_store.py, data/.
Interface: SentLog(path, *, now: datetime | None = None); 모든 읽기 API는 아카이브를 포함한다.
- [x] RED: 월별 이관·KST경계·이관실패후재실행·기존아카이브조회 테스트 실패 확인.
- [x] GREEN: 원자교체/중복제거 포함 월별 이관 구현; 테스트 통과.
- [x] 기존 data/sent.jsonl을 새 구현으로 분리하고 레코드 수·내용 동등성 확인.

### Task2 수집
Files: feeds.py, models.py, pipeline.py, config.py, sources.toml; tests/test_feeds.py, tests/test_pipeline.py.
Interface: FeedClient.fetch는 소스전체피드 반환; fetch(feed, *, now=None)는 HN만48h 검색. Pipeline _collect는 기간/미발송/URL중복/상한을 적용한다.
- [x] RED: 상한 전 미발송·48h·날짜불명·HN개별검색/중복 테스트 실패 확인.
- [x] GREEN: 수집 개선과 세 출처 추가. 기존 실패 격리/동일URL 우선출처 선택 확인.

### Task3 선별·짧은 요약·50건
Files: gemini.py, pipeline.py, telegram.py, cli.py, editorial.md; tests/test_pipeline.py, test_gemini.py, test_digest.py, test_cli.py.
Interface: 요약배치10, 병합출처보존, CLI limit 기본/최대50.
- [x] RED: 다중 배치 병합출처·입력순서/50건·빈최종후보·과대HTML 테스트 실패 확인.
- [x] GREEN: 새사실후속허용 프롬프트와 요약형식, 안전한분할 구현.

### Task4 정시 대기와 운영
Files: scheduling.py, pipeline.py, cli.py, scripts/run-digest.sh, .github/workflows/digest.yml; tests/test_schedule.py, test_pipeline.py, test_cli.py.
Interface: 선택옵션 --scheduled; 실행 시작시 목표슬롯 고정, 준비 후에만 anyio sleep, 실제발송 직전 중복가드 재확인.
- [x] RED: 15분전·지연·자정·드라이런 무대기·전송실패 기록 테스트 실패 확인.
- [x] GREEN: 동일프로세스대기 구현. cron예제 및 스크립트50건, Actions archive도커밋.

### Task5 문서·검증·리뷰
Files: README.md, PRODUCT.md, docs/how-it-works.html, docs/assets/overview.js, DESIGN.md, .impeccable/design.json.
- [x] 실제동작에맞춰소개·수집30출처/435상한/9매체·월별보관/짧은형식 갱신.
- [x] pytest, Ruff, basedpyright, shell syntax, config검증 및 문서링크/브라우저확인.
- [x] fresh-context whole-change review 후 중요한 지적 수정.
- [x] 코드/로컬검증과 실제운영반영 상태를 분리해 최종보고.
