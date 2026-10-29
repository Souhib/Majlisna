# Product

<!-- impeccable:product-schema 1 -->

Durable product facts that constrain design. Visual rules will live in DESIGN.md; the exhaustive
business and technical reference is the root `CLAUDE.md` and the component `backend/CLAUDE.md` /
`front/CLAUDE.md`, which win if this summary drifts. Assembled on 26–27 October 2026 from the
repository (docs, routes, locales, seed data, constants) and the owner's answers during the 2026
redesign. Every fact marked *(inferred — confirm)* is not stated by the owner or the repository and
still needs confirmation.

## Platform

web

One responsive React SPA at majlisna.app, installable as a PWA (`display: standalone`,
`orientation: portrait-primary`). No native app. The service worker caches only the navigation
shell: every game, room and account action needs a live connection.

## Users

- **Muslim players who already know mainstream party games** (Undercover, Codenames, quizzes) and
  want a version whose vocabulary is Islamic: groups of friends, families, and youth or community
  groups *(inferred — confirm: no audience statement exists in the repo; the brief names these
  groups)*. They speak French, English or Arabic; French is likely a large share, given the French
  locale, the creator's French background and the French Human Appeal link *(inferred — confirm
  the language split)*.
- **The host**, the player who creates the room. They choose the game and its settings (timers,
  rounds, difficulty, Mr. White on/off), share the room code and PIN or a link, invite friends,
  kick idle players and start each game. The host is usually the person organising the gathering
  *(inferred — confirm)*.
- **Solo and small-group learners.** Both quizzes accept a single player, so one person can play
  Word Quiz or MCQ Quiz alone as knowledge practice *(inferred — confirm that solo play is an
  intended use, not only a technical minimum)*.
- **Spectators**, who watch a game with a sanitised view (no roles or words until game over) and
  read-only controls. The backend supports this (`PATCH /rooms/join-spectator`, room PIN
  required); the current UI has no entry point for it (the `room.watchGame` string is unused, and
  E2E joins spectators through the API).
- **The owner/operator** (Souhib Trabelsi), who loads game content through the seed script.
  Content endpoints are admin-only via `ADMIN_EMAILS`; there is no admin UI.

Every player needs an account (email + password, or Google) to create or join a room. There is no
guest play.

## Product Purpose

Majlisna lets Muslims play familiar party games in which every secret word, card, hint and
question is an Islamic term or topic: prophets, companions, places, practices, Qur'an and seerah.
The repo's own one-line purpose is "Learn about Islamic words, prophets, and concepts while
playing with friends" (`README.md`); the home page eyebrow is "Learn & Play". Learning rides on
play: words carry trilingual explanations, the game-over screen shows every word's explanation,
and the MCQ Quiz explains each answer.

Success is not defined anywhere in the repo. Candidate signals the product already measures: games
finished, rooms created, return play (play-streak achievements), hint and explanation views
(`total_hints_viewed`), and charity link clicks (tracked in Umami) *(inferred — confirm which of
these the owner treats as success)*.

## Positioning

Islamized versions of party games people already love, in **three equal languages (English,
French, Arabic with full right-to-left)**, where each player at the same table receives hints,
explanations and questions in their own language (every state endpoint takes the requester's
`lang`). Behind the games sits roughly 1,100 hand-written trilingual content entries (see Evidence
on Hand), so a round ends with something learned, not only a winner. It is free, with no ads,
payments or premium tier anywhere in the codebase *(inferred — confirm that free-without-ads is a
commitment, not only the current state)*. Prayer times are built into the navigation.

## Operating Context

- **A session starts with the host.** They create a room (one live room per player), then share a
  5-character code plus a 4-digit PIN, or a link (`/rooms/join?code=…&pin=…`) that joins in one
  tap. There is no public room directory, by design: rooms are private and joined by a code shared
  outside the app, most likely in a messaging group *(inferred — confirm the channel, e.g.
  WhatsApp)*. Friends can also be invited from inside the room, with a real-time notification.
- **Each player uses their own phone.** Roles, secret words and spymaster keys are personal, so
  every participant needs a device and an account. The manifest targets portrait phones, and the
  frontend docs note that a party game spends most of its time in a backgrounded mobile tab.
- **Same room or remote.** Undercover descriptions are typed in the app as a single word and votes
  are cast in the app; Codenames clues are typed and operatives vote on cards in the app. The
  "Discuss and vote" step has no in-game channel: chat exists only in the room lobby, and there is
  no voice. Discussion therefore happens aloud, either around the same table or on a separate call
  *(inferred — confirm which setting dominates)*.
- **When.** Evenings, weekends and gatherings; Ramadan nights and Eid are plausible peaks
  *(inferred — confirm; there is no usage data in the repo)*.
- **Prayer.** A prayer-times widget in the nav shows the next prayer with a countdown, all five
  prayers plus sunrise, and Tahajjud (last third of the night) with the hadith "Our Lord descends
  every night…" (Bukhari 1145) in all three languages. Times are computed on the device with the
  `adhan` library, fixed to the Muslim World League method; location comes from city search,
  browser geolocation, or IP auto-detection. Groups pausing play for salah is plausible
  *(inferred — confirm)*.
- **Tolerance for real life.** Undercover and Codenames timers default to *no limit* (0) so
  conversation sets the pace; hosts can set up to 600 s. A player who drops is kept for 10 minutes
  in the lobby and 180 s in a game before removal, and every departure is repaired so the round
  can still finish.
- **Language choice.** A welcome modal asks for a language on first visit; the choice persists in
  local storage. Players at one table can use different languages.

## Capabilities and Constraints

**Games**

| Game | Players | Mechanism | Host settings and defaults |
|------|---------|-----------|----------------------------|
| Undercover | 3–12 | Civilians share one Islamic term; Undercover players get a paired, different term; Mr. White gets none. Players describe their word in one word, discuss, then vote to eliminate. An eliminated Mr. White gets one guess at the civilian word; a correct guess wins it for the undercovers. One player is the Mayor, whose vote breaks ties. | Description and voting timers (default none, max 600 s); Mr. White toggle (needs 5+ players: at 4, one undercover plus one Mr. White already tie the civilians, and the impostors win at parity). Every deal starts with civilians strictly ahead. |
| Codenames | 4–10 | Two teams (Red/Blue), each with one spymaster and operatives. 5×5 board of Islamic terms: 9 / 8 / 7 neutral / 1 assassin. The spymaster gives a one-word clue and a number; operatives vote on cards (ties are broken at random). A team that loses its spymaster or last operative loses. | Clue and guess timers (default none). Pack selection exists in the API (`word_pack_ids`) but not in the room settings UI. |
| Word Quiz | 1+ | Guess an Islamic term from six progressive hints, vague to specific, released over time. Typed answers; Arabic diacritics, case and spacing are ignored, and each term accepts several spellings per language. Points: 6 at hint 1, down to 1 at hint 6. | 7 rounds, 60 s per turn, a hint every 10 s, difficulty (mixed / easy / medium / hard); 1–50 rounds, 3–120 s hint interval. |
| MCQ Quiz | 1+ | Four-choice questions, one locked answer per round; 1 point plus up to 2 for speed; an explanation after each round. | 10 questions, 15 s each, difficulty. |

Both quizzes have a ready system: the next round starts when every non-host player is ready or
the host advances. A quiz round closes as soon as everyone still at the table has answered (MCQ)
or found the word (Word Quiz), including when the last player still owing an answer leaves; during
a prayer pause it waits for the resume.

**Word of the day** (`/today`, كلمة اليوم, Le mot du jour): one Kalimat word a day, the same for
everyone (the day turns at midnight in Makkah, and #1 was the launch day, 29 October 2026),
found alone from its six hints for 6 points down to 1, or given up for 0. A wrong try opens the
next hint, so it costs what a hint costs: typing every word of the theme at hint 1 does not pay;
streaks, a home-page card, a share line that never names the word, and
the word kept in the Kunnash. Signed-out visitors see hint 1; playing needs an account.

**Rooms and social:** lobby with roster, settings and chat (newest 50 messages); host kick and
automatic host transfer (a player is preferred over a spectator); friend requests and in-room
invites; share links; public player profiles with head-to-head records; a public leaderboard.

**Progression:** stats (games, wins, win rate, streaks, role distribution, durations, per-game
history with vote and clue history); 45 achievements across six tiers (Bronze, Silver, Gold,
Emerald, Diamond, Mythic) with rarity; 32 challenges (16 daily, 16 weekly); toasts when a game
ends with an achievement unlocked. Progression covers Undercover and Codenames in depth. Word Quiz
appears in challenges only. MCQ Quiz has no dedicated stats, achievements or challenges, and
`weekly_play_all_3` still says "all 3 game types".

**Accounts:** email + password (8 to 72 characters) or Google sign-in; optional email
verification (off by default); password reset; account deletion requires the password; light and
dark mode.

**Fairness is a product constraint, enforced on the server.** A client never receives what its
player should not see: other players' roles and words, Undercover vote targets before the round
resolves, Word Quiz hints not yet released, or a game summary before the game ends (and only for
participants). Draws use a cryptographic RNG. Design work must not add any surface that needs
these secrets early.

**Technical constraints that bind design:**

- The Content Security Policy is **enforced**. Scripts load only from the app itself, Google
  Identity and the configured telemetry host. Stylesheets and fonts load only from the app itself
  (every font is self-hosted since the October 2026 redesign; Google Fonts is no longer allowed). Images may come from any HTTPS
  host. A new font host, CDN script or external API needs a CSP change.
- Socket.IO notifies and REST mutates; all UI state derives from the server response.
- Translations live in `front/src/i18n/locales/{en,fr,ar}.json`. Arabic has full key parity with
  English (550 keys); French is missing 10 (Codenames voting strings, kick toasts, the rejoin
  button), which fall back to English.

**Copy that contradicts the server today (fix rather than design around):** the room-code help
text says "6-character" but codes are 5 characters; reset-password copy and validation say
"at least 5 characters" while the server requires 8; the footer heading "Navigation" is hard-coded
English.

**Terminology:** room (FR *salon*, AR *غرفة*), host, room code, PIN, spectator; Civilian,
Undercover, Mr. White, Mayor; Spymaster, Operative, assassin card; hint, explanation, round.
Prophet names use Arabic transliteration (Yunus, not Jonah).

**Undecided product facts:**

- The product name versus its descriptor. The nav says "Majlisna"; the home hero, the footer brand
  and the page `<title>` say "Islamic Party Games", untranslated in French and Arabic.
- Whether Word Quiz is branded "Kalimat". The name appears only in `CLAUDE.md`, never in the UI.
- Whether game-genre vocabulary stays as is (Undercover, Mr. White, Spymaster, Assassin, and
  achievement names such as "Phantom Menace", "Ghost Protocol", "Shadow Lord") or gets Islamic or
  Arabic equivalents.
- Board and secret words in Undercover and Codenames are single Latin transliterations ("Hajj",
  "Salah", "Adam"), shown that way in the Arabic UI too; only hints and explanations are
  translated. Whether Arabic-script words should appear is open.
- The prayer-time calculation method is fixed to Muslim World League. Whether players can choose a
  regional method (UOIF, Umm al-Qura, ISNA…) or an Asr school is open.
- Whether the spectator mode gets a UI entry point.

## Brand Commitments

- **Name:** Majlisna, at `majlisna.app`. The Arabic form مجلسنا ("our majlis", that is, our
  gathering or sitting circle) does not appear anywhere in the codebase; the Arabic UI writes
  "Majlisna" in Latin script *(inferred — confirm the Arabic spelling, and whether the brand
  intends the classical sense of a* majlis *as a circle of knowledge or remembrance)*.
- **Charity:** home page, About page and footer link to **Human Appeal** (`humanappeal.fr`) and
  **Ummah Charity** (`ummahcharity.org`) under "Support the Ummah / Make a Difference". The copy
  calls them "trusted charities"; no partnership or affiliation is stated *(inferred — confirm the
  relationship, whether the two are permanent, and whether Human Appeal should point to the
  French site for every language)*.
- **Creator:** Souhib Trabelsi, software engineer. The About page is his profile (photo
  `front/public/souhib.jpeg`, education, experience, skills, a free mentoring offer, and public
  email, phone, LinkedIn and GitHub links), and the footer carries a creator card. The product
  presents itself as one person's project for the community *(inferred — confirm that the
  personal framing should stay this prominent)*.
- **Voice in use today:** "Learn & Play", "Made with ♥ for the Ummah", "Support the Ummah".
  Islamic vocabulary sits next to spy and pop-culture game vocabulary. No voice guide exists.
- **Redesign direction stated by the owner (October 2026):** the previous site read as generic
  ("too much like AI slop"); the owner wants an identity of its own, tied to wisdom, knowledge,
  Islam and the Arab world, with full latitude to change everything including the palette. Mood
  references he gave: a dark, gold, lamp-lit Arabic luxury site and a contemporary Arab editorial
  collage (dusk sky, desert, calligraphy stretched with kashida). He likes Arabic calligraphy and
  Sadu carpets; he rejected multicolour "gamey" palettes, walls of coloured game tiles and
  floating decorative objects (lanterns, coffee pots). The visual system that answers this lives
  in DESIGN.md.
- **Imagery:** no women and no faces as imagery (owner explicit). Landscapes, architecture,
  textiles and hands at most. The one exception is the creator's own portrait on About (owner
  decision, 2026-10-28).
- **Existing marks:** there is no logo. The favicon and app icon are the 🕌 emoji (on a `#2d6a4f`
  square for the PWA icon), and the nav and footer mark is a generic open-book icon. Nothing here
  is a binding asset *(inferred — confirm that nothing must be preserved)*.

## Evidence on Hand

Real content, all in `backend/scripts/seed_data/`, loaded by `scripts/generate_fake_data.py`:

- **Undercover** (`undercover_data.py`): 95 terms in 19 categories (prophets 18, concepts 14,
  practices 14, places 10, companions 6, …). Each has an English short and long description and a
  trilingual hint. 67 civilian/undercover pairs (e.g. Hajj / Umrah).
- **Codenames** (`codenames_data.py`): 9 thematic packs (Prophets & Messengers, Qur'an & Surahs,
  Islamic History, Worship & Rituals, Islamic Values, Islamic Sciences, Companions & Figures, Daily
  Life & Culture, Sacred Places & Architecture). 203 entries, 200 distinct words, each with a
  trilingual hint.
- **Word Quiz** (`wordquiz_data.py`): 191 terms. Each has a name in all three languages, accepted
  answers per language (e.g. إبراهيم / ابراهيم, Ibrahim / Abraham), a full six-rung trilingual
  hint ladder and a trilingual explanation. 7 categories; 64 easy, 89 medium, 38 hard.
- **MCQ Quiz** (`mcqquiz_data.py`): **610** questions (`CLAUDE.md` says "200+", which is stale).
  Each has a trilingual question, four trilingual choices and a trilingual explanation. 8
  categories: prophets 119, Qur'an 98, seerah 80, practices 73, history and civilisation 71, ethics
  60, pillars 59, companions 50. 224 easy, 282 medium, 104 hard. About 180 explanations name a
  surah, verse or hadith collection; citation is not systematic.
- **Prayer:** one sourced hadith (Bukhari 1145) in three languages.
- **Progression copy:** 45 achievement and 32 challenge definitions, translated in all three
  locales.

Absences that future work must not fill with invented material:

- No record of scholarly or religious review of the content. Do not claim "verified by scholars"
  or similar.
- No testimonials, player counts, community size, ratings, press or partner logos. Do not invent
  them, and do not present E2E test accounts (`e2e-…` usernames) or seed users as real players.
- No photographs of real play sessions or real users, apart from the creator's portrait.
- No terms page. A privacy policy exists (`/privacy`, linked from the footer and from Google's
  consent screen): it names the emails, Google sign-in, Umami and GlitchTip, and the location
  services the browser calls (ipapi.co, Open-Meteo, Nominatim). It states only what the code
  does; it is not a legal review.
- No new Qur'an verse, hadith or scholarly quotation may be added to the interface without a
  source the owner has checked. Existing religious text must keep its attribution.

## Product Principles

1. **The secret is the game.** The server alone holds roles, words, votes and unreleased hints.
   No surface may reveal early what a player should not know, and the draw must be unpredictable.
2. **Play first, learning folded in.** Knowledge comes through hints, explanations and the
   game-over recap, never as a lecture that stands between a group and its next round.
3. **Three languages, one table.** English, French and Arabic are equals. Arabic right-to-left is
   first-class, and each player can play in their own language beside the others.
4. **Every game can finish.** Drop-outs, absent hosts, locked phones and timeouts must never leave
   a table stuck; the default pace is the group's conversation, not a clock.
5. **Faithful and honest about the faith.** Religious content is accurate, respectful and sourced;
   nothing is fabricated, and the product never claims authority it does not have *(inferred —
   confirm wording)*.

## Accessibility & Inclusion

- **Standard:** WCAG 2.x A and AA. A real-browser axe gate (`e2e/tests/accessibility/`) fails on
  serious or critical violations on home, login, register and the rooms page.
  `contrast.spec.ts` waits for animations to settle and checks translucent-tint chips against the
  4.5:1 small-text floor; the `-on-tint` tokens exist for that pairing. Game screens are not
  covered by the axe gate.
- **Bidirectional layout:** Arabic sets `dir="rtl"` at the root, and the E2E suite covers language
  switching. Arabic copy is complete. Latin terms inside Arabic sentences (game words, "Mr.
  White", "Majlisna") are a constant bidi case.
- **Reduced motion:** honoured only in the footer and the language modal (`useReducedMotion`).
  Elsewhere, page and card animations ignore the preference.
- **Typing tolerance:** quiz answers ignore Arabic diacritics, case and extra spaces, and accept
  several spellings per language.
- **Phones:** portrait-first PWA; zoom is allowed (`maximum-scale=5`). No hit-area standard has
  been set *(inferred — confirm a target, e.g. 44 px)*.
- **Audience range:** young people to older family members playing together, and readers in two
  scripts *(inferred — confirm)*.
