--
-- PostgreSQL database dump
--

\restrict 1k8H4J3sZexVO99fZimK0QOQRUEjagY33aJoABnhLjydJ2uVB9cZAX6zgTqswGf

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: achievementcategory; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.achievementcategory AS ENUM (
    'BEGINNER',
    'UNDERCOVER_MASTER',
    'CODENAMES_MASTER',
    'SOCIAL',
    'STREAK',
    'SPECIAL'
);


--
-- Name: challengetype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.challengetype AS ENUM (
    'DAILY',
    'WEEKLY'
);


--
-- Name: friendshipstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.friendshipstatus AS ENUM (
    'PENDING',
    'ACCEPTED',
    'BLOCKED'
);


--
-- Name: gamestatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.gamestatus AS ENUM (
    'WAITING',
    'IN_PROGRESS',
    'FINISHED',
    'CANCELLED'
);


--
-- Name: gametype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.gametype AS ENUM (
    'UNDERCOVER',
    'CODENAMES',
    'WORD_QUIZ',
    'MCQ_QUIZ'
);


--
-- Name: notebookgametype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.notebookgametype AS ENUM (
    'UNDERCOVER',
    'CODENAMES',
    'WORD_QUIZ',
    'DAILY_WORD'
);


--
-- Name: roomstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.roomstatus AS ENUM (
    'OFFLINE',
    'ONLINE'
);


--
-- Name: roomtype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.roomtype AS ENUM (
    'ACTIVE',
    'INACTIVE'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: achievementdefinition; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.achievementdefinition (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    code character varying NOT NULL,
    category public.achievementcategory NOT NULL,
    name character varying NOT NULL,
    description character varying NOT NULL,
    icon character varying NOT NULL,
    threshold integer NOT NULL,
    tier integer NOT NULL,
    game_type character varying
);


--
-- Name: activity; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.activity (
    id uuid NOT NULL,
    room_id uuid,
    user_id uuid,
    name character varying NOT NULL,
    data json,
    "timestamp" timestamp with time zone NOT NULL
);


--
-- Name: auth_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_session (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    last_refreshed_at timestamp with time zone NOT NULL,
    current_refresh_jti character varying(64) NOT NULL,
    previous_refresh_jti character varying(64),
    rotated_at timestamp with time zone,
    legacy_refresh_digest character varying(64),
    revoked_at timestamp with time zone
);


--
-- Name: challengedefinition; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.challengedefinition (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    code character varying NOT NULL,
    description character varying NOT NULL,
    challenge_type public.challengetype NOT NULL,
    target_count integer NOT NULL,
    game_type character varying,
    condition character varying NOT NULL,
    role character varying
);


--
-- Name: chatmessage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chatmessage (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    room_id uuid NOT NULL,
    user_id uuid NOT NULL,
    username character varying NOT NULL,
    message character varying(500) NOT NULL
);


--
-- Name: codenames_word; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.codenames_word (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    word character varying NOT NULL,
    word_pack_id uuid NOT NULL,
    hint json
);


--
-- Name: codenames_word_pack; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.codenames_word_pack (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    name character varying NOT NULL,
    description character varying,
    is_active boolean NOT NULL
);


--
-- Name: daily_word; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_word (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    day date NOT NULL,
    quiz_word_id uuid NOT NULL
);


--
-- Name: daily_word_play; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_word_play (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    day date NOT NULL,
    hints_revealed integer NOT NULL,
    attempts integer NOT NULL,
    last_guess character varying,
    guesses json NOT NULL,
    solved_at timestamp with time zone,
    gave_up boolean NOT NULL,
    score integer,
    started_at timestamp with time zone NOT NULL
);


--
-- Name: emailverificationtoken; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.emailverificationtoken (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    token character varying NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used boolean NOT NULL
);


--
-- Name: event; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event (
    id uuid NOT NULL,
    name character varying NOT NULL,
    data json,
    turn_id uuid,
    user_id uuid,
    "timestamp" timestamp with time zone NOT NULL
);


--
-- Name: friendship; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.friendship (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    requester_id uuid NOT NULL,
    addressee_id uuid NOT NULL,
    status public.friendshipstatus NOT NULL
);


--
-- Name: game; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.game (
    start_time timestamp with time zone NOT NULL,
    end_time timestamp with time zone,
    number_of_players integer NOT NULL,
    type public.gametype NOT NULL,
    game_configurations json,
    live_state jsonb,
    game_status public.gamestatus NOT NULL,
    id uuid NOT NULL,
    room_id uuid,
    user_id uuid
);


--
-- Name: gameturnlink; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gameturnlink (
    game_id uuid NOT NULL,
    turn_id uuid NOT NULL
);


--
-- Name: mcq_question; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mcq_question (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    question_en character varying NOT NULL,
    question_ar character varying,
    question_fr character varying,
    choices json,
    correct_answer_index integer NOT NULL,
    explanation json,
    category character varying NOT NULL,
    difficulty character varying NOT NULL
);


--
-- Name: notebook_entry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notebook_entry (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    term character varying NOT NULL,
    game_type public.notebookgametype NOT NULL,
    source_game_id uuid,
    kept_at timestamp with time zone NOT NULL
);


--
-- Name: passwordresettoken; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.passwordresettoken (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    token character varying NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used boolean NOT NULL
);


--
-- Name: quiz_word; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quiz_word (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    word_en character varying NOT NULL,
    word_ar character varying,
    word_fr character varying,
    accepted_answers json,
    category character varying NOT NULL,
    difficulty character varying NOT NULL,
    hints json,
    explanation json
);


--
-- Name: room; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.room (
    status public.roomstatus NOT NULL,
    password character varying(4) NOT NULL,
    id uuid NOT NULL,
    public_id character varying(5) NOT NULL,
    owner_id uuid,
    created_at timestamp with time zone NOT NULL,
    type public.roomtype NOT NULL,
    settings json,
    active_game_id uuid
);


--
-- Name: room_ban; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.room_ban (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    room_id uuid NOT NULL,
    user_id uuid NOT NULL,
    banned_by uuid
);


--
-- Name: roomactivitylink; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roomactivitylink (
    activity_id uuid NOT NULL,
    room_id uuid NOT NULL
);


--
-- Name: roomgamelink; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roomgamelink (
    room_id uuid NOT NULL,
    game_id uuid NOT NULL
);


--
-- Name: roomuserlink; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roomuserlink (
    id integer NOT NULL,
    room_id uuid,
    user_id uuid,
    joined_at timestamp without time zone NOT NULL,
    connected boolean NOT NULL,
    last_seen_at timestamp without time zone,
    disconnected_at timestamp without time zone,
    is_spectator boolean NOT NULL
);


--
-- Name: roomuserlink_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.roomuserlink_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: roomuserlink_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.roomuserlink_id_seq OWNED BY public.roomuserlink.id;


--
-- Name: term_script; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.term_script (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    term character varying NOT NULL,
    ar character varying NOT NULL,
    ar_vocalized character varying
);


--
-- Name: termpair; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.termpair (
    word1_id uuid NOT NULL,
    word2_id uuid NOT NULL,
    id uuid
);


--
-- Name: turn; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.turn (
    start_time timestamp with time zone NOT NULL,
    end_time timestamp with time zone,
    completed boolean NOT NULL,
    id uuid NOT NULL,
    game_id uuid
);


--
-- Name: turneventlink; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.turneventlink (
    turn_id uuid NOT NULL,
    event_id uuid NOT NULL
);


--
-- Name: user; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."user" (
    username character varying(30) NOT NULL,
    email_address character varying NOT NULL,
    country character varying,
    email_verified boolean NOT NULL,
    bio character varying(200),
    google_sub character varying(255),
    auth_provider character varying(20) NOT NULL,
    profile_picture_url character varying,
    id uuid NOT NULL,
    password character varying NOT NULL
);


--
-- Name: userachievement; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.userachievement (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    achievement_id uuid NOT NULL,
    progress integer NOT NULL,
    unlocked_at timestamp with time zone
);


--
-- Name: userchallenge; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.userchallenge (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    challenge_id uuid NOT NULL,
    progress integer NOT NULL,
    completed boolean NOT NULL,
    assigned_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL
);


--
-- Name: usergamelink; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.usergamelink (
    user_id uuid NOT NULL,
    game_id uuid NOT NULL
);


--
-- Name: userstats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.userstats (
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    total_games_played integer NOT NULL,
    total_games_won integer NOT NULL,
    total_games_lost integer NOT NULL,
    undercover_games_played integer NOT NULL,
    undercover_games_won integer NOT NULL,
    codenames_games_played integer NOT NULL,
    codenames_games_won integer NOT NULL,
    times_civilian integer NOT NULL,
    times_undercover integer NOT NULL,
    times_mr_white integer NOT NULL,
    civilian_wins integer NOT NULL,
    undercover_wins integer NOT NULL,
    mr_white_wins integer NOT NULL,
    times_spymaster integer NOT NULL,
    times_operative integer NOT NULL,
    spymaster_wins integer NOT NULL,
    operative_wins integer NOT NULL,
    total_votes_cast integer NOT NULL,
    correct_votes integer NOT NULL,
    times_eliminated integer NOT NULL,
    times_survived integer NOT NULL,
    current_win_streak integer NOT NULL,
    longest_win_streak integer NOT NULL,
    current_play_streak_days integer NOT NULL,
    longest_play_streak_days integer NOT NULL,
    last_played_at timestamp with time zone,
    mr_white_correct_guesses integer NOT NULL,
    codenames_words_guessed integer NOT NULL,
    codenames_perfect_rounds integer NOT NULL,
    games_without_hints integer NOT NULL,
    total_hints_viewed integer NOT NULL,
    rooms_created integer NOT NULL,
    games_hosted integer NOT NULL
);


--
-- Name: word; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.word (
    word character varying NOT NULL,
    category character varying NOT NULL,
    short_description character varying NOT NULL,
    long_description character varying NOT NULL,
    hint json,
    id uuid NOT NULL
);


--
-- Name: roomuserlink id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roomuserlink ALTER COLUMN id SET DEFAULT nextval('public.roomuserlink_id_seq'::regclass);


--
-- Name: achievementdefinition achievementdefinition_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.achievementdefinition
    ADD CONSTRAINT achievementdefinition_pkey PRIMARY KEY (id);


--
-- Name: activity activity_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity
    ADD CONSTRAINT activity_pkey PRIMARY KEY (id);


--
-- Name: auth_session auth_session_legacy_refresh_digest_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_session
    ADD CONSTRAINT auth_session_legacy_refresh_digest_key UNIQUE (legacy_refresh_digest);


--
-- Name: auth_session auth_session_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_session
    ADD CONSTRAINT auth_session_pkey PRIMARY KEY (id);


--
-- Name: challengedefinition challengedefinition_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.challengedefinition
    ADD CONSTRAINT challengedefinition_pkey PRIMARY KEY (id);


--
-- Name: chatmessage chatmessage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chatmessage
    ADD CONSTRAINT chatmessage_pkey PRIMARY KEY (id);


--
-- Name: codenames_word_pack codenames_word_pack_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.codenames_word_pack
    ADD CONSTRAINT codenames_word_pack_pkey PRIMARY KEY (id);


--
-- Name: codenames_word codenames_word_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.codenames_word
    ADD CONSTRAINT codenames_word_pkey PRIMARY KEY (id);


--
-- Name: daily_word daily_word_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_word
    ADD CONSTRAINT daily_word_pkey PRIMARY KEY (day);


--
-- Name: daily_word_play daily_word_play_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_word_play
    ADD CONSTRAINT daily_word_play_pkey PRIMARY KEY (id);


--
-- Name: emailverificationtoken emailverificationtoken_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emailverificationtoken
    ADD CONSTRAINT emailverificationtoken_pkey PRIMARY KEY (id);


--
-- Name: event event_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event
    ADD CONSTRAINT event_pkey PRIMARY KEY (id);


--
-- Name: friendship friendship_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friendship
    ADD CONSTRAINT friendship_pkey PRIMARY KEY (id);


--
-- Name: game game_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.game
    ADD CONSTRAINT game_pkey PRIMARY KEY (id);


--
-- Name: gameturnlink gameturnlink_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gameturnlink
    ADD CONSTRAINT gameturnlink_pkey PRIMARY KEY (game_id, turn_id);


--
-- Name: mcq_question mcq_question_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcq_question
    ADD CONSTRAINT mcq_question_pkey PRIMARY KEY (id);


--
-- Name: notebook_entry notebook_entry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notebook_entry
    ADD CONSTRAINT notebook_entry_pkey PRIMARY KEY (id);


--
-- Name: passwordresettoken passwordresettoken_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.passwordresettoken
    ADD CONSTRAINT passwordresettoken_pkey PRIMARY KEY (id);


--
-- Name: quiz_word quiz_word_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_word
    ADD CONSTRAINT quiz_word_pkey PRIMARY KEY (id);


--
-- Name: room_ban room_ban_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_ban
    ADD CONSTRAINT room_ban_pkey PRIMARY KEY (id);


--
-- Name: room room_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room
    ADD CONSTRAINT room_pkey PRIMARY KEY (id);


--
-- Name: roomactivitylink roomactivitylink_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roomactivitylink
    ADD CONSTRAINT roomactivitylink_pkey PRIMARY KEY (activity_id, room_id);


--
-- Name: roomgamelink roomgamelink_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roomgamelink
    ADD CONSTRAINT roomgamelink_pkey PRIMARY KEY (room_id, game_id);


--
-- Name: roomuserlink roomuserlink_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roomuserlink
    ADD CONSTRAINT roomuserlink_pkey PRIMARY KEY (id);


--
-- Name: term_script term_script_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.term_script
    ADD CONSTRAINT term_script_pkey PRIMARY KEY (id);


--
-- Name: termpair termpair_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.termpair
    ADD CONSTRAINT termpair_id_key UNIQUE (id);


--
-- Name: termpair termpair_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.termpair
    ADD CONSTRAINT termpair_pkey PRIMARY KEY (word1_id, word2_id);


--
-- Name: turn turn_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turn
    ADD CONSTRAINT turn_pkey PRIMARY KEY (id);


--
-- Name: turneventlink turneventlink_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turneventlink
    ADD CONSTRAINT turneventlink_pkey PRIMARY KEY (turn_id, event_id);


--
-- Name: daily_word_play uq_daily_word_play_user_day; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_word_play
    ADD CONSTRAINT uq_daily_word_play_user_day UNIQUE (user_id, day);


--
-- Name: friendship uq_friendship_pair; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friendship
    ADD CONSTRAINT uq_friendship_pair UNIQUE (requester_id, addressee_id);


--
-- Name: notebook_entry uq_notebook_entry_user_type_term; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notebook_entry
    ADD CONSTRAINT uq_notebook_entry_user_type_term UNIQUE (user_id, game_type, term);


--
-- Name: room_ban uq_room_ban_room_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_ban
    ADD CONSTRAINT uq_room_ban_room_user UNIQUE (room_id, user_id);


--
-- Name: roomuserlink uq_roomuserlink_room_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roomuserlink
    ADD CONSTRAINT uq_roomuserlink_room_user UNIQUE (room_id, user_id);


--
-- Name: user user_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT user_pkey PRIMARY KEY (id);


--
-- Name: userachievement userachievement_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.userachievement
    ADD CONSTRAINT userachievement_pkey PRIMARY KEY (id);


--
-- Name: userachievement userachievement_user_id_achievement_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.userachievement
    ADD CONSTRAINT userachievement_user_id_achievement_id_key UNIQUE (user_id, achievement_id);


--
-- Name: userchallenge userchallenge_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.userchallenge
    ADD CONSTRAINT userchallenge_pkey PRIMARY KEY (id);


--
-- Name: userchallenge userchallenge_user_id_challenge_id_assigned_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.userchallenge
    ADD CONSTRAINT userchallenge_user_id_challenge_id_assigned_at_key UNIQUE (user_id, challenge_id, assigned_at);


--
-- Name: usergamelink usergamelink_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usergamelink
    ADD CONSTRAINT usergamelink_pkey PRIMARY KEY (user_id, game_id);


--
-- Name: userstats userstats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.userstats
    ADD CONSTRAINT userstats_pkey PRIMARY KEY (id);


--
-- Name: word word_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.word
    ADD CONSTRAINT word_pkey PRIMARY KEY (id);


--
-- Name: ix_achievementdefinition_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_achievementdefinition_code ON public.achievementdefinition USING btree (code);


--
-- Name: ix_auth_session_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_session_user_id ON public.auth_session USING btree (user_id);


--
-- Name: ix_challengedefinition_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_challengedefinition_code ON public.challengedefinition USING btree (code);


--
-- Name: ix_chatmessage_room_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chatmessage_room_id ON public.chatmessage USING btree (room_id);


--
-- Name: ix_chatmessage_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chatmessage_user_id ON public.chatmessage USING btree (user_id);


--
-- Name: ix_codenames_word_pack_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_codenames_word_pack_name ON public.codenames_word_pack USING btree (name);


--
-- Name: ix_codenames_word_word; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_codenames_word_word ON public.codenames_word USING btree (word);


--
-- Name: ix_daily_word_play_day; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_daily_word_play_day ON public.daily_word_play USING btree (day);


--
-- Name: ix_daily_word_quiz_word_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_daily_word_quiz_word_id ON public.daily_word USING btree (quiz_word_id);


--
-- Name: ix_emailverificationtoken_token; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_emailverificationtoken_token ON public.emailverificationtoken USING btree (token);


--
-- Name: ix_emailverificationtoken_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_emailverificationtoken_user_id ON public.emailverificationtoken USING btree (user_id);


--
-- Name: ix_friendship_addressee_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_friendship_addressee_id ON public.friendship USING btree (addressee_id);


--
-- Name: ix_friendship_requester_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_friendship_requester_id ON public.friendship USING btree (requester_id);


--
-- Name: ix_game_room_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_game_room_id ON public.game USING btree (room_id);


--
-- Name: ix_game_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_game_user_id ON public.game USING btree (user_id);


--
-- Name: ix_mcq_question_difficulty; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mcq_question_difficulty ON public.mcq_question USING btree (difficulty);


--
-- Name: ix_mcq_question_question_en; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mcq_question_question_en ON public.mcq_question USING btree (question_en);


--
-- Name: ix_notebook_entry_user_kept_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notebook_entry_user_kept_at ON public.notebook_entry USING btree (user_id, kept_at);


--
-- Name: ix_passwordresettoken_token; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_passwordresettoken_token ON public.passwordresettoken USING btree (token);


--
-- Name: ix_passwordresettoken_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_passwordresettoken_user_id ON public.passwordresettoken USING btree (user_id);


--
-- Name: ix_quiz_word_difficulty; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quiz_word_difficulty ON public.quiz_word USING btree (difficulty);


--
-- Name: ix_quiz_word_word_en; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quiz_word_word_en ON public.quiz_word USING btree (word_en);


--
-- Name: ix_room_ban_room_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_room_ban_room_id ON public.room_ban USING btree (room_id);


--
-- Name: ix_room_ban_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_room_ban_user_id ON public.room_ban USING btree (user_id);


--
-- Name: ix_room_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_room_owner_id ON public.room USING btree (owner_id);


--
-- Name: ix_room_public_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_room_public_id ON public.room USING btree (public_id);


--
-- Name: ix_roomuserlink_connected_disconnected_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_roomuserlink_connected_disconnected_at ON public.roomuserlink USING btree (connected, disconnected_at);


--
-- Name: ix_roomuserlink_connected_last_seen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_roomuserlink_connected_last_seen ON public.roomuserlink USING btree (connected, last_seen_at);


--
-- Name: ix_roomuserlink_room_connected; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_roomuserlink_room_connected ON public.roomuserlink USING btree (room_id, connected);


--
-- Name: ix_roomuserlink_room_last_seen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_roomuserlink_room_last_seen ON public.roomuserlink USING btree (room_id, last_seen_at);


--
-- Name: ix_roomuserlink_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_roomuserlink_user_id ON public.roomuserlink USING btree (user_id);


--
-- Name: ix_term_script_term; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_term_script_term ON public.term_script USING btree (term);


--
-- Name: ix_user_email_address; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_user_email_address ON public."user" USING btree (email_address);


--
-- Name: ix_user_email_lower; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_user_email_lower ON public."user" USING btree (lower((email_address)::text));


--
-- Name: ix_user_google_sub; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_user_google_sub ON public."user" USING btree (google_sub);


--
-- Name: ix_user_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_username ON public."user" USING btree (username);


--
-- Name: ix_user_username_lower; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_user_username_lower ON public."user" USING btree (lower((username)::text));


--
-- Name: ix_userachievement_achievement_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_userachievement_achievement_id ON public.userachievement USING btree (achievement_id);


--
-- Name: ix_userachievement_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_userachievement_user_id ON public.userachievement USING btree (user_id);


--
-- Name: ix_userchallenge_challenge_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_userchallenge_challenge_id ON public.userchallenge USING btree (challenge_id);


--
-- Name: ix_userchallenge_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_userchallenge_user_id ON public.userchallenge USING btree (user_id);


--
-- Name: ix_userstats_total_games_won_desc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_userstats_total_games_won_desc ON public.userstats USING btree (total_games_won DESC);


--
-- Name: ix_userstats_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_userstats_user_id ON public.userstats USING btree (user_id);


--
-- Name: ix_word_word; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_word_word ON public.word USING btree (word);


--
-- Name: activity activity_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity
    ADD CONSTRAINT activity_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.room(id);


--
-- Name: activity activity_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity
    ADD CONSTRAINT activity_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: auth_session auth_session_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_session
    ADD CONSTRAINT auth_session_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: chatmessage chatmessage_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chatmessage
    ADD CONSTRAINT chatmessage_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.room(id);


--
-- Name: chatmessage chatmessage_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chatmessage
    ADD CONSTRAINT chatmessage_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: codenames_word codenames_word_word_pack_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.codenames_word
    ADD CONSTRAINT codenames_word_word_pack_id_fkey FOREIGN KEY (word_pack_id) REFERENCES public.codenames_word_pack(id);


--
-- Name: daily_word_play daily_word_play_day_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_word_play
    ADD CONSTRAINT daily_word_play_day_fkey FOREIGN KEY (day) REFERENCES public.daily_word(day);


--
-- Name: daily_word_play daily_word_play_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_word_play
    ADD CONSTRAINT daily_word_play_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: daily_word daily_word_quiz_word_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_word
    ADD CONSTRAINT daily_word_quiz_word_id_fkey FOREIGN KEY (quiz_word_id) REFERENCES public.quiz_word(id);


--
-- Name: emailverificationtoken emailverificationtoken_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emailverificationtoken
    ADD CONSTRAINT emailverificationtoken_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: event event_turn_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event
    ADD CONSTRAINT event_turn_id_fkey FOREIGN KEY (turn_id) REFERENCES public.turn(id);


--
-- Name: event event_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event
    ADD CONSTRAINT event_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: room fk_room_active_game_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room
    ADD CONSTRAINT fk_room_active_game_id FOREIGN KEY (active_game_id) REFERENCES public.game(id);


--
-- Name: friendship friendship_addressee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friendship
    ADD CONSTRAINT friendship_addressee_id_fkey FOREIGN KEY (addressee_id) REFERENCES public."user"(id);


--
-- Name: friendship friendship_requester_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friendship
    ADD CONSTRAINT friendship_requester_id_fkey FOREIGN KEY (requester_id) REFERENCES public."user"(id);


--
-- Name: game game_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.game
    ADD CONSTRAINT game_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.room(id);


--
-- Name: game game_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.game
    ADD CONSTRAINT game_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: gameturnlink gameturnlink_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gameturnlink
    ADD CONSTRAINT gameturnlink_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.game(id);


--
-- Name: gameturnlink gameturnlink_turn_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gameturnlink
    ADD CONSTRAINT gameturnlink_turn_id_fkey FOREIGN KEY (turn_id) REFERENCES public.turn(id);


--
-- Name: notebook_entry notebook_entry_source_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notebook_entry
    ADD CONSTRAINT notebook_entry_source_game_id_fkey FOREIGN KEY (source_game_id) REFERENCES public.game(id);


--
-- Name: notebook_entry notebook_entry_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notebook_entry
    ADD CONSTRAINT notebook_entry_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: passwordresettoken passwordresettoken_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.passwordresettoken
    ADD CONSTRAINT passwordresettoken_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: room_ban room_ban_banned_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_ban
    ADD CONSTRAINT room_ban_banned_by_fkey FOREIGN KEY (banned_by) REFERENCES public."user"(id);


--
-- Name: room_ban room_ban_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_ban
    ADD CONSTRAINT room_ban_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.room(id);


--
-- Name: room_ban room_ban_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_ban
    ADD CONSTRAINT room_ban_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: room room_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room
    ADD CONSTRAINT room_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public."user"(id);


--
-- Name: roomactivitylink roomactivitylink_activity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roomactivitylink
    ADD CONSTRAINT roomactivitylink_activity_id_fkey FOREIGN KEY (activity_id) REFERENCES public.activity(id);


--
-- Name: roomactivitylink roomactivitylink_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roomactivitylink
    ADD CONSTRAINT roomactivitylink_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.room(id);


--
-- Name: roomgamelink roomgamelink_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roomgamelink
    ADD CONSTRAINT roomgamelink_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.game(id);


--
-- Name: roomgamelink roomgamelink_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roomgamelink
    ADD CONSTRAINT roomgamelink_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.room(id);


--
-- Name: roomuserlink roomuserlink_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roomuserlink
    ADD CONSTRAINT roomuserlink_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.room(id);


--
-- Name: roomuserlink roomuserlink_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roomuserlink
    ADD CONSTRAINT roomuserlink_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: termpair termpair_word1_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.termpair
    ADD CONSTRAINT termpair_word1_id_fkey FOREIGN KEY (word1_id) REFERENCES public.word(id);


--
-- Name: termpair termpair_word2_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.termpair
    ADD CONSTRAINT termpair_word2_id_fkey FOREIGN KEY (word2_id) REFERENCES public.word(id);


--
-- Name: turn turn_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turn
    ADD CONSTRAINT turn_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.game(id);


--
-- Name: turneventlink turneventlink_event_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turneventlink
    ADD CONSTRAINT turneventlink_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.event(id);


--
-- Name: turneventlink turneventlink_turn_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turneventlink
    ADD CONSTRAINT turneventlink_turn_id_fkey FOREIGN KEY (turn_id) REFERENCES public.turn(id);


--
-- Name: userachievement userachievement_achievement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.userachievement
    ADD CONSTRAINT userachievement_achievement_id_fkey FOREIGN KEY (achievement_id) REFERENCES public.achievementdefinition(id);


--
-- Name: userachievement userachievement_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.userachievement
    ADD CONSTRAINT userachievement_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: userchallenge userchallenge_challenge_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.userchallenge
    ADD CONSTRAINT userchallenge_challenge_id_fkey FOREIGN KEY (challenge_id) REFERENCES public.challengedefinition(id);


--
-- Name: userchallenge userchallenge_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.userchallenge
    ADD CONSTRAINT userchallenge_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: usergamelink usergamelink_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usergamelink
    ADD CONSTRAINT usergamelink_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.game(id);


--
-- Name: usergamelink usergamelink_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usergamelink
    ADD CONSTRAINT usergamelink_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: userstats userstats_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.userstats
    ADD CONSTRAINT userstats_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- PostgreSQL database dump complete
--

\unrestrict 1k8H4J3sZexVO99fZimK0QOQRUEjagY33aJoABnhLjydJ2uVB9cZAX6zgTqswGf
