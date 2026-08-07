# miniPC 실행 이관 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 브리핑 수집·요약·발송을 GitHub Actions에서 miniPC의 cron으로 옮겨, 도착 시각을 Asia/Seoul 07:30 / 13:30 / 19:30로 고정한다.

**Architecture:** miniPC가 저장소를 clone해 `uv run ai-trend-bot run --send`를 직접 돌린다. GitHub은 코드를 받아오는 창구로만 남고 발송 경로에서 빠진다. 중복 방지 상태 파일만 저장소 밖(`~/.local/state/`)으로 빼면 clone이 읽기 전용이 되어 토큰이 필요 없어진다.

**Tech Stack:** Python 3.13, uv, typer, pydantic-settings, cron(또는 systemd timer)

설계 근거: [`docs/superpowers/specs/2026-08-07-minipc-execution-design.md`](../specs/2026-08-07-minipc-execution-design.md)

## Global Constraints

- Python `>=3.13`. 새 런타임 의존성을 추가하지 않는다.
- ruff `select = ["ALL"]`, line-length 120. `pyproject.toml`의 ignore 목록 외에는 경고를 남기지 않는다.
- basedpyright `typeCheckingMode = "all"`.
- 테스트 기준선은 **22개 통과**다 (`uv run pytest -q`). 이 계획은 2개를 추가해 **24개**로 만든다.
- 테스트는 기존 관례를 따른다: `# Given` / `# When` / `# Then` 주석, 한국어 단언 문구.
- 문서는 한국어 평서체.
- 발송 목표 시각은 **Asia/Seoul 07:30 / 13:30 / 19:30**이다.
- `--min-gap-hours`는 **3**을 유지한다.
- 상태 파일 환경변수 이름은 **`AI_TREND_BOT_SENT_LOG`**로 고정한다.
- miniPC 경로 규약: clone `~/apps/ai-trend-bot`, 시크릿 `~/.config/ai-trend-bot.env`, 스크립트 `~/bin/run-digest.sh`, 상태 `~/.local/state/ai-trend-bot/sent.jsonl`, 로그 `~/logs/ai-trend-bot.log`.
- **시크릿 값(텔레그램 토큰, Gemini 키)을 대화·커밋·로그에 남기지 않는다.**

## 롤아웃 순서가 중요하다

Task 1~2를 먼저 push하고 miniPC를 세운 뒤, **마지막에** GitHub 예약을 지운다. 순서를 뒤집으면
miniPC가 준비되기 전에 브리핑이 끊긴다.

Task 4(첫 실제 발송)와 Task 5(예약 삭제) 사이에는 miniPC와 GitHub 예약이 둘 다 살아 있는 구간이
있다. 이 구간에서 브리핑이 두 번 올 수 있으므로 **두 Task를 한자리에서 연달아 수행한다.**

---

### Task 1: 상태 파일 경로를 환경변수로 재정의 가능하게

`SENT_LOG_PATH`가 `Path("data/sent.jsonl")`로 하드코딩되어 있다. miniPC가 clone을 읽기 전용으로
쓰려면 상태를 저장소 밖에 둬야 한다.

모듈 상수를 그대로 두고 값을 바꾸는 대신 함수로 감싼다. 상수는 import 시점에 한 번만 평가되므로
테스트가 `monkeypatch.setenv`로 검증할 수 없고, 한 테스트 세션 안에서 다른 테스트를 오염시킨다.

**Files:**
- Modify: `ai_trend_bot/cli.py:1-24` (import 추가, 함수 추가), `ai_trend_bot/cli.py:122`, `ai_trend_bot/cli.py:140`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: 없음 (첫 Task)
- Produces: `ai_trend_bot.cli._sent_log_path() -> pathlib.Path` — 환경변수 `AI_TREND_BOT_SENT_LOG`가
  비어 있지 않으면 그 경로를, 아니면 `Path("data/sent.jsonl")`를 반환한다. Task 2의 스크립트가
  이 환경변수를 export한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_cli.py` 끝에 붙인다. import 줄에 `_sent_log_path`를 추가해야 한다.

```python
def test_sent_log_path_when_env_is_unset(monkeypatch) -> None:
    # Given
    monkeypatch.delenv("AI_TREND_BOT_SENT_LOG", raising=False)

    # When
    path = _sent_log_path()

    # Then
    assert path == Path("data/sent.jsonl")


def test_sent_log_path_when_env_overrides_it(monkeypatch, tmp_path) -> None:
    # Given
    override = tmp_path / "state" / "sent.jsonl"
    monkeypatch.setenv("AI_TREND_BOT_SENT_LOG", str(override))

    # When
    path = _sent_log_path()

    # Then
    assert path == override
```

`tests/test_cli.py:5`의 import를 이렇게 바꾼다.

```python
from ai_trend_bot.cli import _sent_log_path, app
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL — `ImportError: cannot import name '_sent_log_path' from 'ai_trend_bot.cli'`

- [ ] **Step 3: 최소 구현**

`ai_trend_bot/cli.py` 맨 위 import 블록에 `os`를 추가한다. 표준 라이브러리이므로
`from dataclasses import dataclass` 위에 온다.

```python
import os
from dataclasses import dataclass
```

`ai_trend_bot/cli.py:23`의 `SENT_LOG_PATH` 선언은 기본값으로 그대로 두고, `EDITORIAL_PATH` 선언
아래에 함수를 추가한다.

```python
def _sent_log_path() -> Path:
    """Where the send log lives. Overridable so a read-only clone can keep state elsewhere."""
    override = os.environ.get("AI_TREND_BOT_SENT_LOG")
    return Path(override) if override else SENT_LOG_PATH
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `uv run pytest tests/test_cli.py -q`
Expected: PASS

- [ ] **Step 5: 호출부 두 곳을 바꾼다**

`ai_trend_bot/cli.py:122` (`_sent_within` 안):

```python
    last = SentLog(_sent_log_path()).last_sent_at()
```

`ai_trend_bot/cli.py:140` (`_execute` 안):

```python
        pipeline = BotPipeline(clients, SentLog(_sent_log_path()), EDITORIAL_PATH)
```

`SENT_LOG_PATH`를 직접 쓰는 곳이 더 없는지 확인한다.

Run: `grep -n "SENT_LOG_PATH" ai_trend_bot/cli.py`
Expected: 선언 1줄과 `_sent_log_path` 안의 1줄, 총 2줄만 나온다.

- [ ] **Step 6: 전체 검증**

```bash
uv run pytest -q
uv run ruff check .
uv run basedpyright
```

Expected: 24 passed (기존 22 + 신규 2), ruff 경고 없음, basedpyright 오류 없음.

- [ ] **Step 7: 커밋**

```bash
git add ai_trend_bot/cli.py tests/test_cli.py
git commit -m "Let the send log live outside the repository

A miniPC running the digest from a clone must not write into that clone,
or git pull stops working and pushing it back needs a token."
```

---

### Task 2: miniPC 실행 스크립트

**Files:**
- Create: `scripts/run-digest.sh`

**Interfaces:**
- Consumes: `AI_TREND_BOT_SENT_LOG` (Task 1)
- Produces: `~/bin/run-digest.sh`로 복사되어 crontab이 호출하는 실행 진입점. 표준출력에
  `<ISO8601> done` 한 줄을 남긴다.

- [ ] **Step 1: 스크립트를 만든다**

```bash
mkdir -p scripts
cat > scripts/run-digest.sh <<'SH'
#!/usr/bin/env bash
# miniPC cron에서 하루 세 번 호출한다. 설치 위치는 ~/bin/run-digest.sh 다.
set -euo pipefail

REPO="$HOME/apps/ai-trend-bot"
UV="$HOME/.local/bin/uv"
export AI_TREND_BOT_SENT_LOG="$HOME/.local/state/ai-trend-bot/sent.jsonl"

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
"$UV" run ai-trend-bot run --send --limit 30 --min-gap-hours 3
echo "$(date -Is) done"
SH
chmod +x scripts/run-digest.sh
```

- [ ] **Step 2: 문법을 검사한다**

`shellcheck`는 이 환경에 없다. bash 내장 문법 검사로 대체한다.

Run: `bash -n scripts/run-digest.sh && echo "문법 정상"`
Expected: `문법 정상`

- [ ] **Step 3: 실행 권한을 확인한다**

Run: `test -x scripts/run-digest.sh && echo "실행 가능"`
Expected: `실행 가능`

- [ ] **Step 4: 커밋**

```bash
git add scripts/run-digest.sh
git commit -m "Add the miniPC run script

cd into the clone first: sources.toml and editorial.md open on relative
paths, and cron starts in the home directory."
```

- [ ] **Step 5: push**

miniPC가 clone할 수 있도록 여기서 한 번 올린다. **아직 GitHub 예약은 살아 있다.**

```bash
git push origin main
```

---

### Task 3: miniPC 설치와 드라이런 검증

**이 Task의 명령은 miniPC에서 실행한다.** 이 맥에서는 SSH가 Cloudflare Access 대화형 로그인을
요구해 에이전트가 직접 붙을 수 없다. 사용자가 `! ssh miniPC ...` 형태로 직접 돌리거나,
`cloudflared access login`으로 토큰을 캐시한 뒤 위임한다.

**Files:** 저장소 변경 없음

**Interfaces:**
- Consumes: `scripts/run-digest.sh` (Task 2), `_sent_log_path()` (Task 1)
- Produces: 동작하는 miniPC 설치본. Task 4가 이 위에서 실제 발송을 한다.

- [ ] **Step 1: 타임존과 기존 crontab을 확인한다**

Run: `ssh miniPC 'timedatectl; echo ---; crontab -l'`
Expected: `Time zone:` 줄을 읽어 **Task 4 Step 3**에서 쓸 crontab 줄을 고른다. 기존 항목과 충돌이 없는지 본다.

- [ ] **Step 2: uv를 설치한다**

이미 있으면 건너뛴다.

```bash
ssh miniPC 'command -v ~/.local/bin/uv || curl -LsSf https://astral.sh/uv/install.sh | sh'
ssh miniPC '~/.local/bin/uv --version'
```

Expected: 버전 문자열이 나온다.

- [ ] **Step 3: read-only deploy key를 만들어 등록한다**

비공개 저장소라 clone에 인증이 필요하다. 계정 전체에 권한이 붙는 PAT 대신 **이 저장소 하나에만
붙는 읽기 전용 deploy key**를 쓴다. 쓰기를 안 주므로 miniPC에서 push가 구조적으로 불가능하고,
만료도 없다.

```bash
ssh miniPC 'ssh-keygen -t ed25519 -f ~/.ssh/ai-trend-bot -N "" -C "minipc-ai-trend-bot"'
ssh miniPC 'cat ~/.ssh/ai-trend-bot.pub'
```

출력된 공개키를 `https://github.com/jaymunsh/ai-trend-bot/settings/keys` → **Add deploy key**에
붙인다. Title은 `minipc`. **`Allow write access`는 체크하지 않는다.**

이 키로만 github.com에 붙도록 SSH 설정을 넣는다. miniPC에는 jay-wiki 러너도 있으므로
호스트 별칭을 따로 둬서 서로 간섭하지 않게 한다.

```bash
ssh miniPC 'cat >> ~/.ssh/config <<EOF

Host github-ai-trend-bot
  HostName github.com
  User git
  IdentityFile ~/.ssh/ai-trend-bot
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config'
```

연결을 확인한다.

Run: `ssh miniPC 'ssh -T git@github-ai-trend-bot 2>&1 | head -1'`
Expected: `Hi jaymunsh/ai-trend-bot! You've successfully authenticated, but GitHub does not provide shell access.`
`Permission denied`가 나오면 deploy key 등록이 안 된 것이다.

- [ ] **Step 4: 저장소를 clone한다**

위에서 만든 별칭으로 clone한다. 이렇게 하면 `origin`이 별칭을 가리켜 `git pull`이 계속 이 키를 쓴다.

```bash
ssh miniPC 'mkdir -p ~/apps && cd ~/apps && \
  git clone github-ai-trend-bot:jaymunsh/ai-trend-bot.git'
ssh miniPC 'cd ~/apps/ai-trend-bot && git log --oneline -1 && git remote -v'
```

Expected: Task 2의 커밋이 보이고, `origin`이 `github-ai-trend-bot:jaymunsh/ai-trend-bot.git`이다.

- [ ] **Step 5: pull이 되는지 확인한다**

스크립트가 매 실행마다 `git pull --ff-only`를 하므로 여기서 미리 검증한다.

Run: `ssh miniPC 'cd ~/apps/ai-trend-bot && git pull --ff-only && echo "pull 정상"'`
Expected: `Already up to date.`와 `pull 정상`. 암호를 묻거나 멈추면 `IdentitiesOnly`/키 경로를 다시 본다.

- [ ] **Step 6: 시크릿 파일을 만든다**

**값은 사용자가 직접 넣는다. 이 대화나 로그에 붙이지 않는다.** GitHub Actions Secrets에 있는
것과 같은 값 세 개다.

```bash
ssh miniPC 'install -m 600 /dev/null ~/.config/ai-trend-bot.env'
```

그다음 miniPC에서 편집기로 세 줄을 넣는다.

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
GEMINI_API_KEY=...
```

권한을 확인한다.

Run: `ssh miniPC 'ls -l ~/.config/ai-trend-bot.env'`
Expected: `-rw-------` (600)

- [ ] **Step 7: 기존 발송 기록을 상태 경로로 옮긴다**

**이 단계를 빠뜨리면 첫 실행이 대량 중복 발송을 만든다.** 상태 파일이 비면 최근 항목이 전부
미발송으로 보인다.

```bash
ssh miniPC 'mkdir -p ~/.local/state/ai-trend-bot ~/logs ~/bin && \
  cp ~/apps/ai-trend-bot/data/sent.jsonl ~/.local/state/ai-trend-bot/sent.jsonl && \
  wc -l ~/.local/state/ai-trend-bot/sent.jsonl'
```

Expected: 167줄 이상 (2026-08-07 기준. 그 사이 발송분만큼 늘어나 있다).

- [ ] **Step 8: 스크립트를 설치한다**

```bash
ssh miniPC 'cp ~/apps/ai-trend-bot/scripts/run-digest.sh ~/bin/run-digest.sh && chmod 755 ~/bin/run-digest.sh'
```

- [ ] **Step 9: 발송 없이 파이프라인을 확인한다**

`--dry-run`은 `_sent_within` 검사를 건너뛰고 텔레그램으로 보내지 않는다
(`ai_trend_bot/cli.py:75`). 상태 파일도 쓰지 않는다.

```bash
ssh miniPC 'cd ~/apps/ai-trend-bot && set -a && . ~/.config/ai-trend-bot.env && set +a && \
  AI_TREND_BOT_SENT_LOG=~/.local/state/ai-trend-bot/sent.jsonl \
  ~/.local/bin/uv run ai-trend-bot run --dry-run --limit 30'
```

Expected: 수집·요약이 돌고 브리핑 후보가 출력된다. 텔레그램에는 아무것도 오지 않는다.
`설정 파일을 찾을 수 없음` 류의 오류가 나면 `cd`가 안 된 것이다.

- [ ] **Step 10: 리소스를 실측한다**

spec 7장의 RAM·디스크가 추정치로 남아 있다. 여기서 실제 값을 잰다. **Step 9와 같은
`--dry-run`을 감싸므로 발송은 일어나지 않는다.** 수집·본문 fetch·Gemini 요약이 메모리의
대부분이라 실제 발송분과 차이가 없다.

```bash
ssh miniPC 'cd ~/apps/ai-trend-bot && set -a && . ~/.config/ai-trend-bot.env && set +a && \
  AI_TREND_BOT_SENT_LOG=~/.local/state/ai-trend-bot/sent.jsonl \
  /usr/bin/time -v ~/.local/bin/uv run ai-trend-bot run --dry-run --limit 30 2>&1 \
  | grep -i "maximum resident"'
ssh miniPC 'du -sh ~/apps/ai-trend-bot ~/.cache/uv 2>/dev/null'
```

Expected: `Maximum resident set size (kbytes)` 한 줄과 두 디렉터리 크기.
측정값은 Task 6 Step 4에서 spec 7장 표에 반영한다.

---

### Task 4: 실제 발송 확인과 예약 차단

Task 3에서 파이프라인이 도는 것까지 봤다. 여기서 실제 발송을 한 번 하고, **바로 이어서**
GitHub 예약을 지운다. 두 단계 사이에 miniPC와 GitHub이 둘 다 살아 있어 중복이 갈 수 있으므로
한자리에서 끝낸다.

**Files:**
- Modify: `.github/workflows/digest.yml:2-17` (`schedule:` 블록 삭제)

**Interfaces:**
- Consumes: Task 3의 설치본
- Produces: `on:`이 `workflow_dispatch:`만 남은 워크플로. 수동 실행 창구로만 쓴다.

- [ ] **Step 1: miniPC에서 실제로 한 번 보낸다**

```bash
ssh miniPC '~/bin/run-digest.sh'; echo "exit=$?"
```

Expected: `exit=0`, 마지막 줄에 `<시각> done`. **텔레그램에 브리핑이 도착한다.**
직전 3시간 안에 GitHub 예약분이 나갔다면 "최근 3시간 안에 발송한 기록이 있어 건너뜁니다"가
나올 수 있다 — 상태 파일을 복사했으므로 정상 동작이다. 그 경우 3시간 뒤 다시 시도하거나,
도착 확인 없이 다음 Step으로 가고 Task 5의 관측으로 대체한다.

- [ ] **Step 2: 상태가 기록됐는지 확인한다**

```bash
ssh miniPC 'wc -l ~/.local/state/ai-trend-bot/sent.jsonl; tail -1 ~/.local/state/ai-trend-bot/sent.jsonl'
ssh miniPC 'cd ~/apps/ai-trend-bot && git status --short'
```

Expected: 줄 수가 늘어 있고, **clone은 깨끗하다**(`git status`가 아무것도 출력하지 않는다).
clone에 변경이 잡히면 Task 1의 환경변수가 안 먹은 것이다.

- [ ] **Step 3: crontab을 등록한다**

Task 3 Step 1에서 확인한 타임존에 맞는 줄 하나만 고른다.

```bash
# 서버가 KST인 경우
ssh miniPC '(crontab -l 2>/dev/null; echo "30 7,13,19 * * * ~/bin/run-digest.sh >> ~/logs/ai-trend-bot.log 2>&1") | crontab -'

# 서버가 UTC인 경우 (KST = UTC+9)
ssh miniPC '(crontab -l 2>/dev/null; echo "30 22,4,10 * * * ~/bin/run-digest.sh >> ~/logs/ai-trend-bot.log 2>&1") | crontab -'
```

확인한다.

Run: `ssh miniPC 'crontab -l'`
Expected: 방금 넣은 줄이 정확히 한 번 보인다.

- [ ] **Step 4: `digest.yml`에서 `schedule:` 블록을 지운다**

`.github/workflows/digest.yml`의 `on:` 아래에서 `schedule:` 키와 여섯 개 `- cron:` 항목,
그리고 그에 딸린 주석을 전부 지운다. 결과는 이렇게 된다.

```yaml
name: AI trend digest

on:
  # 정규 발송은 miniPC의 cron이 한다. 여기는 miniPC가 죽었을 때 사람이 누르는 창구다.
  # 이 워크플로는 저장소의 data/sent.jsonl 스냅샷을 보므로 miniPC의 최근 발송을 모른다.
  # 중복이 갈 수 있음을 알고 누른다.
  workflow_dispatch:

permissions:
  contents: write
```

`permissions`, `concurrency`, `jobs` 이하는 **건드리지 않는다.** 수동 실행 시 `Commit send log`
스텝이 여전히 `contents: write`를 필요로 한다.

- [ ] **Step 5: `schedule:`이 사라졌는지 확인한다**

Run: `grep -n "schedule\|cron" .github/workflows/digest.yml; echo "exit=$?"`
Expected: 아무것도 출력되지 않고 `exit=1`.

- [ ] **Step 6: 커밋하고 push**

```bash
git add .github/workflows/digest.yml
git commit -m "Stop scheduling the digest on GitHub

The miniPC cron owns the schedule now and keeps its send log outside the
clone, so a scheduled run here would judge from a stale snapshot and send
the same briefing twice."
git push origin main
```

- [ ] **Step 7: 예약이 더 안 걸리는지 확인한다**

Run: `gh run list --repo jaymunsh/ai-trend-bot --workflow digest.yml -L 5 --json event,createdAt`
Expected: 이후로 `"event":"schedule"`인 실행이 새로 생기지 않는다. 이 시점에 이미 걸려 있던
실행이 있으면 끝날 때까지 둔다.

---

### Task 5: 문서 정리

구현이 끝난 상태를 문서에 반영한다. README의 여러 절이 "GitHub Actions가 실행한다"를 전제로
쓰여 있어 그대로 두면 틀린 문서가 된다.

**Files:**
- Modify: `README.md` — `## 운영 기준`, `## 정시 발송이 필요하면`, `## 데이터 저장` 세 절 전체와
  `## 설정` 절의 마지막 두 문단. **줄 번호가 아니라 절 제목으로 찾는다. 앞 Step의 편집으로 계속 밀린다.**
- Delete: `docs/server-trigger-handoff.md`

**Interfaces:**
- Consumes: Task 4의 최종 상태
- Produces: 없음 (문서)

- [ ] **Step 1: `운영 기준` 절을 고친다**

`README.md:8`부터 `## 정시 발송이 필요하면` 직전까지를 이걸로 바꾼다.

```markdown
## 운영 기준

- 발송: 매일 07:30, 13:30, 19:30 (Asia/Seoul). **miniPC의 cron이 실행합니다**
- 중복 게시물은 다시 보내지 않음
- 현재 운영 모드: RSS 뉴스 중심
- 발송 개수는 **가변**입니다. 편집 기준을 통과한 것만 보내며, 통과분이 없으면 보내지 않습니다.
  `--limit`(기본 30, 최대 40)은 목표치가 아니라 폭주 방지선입니다.

**GitHub Actions는 더 이상 예약 실행하지 않습니다.** best-effort 큐라서 지연이 흔했고
(2026-08-05~07 관측 +63~193분), 지연이 다음 슬롯까지 밀리면 아예 폐기됐습니다. 실행을
miniPC로 옮긴 이유이며 근거는
[`docs/superpowers/specs/2026-08-07-minipc-execution-design.md`](docs/superpowers/specs/2026-08-07-minipc-execution-design.md)에 있습니다.

`--min-gap-hours 3`은 유지합니다. cron이 어떤 이유로 두 번 발사되는 경우를 막습니다.

한 회차를 통째로 놓쳐도 항목이 사라지지는 않습니다. 중복 판정이 시각이 아니라 URL
기준이라, 다음 회차가 그대로 후보로 잡습니다.
```

- [ ] **Step 2: `정시 발송이 필요하면` 절을 `miniPC 실행`으로 바꾼다**

`README.md`의 `## 정시 발송이 필요하면` 절 전체를 이걸로 교체한다.

````markdown
## miniPC 실행

정규 발송은 miniPC에서 돕니다. GitHub은 코드를 받아오는 창구로만 씁니다.

| 위치 | 무엇 |
| --- | --- |
| `~/apps/ai-trend-bot` | clone. 읽기 전용 |
| `~/.config/ai-trend-bot.env` | 시크릿 3개 (0600) |
| `~/bin/run-digest.sh` | `scripts/run-digest.sh` 사본 |
| `~/.local/state/ai-trend-bot/sent.jsonl` | 발송 기록. 저장소 밖 |
| `~/logs/ai-trend-bot.log` | 실행 결과 |

```bash
crontab -l                          # 30 7,13,19 * * * ~/bin/run-digest.sh ...
tail -5 ~/logs/ai-trend-bot.log     # 회차마다 "<시각> done"
```

코드를 고쳤으면 `main`에 머지만 하면 됩니다. 스크립트가 실행 전에 `git pull --ff-only`를 합니다.
`scripts/run-digest.sh` 자체를 고쳤을 때만 `~/bin/`으로 다시 복사해야 합니다.

miniPC가 죽으면 그 회차는 오지 않습니다. GitHub Actions에서 `workflow_dispatch`를 수동으로
누르면 보낼 수 있지만, 그쪽은 저장소의 오래된 `data/sent.jsonl`을 보므로 **중복이 갈 수 있습니다.**
````

- [ ] **Step 3: `데이터 저장` 절을 고친다**

`README.md`의 `## 데이터 저장` 절 전체를 이걸로 교체한다.

````markdown
## 데이터 저장

발송한 항목을 JSONL로 한 줄씩 기록합니다. 이 파일 하나가 유일한 상태입니다. DB도 캐시도 없습니다.

```jsonc
{"key": "<URL의 sha256>", "title": "...", "url": "...", "source": "...", "category": "...", "event": "...", "sent_at": "..."}
```

경로는 `AI_TREND_BOT_SENT_LOG`로 정합니다. **miniPC는 `~/.local/state/ai-trend-bot/sent.jsonl`을
쓰고, 값이 없으면 `data/sent.jsonl`로 떨어집니다.** clone을 읽기 전용으로 유지하려는 것입니다.
저장소의 `data/sent.jsonl`은 2026-08-07 이관 시점 스냅샷이며 더는 갱신되지 않습니다.

세 곳에서 읽습니다. 중복 방지 로그이면서 요약 품질에도 물려 있습니다.

| 읽는 곳 | 범위 | 없으면 |
| --- | --- | --- |
| `unseen()` | 전 기간의 `key` | 이미 보낸 항목을 다시 보냅니다 |
| `last_sent_at()` | 마지막 1줄 | 회차 중복 방지가 풀립니다 |
| `recent_events(days=14)` | 최근 14일의 `event` | triage가 후속 보도를 새 소식으로 봅니다 |

- 기록은 텔레그램 메시지 하나가 실제로 전달된 뒤에만 남습니다. 여러 메시지로 쪼개져 나가다
  중간에 실패해도, 이미 도착한 것은 다시 오지 않습니다.
- 이전에는 SQLite 파일을 GitHub Actions 캐시에 두었으나, 캐시는 7일 미사용·용량 초과로
  evict되며 그때마다 대량 재발송이 발생합니다. 그래서 파일로 옮겼습니다.
- 실측 407B/줄, 하루 약 24줄, **연 3.4MB**입니다. 가지치기는 없습니다. 커지면 오래된 줄부터
  잘라내면 됩니다.
- 백업은 두지 않습니다. 날아가면 중복 브리핑이 한 번 가고 2주간 triage 맥락이 비지만,
  둘 다 자가 복구됩니다.

탈락 항목과 그 사유는 저장하지 않습니다. 드라이런에서 터미널로 확인하세요
(`--show-dropped`, 기본 켜짐).
````

- [ ] **Step 4: `설정` 절 끝의 Actions 문구를 고친다**

앞선 Step들의 편집으로 줄 번호가 밀렸으므로 문구로 찾는다. `## 설정` 절 끝의 이 두 문단을 지운다.

> `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`를 GitHub Actions Secrets에
> 등록해야 자동 실행이 동작합니다. 로컬에서는 `.env.example`을 `.env`로 복사해 값을 넣습니다.
> **발급받은 키를 채팅이나 저장소에 직접 올리지 마세요.**
>
> Actions가 `data/sent.jsonl`을 푸시해야 하므로 워크플로에 `contents: write` 권한이 필요합니다.

그 자리에 이걸 넣는다.

```markdown
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`가 필요합니다. miniPC는
`~/.config/ai-trend-bot.env`에서, 로컬에서는 `.env.example`을 `.env`로 복사해 읽습니다.
수동 `workflow_dispatch`를 쓰려면 GitHub Actions Secrets에도 같은 값이 있어야 합니다.
**발급받은 키를 채팅이나 저장소에 직접 올리지 마세요.**

수동 실행 시 `data/sent.jsonl`을 푸시하므로 워크플로에 `contents: write` 권한이 필요합니다.
```

- [ ] **Step 5: 낡은 인계 문서를 지운다**

A안(서버가 `workflow_dispatch`만 호출)을 전제로 쓰여 있어 폐기한다.

```bash
git rm docs/server-trigger-handoff.md
```

- [ ] **Step 6: 링크가 깨지지 않았는지 확인한다**

Run: `grep -rn "server-trigger-handoff" . --include=*.md`
Expected: 아무것도 나오지 않는다. 나오면 그 참조도 지운다.

- [ ] **Step 7: 낡은 시각과 수치가 남았는지 확인한다**

Run: `grep -rn "07:23\|13:23\|19:23\|50분 뒤\|연 2MB" README.md`
Expected: 아무것도 나오지 않는다.

- [ ] **Step 8: 커밋하고 push**

```bash
git add README.md docs/server-trigger-handoff.md
git commit -m "Document the miniPC as the thing that runs the digest

Also record what the send log actually costs: 407 bytes a line, 24 lines
a day, and no backup because losing it heals itself."
git push origin main
```

---

### Task 6: 관측과 spec 갱신

며칠 돌려서 정시성이 실제로 회복됐는지 확인하고, spec에 추정치로 남은 값을 실측으로 바꾼다.

**Files:**
- Modify: `docs/superpowers/specs/2026-08-07-minipc-execution-design.md` (7장 리소스 표, 10장)

**Interfaces:**
- Consumes: Task 3 Step 10의 측정값, Task 4 이후 며칠간의 로그
- Produces: 블로그 글의 재료가 되는 전후 비교 수치

- [ ] **Step 1: 사흘치 실행 로그를 본다**

```bash
ssh miniPC 'tail -30 ~/logs/ai-trend-bot.log'
```

Expected: 하루 세 줄씩 `done`. 시각이 07:3x / 13:3x / 19:3x에 몰려 있다.
`git pull 실패`나 트레이스백이 섞여 있으면 원인을 조사한다.

- [ ] **Step 2: 텔레그램 도착 시각을 기록한다**

앱에서 실제 도착 시각 아홉 개(사흘 × 3회)를 적어 둔다. 목표 대비 편차가 90초 안쪽이어야 한다.

- [ ] **Step 3: GitHub에 예약 실행이 없는지 확인한다**

Run: `gh run list --repo jaymunsh/ai-trend-bot --workflow digest.yml -L 20 --json event,createdAt`
Expected: `schedule` 이벤트가 하나도 없다.

- [ ] **Step 4: spec 7장 표를 실측으로 갱신한다**

`실행 시 RAM`과 `디스크` 행의 `(추정)` 표기를 Task 3 Step 10에서 잰 값으로 바꾼다.
근거 열에 `미측정` 대신 측정 방법을 적는다.

- [ ] **Step 5: spec 10장의 첫 항목을 지운다**

"설치 후 RAM·디스크를 실측해 7장 표를 갱신한다"는 Step 4로 완료됐다. 지운다.

- [ ] **Step 6: 커밋**

```bash
git add docs/superpowers/specs/2026-08-07-minipc-execution-design.md
git commit -m "Replace the estimated resource figures with measured ones"
git push origin main
```

---

## 완료 기준

- [ ] `uv run pytest -q` 24개 통과
- [ ] `uv run ruff check .` 경고 없음
- [ ] `uv run basedpyright` 오류 없음
- [ ] miniPC clone이 `git status --short`에서 깨끗하다 (상태 파일이 저장소 밖에 있다는 증거)
- [ ] 텔레그램 도착 시각이 사흘 연속 07:3x / 13:3x / 19:3x
- [ ] GitHub Actions에 `event=schedule` 실행이 하나도 안 생긴다
- [ ] README에 `07:23`이 남아 있지 않다

## 롤백

Task 4까지 갔다가 되돌리려면 `digest.yml`에 `schedule:` 블록을 복원하고
(`git revert`로 Task 4 Step 6 커밋을 되돌리면 된다), miniPC의 crontab 줄을 지운 뒤,
`~/.local/state/ai-trend-bot/sent.jsonl`을 clone의 `data/sent.jsonl`에 복사해 커밋한다.
마지막 단계를 빼먹으면 Actions가 오래된 스냅샷을 보고 중복 발송한다.
