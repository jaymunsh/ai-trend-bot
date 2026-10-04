"use strict";
const stages = [
  {
    title: "여러 출처를 하나의 후보 목록으로.",
    body: "28개 RSS·Atom 피드와 Hacker News, Hugging Face API를 병렬로 조회합니다. 최근 48시간의 미발송 기사를 최신순으로 추리고, URL 중복 제거 후 출처별 상한을 적용합니다. 게시일이 없는 글은 별도 경고를 남깁니다.",
    facts: [
      ["입력", "30개 출처"],
      ["출력", "최근·미발송 후보 목록"],
      ["소스별 상한 합계", "최대 435건 · 기간·중복 필터 적용 후"],
    ],
  },
  {
    title: "새로운 사실이 있는 소식을 고릅니다.",
    body: "제목과 티저를 편집 기준으로 심사합니다. 100건 단위로 1차 선별하고, 여러 배치가 있으면 생존자를 함께 놓고 다시 비교합니다. 같은 사건을 병합하고 최근 14일의 발송 사건과 대조합니다. 새 사실이 있는 후속 보도와 다른 회사의 별개 발표는 남길 수 있습니다.",
    facts: [
      ["기준", "config/editorial.md"],
      ["판정", "분류 · 사건 · 중복 · 순위"],
      ["발송 상한", "정규 실행 최대 50건"],
    ],
  },
  {
    title: "통과한 기사의 원문을 읽습니다.",
    body: "선별한 기사만 요청하고 trafilatura로 본문을 추출합니다. 제목이나 티저를 다시 쓰는 요약에 머무르지 않도록 재료를 보강합니다. 추출 실패 시에는 RSS 티저를 그대로 사용합니다.",
    facts: [
      ["대상", "선별을 통과한 기사"],
      ["본문 상한", "기사당 12,000자"],
      ["추출 실패 시", "RSS 티저로 대체"],
    ],
  },
  {
    title: "원문에서 구체적인 사실을 꺼냅니다.",
    body: "Gemini에 기사 내용을 전달해 한국어 제목과 요약을 생성합니다. 짧은 제목과 모바일 2~3줄 분량을 목표로 한 핵심 요약으로 읽는 부담을 줄입니다. 10건씩 순서대로 요청해 응답 크기와 순간 요청량을 제한합니다.",
    facts: [
      ["모델 기본값", "gemini-3.1-flash-lite"],
      ["출력 형식", "JSON 구조화 출력"],
      ["기사 대응", "입력 index로 원문 연결"],
    ],
  },
  {
    title: "전송을 확인한 뒤 기록합니다.",
    body: "준비한 요약을 메모리에서 발송 시각까지 보관합니다. 제목만 굵게 표시하고 분류와 긴 구분선은 생략합니다. 대표 원문 링크 하나와 외 N곳을 표시하며, 길이에 맞춰 기사 단위로 분할합니다. 메시지 하나의 전송 성공이 확인될 때마다 포함된 기사를 기록합니다. 기준을 통과한 항목이 없으면 보내지 않습니다.",
    facts: [
      ["전송", "Telegram Bot API"],
      ["메시지 분할 기준", "HTML 문자열 3,800자"],
      ["발송 기록", "월별 JSONL · 성공한 메시지만 기록"],
    ],
  },
];
const stageButtons = document.querySelectorAll("[data-step]");
const stageDetail = document.querySelector("#stage-detail");
stageButtons.forEach((button) =>
  button.addEventListener("click", () => {
    const stage = stages[Number(button.dataset.step)];
    stageButtons.forEach((other) =>
      other.setAttribute("aria-pressed", String(other === button)),
    );
    stageDetail.querySelector("h3").textContent = stage.title;
    stageDetail.querySelector(".stage-copy p").textContent = stage.body;
    const facts = stageDetail.querySelector(".stage-facts");
    facts.replaceChildren(
      ...stage.facts.map(([label, value]) => {
        const row = document.createElement("div");
        const term = document.createElement("dt");
        const description = document.createElement("dd");
        term.textContent = label;
        description.textContent = value;
        row.append(term, description);
        return row;
      }),
    );
  }),
);
const sourceButtons = document.querySelectorAll("[data-source-filter]");
const sourceRows = [...document.querySelectorAll(".source-row")];
sourceButtons.forEach((button) =>
  button.addEventListener("click", () => {
    const filter = button.dataset.sourceFilter;
    sourceButtons.forEach((other) =>
      other.setAttribute("aria-pressed", String(other === button)),
    );
    let count = 0;
    sourceRows.forEach((row) => {
      row.hidden = filter !== "all" && row.dataset.group !== filter;
      if (!row.hidden) count += 1;
    });
    const label =
      filter === "all" ? "전체" : button.firstChild.textContent.trim();
    document.querySelector("#source-count").textContent =
      `${label} ${count}개 출처`;
  }),
);
const navLinks = [...document.querySelectorAll(".site-header nav a")];
if ("IntersectionObserver" in window) {
  const visible = new Map();
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) =>
        visible.set(entry.target.id, entry.isIntersecting),
      );
      const active = navLinks.find((link) => visible.get(link.hash.slice(1)));
      navLinks.forEach((link) => {
        if (link === active) link.setAttribute("aria-current", "true");
        else link.removeAttribute("aria-current");
      });
    },
    { rootMargin: "-15% 0px -50% 0px" },
  );
  navLinks.forEach((link) =>
    observer.observe(document.querySelector(link.hash)),
  );
}
document
  .querySelector("[data-print]")
  .addEventListener("click", () => window.print());
const beforePrint = () =>
  document.querySelectorAll("details").forEach((details) => {
    details.dataset.printOpen = String(details.open);
    details.open = true;
  });
const afterPrint = () =>
  document.querySelectorAll("details").forEach((details) => {
    details.open = details.dataset.printOpen === "true";
    delete details.dataset.printOpen;
  });
window.addEventListener("beforeprint", beforePrint);
window.addEventListener("afterprint", afterPrint);
