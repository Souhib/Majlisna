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
first paint. The choices are the afternoon, the night, "Follow the sky" (night from Maghrib to
sunrise in the stored prayer-times city, §7) and, until the player chooses, the device's light.
Any element can re-theme its subtree with its own `data-theme` (then give it
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
| `Wordmark` | `size` (px or CSS length) `stretch` (em number, or a CSS length such as `var(--hero-stretch)`) `woven` `weave` `label` | Live text with the woven kashida (≥ 80 px) or ink kashida + madder thread (< 80); the woven band is its own `.k-band` in the kashida's clip. `weave` (the home's name only) weaves it in once per session (§7). Colour = currentColor. On phones size it with `clamp()`; it must not overflow 390 px. |
| `Lockup` | `size` (px or CSS length, e.g. `var(--lockup-size)`) `compactOnMobile` | wordmark │ MAJLISNA (Marcellus spaced caps), colour `--lockup`. |
| `SaduBand` | `variant` madd·teeth·ayn·goat·plain·khayt, `height` | One thick band per screen. `madd` follows the light. `khayt` is reserved for the clock. Never under text. |
| `Lozenge` | `state` host·ready·brass·ink·away·spectator·open·you·madder·undyed·seal, `size`, `label` | The only geometry: bullets, seats, nodes, legends. |
| `TeamGlyph` | `team` madder (▲ tooth) · indigo (◆ eye) · bystander · assassin, `size`, `label` | Always next to a team colour. |
| `Seal` | `size pressed index progress ground title caption` | Pressed once (330 ms) then still. `index` (its place in a set: the colophon passes it) waits for the phase crossfade and staggers the press. `progress` draws the lawh's hold ring. |
| `ThreadClock` | `remaining total label hideTime`, plus `startedAt durationMs paused` (the loom) | Pure display. The thread is drawn back through the loom at the reading start: full length in a clipped track, placed by a `transform` (never its width), ONE Web Animation per phase segment from `startedAt` + `durationMs` (re-created only when they change), paused and played for the prayer pause. Without them, or under reduced motion, it steps once a second from `--left`. 14 px stub and 5 brass lozenges stamped in the last 5 s; knot pressed at 0. NEVER red. Live region speaks at 30/10/5 s only. |
| `PhaseTimer` (`components/games/shared/PhaseTimer`) | props `timerStartedAt durationSeconds onExpired className`, plus `paused` and `frozenRemaining` (the prayer pause) | Ticks + fires `onExpired` once per window (see front/CLAUDE.md), renders ThreadClock. |
| `Halqa` | `seats[{id,name,sub,state,me}] capacity quorum center{code,label}|{count,label}|{node} openLabel dir label fontSize radius padX padY` | Host at the ṣadr; fills clockwise LTR, anticlockwise RTL; ring closes at quorum. Keep the real player list in the DOM; the ring is a picture. `padX`/`padY` tighten the label room so the ring fills its box (the home card uses the sketch's 340 × 300: `fontSize 17, padX 66, padY 46`; 72/68 when seats carry a second line). |
| `CodeTiles` | `value label length kind="code|pin" size="sm|md|lg"` | Display (lobby). Always LTR. |
| `CodeTilesInput` | `value onChange length label id split charset="alnum|digits" kind size cellLabel autoFocus invalid describedBy` | Single mode = one real input (keeps `id="room-code"`); split mode = one input per tile (keep `cellLabel={(i) => \`Password digit ${i + 1}\`}`). Paste fills, Backspace steps back. |
| `ArchFrame` | `photo children` | Qandil's pointed arch, double brass hairline, three nodes, Jabreen duotone. Proportions in units of its own width (max 560 px): springers at 48 %, the card's top at 58 % below 1100 px (the photograph a full band above the card) and at 34 % from 1100 px, where the card rises into the arch's head and the photograph is the niche's cap (~180 px instead of ~300 at 1440 × 900), so the colophon opens above the fold and the Codenames colophon column ends above the board's. Never removed, never rounded. |
| `Colophon` | `title titleAs summary meta words[{word,translit,note,meaning,action}] seals[{title,caption}] actions children arch` | The single game-over surface for all four games. Title is an h2: keep "Game Over" reachable for E2E. Achievements arrive here as seals (one per achievement, captioned with everyone who earned it: `useAchievementSeals`), never as mid-game toasts. Slots: `summary` (one sentence on how it ended), `meta` (`ColophonMeta`: game · host's majlis · count · duration, "Undercover · Yusuf’s majlis · 3 rounds · 21:40", from the state's `host_username`/`started_at`/`ended_at`, `num` on figures), `words` (Amiri word, Latin form + `note`, `meaning`, and an end `action`: the notebook's keep toggle), `seals`, `actions` (`ColophonActions`, the same in the four games: "Keep the words" (primary while some word is not kept), "Back to the room" (primary when there is nothing to keep), the host's "Play again" (secondary), "Share" (secondary, a player's only: the colophon card, below), "Leave the room" (ghost, logout mark; `room.lobbyPage.leave`, the one label of every leave)), `children` (scoreboard, vote history). `ColophonWordList` sets the same rows elsewhere (Kalimat lists its words after the final scores). A row with a keep toggle stacks (Arabic + toggle, then the word and its meaning) only when the list is under 384 px (a phone): px, not rem, or Arabic's 110 % rem stacks the desktop Codenames list too. On wide screens the Codenames colophon is a 520 px column beside the board and lists what it always did (the turned words, then "The other N words on the board" folded). |
| `ShareCardAction` (`brand/share-card/`) | `copy line title fileName card fieldId` | The colophon card: a 1080 × 1350 PNG of the evening, always under the night's light (the samar), whatever the light on screen. Qandil's arch as its double brass hairline with its three nodes (ArchFrame's geometry, no photograph), the game's Arabic name large in Amiri brass (the games list's form, one kashida; كلمة اليوم for the day), the Latin name in Marcellus (none in the Arabic UI), the colophon's meta line in Readex (one or two lines, split at a separator), the brass rule, then: a game's words (public once it is over: the notebook's read, a grid filled from the reading start, 1 to 5 columns, 25 cells at most, the last saying how many more), each in Amiri with its form in the interface language under it, clear of Amiri's tails; a game without words (the Quiz) sets its head in the middle of the arch; the word of the day NEVER its word, a hint or a guess, only the ladder as a woven strip (six rungs from the reading start, each lozenge carrying its worth 6 → 1, the rung it was found at in brass, the rungs passed struck, the rest bare warp), "found at hint 3 · 4 points" or "given up", the two streaks. One madd band closes the arch (the band's own tile, cell for cell); `majlisna.app` under it. Colours are tokens only, resolved under `data-theme="dark"`. Shared with `navigator.share({ files, title, text })` when `canShare` says yes; otherwise the plain line is copied (a read-only field when the clipboard is refused). Drawn on the tap, on the device: no request, no CSP entry. A sheet closed says nothing; a browser that wants a fresh tap keeps the card and says "The image is ready: press Share again". A spectator gets no Share (as no Keep). Model `model.ts` (pure draw operations), `render.ts` (canvas), `game-card.ts` / `daily-card.ts` (what it says). |

## 6b. The shell and the home (built)

- **Nav** (`layout/main-nav.tsx`): lockup · Play (/) Rooms Challenges Leaderboard About · prayer
  chip (next prayer + its time, 24 h, Western digits; the day's times, Tahajjud and the city in a
  popover) · EN FR ع (one tap, a `role=group` named "Switch language", each button named by its
  endonym) · theme menu (an icon for the current choice, "Theme: Night"; Afternoon, Night, Follow
  the sky, whose line says when the sky next turns or that no city is chosen; in the menu sheet
  three text segments like the language switch) · Log in / Register, or the account menu
  (`user-menu-trigger`). Sticky.
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
  (`public/sky/`, also `og-image.jpg`) and the Jabreen arch, then the typefaces (OFL) and Lucide
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
  nav by one nav height; one `<picture>` per light (≤ 760 px 800/1000, 761–1100 px tab800/1200/1600,
  above 1600/2400), preloaded for the stored light by the inline script in `index.html` (for
  "Follow the sky", the light its stored turns give; keep the two in sync); following the sky,
  the other light's sky is fetched 10 min before a turn (`useSkyWarmUp`). The giant name's
  kashida is woven once per session (§7); the CSS ground starts on the image's last row. The title follows the light
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
| `PlayerRoster` | `components/rooms/PlayerRoster.tsx` | The real list behind the halqa (the ring is a picture): "Players (N)", one row per seat with its state lozenge, the full name, the host's Remove (behind an `AlertDialog`: a removed player cannot come back to the room until the host lets them, danger action, never a red fill). The host's removed players are `RoomBans` under it (no panel while nobody was removed; "Let {{name}} come back" per row). An away seat says how long it is kept ("away · 9:58", on the ring and in the legend too), counted down from the server's `away_seconds_left`, and recedes (ERASE, §7; restored when the player is back). Seats keep first-seen order (`stableOrder`, `rooms/lobby.ts`). Arrivals and departures are a status line, never toasts. E2E reads its exact row shape. |
| `Lawh` | `components/games/undercover/Lawh.tsx` | The tablet that carries a word. At rest bare warp + a brass seal, the word NOT in the DOM; press and hold (pointer, Space/Enter) fills the seal's ring (240 ms) and writes the word in its reading direction; letting go fades it (a fade, never a sweep: some words are sacred names). "I can't hold: show until I hide it" pins it open. Same tablet for every role: Civilians and Undercovers are not told their side; Mr. White's says he has no word. Roles show on elimination (`Verdict`: the turned tablet, the role's band at its foot, turned over once when the vote resolves on screen, §7) and at game over. |
| `ScoreBands` | `components/games/mcqquiz/ScoreBands.tsx` | The Quiz's rule as a picture: +3 first quarter of the clock, +2 middle half, +1 last quarter (`bandFor`, mirrors the server). Before answering, the current band is brass and says "now"; once locked, a thread runs to the moment you answered with a lozenge on it ("locked in at 0:09", the server's `my_answer_time_ms` once revealed). A sentence says the same for screen readers. At the reveal each choice says how many chose it (`choice_tallies`: "1 player", "you and 2 others", "+2 · you"). |
| `LastRoundCard` | `components/games/wordquiz/LastRoundCard.tsx` | Kalimat, under the answer row: "Last round · Maryam wrote زكريّا · right at hint 5 · +5", from the results phase (`typed_answer`), kept in the tab for a reload. Arabic in Aref Ruqaa. The header names the theme ("Round 3 of 7 · a prophet", `category`). |
| `HintDisplay` (the hint ladder) | `components/games/wordquiz/HintDisplay.tsx` | Kalimat's ladder: one rung per hint of the FULL ladder (`max_hints`, never the prefix held), vaguest on top. Each rung's lozenge carries its worth (6 → 1); passed rungs strike their worth and recede, the rung in play is brass and says "now", hidden rungs are bare warp and the next says when it arrives. New hints are written in. The word of the day passes `offer` (its next rung holds "Another hint: 5 points instead of 6" instead of warp: words, never an arrow glyph, §9), `nowTag` ("found") and `settled` (given up: nothing in play). |
| `DailyWordPage`, `DailyReveal`, `DailyCountdown` | `components/daily/`, `routes/today.tsx` | The word of the day (كلمة اليوم), a Read-width column (42 rem): the Arabic name in Amiri brass over the Latin in Marcellus (the Arabic UI: the Arabic alone), "#2 · Thursday 29 October 2026 · a place" (Western digits, Makkah date), the lede. One panel: the question for the theme ("Who is it?"), "Worth 6 points now", the ladder with its offer, Kalimat's answer field (a wrong try opens the next rung and its error names it; the field stops at the server's 100 characters), the tries (Arabic in Aref Ruqaa, the right one brass), Give up behind an `AlertDialog`; under it "N players found it today" and the countdown. Once over, the reveal is a colophon in the `ArchFrame` (the arch's second use): the Arabic word large in Amiri (vocalised when known), the word, its explanation, "found at hint 3 · 4 points" with a seal pressed once (the screen's one authored moment) or "given up", the two streaks as Readex figures, Keep in your kunnash, Share (the day's card, never the word: below; the plain line where an image cannot be shared), the countdown, the madd band (the screen's one band); the ladder as played follows in its own panel. Focus goes to the new hint, and to the reveal's title after a right guess or a give-up. Signed out: hint 1 and "Sign in to play". |
| `PlayerScoreboard`, `QuizGameOver`, `RoundAdvanceButton` | `components/games/shared/` | Both quizzes. The Quiz's server holds the scores back while a question is open (totals from before the round); a lozenge says who answered, never what. Each row carries its thread (the share of `maxScore`, the viewer's in madd) and the round's gain, and the table weaves when the totals change (§7). The host advances, others mark ready; the line under the button says where the table stands. |
| `PauseLayer` / `PauseVeil`, `PauseControl`, `AdhanSuggestion` | `components/games/shared/prayer-pause/` | The prayer pause (وقفة الصلاة). The veil lies over the game (made `inert`): why ("The majlis pauses for ṣalāh"), who paused and for how long (minutes, not a live region), the clock stopped as a still thread, Resume or who may resume and from when; the Arabic name is the title's echo UNDER it, and the veil carries no band (the lawh's is the screen's one). Takes focus only if focus was in the game; lifting it says "The game resumes" once and returns focus. `PauseControl` is a quiet secondary hairline in the header: the host's Pause while the game runs, nothing while paused (the veil carries the one Resume; the header's showed through it as an unpressable ghost). `AdhanSuggestion` is the host's one-time strip when a prayer time arrives ("It's ʿAṣr. Pause the majlis for ṣalāh?"): no toast, no modal, takes no focus. |
| `KeepWordsAction`, `KeepAction`, `KeepWordToggle`, `GameWordsList` | `components/notebook/KeepWords.tsx` | The colophon's notebook slots: "Keep the words" (brass primary while some word is not kept, then "Kept in your kunnash", a link; focus follows; `KeepAction` is that pattern on its own, which the word of the day labels "Keep in your kunnash"), the per-word bookmark toggle (`aria-pressed`, names its word) in each word row's `action`, and the word list read from the notebook for Kalimat. Nothing for spectators or the MCQ quiz (no words). |
| `NotebookEntryRow`, `/notebook` | `components/notebook/`, `routes/_auth/notebook.tsx` | The Kunnash (الكُنّاش): kept words newest first, runs from one game under one heading (game, day). Each entry reads like a dictionary: Arabic headword large in Amiri (vocalised when known), the word as its game showed it in the interface language (no transliteration in the Arabic UI), the meaning at a reading measure, an eraser with an undo window (focus moves to Undo and back). Loads more as the reader nears the end, and on "Show more words". |
| `RoomInviteStrip` | `components/rooms/RoomInviteStrip.tsx` | A friend's invite, a quiet brass-hairline strip under the nav on any signed-in page but a game ("Yusuf invites you to their majlis" [Join] [Not now]), polite, takes no focus. Never a toast: the player did not cause it. Being removed by the host is likewise an inline `Alert tone="info"` on /rooms (`lib/room-notice`), not a toast. |
| `ClueAnnouncer` | `components/games/codenames/CluePanel.tsx` | Codenames: a polite, always-mounted status that reads a new clue out once ("Clue for the Red team: KNOWLEDGE, 2"); the header's live line only says whose turn it is. It is also the table's witness that a clue has just landed (`clueJustLanded`, for the commit that brings it), which `ClueBanner` reads to write the spymaster's own clue in (§7). |
| `SamarRiddle` | `components/rooms/SamarRiddle.tsx` (rules: `samar-riddle.ts`) | A riddle while the table waits (السَّمَر): in the lobby under the activity line (for everyone while the table is short of its quorum, for every guest and spectator while it waits for the host; never for the host of a ready table), and under The Quiz's results between two questions. "While you wait: who is it?" over rung 1 of a Kalimat word in Amiri (existing content only, `GET /rooms/{id}/riddle`), "The answer in a moment, or after the game." and, 30 s after it was first shown, "Show the answer"; then "It was Ibrahim · إبراهيم" (the Arabic UI: the Arabic alone) and "Another riddle". The game's start answers it at the room's next wait: "The last riddle, “…”, was Ibrahim." (the lobby follows the table at once, so it cannot be read at the start itself). The tab keeps one riddle per room and wait: no request on a remount or a reload. A Kalimat lobby offers no tap (the word could come up in the game), and there is no riddle between Kalimat rounds (its words are drawn round by round). A refusal shows nothing; a bare-warp skeleton holds its place while it loads. No heading (the Quiz's focus target is the reveal's first h3), no live region, no toast. |

## 7. Motion

Grammar (from the motion playbook): one place (the circle), three gestures (write, erase, seal).

- Durations: tap 90 ms · state 180 · move 320 · authored 640 · ceremony 1100 (once per game; and
  the home's kashida woven once per session, the sky's turn of the light).
  Exits = 0.66 × entry on `--ease-in`. Tokens: `--dur-*`, `--ease-out|in|ink|settle|press`,
  `--stagger` (30 ms); `lib/motion.ts` exports only `ease`, `dur` (the tokens as numbers),
  `inkDuration()`, `REREAD`, `stagger` (the `--stagger` step and the 240 ms cap, in seconds),
  `bezier()` (a curve as Web Animations take it) and `erase` (the receded levels, mirroring
  `--erase-ink` / `--erase-mark`) (the motion/react variants were never used and were removed).
- CSS: `ink` (mask-write in the reading direction, visible by default; text only), `seal-press`,
  `animate-fade-in`, `animate-loz-stamp`. Seals pressed as a set (the colophon's, `Seal index`)
  wait for the phase crossfade, then land one by one: `--dur-state + min(i × --stagger, 240 ms)`.
- The gestures as built: the CIRCLE is the halqa's one thread circle (arrival 320 ms
  `--ease-settle`, the quorum closing 640 ms `--ease-ink` with 1.6 → 2.6, departure 211 ms
  `--ease-in`; a new seat's lozenge .25 → 1 once); the clock is the loom (`ThreadClock`);
  woven bands (a turned Codenames card's selvedge, the end veil's band) slide in through a
  clipping box from the reading start. Animate `transform`/`opacity`, never `width`, `height`,
  `left`, a mask or a clip path (in a loop above all), except the `ink` mask on text (which
  repaints every frame: a new writing can use the clue's compositor qalam instead); the thread
  clock is ONE Web Animation on `transform` per timer window (`e2e/tests/perf/thread-clock.spec.ts`
  counts the layouts).
- The kashida woven once (`Wordmark weave`, the home's مجلسنا only): on the first home of a
  session (sessionStorage `majlisna-kashida-woven`, taken at the first commit; a storage that
  cannot be read weaves nothing, as a reload could not be told from a first visit) the madd
  band, a full-length element (`.k-band`) in the kashida's own clip (`.k`, `overflow: hidden`),
  is held out at the right by its own paused animation from the first frame (2 px past the clip's
  end, `translateX(calc(100% + 2px))`: at exactly 100% a fractional clip width left a
  1-device-pixel madder line in the open joint while the face loaded) and woven in once
  the wordmark's face is loaded (`document.fonts.load`, then `fonts.ready`; 3 s at most): ONE
  Web Animation on `transform`, `translateX(100%)` → 0, 1100 ms `--ease-ink`, from the right in
  every interface (the word is Arabic in all three). The letters are drawn from the first frame
  and never move; the band is `aria-hidden`; the sky stays the LCP. Never on a reload, a second
  home in the tab, under reduced motion or without Web Animations: the band then rests in place,
  pixel-identical to before (2 widths × 2 lights × en/ar). Measured on a production build at
  390 and 1440 px, 1× and 4× CPU: composited, no frame over 20 ms and no long task in its
  window; 2 layouts under 1 ms when it starts (resolving the percentage) and 1 when it ends,
  none while it moves. Tests: `components/brand/__tests__/Wordmark.test.tsx`.
- The Quiz's reveal (`ChoiceButtons`): each choice draws its tally as a 3 px khayt thread under
  its words, its share of the players (`choice_tallies` over the players, `tallyShares`); the
  right one is brass, a choice nobody took keeps its bare warp, a wrong pick keeps its struck
  letter. When the reveal happens on screen (never on a load or a reload, never again on a
  refetch) the threads are woven in from the reading start, 640 ms `--ease-ink`, `--stagger`
  apart (CSS: `ul.quiz-choices[data-weave]`, one `quiz-tally` keyframes from `--tally-from`,
  fill backwards), and the
  right letter is pressed as a seal once the crossfade is done (`seal-press` +
  `data-seal-index`). The tag at the end of the row stays the words; the thread is `aria-hidden`.
- Scores, woven (`PlayerScoreboard`, both quizzes): under each name a 6 px thread, the player's
  share of the most the game can give (`maxScore`: rounds × 3 in The Quiz, rounds ×
  `max_hints` in Kalimat), so it only ever grows; the viewer's is the madd band. Beside the
  total, what this round earned ("+3", `current_round_points`), every row keeping the gain's
  slot whether it gained or not, so the totals stay aligned and a first gain (Kalimat,
  mid-round) moves none sideways. When the totals change the list is already in its new order
  (truth first) and each row travels from its old slot (320 ms `--ease-settle`, `--stagger`
  apart, 240 ms at most), then each thread is written longer (640 ms `--ease-ink`, starting
  320 ms later) and the gain fades in after 320 ms: Web Animations on `transform` and `opacity`
  (FLIP; the old place is the old index read in the layout of the moment). The Quiz's totals
  change at the reveal; Kalimat's server sends them as they move, so its table weaves when a
  player finds the word. A first state and the same totals sent again move nothing. At The
  Quiz's reveal the tally threads are the screen's one authored moment: the scoreboard's whole
  weave (rows, threads, gains) waits for them (`PlayerScoreboard weaveAfter` =
  `tallyWeaveMs(choices)`, 730 ms for four), so two weaves never run side by side (review
  RM-2; reduced motion waits for nothing). The rows and the gain rest on an identity
  transform (the gain an inline-block), so neither a row's travel nor the gain's fade lays the
  list out when it ends. Measured on a production build (4 players): all of these composite (the only non-composited
  animations on screen are the browser's own view-transition pseudo-elements), and no frame
  passes 20 ms at 1× or 4× CPU except the phase swap's own render, which is as long with
  reduced motion. Re-measured after RM-2/RM-6/RM-7 (1280 px en and 390 px ar, 1× and 4×): in
  the 1.9 s after the swap 2 layouts of 1–2 objects (≤ 0.9 ms, the riddle under the results)
  against 7 before, 0 under reduced motion; compositor gaps 12–14 ms at 1×, one of 24 ms at
  4× (1280 px, software compositing) when the scoreboard's animations start.
- The Codenames clue is written in, and its count stamped (`ClueBanner`): when a NEW clue is on
  the table (after none or after another; for the spymaster too, whose banner mounts with the
  clue they just gave, which the always-mounted `ClueAnnouncer` reports for that commit only:
  `clueJustLanded`), never on a load, a reload, a refetch or a socket push of the same clue.
  The word is written in its own reading direction (an Arabic clue right to left in any
  interface) in `inkDuration(word)` on `--ease-ink`, by the qalam on the compositor, not the
  `ink` mask sweep: a pen box with a static soft edge at its reading end is translated in from
  one length before the reading start while its ink is translated the other way on the same
  clock, so the letters stand still and the edge writes them. A clue is the spymaster's free
  text and the server refuses only a card's own word, so it may be a sacred name ("Allah",
  «الله», a prophet): such a clue is never written, the pen never passes over it; its word
  fades in over `--dur-state` on `--ease-out` (`holdsSacredName`, `lib/sacred-names.ts`, the
  one list the riddle uses too). Either way, the count is then stamped
  (`loz-stamp` keyframes, 220 ms `--ease-press`, `--dur-tap` apart, fill backwards only while
  waiting): its brass lozenges, 1 to 4, beside the figure on a banner of 480 px or more (a
  container query; on a phone's banner they wrapped the guess column, so the figure alone is
  shown and stamped once), the figure itself for "no limit" (∞). The figure is the text that is
  read; the lozenges are `aria-hidden`. The banner keeps the clue's height reserved at every
  width (`.cn-clue` min-height, from the word's own size; 26.7 px and CLS 0.05 at 1280 px
  before), the faces a clue is set in are asked for while the spymaster chooses (Marcellus;
  the hand too in the Arabic interface), and the moved boxes keep an identity transform so an
  animation's end lays nothing out. Measured on a production build at 390 and 1280 px, en and
  ar, 1× and 4× CPU: every animation composites, no layout during the writing, no layout
  shift from the banner, no horizontal scroll; the one frame over 20 ms at 4× is the commit
  that brings the clue (the page's render and layout), as long with reduced motion.
- The lawh turns over (`Verdict` `turn`, Undercover's round-over screen): the verdict tablet's
  foot is the role's band (madder teeth for an Undercover, undyed for a Civilian, goat-hair for
  Mr. White: a layer inside the band, which clips it). When the vote resolves ON SCREEN (the
  table's list, `DescriptionList`, is still mounted as `RoundOverPanel` first renders:
  `table-witness`), the turn plays once, after the 180 ms crossfade: the bare-warp cover over
  the role chip and the face parts from the reading start (320 ms `--ease-settle`, each a layer
  clipped by its own box, translated to the reading end), the role band is woven in at the foot
  (640 ms `--ease-ink`), the chip's lozenge is pressed (`seal-press`, once the cover has passed).
  CSS on `.uc-verdict[data-turn]`, fill backwards only (every layer rests where it ends). A vote
  that finds Mr. White on screen turns his tablet in the compact verdict everyone else reads
  while he guesses (`MrWhiteGuessPanel`, `verdictTurnNow()`: no band at that foot, so the cover
  parts and the lozenge is pressed). Never on a page loaded on the verdict, a refetch, a socket
  push, nor after Mr. White's guess (his tablet turned with the vote). Your own tablet shows your word: its cover only fades
  (`data-word`), never passes over it. The sentence, the role and the votes are in the DOM from
  the first frame; focus still goes to the verdict title. Measured on a production build
  (4 and 6 players, en and ar, 390 and 1280 px, both lights): every gesture composites, no
  frame over 20 ms in the turn at 1× or 4× CPU, one layout of 0.1 ms when the band's layer
  comes to rest, no horizontal scroll; the crossfade's capture frame (26 ms at 1×, 59 ms at 4×)
  is the same on HEAD.
- ERASE (`hooks/use-seat-erase`): what is finished recedes, never vanishes. An emptied seat
  (Undercover's `DescriptionList` and `UndercoverPlayerList`: `data-out`; the lobby roster's
  away seat: `data-away`) shows its name in ink at `--erase-ink` (.72: the muted token's
  contrast, 6.8:1 by day and 8.4:1 at night; .45 of the ink would be 2.9:1), its lozenge at
  `--erase-mark` (.45), its status line ("Eliminated · Civilian", "away · 9:58") in the muted
  token. A seat that empties ON SCREEN is erased into that state with Web Animations on
  opacity alone: name and lozenge over 640 ms `--ease-ink`, the status faded in over 180 ms; a
  lobby seat whose player comes back returns in 180 ms. Never on the first render, never for
  the same state again. A seat emptied mid-round stays in its place in the speaking order
  (only the seats emptied in earlier rounds wait at the end), and while a voter chooses every
  row keeps a candidate's height, so nothing under the finger moves. The vote's list erases
  nothing once the vote is complete (the verdict tells that seat). A player who leaves the room
  or a Codenames table is no longer in the state: their row goes, never kept as a ghost.
  Measured: opacity animations only, all composited, no row moved, no frame over 20 ms at 1×
  or 4×.
- The samar riddle (`SamarRiddle`, §6c: the lobby while it waits, The Quiz between two
  questions): its line is written in only when it CHANGES ("Another riddle"), never the riddle a
  panel opens on, a reload, a refetch or a push. The same compositor qalam as the clue: a window
  with a static soft edge at its reading end (1.25 em past the line, clipped by the line's box at
  rest) translated in from one length before the reading start while the text inside travels
  the other way, two transforms in step, `inkDuration(hint, "line")` on `--ease-ink`, from the
  right in Arabic. A line naming Allah, the Prophet ﷺ, a prophet, Jibril, the Qur'an or the
  Kaaba is never swept: it fades in over `--dur-state` (`holdsSacredName`, `lib/sacred-names.ts`,
  about a quarter of the rung-1 lines). A line that wraps fades too: the one window would
  uncover all its lines at once, a wipe and not a pen (its line boxes are read once, as the new
  line is about to be written; at 390 px most rungs wrap). The answer (asked for) and the offer to show it (30 s after the riddle
  was first shown) fade in over `--dur-state` when they arrive on screen, never when a panel
  opens on them. Measured on a production build at 390 px, en, fr and ar, 1× and 4× CPU: both
  transforms composite, no frame over 20 ms (compositor gaps 15 ms at most), one layout while
  it is written (the commit of the new line).
- Focus follows the phase: after every phase swap and every game over, focus moves to the new
  phase's heading (or the colophon title) when it was free, on `<body>` or on a control of the
  game region that is not a field being typed in (`usePhaseFocus`); never on a page load.
  Tests: `front/src/hooks/use-phase-focus.test.ts`, `e2e/tests/accessibility/phase-focus.spec.ts`.
- Overlays: dialogs, menus, popovers and selects arrive in `--dur-state` on `--ease-out` and leave
  in 0.66 × that on `--ease-in`; a sheet lands in `--dur-move` on `--ease-settle`, leaves in
  211 ms; toasts (sonner) are re-timed on the same tokens in styles/brand.css.
- One authored moment per screen; ≤ 3 other moving things; no loop except the visible clock; no
  hover lift, float, glow, pulse, bounce, confetti, or shimmer. Nothing ever passes over a sacred
  name (strike the option letter, not the word).
- Truth first: the final state is in the DOM on the first frame; motion only sequences reading.
- The colophon card (Share, `components/brand/share-card/`) is a still image and moves nothing:
  no animation is created by a press, on the page or on the card, and reduced motion changes
  nothing. It is drawn on demand only, off the screen, in pieces with a turn for the browser
  between them (the tap's own task ends first), and the PNG is encoded by the browser in idle
  slices: measured on a production build at 1x and 4x CPU, no frame over 20 ms, no task over
  20 ms, no request but a face the page had not loaded yet (same origin). The one press
  feedback is the Button's own `loading` (◆◆◆, still).
- Route changes do not animate (the old `AnimatePresence mode="wait"` blank was removed). For a
  phase change use `withViewTransition(() => setPhase(x))` or
  `const phase = useViewTransitionValue(state.phase)` (feature-detected, no-op otherwise, 180 ms;
  the first real value, a page load, is adopted with no transition). Never wrap a phase in
  `AnimatePresence mode="wait"`.
- The light follows the sky (the theme choice "Follow the sky": `ThemeProvider`,
  `lib/sky-light.ts`): the afternoon from sunrise to Maghrib, the night from Maghrib to sunrise,
  computed on the device from the stored prayer-times city (adhan, Muslim World League, as the
  prayer chip). With no city stored it follows the device's light and the choice says so; it
  never asks the network or the location API itself. index.html's pre-paint script walks the
  week of turns ThemeProvider stores (`majlisna-sky-light`), so a load opens in the sky's light;
  past the last turn the device's light stands in. When the sky turns with the page open, the
  app's one ceremony: `withViewTransition`, with `:root[data-sky-turn]` running the root
  crossfade at `--dur-ceremony` on `--ease-out`. Never while a game is on the table (a `/game/`
  route without its colophon's `data-colophon-title`): the turn waits for the colophon or the
  lobby, then 1100 ms more so the colophon lands first. A view transition takes every press for
  its length (Chrome hit-tests them to `<html>`, whatever `pointer-events` say), so the ceremony
  waits for a still page (no press, key, wheel or touch for 2 s) and a press ends it at once
  (`finish()` on its pseudo-elements' animations; the new light is already there). That press
  itself is spent ending the ceremony: the player presses again (review RM-4; keeping it would
  change the ceremony's form, an owner decision). Every change of light, the ceremony's
  included, ends at once the colour transitions it starts (`finishLightTransitions`: the
  tokens' in the same task, React's re-render of the light's readers a microtask later, both
  before the browser captures the new light): without it every `transition-colors` on the
  page ran from the old light, 74 non-composited transitions in the ceremony at 1440 px. At once:
  under reduced motion, in a hidden tab, without view transitions, and for every change that is
  not the sky turning (a load, a choice, a new city, the device's light). An explicit afternoon
  or night always wins. On `/` the other sky is fetched (low priority, the very file the
  picture draws at that width) 10 min before the turn, never at load; the turn itself requests
  nothing. Measured on a production build, the turn live on the home page: the crossfade's two
  animations composite (the UA's root group animation is reported "no visible change"); with a
  GPU no frame over 20 ms at 1440 px, 1× or 4× (worst 10.4 ms); without one (headless software
  compositing) 390 px stays clean but 1440 px drops compositor frames of 20–37 ms (two
  full-viewport layers blended in software). The flip itself (the page's restyle, before the
  crossfade starts) is a 70 ms task at 4×, as long as an instant theme change. Re-measured with
  the transitions finished (1440 px 1× and 4×, 390 px 4×): no CSS transition in the ceremony
  (74 before), the only non-composited animations the UA's own view-transition pseudo-elements;
  after a theme chosen in the nav's menu, only the menu's own button and the closing menu
  transition (74 for the bare flip). Tests:
  `providers/ThemeProvider.test.tsx`, `lib/sky-light.test.ts`,
  `components/layout/__tests__/theme-toggle.test.tsx`, `components/home/__tests__/home-sky.test.tsx`.
- Reduced motion is the CSS's job (plus `matchMedia` in the three scripts that time a
  gesture: `ThreadClock`, the Lawh, Codenames' end veil): no component animates through
  motion/react, so the root has no `MotionConfig` (removed 2026-10-31, it wrapped nothing; the
  `motion` package is still listed in `front/package.json`, unused); CSS twins switch to
  short fades; the clock steps per second; a phase change still crossfades, in 120 ms with no
  group movement (never a hard cut); the halqa's thread jumps and a new seat fades in. Holding the lawh to
  read still works. Sheets, dialogs, popovers and menus (`[data-slot$="-content"]`) lose their
  tw-animate slide and zoom and only fade (index.css). Tests: `front/src/lib/view-transition.test.ts`
  (the 120 ms crossfade), `components/brand/__tests__/Seal.test.tsx`, `ThreadClock.test.tsx`.
  The Quiz's tally threads fade in over 140 ms at their final lengths (the right letter keeps
  `seal-press`'s fade); the scoreboard, a script (its FLIP reads `matchMedia`), shows its final
  order and threads at once and only fades the gain in. Tests: `mcqquiz/ChoiceButtons.test.tsx`,
  `mcqquiz/reveal.test.ts`, `shared/__tests__/PlayerScoreboard.test.tsx`. The Codenames clue,
  a script too (`ClueBanner` reads `matchMedia`), fades its line in over 140 ms, nothing moved
  or stamped. Tests: `codenames/ClueBanner.motion.test.tsx`, `ClueAnnouncer.test.tsx`,
  `codenames/__tests__/codenames-motion.test.ts`. The lawh's turn becomes a 140 ms fade of the
  cover (`RoundOverPanel` reads `matchMedia`: `data-turn="fade"`; the CSS also turns a "turn"
  into that fade); the erase is one 180 ms opacity change. Tests:
  `undercover/__tests__/verdict-turn.test.tsx`, `undercover/__tests__/erase.test.tsx`,
  `rooms/__tests__/PlayerRoster.erase.test.tsx`. The kashida's weave and the sky's ceremony do
  not run (`Wordmark` and `ThemeProvider` read `matchMedia`): the band rests in place, the light
  changes at once. Tests: `brand/__tests__/Wordmark.test.tsx`, `providers/ThemeProvider.test.tsx`.
  The samar riddle's new line fades in over `--dur-state` (`SamarRiddle` reads `matchMedia`).
  Tests: `rooms/__tests__/SamarRiddle.test.tsx`.

## 8. RTL

- `dir`/`lang` are set on `<html>`. Logical properties only (`ms-`, `me-`, `ps-`, `pe-`,
  `start-`, `end-`, `border-s`, `text-start`). Mirror directional icons with `rtl-flip`.
- Reading-start anchors: the clock thread and band weaving start right in Arabic; the halqa fills
  anticlockwise; the arrow on "Start" points left. The home's kashida is woven from the right in
  every interface: the word is Arabic in all three.
- A CSS gesture takes its direction from a custom property that `[dir="rtl"]` sets (The Quiz's
  `--tally-from`, the verdict's `--uc-to-reading-end` / `--uc-from-reading-start`), with ONE
  `@keyframes` for both directions. Never an `-rtl` twin swapped in by `animation-name`: a new
  name is a new animation, so switching the language with a gesture on screen played it again
  from the start.
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
