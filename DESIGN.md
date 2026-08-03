# AI Trend Bot Overview Design System

## 0. Research Log

- Embedded refs: shortlisted Notion, Linear, GitBook → picked Minimalist + Notion because a long Korean technical brief needs warm editorial hierarchy, quiet navigation, and dense information without dashboard decoration.
- UI/UX DB: 1 design-system query → kept the content-first newsletter structure and system-font performance guidance; rejected the suggested pink accent and oversized display type because they compete with operational content.
- Lazyweb: 3 queries, 5 screens viewed (Better Stack, ButterDocs, Coda, GitBook, n8n) → took the slim rail, bordered metric strip, wide reading canvas, and low-chrome tables; did not copy brand assets or screen compositions.
- Imagen drafts: `/Users/sunghyuk/.codex/generated_images/019fba75-1b68-73d3-93b5-06f11e1dd8f9/exec-e36e2a42-5a1f-4b68-9e85-c3823b04d7f5.png`, `/Users/sunghyuk/.codex/generated_images/019fba75-1b68-73d3-93b5-06f11e1dd8f9/exec-11aa808c-3a70-4f86-a1fa-31bd7e6daa36.png` → picked the second draft as the direction contract because its numbered rail, factual density, and restrained hierarchy suit a system overview.
- Reference status: all external screens and generated drafts are direction references, not pixel targets. The final page is an original implementation grounded in the repository facts.

## 1. Atmosphere & Identity

A quiet operations handbook: factual, calm, and easy to scan even when the reader does not know the codebase. The signature is the **blue ledger line** — one restrained cobalt rule that links navigation, status, diagrams, and schedule markers across a warm paper canvas.

Primary persona: the project owner checking what is built, what runs automatically, and what remains. Secondary persona: a friend or future maintainer with no prior code context. Stress contexts include a 375px phone, 200% zoom, keyboard-only navigation, reduced motion, and dense Korean text.

## 2. Color

| Role              | Token                   |     Light | Usage                      |
| ----------------- | ----------------------- | --------: | -------------------------- |
| Canvas            | `--surface-canvas`      | `#F7F6F3` | Page background            |
| Primary surface   | `--surface-primary`     | `#FFFEFC` | Main reading surface       |
| Secondary surface | `--surface-secondary`   | `#F1F0EC` | Quiet panels and code      |
| Ink               | `--text-primary`        | `#242628` | Headings and body          |
| Muted ink         | `--text-secondary`      | `#656965` | Supporting copy            |
| Faint ink         | `--text-tertiary`       | `#5F635E` | Metadata                   |
| Default rule      | `--border-default`      | `#D9D9D3` | Cards and tables           |
| Subtle rule       | `--border-subtle`       | `#E9E8E3` | Internal separators        |
| Primary accent    | `--accent-primary`      | `#1459C7` | Links, focus, active state |
| Accent hover      | `--accent-hover`        | `#0C439A` | Interactive hover          |
| Accent tint       | `--accent-soft`         | `#EAF1FD` | Active nav and info panels |
| Success           | `--status-success`      | `#246B45` | Operating status           |
| Success tint      | `--status-success-soft` | `#E8F3EC` | Success badges             |
| Warning           | `--status-warning`      | `#9B5D12` | Deferred or caution state  |
| Warning tint      | `--status-warning-soft` | `#FBF0DD` | Warning panels             |
| Error             | `--status-error`        | `#A63A32` | Error showcase only        |
| Error tint        | `--status-error-soft`   | `#F9E9E7` | Error showcase only        |

Rules: accent is functional, never decorative; status always includes text; no color outside this table; contrast target is WCAG 2.2 AA.

## 3. Typography

| Level    |                           Size | Weight | Line height |   Tracking | Usage           |
| -------- | -----------------------------: | -----: | ----------: | ---------: | --------------- |
| Display  | `clamp(2.75rem, 7vw, 5.25rem)` |    700 |        1.02 | `-0.045em` | Hero title      |
| H1       |                         `2rem` |    700 |         1.2 | `-0.025em` | Major section   |
| H2       |                       `1.5rem` |    700 |         1.3 | `-0.015em` | Subsection      |
| H3       |                     `1.125rem` |    700 |         1.4 | `-0.005em` | Card title      |
| Body/lg  |                     `1.125rem` |    400 |         1.7 |        `0` | Lead copy       |
| Body     |                         `1rem` |    400 |         1.7 |        `0` | Default copy    |
| Body/sm  |                     `0.875rem` |    400 |        1.55 |        `0` | Supporting copy |
| Caption  |                      `0.75rem` |    600 |        1.45 |   `0.02em` | Metadata        |
| Overline |                    `0.6875rem` |    700 |         1.3 |   `0.12em` | Section labels  |

- Primary: `ui-sans-serif, -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif`.
- Editorial display: `"Iowan Old Style", "Noto Serif KR", Georgia, serif`.
- Mono: `ui-monospace, SFMono-Regular, Menlo, monospace`.
- Body never drops below 14px. Korean headings use `word-break: keep-all`; long URLs use `overflow-wrap: anywhere`.

## 4. Spacing & Layout

Base unit: **4px**.

| Token        | Value | Usage              |
| ------------ | ----: | ------------------ |
| `--space-1`  |   4px | Tight              |
| `--space-2`  |   8px | Inline             |
| `--space-3`  |  12px | Compact            |
| `--space-4`  |  16px | Standard           |
| `--space-5`  |  20px | Comfortable        |
| `--space-6`  |  24px | Card               |
| `--space-8`  |  32px | Group              |
| `--space-10` |  40px | Section inner      |
| `--space-12` |  48px | Major break        |
| `--space-16` |  64px | Page rhythm        |
| `--space-20` |  80px | Hero               |
| `--space-24` |  96px | Maximum separation |

- Max shell width: 1440px; rail: 248px; reading measure: 1120px.
- Desktop uses a fixed left rail and broad content column. The hero intentionally leaves more whitespace on the right to establish editorial hierarchy.
- At 1024px the rail becomes horizontal; at 768px metrics and two-column sections collapse; at 640px everything becomes one readable column.
- Tables may scroll inside a labelled wrapper; the primary page never scrolls horizontally.

## 5. Components

### TOC Link

- **Structure**: anchor with two-digit index and label.
- **States**: default, hover, active (`aria-current`), focus-visible.
- **Accessibility**: native anchor, 44px minimum hit area, visible focus.
- **Layout**: vertical stack in the sticky rail; horizontal scroll list at smaller widths.

### Status Badge

- **Structure**: text label plus CSS dot.
- **Variants**: success, warning, neutral.
- **States**: static; color is never the sole signal.
- **Accessibility**: readable text announces the status.

### Metric Tile

- **Structure**: overline, tabular value, one-line explanation.
- **Variants**: standard and emphasized.
- **States**: static; long labels wrap without clipping.
- **Layout**: responsive auto-fit grid.

### Diagram Panel

- **Structure**: figure, heading, Mermaid source, figcaption, text fallback.
- **Variants**: architecture, sequence, lifecycle.
- **States**: loading text before Mermaid renders; readable fallback if the CDN is unavailable.
- **Accessibility**: explanatory caption and adjacent text summary; diagram color is not the only carrier.

### Data Table

- **Structure**: labelled overflow wrapper, table, caption, semantic head/body.
- **Variants**: source registry, priority matrix, test evidence.
- **States**: normal and narrow scroll.
- **Accessibility**: real table markup, scoped headers, persistent caption.

### Callout

- **Structure**: title, status label, body, optional checklist.
- **Variants**: info, success, warning, error.
- **States**: static; error variant exists for the primitive showcase only.
- **Accessibility**: border, label, and text reinforce color.

### Timeline Stop

- **Structure**: time, ordinal, count, explanation.
- **Variants**: morning, afternoon, evening using the same accent family.
- **States**: static; reflows vertically on mobile.
- **Accessibility**: ordered-list semantics; chronological order remains in DOM.

### Code Block

- **Structure**: pre/code with a visible purpose label.
- **States**: horizontal overflow only within the block.
- **Accessibility**: selectable text and sufficient contrast.

## 6. Motion & Interaction

| Type     | Duration | Easing      | Usage              |
| -------- | -------: | ----------- | ------------------ |
| Micro    |    140ms | ease-out    | Link/button hover  |
| Standard |    220ms | ease-in-out | Details disclosure |

- Only color, background-color, border-color, transform, and opacity may transition.
- No decorative entrance animation. Smooth scrolling is the only page motion and is disabled under `prefers-reduced-motion`.
- The print button and links provide hover, active, and focus-visible feedback. Static cards do not pretend to be clickable.

## 7. Depth & Surface

Strategy: **borders-only with tonal shift**. Surfaces are separated by 1px rules and warm tonal changes. No gradients, glass effects, or box shadows. Radius scale is restrained: 4px for tags, 8px for panels, 12px only for the hero summary.

## 8. Accessibility Constraints & Accepted Debt

### Constraints

- WCAG target: 2.2 AA, contrast floor 4.5:1 for body and 3:1 for large text and UI boundaries.
- Skip link, semantic landmarks, sequential headings, visible keyboard focus, 44px touch targets.
- 200% zoom and 375px viewport must preserve every section with no primary horizontal overflow.
- Reduced motion honored. Korean text must not clip, lose descenders, or create avoidable single-character orphan lines.
- Mermaid diagrams always have plain-language captions and summaries.

### Accepted Debt

| Item                                             | Location                          | Why accepted                                                                                                                                         | Owner / Exit                                                                |
| ------------------------------------------------ | --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Mermaid needs a network connection on first open | `docs/how-it-works.html` | A plain-language fallback keeps the content available offline; bundling the library would add a large generated dependency to this small repository. | Bundle Mermaid locally if fully offline distribution becomes a requirement. |
| No dark theme                                    | Entire document                   | The requested artifact is a printable operational brief; one carefully verified light theme is clearer and smaller.                                  | Add only if the owner requests ongoing web publication.                     |
