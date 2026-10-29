# DESIGN.md: Samar (السَّمَر)

The visual contract for every page of Majlisna. Product facts live in `PRODUCT.md`; this file
says how the product looks, moves and reads. The validated source is the owner-approved sketch
("Samar Final"). When this file and a page disagree, this file wins; when this file is silent,
follow the sketch.

**One world under two lights.** The samar is the evening majlis of talk and riddles. Dark theme =
night (Maghrib) over the AlUla mesas; light theme = the same horizon in ʿAṣr afternoon light.
Brass marks what you can act on, wool marks the teams, a woven thread is the only clock, the
lozenge is the only geometry.

---

## 1. Where things live

| What | Path |
|---|---|
| Tokens, Tailwind mapping, base, type and motion utilities | `front/src/index.css` |
| CSS of the brand components (madd, tiles, clock, halqa, arch, sonner) | `front/src/styles/brand.css` |
| Woven Sadu bands as `--band-*` data URIs (generated) | `front/src/styles/sadu.css` ← `front/scripts/brand/sadu.py` |
| Page CSS (Codenames cloth, quiz ladder and bands, lobby head, Undercover lawh) | `front/src/styles/pages/*.css` (imported from `index.css`) |
| Self-hosted fonts | `front/src/fonts.ts` (imported 2nd in `main.tsx`) |
| Motion presets | `front/src/lib/motion.ts` |
| View Transitions helper | `front/src/lib/view-transition.ts` |
| UI primitives | `front/src/components/ui/*` |
| Brand components | `front/src/components/brand/*` (barrel: `@/components/brand`) |
| Frozen wordmark, app icon, colophon photo, credits | `front/src/assets/brand/` (`SOURCES.txt`), `front/public/favicon.svg` |
| Band SVG files | `front/src/assets/sadu/*.svg` |
| Shell (nav, menu sheet, footer) and home CSS | `front/src/styles/shell.css`, `front/src/styles/home.css` (imported from `index.css`, `@layer components`) |
| Nav, footer, language switch, theme toggle | `front/src/components/layout/*` |
| Home sections (hero, join row, halqa card, the four games, charities) | `front/src/components/home/*` |
| Hero skies (night `sky-maghrib.*`, afternoon `sky-asr.*`; CC BY-SA 4.0) | `front/public/sky/` (`SOURCES.txt`) |
| Favicon / PWA icons / OG card (rasters rendered from the SVGs) | `front/public/` ← `front/scripts/brand/render-icons.mjs` |

Theme switching: `ThemeProvider` sets BOTH `class="dark|light"` (Tailwind's `dark:` variant) and
`data-theme="dark|light"` (the tokens) on `<html>`; `index.html` applies the same rule before
first paint. Any element can re-theme its subtree with its own `data-theme` (then give it
`bg-background text-foreground`).

## 2. Palette

All colours are OKLCH tokens on `:root`/`[data-theme]`. Use the Tailwind names in the last column.

| Token | ʿAṣr (light) | Samar (dark) | Role | Utility |
|---|---|---|---|---|
| `--bg` | 0.975 0.005 80 gypsum | 0.165 0.012 52 tent black | page | `bg-background` |
| `--bg-deep` | 0.94 0.018 70 | 0.135 0.01 50 | rocks, ground, deep wells | `bg-bg-deep` |
| `--surface` | 0.996 0.002 80 | 0.205 0.014 54 | panels, cards, inputs | `bg-surface` |
| `--surface-2` | 0.94 0.016 72 sand | 0.245 0.017 56 | tiles, chips, muted fills | `bg-surface-2`, `bg-muted` |
| `--card` | = surface | 0.235 0.016 58 | unrevealed Codenames card | `bg-card` |
| `--line` | 0.86 0.02 68 | 0.34 0.022 60 | hairlines, dividers | `border-line` (`border-border`) |
| `--line-brass` | bronze 42 % | brass 40 % | frames, rules, rings | `border-line-brass` |
| `--line-brass-strong` | bronze 85 % | brass 75 % | secondary buttons, lawh, arch | `border-line-brass-strong` |
| `--line-field` | 0.60 0.03 65 | 0.55 0.03 70 | a text field's boundary (≥ 3:1 on surface, sand, bg: WCAG 1.4.11) | `border-line-field` |
| `--text` | 0.21 0.016 50 goat-hair ink (16.5:1) | 0.93 0.022 84 wool cream (15.7:1) | text | `text-foreground` |
| `--text-muted` | 0.46 (6.7:1; 5.6 on sand) | 0.75 (8.7:1; 7.5 on card) | secondary text | `text-muted-foreground` |
| `--brass` | 0.52 0.10 63 bronze (5.3:1) | 0.80 0.105 77 (10.2:1) | focus, lines, "yours", seals | `text-brass`, `bg-brass` |
| `--primary` | = text (ink) | = brass | the primary action fill | `bg-primary text-primary-foreground` |
| `--ember` | 0.54 0.17 34 (5.1:1) | 0.69 0.15 42 (6.1:1 on surface) | errors, assassin edge. Never a fill. | `text-ember`, `border-ember` |
| `--warp` | translucent | translucent | bare warp threads (unrevealed) | `warp-threads` |
| `--focus` | = brass | = brass | focus rings | `outline-focus` |

Wool (identical in both lights): `--wool-madder` 0.63 0.14 33 (team 1, Undercover role; ink on
it 5.0:1), `--wool-indigo` 0.36 0.10 266 (team 2 only; cream on it 10.3:1), `--wool-undyed`
(Civilian), `--wool-ink`, `--wool-on-indigo`, `--madd-madder` (the ribbon's darker dye).
Utilities: `bg-wool-madder`, `text-wool-ink`, etc. Bystander / assassin: `--bystander`,
`--on-bystander`, `--assassin`.

Contrast rules: body and placeholder text ≥ 4.5:1, large text ≥ 3:1. Text on a tint uses an
`-on-tint` token (`text-primary-on-tint`, `text-destructive-on-tint`), see `front/CLAUDE.md`.
Madder vs indigo is only 2.97:1 apart in luminance: a team is ALWAYS colour + glyph + selvedge.

Home-only: `--sky-fallback`, `--ground-foot`, `--ground-0/1`, `--fire` (the halqa's ember glow).

## 3. Type

Five families, one role each, all self-hosted (`fonts.ts`; the CSP allows no font CDN). Arabic is
loaded in every language. Arabic is never letter-spaced; it is set 2–3 px larger than Latin at the
same role (`html[dir=rtl]` scales rem by 110 %).

| Role | Face | Use it for | Utility |
|---|---|---|---|
| wordmark | Reem Kufi 700 | the name مجلسنا ONLY, via `<Wordmark>` | `type-wordmark`, `font-wordmark` |
| display | Marcellus 400 (figures from Readex pinned to the letters' weight, Arabic letters fall to Amiri 700) | Latin page/section titles, colophon title, lockup | `type-hero`, `type-h2`, `type-h3`, `type-title`, `font-display` |
| ui | Readex Pro 160–700 | every control, every body line, EVERY figure | `type-body`, `type-lede`, `type-panel`, `type-label`, `type-meta`, `font-sans` |
| nass | Amiri 400/700 | revealed words, Arabic names and titles, explanations | `type-word`, `type-arabic-name`, `type-nass`, `font-nass` |
| hand | Aref Ruqaa 700 | what a player wrote in Arabic (descriptions, clues, answers) | `type-hand`, `font-hand` |

- `h1`/`h2` default to the display role; add `type-*` for size. Marcellus has one weight:
  `font-bold` on a title does nothing (synthesis is off), so emphasis comes from size.
- Figures inside a display title ("Bilalbd1 wins!", "Round 3 of 10") are Readex digits (the
  `Samar Figures` face, first in the stack: Marcellus's 1 reads as I) at ONE fixed weight, 280,
  Marcellus's stem, in every language: in a title they sit in a Latin run (a username) set in
  Marcellus, Arabic titles included (`fonts.ts`). Never let them follow the title's requested
  weight, and never synthesize a bold in the display stack (`.font-display` and the `type-*`
  roles turn synthesis off).
- Body: Readex 300, 17 px / 1.55 (Arabic 1.75–1.9). Controls 500. Measure 50–55 ch.
- Figures: tabular for clocks, codes, PINs, scores, counts: `num` (or `tabular-nums`).
  `font-mono` is now Readex with tabular figures; do not use it for new code, use `num`.
- Codes, PINs, clocks and scores use Western digits in every language (read aloud at mixed
  tables). Eastern Arabic digits are fine in Arabic prose.
- Mixed lines (Latin term in Arabic, Arabic word in English): separate spans with `lang` and
  `dir`, isolated with the `bidi-isolate` utility or `<bdi>` (Tailwind's `isolate` is
  `isolation`, not bidi).
- No eyebrow labels above headings, no section numbers, no gradient text.

## 4. Space, radius, line, depth

- Container: `page-wrap` (max `--maxw` 1440 px, 1680 above 2200 px; side gutter
  `--gutter` = clamp(16px, 5vw, 96px)). Nav height `--navh` 76 / 62 px phones / 92 px ≥ 2200.
- Radii: 2 px controls and tiles (`rounded-sm`), 3 px panels (`rounded-lg`), 4 px the lawh
  (`rounded-2xl`). Arches are drawn, not rounded. `rounded-full` only for avatars.
- Lines: 1 px. `--line` for structure, brass for frames and invitations, lozenge nodes at corners
  and in the middle of rules (`<Separator>`, `rule-brass`). Never a coloured side stripe.
- Depth: almost none. Panels are flat with a hairline. The only shadows are offset and blurred,
  on floating layers (dialogs, menus, toasts). No glow, no glass, no coloured shadow.
- Atmosphere: grain only on the sky/nav (`grain`). One warmth: the ember at the halqa's centre.
- Touch targets ≥ 44 px on touch screens (`pointer-coarse:` variants are built into Button,
  Tabs, menu items, Switch/Checkbox hit areas).

## 5. UI primitives (`@/components/ui/...`)

| Component | Import | API |
|---|---|---|
| Button | `ui/button` | `variant` primary·secondary·ghost·danger·link, `size` sm·md·lg·icon·icon-sm, `block`, `loading` (keeps label + ◆◆◆, aria-busy), `iconStart`/`iconEnd`, `asChild`. Disabled = dashed hairline; say why next to it. Also `buttonVariants`, `BusyLozenges`. |
| Field, Input, Textarea | `ui/field` | `<Field label hint error id hideLabel labelEnd errorTestId>` wires id, aria-describedby, aria-invalid; error has role=alert. 48 px controls. `useField()` for custom controls. A link in `labelEnd` is tabbed BEFORE its control: when it belongs after it ("Forgot password?"), render it after the Field in the same grid cell (`routes/auth/login.tsx`). |
| Alert | `ui/alert` | `tone` error (role=alert) · info (role=status). Form-level messages; keep `data-testid="form-error"` on auth forms. |
| Panel, PanelHeader | `ui/panel` | `<Panel tone="line|brass" nodes flush asChild>`; `<PanelHeader title sub end titleAs>`. Never nest panels. |
| Dialog, Sheet | `ui/dialog` | Radix Dialog parts (`DialogContent hideClose`, Header, Title, Description, Footer). `SheetContent side="bottom|start|end"`. |
| AlertDialog | `ui/alert-dialog` | confirmations; `AlertDialogAction variant="danger"`. |
| DropdownMenu | `ui/dropdown-menu` | Content, Item, CheckboxItem, RadioGroup/RadioItem (lozenge mark), Label, Separator. Keep trigger aria-labels/testids. |
| Popover | `ui/popover` | `PopoverContent arrow`. Word meanings, prayer times. |
| Tabs | `ui/tabs` | segmented strip (the lobby game picker): `TabsList`, `TabsTrigger`, `TabsContent`. |
| Select | `ui/select` | `SelectTrigger` (48 px, pass Field's id), `SelectContent`, `SelectItem`. |
| Switch, Checkbox | `ui/switch`, `ui/checkbox` | Radix; lozenge thumb; 44 px hit areas. |
| Chip, Badge | `ui/chip` | `<Chip tone="neutral|brass|ember|outline" mark={<TeamGlyph/>|<Lozenge/>} swatch="teeth|ayn|plain|goat|madd">`; `<Badge tone>` 22 px tabular count. |
| Avatar | `ui/avatar` | `<Avatar name src size ring>`: real photo or initials (any script). `initialsOf()`. |
| Separator | `ui/separator` | `variant="brass"` (rule + lozenge, default) · `"line"`; vertical is plain. |
| Skeleton | `ui/skeleton` | bare warp, still. No shimmer. |
| EmptyState | `ui/empty-state` | `title description action mark titleAs`. No illustration. |
| Progress | `ui/progress` | brass on a 4 px line, 0–100 (challenges, achievements; not time). |
| Toaster | `ui/toaster` | already mounted in `__root.tsx`. Toasts only for the result of the player's own action. |

## 6. Brand components (`@/components/brand`)

| Component | API | Notes |
|---|---|---|
| `Wordmark` | `size` (px or CSS length) `stretch` (em number, or a CSS length such as `var(--hero-stretch)`) `woven` `label` | Live text with the woven kashida (≥ 80 px) or ink kashida + madder thread (< 80). Colour = currentColor. On phones size it with `clamp()`; it must not overflow 390 px. |
| `Lockup` | `size` (px or CSS length, e.g. `var(--lockup-size)`) `compactOnMobile` | wordmark │ MAJLISNA (Marcellus spaced caps), colour `--lockup`. |
| `SaduBand` | `variant` madd·teeth·ayn·goat·plain·khayt, `height` | One thick band per screen. `madd` follows the light. `khayt` is reserved for the clock. Never under text. |
| `Lozenge` | `state` host·ready·brass·ink·away·spectator·open·you·madder·undyed·seal, `size`, `label` | The only geometry: bullets, seats, nodes, legends. |
| `TeamGlyph` | `team` madder (▲ tooth) · indigo (◆ eye) · bystander · assassin, `size`, `label` | Always next to a team colour. |
| `Seal` | `size pressed progress ground title caption` | Pressed once (330 ms) then still. `progress` draws the lawh's hold ring. |
| `ThreadClock` | `remaining total label hideTime` | Pure display. Thread contracts; 5 brass lozenges stamped in the last 5 s; knot at 0. NEVER red. Live region speaks at 30/10/5 s only. |
| `PhaseTimer` (`components/games/shared/PhaseTimer`) | props `timerStartedAt durationSeconds onExpired className`, plus `paused` and `frozenRemaining` (the prayer pause) | Ticks + fires `onExpired` once per window (see front/CLAUDE.md), renders ThreadClock. |
| `Halqa` | `seats[{id,name,sub,state,me}] capacity quorum center{code,label}|{count,label}|{node} openLabel dir label fontSize radius padX padY` | Host at the ṣadr; fills clockwise LTR, anticlockwise RTL; ring closes at quorum. Keep the real player list in the DOM; the ring is a picture. `padX`/`padY` tighten the label room so the ring fills its box (the home card uses the sketch's 340 × 300: `fontSize 17, padX 66, padY 46`; 72/68 when seats carry a second line). |
| `CodeTiles` | `value label length kind="code|pin" size="sm|md|lg"` | Display (lobby). Always LTR. |
| `CodeTilesInput` | `value onChange length label id split charset="alnum|digits" kind size cellLabel autoFocus invalid describedBy` | Single mode = one real input (keeps `id="room-code"`); split mode = one input per tile (keep `cellLabel={(i) => \`Password digit ${i + 1}\`}`). Paste fills, Backspace steps back. |
| `ArchFrame` | `photo children` | Qandil's pointed arch, double brass hairline, three nodes, Jabreen duotone. Proportions in units of its own width (max 560 px): springers at 48 %, the card's top at 58 % below 1100 px (the photograph a full band above the card) and at 34 % from 1100 px, where the card rises into the arch's head and the photograph is the niche's cap (~180 px instead of ~300 at 1440 × 900), so the colophon opens above the fold and the Codenames colophon column ends above the board's. Never removed, never rounded. |
| `Colophon` | `title titleAs summary meta words[{word,translit,note,meaning,action}] seals[{title,caption}] actions children arch` | The single game-over surface for all four games. Title is an h2: keep "Game Over" reachable for E2E. Achievements arrive here as seals (one per achievement, captioned with everyone who earned it: `useAchievementSeals`), never as mid-game toasts. Slots: `summary` (one sentence on how it ended), `meta` (`ColophonMeta`: game · host's majlis · count · duration, "Undercover · Yusuf’s majlis · 3 rounds · 21:40", from the state's `host_username`/`started_at`/`ended_at`, `num` on figures), `words` (Amiri word, Latin form + `note`, `meaning`, and an end `action`: the notebook's keep toggle), `seals`, `actions` (`ColophonActions`, the same in the four games: "Keep the words" (primary while some word is not kept), "Back to the room" (primary when there is nothing to keep), the host's "Play again" (secondary), "Leave the room" (ghost, logout mark; `room.lobbyPage.leave`, the one label of every leave)), `children` (scoreboard, vote history). `ColophonWordList` sets the same rows elsewhere (Kalimat lists its words after the final scores). A row with a keep toggle stacks (Arabic + toggle, then the word and its meaning) only when the list is under 384 px (a phone): px, not rem, or Arabic's 110 % rem stacks the desktop Codenames list too. On wide screens the Codenames colophon is a 520 px column beside the board and lists what it always did (the turned words, then "The other N words on the board" folded). |

## 6b. The shell and the home (built)

- **Nav** (`layout/main-nav.tsx`): lockup · Play (/) Rooms Challenges Leaderboard About · prayer
  chip (next prayer + its time, 24 h, Western digits; the day's times, Tahajjud and the city in a
  popover) · EN FR ع (one tap, a `role=group` named "Switch language", each button named by its
  endonym) · theme toggle · Log in / Register, or the account menu (`user-menu-trigger`). Sticky.
  No ground over the home sky until the page scrolls (`data-over-sky`), espresso + grain
  everywhere else, Qandil's rule under it. At ≤ 1180 px everything moves into a "Menu" sheet
  (`side="end"`), whose page links add the word of the day (`/today`) after Play. Breakpoint visibility is done with Tailwind classes in the markup, never in
  shell.css (a utility in a later layer would beat it).
- **Footer** (`layout/footer.tsx`): a quiet colophon (lockup, one line, pages incl. `/today`,
  `/credits` and `/privacy`,
  the two charities (not on `/` nor `/about`, whose own sections name them), the maker, small
  print).
  Not rendered on `/game/*`.
- **Credits** (`routes/credits.tsx`): the visible attribution the CC BY-SA images require
  (title, author, source, licence, what we changed, where it appears) for the skies
  (`public/sky/`, also `og-image.png`) and the Jabreen arch, then the typefaces (OFL) and Lucide
  (ISC). Any new third-party image must be added there before it ships.
- **Privacy** (`routes/privacy.tsx`): a Read page on the About rails: title, date and lede, the
  brass rule, then one hairline-separated section per `privacy.sections` entry (title on the
  start rail in `type-title` 24 px, text at ≤ 60 ch in `type-body`; several paragraphs read as
  a list behind 6 px brass lozenges set one line high, lead terms in Readex 500), the contact
  address in brass at the end.
- **How the games play** (`components/about/GameRules.tsx`, on `/about`): one block per game
  with the ids `undercover`, `codenames`, `kalimat`, `quiz`, the targets of the fihrist's
  "How it plays" links; `scroll-margin` clears the sticky nav.
- **Page width**: nothing clips the page sideways (no `overflow-x` on `html`/`body`): content
  that does not fit at 390 px must wrap (the lobby picker is 2 × 2 on phones), and an entrance
  never travels sideways (in Arabic a card waiting at `x: -20` sits past the start edge and the
  whole page scrolls). The home hero clips its own sky (`.home-hero { overflow: hidden }`).
- **Home** (`routes/index.tsx` → `components/home/*`): the hero is pulled up under the sticky
  nav by one nav height; one `<picture>` per light (≤ 760 px 800/1000, 761–1100 px tab1600,
  above 1600/2400), preloaded for the stored light by the inline script in `index.html` (keep
  the two in sync); the CSS ground starts on the image's last row. The title follows the light
  (`useResolvedTheme`). The join row hands code + PIN to `/rooms/join` (through the login when
  needed). The halqa card is the player's real room when they are seated in one, otherwise a
  captioned example. Then the word of the day card (`DailyWordCard`: a brass-hairline panel with
  nodes; كلمة اليوم in Amiri brass over the Latin name in Marcellus, the number and theme, one
  rung — hint 1 worth 6, or for a player under way the hint they reached at its worth now
  ("Continue today’s word") — and once over how it went ("You found it · 4 points" or "You gave
  up today’s word"), the way to `/today`; one row from 1101 px, stacked below), the four
  games (fihrist) and the charities.
- `useResolvedTheme()` (`hooks/use-resolved-theme.ts`) reads `<html data-theme>`: use it when
  markup, not only colour, changes with the light.

## 6c. Rooms, games and the notebook (built)

| Component | Where | What it is |
|---|---|---|
| `PlayerRoster` | `components/rooms/PlayerRoster.tsx` | The real list behind the halqa (the ring is a picture): "Players (N)", one row per seat with its state lozenge, the full name, the host's Remove. An away seat says how long it is kept ("away · 9:58", on the ring and in the legend too), counted down from the server's `away_seconds_left`. Seats keep first-seen order (`stableOrder`, `rooms/lobby.ts`). Arrivals and departures are a status line, never toasts. E2E reads its exact row shape. |
| `Lawh` | `components/games/undercover/Lawh.tsx` | The tablet that carries a word. At rest bare warp + a brass seal, the word NOT in the DOM; press and hold (pointer, Space/Enter) fills the seal's ring (240 ms) and writes the word in its reading direction; letting go fades it (a fade, never a sweep: some words are sacred names). "I can't hold: show until I hide it" pins it open. Same tablet for every role: Civilians and Undercovers are not told their side; Mr. White's says he has no word. Roles show on elimination (`Verdict`) and at game over. |
| `ScoreBands` | `components/games/mcqquiz/ScoreBands.tsx` | The Quiz's rule as a picture: +3 first quarter of the clock, +2 middle half, +1 last quarter (`bandFor`, mirrors the server). Before answering, the current band is brass and says "now"; once locked, a thread runs to the moment you answered with a lozenge on it ("locked in at 0:09", the server's `my_answer_time_ms` once revealed). A sentence says the same for screen readers. At the reveal each choice says how many chose it (`choice_tallies`: "1 player", "you and 2 others", "+2 · you"). |
| `LastRoundCard` | `components/games/wordquiz/LastRoundCard.tsx` | Kalimat, under the answer row: "Last round · Maryam wrote زكريّا · right at hint 5 · +5", from the results phase (`typed_answer`), kept in the tab for a reload. Arabic in Aref Ruqaa. The header names the theme ("Round 3 of 7 · a prophet", `category`). |
| `HintDisplay` (the hint ladder) | `components/games/wordquiz/HintDisplay.tsx` | Kalimat's ladder: one rung per hint of the FULL ladder (`max_hints`, never the prefix held), vaguest on top. Each rung's lozenge carries its worth (6 → 1); passed rungs strike their worth and recede, the rung in play is brass and says "now", hidden rungs are bare warp and the next says when it arrives. New hints are written in. The word of the day passes `offer` (its next rung holds "Another hint: 5 points instead of 6" instead of warp: words, never an arrow glyph, §9), `nowTag` ("found") and `settled` (given up: nothing in play). |
| `DailyWordPage`, `DailyReveal`, `DailyCountdown` | `components/daily/`, `routes/today.tsx` | The word of the day (كلمة اليوم), a Read-width column (42 rem): the Arabic name in Amiri brass over the Latin in Marcellus (the Arabic UI: the Arabic alone), "#2 · Thursday 29 October 2026 · a place" (Western digits, Makkah date), the lede. One panel: the question for the theme ("Who is it?"), "Worth 6 points now", the ladder with its offer, Kalimat's answer field (a wrong try opens the next rung and its error names it; the field stops at the server's 100 characters), the tries (Arabic in Aref Ruqaa, the right one brass), Give up behind an `AlertDialog`; under it "N players found it today" and the countdown. Once over, the reveal is a colophon in the `ArchFrame` (the arch's second use): the Arabic word large in Amiri (vocalised when known), the word, its explanation, "found at hint 3 · 4 points" with a seal pressed once (the screen's one authored moment) or "given up", the two streaks as Readex figures, Keep in your kunnash, Share (a plain line, never the answer), the countdown, the madd band (the screen's one band); the ladder as played follows in its own panel. Focus goes to the new hint, and to the reveal's title after a right guess or a give-up. Signed out: hint 1 and "Sign in to play". |
| `PlayerScoreboard`, `QuizGameOver`, `RoundAdvanceButton` | `components/games/shared/` | Both quizzes. The Quiz's server holds the scores back while a question is open (totals from before the round); a lozenge says who answered, never what. The host advances, others mark ready; the line under the button says where the table stands. |
| `PauseLayer` / `PauseVeil`, `PauseControl`, `AdhanSuggestion` | `components/games/shared/prayer-pause/` | The prayer pause (وقفة الصلاة). The veil lies over the game (made `inert`): why ("The majlis pauses for ṣalāh"), who paused and for how long (minutes, not a live region), the clock stopped as a still thread, Resume or who may resume and from when; the Arabic name is the title's echo UNDER it, and the veil carries no band (the lawh's is the screen's one). Takes focus only if focus was in the game; lifting it says "The game resumes" once and returns focus. `PauseControl` is a quiet secondary hairline in the header: the host's Pause while the game runs, nothing while paused (the veil carries the one Resume; the header's showed through it as an unpressable ghost). `AdhanSuggestion` is the host's one-time strip when a prayer time arrives ("It's ʿAṣr. Pause the majlis for ṣalāh?"): no toast, no modal, takes no focus. |
| `KeepWordsAction`, `KeepAction`, `KeepWordToggle`, `GameWordsList` | `components/notebook/KeepWords.tsx` | The colophon's notebook slots: "Keep the words" (brass primary while some word is not kept, then "Kept in your kunnash", a link; focus follows; `KeepAction` is that pattern on its own, which the word of the day labels "Keep in your kunnash"), the per-word bookmark toggle (`aria-pressed`, names its word) in each word row's `action`, and the word list read from the notebook for Kalimat. Nothing for spectators or the MCQ quiz (no words). |
| `NotebookEntryRow`, `/notebook` | `components/notebook/`, `routes/_auth/notebook.tsx` | The Kunnash (الكُنّاش): kept words newest first, runs from one game under one heading (game, day). Each entry reads like a dictionary: Arabic headword large in Amiri (vocalised when known), the word as its game showed it in the interface language (no transliteration in the Arabic UI), the meaning at a reading measure, an eraser with an undo window (focus moves to Undo and back). Loads more as the reader nears the end, and on "Show more words". |
| `RoomInviteStrip` | `components/rooms/RoomInviteStrip.tsx` | A friend's invite, a quiet brass-hairline strip under the nav on any signed-in page but a game ("Yusuf invites you to their majlis" [Join] [Not now]), polite, takes no focus. Never a toast: the player did not cause it. Being removed by the host is likewise an inline `Alert tone="info"` on /rooms (`lib/room-notice`), not a toast. |
| `ClueAnnouncer` | `components/games/codenames/CluePanel.tsx` | Codenames: a polite, always-mounted status that reads a new clue out once ("Clue for the Red team: KNOWLEDGE, 2"); the header's live line only says whose turn it is. |

## 7. Motion

Grammar (from the motion playbook): one place (the circle), three gestures (write, erase, seal).

- Durations: tap 90 ms · state 180 · move 320 · authored 640 · ceremony 1100 (once per game).
  Exits = 0.66 × entry on `--ease-in`. Tokens: `--dur-*`, `--ease-out|in|ink|settle|press`;
  `lib/motion.ts` exports `ease`, `dur`, `t`, `exit()`, `stagger()`, `inkDuration()`, and variants
  `write` (custom = "ltr"|"rtl"), `erase`, `seal`, `stamp`, `seatArrive`, `arrive`, `fade`.
- CSS: `ink` (mask-write in the reading direction, visible by default), `seal-press`,
  `animate-fade-in`, `animate-loz-stamp`.
- One authored moment per screen; ≤ 3 other moving things; no loop except the visible clock; no
  hover lift, float, glow, pulse, bounce, confetti, or shimmer. Nothing ever passes over a sacred
  name (strike the option letter, not the word).
- Truth first: the final state is in the DOM on the first frame; motion only sequences reading.
- Route changes do not animate (the old `AnimatePresence mode="wait"` blank was removed). For a
  phase change use `withViewTransition(() => setPhase(x))` or
  `const phase = useViewTransitionValue(state.phase)` (feature-detected, no-op otherwise, 180 ms).
  Never wrap a phase in `AnimatePresence mode="wait"`.
- Reduced motion: `<MotionConfig reducedMotion="user">` is at the root (transforms dropped,
  opacity kept); CSS twins switch to short fades; the clock steps per second. Holding the lawh to
  read still works. Sheets, dialogs, popovers and menus (`[data-slot$="-content"]`) lose their
  tw-animate slide and zoom and only fade (index.css).

## 8. RTL

- `dir`/`lang` are set on `<html>`. Logical properties only (`ms-`, `me-`, `ps-`, `pe-`,
  `start-`, `end-`, `border-s`, `text-start`). Mirror directional icons with `rtl-flip`.
- Reading-start anchors: the clock thread and band weaving start right in Arabic; the halqa fills
  anticlockwise; the arrow on "Start" points left.
- Always LTR, even in Arabic: room codes, PINs, clocks, scores (`CodeTiles` handles it).
- The kashida word is always in its own `dir="rtl"` (the Wordmark does it).
- Arabic interface: no transliteration; abjad (أ ب ج د) for choice letters.

## 9. Imagery and ornament (owner decisions, binding)

- Home: one pre-composed sky (night / afternoon), full-bleed at every width (390–3440 px), the
  mesas never cut; the giant مجلسنا lies on the horizon, its kashida woven. Sky files and their
  CC BY-SA 4.0 credit come with the home work.
- Game-over: the arch over the Jabreen duotone (CC BY-SA 2.0, credit in `SOURCES.txt`). The word
  of the day's reveal is the same colophon in the same arch.
- NEVER: floating decorative objects (lantern, dallah, stars, ornaments), collage heroes, photos
  in the games list, women or faces (the creator's portrait on About is the one exception, owner
  decision), Qur'anic text or the name of Allah as decoration, crescents,
  domes or minarets as logos, multicolour palettes, walls of coloured game tiles, emoji or Unicode
  glyphs as icons. The lozenge is the only geometry.
- Icons: lucide at 1.6 px stroke (set globally), one family.

## 10. Game names

| | EN | FR | AR |
|---|---|---|---|
| Undercover | Undercover | Undercover | أندركفر |
| Codenames | Codenames | Codenames | كودنيمز |
| Word Quiz | Kalimat | Kalimat | كلمات |
| MCQ Quiz | The Quiz | Le Quiz | مسائل |

Keys: `games.{undercover,codenames,wordQuiz,mcqQuiz}.name`. In the games list the Arabic name is
large in Amiri brass (`type-arabic-name`), the Latin name under it in Marcellus.

That large name (`home.fihrist.*.arabic`, the same string in the three locales) carries ONE
kashida, at a join Naskh allows (F. S. Afifi, *Learning Arabic Calligraphy* III; Benatia,
Elyaakoubi & Lazrek, TUGboat 27:2, 2006; W3C alreq: one stretched join per word): never after a
letter that does not join forward, nor after ك or ل; never before ص ع و ه, the ح family, ف or
ق. Hence أندركفـــر (fa → ra: after the kaf and before the fa it broke two rules), كودنيـــمز
(ya → mim), كلمـــات (mim → alif, the one join the word allows), مســـائل (after the seen, the
classic stretch). `components/stats/__tests__/locales.test.ts` checks it. In running text a
name keeps its exact form: «وكلمات ومسائل», never «والمسائل».

Roles keep the game's English names in every language (owner decision), never translated:
French writes them as English does, Arabic writes them phonetically.

| Role | EN | FR | AR | AR collective / "as a …" |
|---|---|---|---|---|
| Civilian | Civilian | Civilian | سيفيليان | السيفيليان · كسيفيليان |
| Undercover | Undercover | Undercover | أندركفر | الأندركفر · كأندركفر |
| Mr. White | Mr. White | Mr. White | مستر وايت | — · كمستر وايت |
| Spymaster | Spymaster | Spymaster | سبايماستر | السبايماستر |
| Operative | Operative | Operative | أوبريتيف | الأوبريتيف |

Write a loanword's plural as the collective with the article ("فاز الأندركفر", "فاز
السيفيليان"), never as a broken or sound plural ("المتخفّون", "المدنيون", "الجواسيس", "العملاء"
are the old translations: do not use them). French takes the English plural, capitalised like a
name (« les Civilians », « les Spymasters », « en tant qu’Undercover »); Infiltré, Maître-espion,
Civil and Agent-as-a-role are the old translations. The side that wins with Mr. White is « les
imposteurs » / "the impostors": a side, not a role, so it is translated (« les agents » are the
cards, as in English).

Codenames teams are the plain colour, as in the original game (owner decision): Red / Blue,
Rouge / Bleue, الأحمر / الأزرق (`game.codenames.teams.red|blue`). A colour is an ordinary word,
not one of the game's names, so it is translated, not transliterated. Sentences carry the word
"team" themselves: "the {{team}} team", « l’équipe {{team}} », «الفريق {{team}}». Madder and
indigo stay the names of the dyes (tokens, selvedges), never of the teams.

Arabic copy, house rules (`locales.test.ts` checks the first two): Western digits ("البخاري
1145", never ١١٤٥); the tanwin fath on the letter before its alif, as in the Mushaf ("مجددًا",
"رابطًا", never "مجدداً"); giving up the word of the day is انسحب, never استسلم; a streak is a سلسلة («سلسلتك»,
«أطول سلسلة», «سلسلة أيامك»), never «أيامك المتتالية» as a label; a count goes
through the plural keys or a label ("الفوز: 3"), never a bare "3 فوز".

## 11. No compatibility layer

Every page is built on §5–6. The temporary `styles/compat.css` (re-dyed Tailwind palette,
neutralised `.glass`, `.gradient-text`, `.card-hover`, looping `animate-*`, flat gradient fills,
neutral coloured shadows, borders for raw inputs) was deleted on 2026-10-28 once nothing used it:
every page, captured in both lights before and after, was pixel-identical. Nothing shims the old
habits any more, so none of them may come back: no Tailwind palette colours (`text-red-500`,
`bg-blue-600`, `emerald`, `amber`, `purple`, `gray`…), no `glass`, `backdrop-blur`,
`gradient-text`, `bg-gradient-to-*`, `shadow-primary/*`, `bg-glow`, `card-hover`, no looping or
travelling `animate-*`, no `font-mono` (use `num`). A raw `<input>` gets no border for free: use
`ui/field` or `border-line-field`.

## 12. Do / Don't

Do: brass for what is yours to act on · one band per screen · hairline panels · Readex for every
figure · glyph + colour for teams · say why a button is disabled · errors that name the repair ·
keep every E2E hook (`user-menu-trigger`, "View profile and more", "Switch language",
`codenames-board`, `codenames-card`, `form-error`, `elimination-overlay`, `you-are-eliminated`,
`leaderboard`, ids `email`/`password`/`username`/`room-code`, "Password digit N", h2 "Game Over").

Don't: red timers or pulsing urgency · gradients, glass, glow, coloured shadows · cards in cards ·
eyebrow labels · Marcellus for numbers or for words with ḥ ṣ ʿ ā · letter-spaced Arabic ·
toasts for game events · new font or image hosts (the CSP is enforced) · hand-edit
`src/api/generated` or `styles/sadu.css`.
