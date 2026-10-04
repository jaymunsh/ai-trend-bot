---
name: AI Trend Bot
description: A Korean editorial introduction to a personal AI news briefing bot.
colors:
  canvas: "#f4f2eb"
  paper: "#fffef9"
  ink: "#20291f"
  muted: "#62685d"
  rule: "#d2d3c8"
  accent: "#ae4d20"
  accent-soft: "#efe0d3"
  dark: "#202d27"
  dark-ink: "#f4f2eb"
  dark-muted: "#c0cbbb"
  dark-rule: "#4c5c50"
typography:
  display:
    fontFamily: 'Pretendard, "Apple SD Gothic Neo", sans-serif'
    fontSize: "clamp(44px, 5.35vw, 72px)"
    fontWeight: 850
    lineHeight: 1.19
    letterSpacing: "-0.04em"
  headline:
    fontFamily: 'Pretendard, "Apple SD Gothic Neo", sans-serif'
    fontSize: "clamp(26px, 3.2vw, 40px)"
    fontWeight: 750
    lineHeight: 1.3
    letterSpacing: "-0.03em"
  title:
    fontFamily: 'Pretendard, "Apple SD Gothic Neo", sans-serif'
    fontSize: "25px"
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "-0.02em"
  body:
    fontFamily: 'Pretendard, "Apple SD Gothic Neo", sans-serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.75
  label:
    fontFamily: 'Pretendard, "Apple SD Gothic Neo", sans-serif'
    fontSize: "14px"
    fontWeight: 550
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "0.88em"
rounded:
  button: "6px"
  filter: "5px"
spacing:
  space-2: "8px"
  space-3: "12px"
  space-4: "16px"
  space-5: "20px"
  space-6: "24px"
  space-8: "32px"
  space-12: "48px"
  space-20: "80px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.button}"
    padding: "14px 20px"
  button-primary-hover:
    backgroundColor: "{colors.dark-rule}"
  text-link:
    textColor: "{colors.ink}"
  navigation:
    textColor: "{colors.muted}"
    typography: "{typography.label}"
  filter:
    textColor: "{colors.muted}"
    rounded: "{rounded.filter}"
    padding: "10px 14px"
  filter-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  pipeline-step:
    textColor: "{colors.ink}"
    padding: "22px 20px 24px"
  pipeline-step-selected:
    backgroundColor: "{colors.dark}"
    textColor: "{colors.paper}"
  stage-panel:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    padding: "36px 32px"
  disclosure:
    textColor: "{colors.ink}"
    padding: "18px 0"
  schedule:
    backgroundColor: "{colors.dark}"
    textColor: "{colors.dark-ink}"
---

# Design System: AI Trend Bot

## Overview

**Creative North Star: "The Korean Editorial Brief"**

Warm paper, dark olive ink and burnt orange emphasis frame a Korean introduction to the project. Large, closely tracked headings establish hierarchy; quieter descriptions and ruled lists carry the implementation details. The page explains the personal bot before introducing code.

This scan documents `docs/how-it-works.html`, with `docs/assets/overview.css` and `docs/assets/overview.js` as implementation authority. `docs/digest-preview.html` has an independent Telegram comparison design. `docs/design-showcase.html` is a historical prototype, not authority for the current overview. The overview uses HTML, CSS and inline SVG for content and diagrams. The owner-supplied transparent robot image at `docs/assets/ai-news-robot.png` appears in the header and hero; README.md references that same asset. The format comparison prototype is not linked from this introduction.

**Key Characteristics:**

- Generous Korean type hierarchy with a locally bundled variable font.
- Warm, flat surfaces divided by fine rules.
- Dark selected controls and a dark operating schedule.
- Functional step selection, source filtering and native disclosures.

## Colors

Burnt orange supplies the primary accent; warm neutrals and olive ink carry the reading surface.

The sidecar's generated tonal ramps support color previews; they are not additional implemented palette tokens.

### Primary

- **Burnt Orange — `accent`:** highlighted hero text, active navigation, focus outlines and small explanatory labels.
- **Orange Wash — `accent-soft`:** step hover and text selection.

### Neutral

- **Warm Paper — `canvas`:** page and sticky header background.
- **Light Paper — `paper`:** stage detail panel and text on dark controls.
- **Olive Ink — `ink`:** headings, primary actions and selected source filters.
- **Muted Olive — `muted`:** supporting text, metadata and inactive navigation.
- **Paper Rule — `rule`:** section, row and control boundaries.
- **Deep Olive — `dark`:** selected processing step and operating section; `dark-ink`, `dark-muted` and `dark-rule` provide their text and separators.

## Typography

**Display and Body Font:** Pretendard, with Apple SD Gothic Neo and sans-serif fallbacks. The variable WOFF2 is bundled in `docs/assets/`, preloaded by the HTML and declared for weights 100–900 with `font-display: swap`.

**Code Font:** the system monospace stack in the frontmatter. Code appears inside expandable technical content and answers.

The desktop display, headline and stage title roles above are extracted directly from CSS. Lead copy uses 18px with a 1.8 line height and a 42ch maximum measure. Supporting descriptions range from 13–16px; 11–12px text is reserved for compact metadata. Stage descriptions are limited to 62ch. Schedule times use tabular numerals, a 550 weight and `clamp(40px, 5vw, 68px)`.

Headings use balanced wrapping. Korean headings and paragraphs preserve word boundaries with `word-break: keep-all`; long strings can wrap with `overflow-wrap: anywhere`. Mobile display overrides and other responsive changes remain in CSS rather than being separate global roles.

## Layout

The centered content width is capped at 1184px. Desktop gutters total 96px, narrowing to 64px at 1060px, 40px at 760px and 32px at 360px. The header is sticky, with section anchors and a repository link. Mobile navigation moves into a second horizontal row.

Desktop sections combine asymmetric two-column reading layouts, a five-column processing rail and ruled source lists. Most major sections use 80–88px vertical spacing. At 760px, hero, principles, stage detail, editorial introduction and FAQ become single-column; section spacing reduces to 48–56px. Processing controls become stacked rows. The source registry retains three narrower columns, and the schedule retains its three time columns. Editorial rule columns stack at 360px.

## Elevation & Depth

There are no box shadows. Fine borders and changes between paper and dark olive provide separation. A small rotated square connects the selected processing step to its explanatory panel. Depth comes from content hierarchy and state rather than lifted containers.

## Shapes

Reading sections and stage panels are square. Primary actions have gently rounded corners; source filters use a slightly smaller radius. The representative robot retains the supplied PNG transparency and proportions, without cropping or geometric masks. Inline SVG supplies compact line icons; the header uses a 40px version of the robot asset. The unused `--radius` declaration is not a component shape contract.

## Components

### Actions and navigation

The primary anchor uses olive ink with light paper text and a 50px minimum height; hover changes its background to `dark-rule`. Text links use small inline arrows and gain an orange underline on hover. Navigation uses muted text, orange hover and an orange underline for `aria-current="true"`; JavaScript updates that state while sections enter view. Global keyboard focus is a 2px orange outline with a 5px offset. The page includes a skip link.

### Processing rail and detail panel

Five native buttons select collection, selection, article extraction, Korean summarization and delivery. Selected buttons use dark olive, light text and `aria-pressed`; unselected buttons show an orange wash on hover. Clicking updates the title, explanation and definition list in an `aria-live="polite"` panel. This is an interactive explanation of the implemented processing steps, not a live progress indicator. The panel uses light paper, a fine border and a desktop two-column split.

### Source filters and rows

Rounded filter buttons group the configured sources; selected filters invert to ink and paper. Hover changes the border and text to orange. JavaScript hides unmatched rows and updates a polite live count. Each ruled row presents the source, retrieval method and candidate cap; numbers use tabular numerals. There is no search field.

### Representative image

The owner-supplied robot is the hero artwork, capped at 440px on desktop and 280px on mobile. Explicit intrinsic dimensions prevent layout shift. The same image is used in the header at 40px and in README.md at 220px. The introduction has no message-format switch or comparison link.

### Schedule and disclosures

The dark operating section displays three large tabular times in a bordered ordered list, followed by a compact runtime flow and notes. Native `details` elements reveal technical information and FAQ answers; their plus sign rotates when open. The footer print action invokes browser printing, temporarily opens disclosures and restores them afterward.

Processing hover and disclosure indicators use 160ms ease-out transitions. Desktop hero copy enters over 650ms at widths of at least 1000px. Reduced motion disables animation, transitions and smooth scrolling. Print styles remove navigation and controls and render the operating section on white.

## Do's and Don'ts

### Do:

- **Do** use the current overview stylesheet as the source of truth for tokens and responsive behavior.
- **Do** preserve Korean word boundaries, source attribution and visible keyboard focus.
- **Do** pair selected colors with semantic state and explanatory text.
- **Do** label examples and proposed changes so they remain distinguishable from implemented behavior.

### Don't:

- **Don't** reuse the historical showcase's cobalt palette or fixed sidebar for the current overview.
- **Don't** infer a shared visual system from the independent digest comparison page.
- **Don't** invent subscriber metrics, live operating status or signup functionality.
- **Don't** replace text, processing controls or source rows with flattened bitmap compositions.
