# Studio Duotone design system -- liquid glass, dual tone

A calm, evidence-heavy data identity with equal dark and light support. Tokens live in
`web/styles/globals.css` and are exposed to Tailwind v4. References: a glassmorphism social dashboard,
a dark-sidebar analytics dashboard and a liquid-glass analytics SaaS (frame-by-frame motion study).

## Foundations

- **Dual tone.** A deep floating sidebar (`.gp-sidebar`, navy with a violet glow, identical in both themes)
  against the main window: light mode is a pastel lilac / peach / sky mesh, dark mode a deep indigo mesh.
- **Two accents only.** *Primary* violet `#6D5EF6` carries everything interactive (buttons, links, focus
  ring, active states, the first chart series). *Accent* coral to rose (`--accent` `#FF7A5C`, `--accent-2`
  `#F0508A`) is for the hero gradient, highlights and the second chart series. `--highlight` is a soft tint
  of the primary, not a third hue. Emerald / amber / rose stay as functional status colours only.
- **Liquid glass.** Cards (`.rounded-card`) are translucent fills with a bright specular top edge, blur and
  saturation (`backdrop-filter`) so the mesh refracts through. Menus and sheets (`gp-menu-in`, `gp-pop-in`,
  `gp-sheet-right-in`) use a denser glass for legibility. `.gp-glass-sm` is the small-chip variant and
  `.gp-hero` the single gradient headline tile per screen.
- **Rounded everywhere.** Cards 28px, controls are pills (`rounded-full`), legacy 5-14px radii are retuned
  globally to 10-26px in `globals.css`, textareas 20px.
- Chart order: primary, accent, navy, lilac, accent-2, slate. Status colours for sentiment/ratings are kept.
- Inter is body text; Inter Tight and tabular numerals are used for measures.

## Density and spacing

- **80% root size.** `html { font-size: 80% }`, so every rem-based utility scales together (this is what 80% browser
  zoom did, with proportions unchanged). Design for a 1280x720 viewport. Fixed pixel values would not scale, so
  arbitrary Tailwind values are written in rem (`text-[0.6875rem]`, `max-w-[93.75rem]`), lucide icon sizes scale
  through attribute rules in `@layer base`, and `globals.css` uses rem for everything except 1-2px hairlines.
  Media-query breakpoints use the browser's own rem, so layout breakpoints are unaffected.
- **Spacing tokens.** Page roots use `mx-auto grid max-w-[...] gap-5`; cards are `p-5` (or `p-0` for flush tables);
  `main` is `p-4 md:p-6`; the sidebar and top bar float 1rem from the edges. Do not introduce other card paddings
  or page-level gaps.

## Charts

All charts share `components/charts/chart-kit.tsx`:

- Palette tokens `--chart-1..6` (primary violet, coral accent, navy, lilac, peach, slate; lighter in dark mode).
  The focus brand is always `--chart-1`. Sentiment and status series keep semantic colours (`semantic`).
- `TrendChart`: labelled axes (dates as "Oct 5", four y ticks), a light dashed grid, the focus series thick with a soft
  gradient and the others thinner, one glass tooltip listing every series high to low, and clickable legend chips
  showing the latest value that hide or show a series. No dashed series: forecasts are told apart by colour and label.
- `ChartTooltip`, `TICK`, `GRID` and `TOOLTIP_STYLE` for bar and pie charts. Axis text stays 11px (it does not shrink with
  the 80% scale) so it stays legible.

## Motion

One easing (`--ease-out`, `cubic-bezier(.22,1,.36,1)`) and four durations: **160ms** hover, **200ms**
popover/menu, **300ms** sheet/modal and the sliding pills, **440ms** page entrance. Entrances use opacity and
transform only (cheap on glass); blur-to-focus is reserved for the page title.

- `tw-animate-css` provides the shadcn utilities (`animate-in`, `fade-in-0`, `zoom-in-95`, `slide-in-from-*`).
- Our keyframes: `gp-fade-in`, `gp-pop-in` (dialog / palette), `gp-sheet-in` (left), `gp-sheet-in-right`,
  `gp-menu-in` (zoom + rise), `gp-card-in` (every `.rounded-card`, staggered by position and capped),
  `gp-focus-in` (page `h1`). Overlays fade and blur the page behind (`.gp-overlay-in`).
- **Sliding pills.** `TabBar` (`components/ui/tab-bar.tsx`) and the sidebar's active link share one indicator
  that glides to the active item (transform driven from measured offsets, CSS-only easing). The tab label turns
  light only as the pill arrives under it. Sidebar groups collapse by animating grid rows, not by popping.
- **Select.** `components/ui/select.tsx` is a rounded glass dropdown (rotating chevron, zoom-in menu, flips
  upward near the bottom) layered over a real, labelled `<select>` that stays the source of truth: forms,
  keyboard use and Playwright `selectOption` are unchanged, and `onChange` handlers receive a genuine event.
- `@media (prefers-reduced-motion: reduce)` collapses every transition and animation to ~0ms.
- To review motion frame by frame, slow it with CDP `Animation.setPlaybackRate` and screenshot each step.

## Components

Copy-in primitives live under `web/components/ui`. Radix powers dialog behavior. Composed components cover app shell, workspace switcher, searchable command palette (`command-palette.tsx`), stat tiles, delta/action cards, gauge, topic chart, interval bars, conversation mix, topic cloud, filters, virtualized mention rows, pills, ratings, provenance, the admin config surface (`admin-view.tsx`), the calibration queue, the onboarding wizard, the SSE job console (`job-console.tsx`), and loading/error/empty states.

The app shell has a skip-to-content link, `Esc` closes the mobile nav, the primary `<nav>` is labelled, and `<main id="main">` is the skip target.

## Adding a widget

Start from a backend field covered by `openapi.yaml`. Use a Card, visible title and qualifier, preserve sample size/interval/non-estimable information, and provide all states. Any clickable data mark creates a meaningful URL drilldown.

Use Recharts for standard line/area/bar views. The topic-volume hero and share-of-voice confidence intervals remain hand-rolled SVG. Test charts in both themes and never encode a series by color alone.
