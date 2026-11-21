-- Complete Roleplay PostgreSQL schema — fresh/empty databases only.
-- Generated from the running database; application rows and credentials are excluded.
-- Existing databases: use python -m shared.db.migrate instead.
-- The transaction rolls back if this is accidentally applied to an existing schema.
BEGIN;
--
-- PostgreSQL database dump
--


-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA IF NOT EXISTS public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: catalog_terms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.catalog_terms (
    kind text NOT NULL,
    slug text NOT NULL,
    label text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    aliases text[] DEFAULT '{}'::text[] NOT NULL,
    "position" integer DEFAULT 0 NOT NULL,
    active boolean DEFAULT true NOT NULL,
    requires_adult_cast boolean DEFAULT false NOT NULL,
    CONSTRAINT catalog_terms_kind_check CHECK ((kind = ANY (ARRAY['genre'::text, 'tone'::text, 'life_stage'::text, 'gender'::text]))),
    CONSTRAINT catalog_terms_label_check CHECK (((length(label) >= 1) AND (length(label) <= 80))),
    CONSTRAINT catalog_terms_slug_check CHECK ((slug ~ '^[a-z][a-z0-9_]{0,49}$'::text))
);


--
-- Name: catalog_vector_checkpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.catalog_vector_checkpoints (
    version_id bigint NOT NULL,
    indexed_at timestamp with time zone,
    retry_at timestamp with time zone DEFAULT now() NOT NULL,
    attempts integer DEFAULT 0 NOT NULL
);


--
-- Name: characters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.characters (
    id integer NOT NULL,
    scenario_id integer NOT NULL,
    is_ai boolean DEFAULT true,
    name character varying(50) NOT NULL,
    gender character varying(20),
    age integer,
    personality text,
    likes text[],
    dislikes text[],
    backstory text,
    example_dialogue text,
    appearance text,
    greeting text,
    scenario text,
    role_description text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: characters_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.characters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: characters_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.characters_id_seq OWNED BY public.characters.id;


--
-- Name: conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversations (
    id integer NOT NULL,
    scenario_id integer NOT NULL,
    user_id integer NOT NULL,
    ai_character_id integer,
    user_character_id integer,
    current_place text DEFAULT 'Unknown'::text,
    "current_time" text DEFAULT 'Unknown'::text,
    status character varying(20) DEFAULT 'active'::character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    state_version bigint DEFAULT 0 NOT NULL,
    scenario_version_id bigint,
    title text,
    start_request_id uuid,
    preferences jsonb DEFAULT '{}'::jsonb NOT NULL,
    persona jsonb DEFAULT '{}'::jsonb NOT NULL,
    parent_conversation_id integer,
    fork_message_id integer,
    start_request_payload jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: conversations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.conversations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: conversations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.conversations_id_seq OWNED BY public.conversations.id;


--
-- Name: event_outbox; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event_outbox (
    id bigint NOT NULL,
    subject text NOT NULL,
    payload bytea NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    event_key text
);


--
-- Name: event_outbox_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.event_outbox_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: event_outbox_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.event_outbox_id_seq OWNED BY public.event_outbox.id;


--
-- Name: game_states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.game_states (
    conversation_id integer NOT NULL,
    inventory jsonb DEFAULT '[]'::jsonb NOT NULL,
    relationships jsonb DEFAULT '{}'::jsonb NOT NULL,
    quest_flags text[] DEFAULT '{}'::text[] NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    schema_version integer DEFAULT 1 NOT NULL,
    runtime jsonb DEFAULT '{"characters": {}, "clock_minutes": 0, "executed_rules": [], "quest_progress": {}}'::jsonb NOT NULL,
    CONSTRAINT inventory_array CHECK ((jsonb_typeof(inventory) = 'array'::text)),
    CONSTRAINT relationships_object CHECK ((jsonb_typeof(relationships) = 'object'::text)),
    CONSTRAINT runtime_object CHECK ((jsonb_typeof(runtime) = 'object'::text)),
    CONSTRAINT supported_state_schema CHECK ((schema_version = 1))
);


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    id uuid NOT NULL,
    turn_id uuid NOT NULL,
    stage text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    payload jsonb NOT NULL,
    owner uuid,
    fence bigint DEFAULT 0 NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    lease_until timestamp with time zone,
    available_at timestamp with time zone DEFAULT now() NOT NULL,
    last_notified_at timestamp with time zone,
    last_error text,
    result jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT jobs_stage_check CHECK ((stage = ANY (ARRAY['validate'::text, 'actor'::text, 'director'::text]))),
    CONSTRAINT jobs_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'completed'::text, 'dead'::text])))
);


--
-- Name: lore_checkpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lore_checkpoints (
    lore_id integer NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: lorebook; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lorebook (
    id integer NOT NULL,
    scenario_id integer NOT NULL,
    keyword character varying(50) NOT NULL,
    description text NOT NULL,
    category character varying(50),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: lorebook_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.lorebook_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: lorebook_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.lorebook_id_seq OWNED BY public.lorebook.id;


--
-- Name: memory_blocks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memory_blocks (
    conversation_id integer NOT NULL,
    start_id integer NOT NULL,
    end_id integer NOT NULL,
    summary text NOT NULL,
    model_version text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: memory_checkpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memory_checkpoints (
    conversation_id integer NOT NULL,
    last_message_id integer DEFAULT 0 NOT NULL,
    generation bigint DEFAULT 0 NOT NULL
);


--
-- Name: memory_fact_revisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memory_fact_revisions (
    id bigint NOT NULL,
    conversation_id integer NOT NULL,
    fact_key text NOT NULL,
    content text NOT NULL,
    kind text NOT NULL,
    source_message_id integer NOT NULL
);


--
-- Name: memory_fact_revisions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.memory_fact_revisions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memory_fact_revisions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.memory_fact_revisions_id_seq OWNED BY public.memory_fact_revisions.id;


--
-- Name: memory_facts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memory_facts (
    id bigint NOT NULL,
    conversation_id integer NOT NULL,
    fact_key text NOT NULL,
    content text NOT NULL,
    kind text NOT NULL,
    source_message_id integer NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    pinned boolean DEFAULT false NOT NULL,
    suppressed boolean DEFAULT false NOT NULL,
    manual boolean DEFAULT false NOT NULL,
    known_by text[],
    CONSTRAINT memory_facts_kind_check CHECK ((kind = ANY (ARRAY['fact'::text, 'promise'::text, 'goal'::text, 'relationship'::text])))
);


--
-- Name: memory_facts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.memory_facts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memory_facts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.memory_facts_id_seq OWNED BY public.memory_facts.id;


--
-- Name: memory_notes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memory_notes (
    id bigint NOT NULL,
    conversation_id integer NOT NULL,
    content text NOT NULL,
    pinned boolean DEFAULT true NOT NULL
);


--
-- Name: memory_notes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.memory_notes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memory_notes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.memory_notes_id_seq OWNED BY public.memory_notes.id;


--
-- Name: memory_reconciliation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memory_reconciliation (
    collection text NOT NULL,
    cursor text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id integer NOT NULL,
    conversation_id integer NOT NULL,
    sender character varying(10) NOT NULL,
    content text NOT NULL,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    event_id text,
    revision_of integer,
    superseded boolean DEFAULT false NOT NULL,
    CONSTRAINT messages_sender_check CHECK (((sender)::text = ANY (ARRAY[('user'::character varying)::text, ('ai'::character varying)::text, ('director'::character varying)::text, ('system'::character varying)::text])))
);


--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
-- Name: player_personas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.player_personas (
    id bigint NOT NULL,
    user_id integer NOT NULL,
    name text NOT NULL,
    definition jsonb NOT NULL
);


--
-- Name: player_personas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.player_personas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: player_personas_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.player_personas_id_seq OWNED BY public.player_personas.id;


--
-- Name: request_limits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.request_limits (
    key text NOT NULL,
    bucket bigint NOT NULL,
    count integer NOT NULL
);


--
-- Name: scenario_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scenario_versions (
    id bigint NOT NULL,
    scenario_id integer NOT NULL,
    version integer NOT NULL,
    definition jsonb NOT NULL,
    published boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    search_document tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, ((((((COALESCE((definition ->> 'title'::text), ''::text) || ' '::text) || COALESCE((definition ->> 'introduction'::text), ''::text)) || ' '::text) || COALESCE((definition ->> 'place'::text), ''::text)) || ' '::text) || COALESCE((jsonb_path_query_array(definition, '$."cast"[*]."name"'::jsonpath))::text, ''::text)))) STORED
);


--
-- Name: scenario_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.scenario_versions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scenario_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.scenario_versions_id_seq OWNED BY public.scenario_versions.id;


--
-- Name: scenarios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scenarios (
    id integer NOT NULL,
    user_id integer NOT NULL,
    title character varying(100) NOT NULL,
    greeting text,
    place text,
    "time" text,
    introduction text,
    is_public boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    rules jsonb DEFAULT '{"flags": [], "items": {}, "times": [], "locations": [], "world_events": []}'::jsonb NOT NULL,
    deleted_at timestamp with time zone,
    initial_state jsonb DEFAULT '{}'::jsonb NOT NULL,
    discovery jsonb DEFAULT '{"tones": [], "genres": [], "life_stage": "any"}'::jsonb NOT NULL,
    CONSTRAINT scenario_discovery_object CHECK ((jsonb_typeof(discovery) = 'object'::text))
);


--
-- Name: scenarios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.scenarios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scenarios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.scenarios_id_seq OWNED BY public.scenarios.id;


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version text NOT NULL,
    checksum text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: state_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.state_events (
    id bigint NOT NULL,
    conversation_id integer NOT NULL,
    turn_id uuid,
    operation_id text NOT NULL,
    state_version bigint NOT NULL,
    snapshot jsonb NOT NULL,
    changes jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: state_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.state_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: state_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.state_events_id_seq OWNED BY public.state_events.id;


--
-- Name: turn_checkpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.turn_checkpoints (
    turn_id uuid NOT NULL,
    phase text NOT NULL,
    snapshot jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT turn_checkpoints_phase_check CHECK ((phase = ANY (ARRAY['before_reply'::text, 'after_turn'::text])))
);


--
-- Name: turns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.turns (
    id uuid NOT NULL,
    conversation_id integer NOT NULL,
    request_id uuid NOT NULL,
    user_message_id integer,
    content text NOT NULL,
    user_id integer NOT NULL,
    status text NOT NULL,
    state_version bigint NOT NULL,
    failure text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT turns_status_check CHECK ((status = ANY (ARRAY['validating'::text, 'generating'::text, 'narrating'::text, 'completed'::text, 'blocked'::text, 'failed'::text])))
);


--
-- Name: user_preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_preferences (
    user_id integer NOT NULL,
    settings jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(50) NOT NULL,
    password_hash character varying(255) NOT NULL,
    email character varying(100),
    api_key character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    api_key_hashed boolean DEFAULT false NOT NULL
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: version_lore_checkpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.version_lore_checkpoints (
    version_id bigint NOT NULL,
    next_offset integer DEFAULT 0 NOT NULL,
    CONSTRAINT version_lore_checkpoints_next_offset_check CHECK ((next_offset >= 0))
);


--
-- Name: websocket_tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.websocket_tickets (
    digest text NOT NULL,
    user_id integer NOT NULL,
    conversation_id integer NOT NULL,
    expires_at timestamp with time zone NOT NULL
);


--
-- Name: characters id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.characters ALTER COLUMN id SET DEFAULT nextval('public.characters_id_seq'::regclass);


--
-- Name: conversations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations ALTER COLUMN id SET DEFAULT nextval('public.conversations_id_seq'::regclass);


--
-- Name: event_outbox id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_outbox ALTER COLUMN id SET DEFAULT nextval('public.event_outbox_id_seq'::regclass);


--
-- Name: lorebook id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lorebook ALTER COLUMN id SET DEFAULT nextval('public.lorebook_id_seq'::regclass);


--
-- Name: memory_fact_revisions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_fact_revisions ALTER COLUMN id SET DEFAULT nextval('public.memory_fact_revisions_id_seq'::regclass);


--
-- Name: memory_facts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_facts ALTER COLUMN id SET DEFAULT nextval('public.memory_facts_id_seq'::regclass);


--
-- Name: memory_notes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_notes ALTER COLUMN id SET DEFAULT nextval('public.memory_notes_id_seq'::regclass);


--
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- Name: player_personas id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_personas ALTER COLUMN id SET DEFAULT nextval('public.player_personas_id_seq'::regclass);


--
-- Name: scenario_versions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scenario_versions ALTER COLUMN id SET DEFAULT nextval('public.scenario_versions_id_seq'::regclass);


--
-- Name: scenarios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scenarios ALTER COLUMN id SET DEFAULT nextval('public.scenarios_id_seq'::regclass);


--
-- Name: state_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_events ALTER COLUMN id SET DEFAULT nextval('public.state_events_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: catalog_terms catalog_terms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.catalog_terms
    ADD CONSTRAINT catalog_terms_pkey PRIMARY KEY (kind, slug);


--
-- Name: catalog_vector_checkpoints catalog_vector_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.catalog_vector_checkpoints
    ADD CONSTRAINT catalog_vector_checkpoints_pkey PRIMARY KEY (version_id);


--
-- Name: characters characters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.characters
    ADD CONSTRAINT characters_pkey PRIMARY KEY (id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: event_outbox event_outbox_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_outbox
    ADD CONSTRAINT event_outbox_pkey PRIMARY KEY (id);


--
-- Name: game_states game_states_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.game_states
    ADD CONSTRAINT game_states_pkey PRIMARY KEY (conversation_id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);


--
-- Name: jobs jobs_turn_id_stage_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_turn_id_stage_key UNIQUE (turn_id, stage);


--
-- Name: lore_checkpoints lore_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lore_checkpoints
    ADD CONSTRAINT lore_checkpoints_pkey PRIMARY KEY (lore_id);


--
-- Name: lorebook lorebook_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lorebook
    ADD CONSTRAINT lorebook_pkey PRIMARY KEY (id);


--
-- Name: memory_blocks memory_blocks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_blocks
    ADD CONSTRAINT memory_blocks_pkey PRIMARY KEY (conversation_id, start_id, end_id);


--
-- Name: memory_checkpoints memory_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_checkpoints
    ADD CONSTRAINT memory_checkpoints_pkey PRIMARY KEY (conversation_id);


--
-- Name: memory_fact_revisions memory_fact_revisions_conversation_id_fact_key_source_messa_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_fact_revisions
    ADD CONSTRAINT memory_fact_revisions_conversation_id_fact_key_source_messa_key UNIQUE (conversation_id, fact_key, source_message_id);


--
-- Name: memory_fact_revisions memory_fact_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_fact_revisions
    ADD CONSTRAINT memory_fact_revisions_pkey PRIMARY KEY (id);


--
-- Name: memory_facts memory_facts_conversation_id_fact_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_facts
    ADD CONSTRAINT memory_facts_conversation_id_fact_key_key UNIQUE (conversation_id, fact_key);


--
-- Name: memory_facts memory_facts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_facts
    ADD CONSTRAINT memory_facts_pkey PRIMARY KEY (id);


--
-- Name: memory_notes memory_notes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_notes
    ADD CONSTRAINT memory_notes_pkey PRIMARY KEY (id);


--
-- Name: memory_reconciliation memory_reconciliation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_reconciliation
    ADD CONSTRAINT memory_reconciliation_pkey PRIMARY KEY (collection);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: player_personas player_personas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_personas
    ADD CONSTRAINT player_personas_pkey PRIMARY KEY (id);


--
-- Name: request_limits request_limits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.request_limits
    ADD CONSTRAINT request_limits_pkey PRIMARY KEY (key, bucket);


--
-- Name: scenario_versions scenario_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scenario_versions
    ADD CONSTRAINT scenario_versions_pkey PRIMARY KEY (id);


--
-- Name: scenario_versions scenario_versions_scenario_id_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scenario_versions
    ADD CONSTRAINT scenario_versions_scenario_id_version_key UNIQUE (scenario_id, version);


--
-- Name: scenarios scenarios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scenarios
    ADD CONSTRAINT scenarios_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: state_events state_events_conversation_id_state_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_events
    ADD CONSTRAINT state_events_conversation_id_state_version_key UNIQUE (conversation_id, state_version);


--
-- Name: state_events state_events_operation_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_events
    ADD CONSTRAINT state_events_operation_id_key UNIQUE (operation_id);


--
-- Name: state_events state_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_events
    ADD CONSTRAINT state_events_pkey PRIMARY KEY (id);


--
-- Name: turn_checkpoints turn_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turn_checkpoints
    ADD CONSTRAINT turn_checkpoints_pkey PRIMARY KEY (turn_id, phase);


--
-- Name: turns turns_conversation_id_request_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turns
    ADD CONSTRAINT turns_conversation_id_request_id_key UNIQUE (conversation_id, request_id);


--
-- Name: turns turns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turns
    ADD CONSTRAINT turns_pkey PRIMARY KEY (id);


--
-- Name: user_preferences user_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT user_preferences_pkey PRIMARY KEY (user_id);


--
-- Name: users users_api_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_api_key_key UNIQUE (api_key);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: version_lore_checkpoints version_lore_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.version_lore_checkpoints
    ADD CONSTRAINT version_lore_checkpoints_pkey PRIMARY KEY (version_id);


--
-- Name: websocket_tickets websocket_tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.websocket_tickets
    ADD CONSTRAINT websocket_tickets_pkey PRIMARY KEY (digest);


--
-- Name: conversation_library; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX conversation_library ON public.conversations USING btree (user_id, updated_at DESC, id DESC);


--
-- Name: conversation_start_request; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX conversation_start_request ON public.conversations USING btree (user_id, start_request_id);


--
-- Name: idx_characters_is_ai; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_characters_is_ai ON public.characters USING btree (scenario_id, is_ai);


--
-- Name: idx_characters_scenario_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_characters_scenario_id ON public.characters USING btree (scenario_id);


--
-- Name: idx_conversations_scenario_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_scenario_id ON public.conversations USING btree (scenario_id);


--
-- Name: idx_conversations_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_status ON public.conversations USING btree (status);


--
-- Name: idx_conversations_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_user_id ON public.conversations USING btree (user_id);


--
-- Name: idx_lorebook_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lorebook_category ON public.lorebook USING btree (category);


--
-- Name: idx_lorebook_keyword; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lorebook_keyword ON public.lorebook USING btree (keyword);


--
-- Name: idx_lorebook_scenario_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lorebook_scenario_id ON public.lorebook USING btree (scenario_id);


--
-- Name: idx_messages_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_conversation_id ON public.messages USING btree (conversation_id);


--
-- Name: idx_messages_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_created_at ON public.messages USING btree (created_at);


--
-- Name: idx_scenarios_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scenarios_user_id ON public.scenarios USING btree (user_id);


--
-- Name: idx_users_api_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_api_key ON public.users USING btree (api_key);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_email ON public.users USING btree (email);


--
-- Name: idx_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_username ON public.users USING btree (username);


--
-- Name: jobs_recovery; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX jobs_recovery ON public.jobs USING btree (status, available_at, lease_until);


--
-- Name: messages_conversation_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX messages_conversation_order ON public.messages USING btree (conversation_id, id);


--
-- Name: messages_event_id_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX messages_event_id_unique ON public.messages USING btree (event_id);


--
-- Name: one_active_turn; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX one_active_turn ON public.turns USING btree (conversation_id) WHERE (status = ANY (ARRAY['validating'::text, 'generating'::text, 'narrating'::text]));


--
-- Name: outbox_event_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX outbox_event_key ON public.event_outbox USING btree (event_key) WHERE (event_key IS NOT NULL);


--
-- Name: scenario_version_discovery; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scenario_version_discovery ON public.scenario_versions USING gin (((definition -> 'discovery'::text))) WHERE published;


--
-- Name: scenario_version_search; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scenario_version_search ON public.scenario_versions USING gin (search_document) WHERE published;


--
-- Name: characters update_characters_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_characters_updated_at BEFORE UPDATE ON public.characters FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: conversations update_conversations_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_conversations_updated_at BEFORE UPDATE ON public.conversations FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: game_states update_game_states_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_game_states_updated_at BEFORE UPDATE ON public.game_states FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: lorebook update_lorebook_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_lorebook_updated_at BEFORE UPDATE ON public.lorebook FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: scenarios update_scenarios_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_scenarios_updated_at BEFORE UPDATE ON public.scenarios FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: users update_users_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: catalog_vector_checkpoints catalog_vector_checkpoints_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.catalog_vector_checkpoints
    ADD CONSTRAINT catalog_vector_checkpoints_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.scenario_versions(id) ON DELETE CASCADE;


--
-- Name: characters characters_scenario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.characters
    ADD CONSTRAINT characters_scenario_id_fkey FOREIGN KEY (scenario_id) REFERENCES public.scenarios(id) ON DELETE CASCADE;


--
-- Name: conversations conversations_parent_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_parent_conversation_id_fkey FOREIGN KEY (parent_conversation_id) REFERENCES public.conversations(id) ON DELETE SET NULL;


--
-- Name: conversations conversations_scenario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_scenario_id_fkey FOREIGN KEY (scenario_id) REFERENCES public.scenarios(id) ON DELETE CASCADE;


--
-- Name: conversations conversations_scenario_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_scenario_version_id_fkey FOREIGN KEY (scenario_version_id) REFERENCES public.scenario_versions(id);


--
-- Name: conversations conversations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: game_states game_states_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.game_states
    ADD CONSTRAINT game_states_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: jobs jobs_turn_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_turn_id_fkey FOREIGN KEY (turn_id) REFERENCES public.turns(id) ON DELETE CASCADE;


--
-- Name: lore_checkpoints lore_checkpoints_lore_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lore_checkpoints
    ADD CONSTRAINT lore_checkpoints_lore_id_fkey FOREIGN KEY (lore_id) REFERENCES public.lorebook(id) ON DELETE CASCADE;


--
-- Name: lorebook lorebook_scenario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lorebook
    ADD CONSTRAINT lorebook_scenario_id_fkey FOREIGN KEY (scenario_id) REFERENCES public.scenarios(id) ON DELETE CASCADE;


--
-- Name: memory_blocks memory_blocks_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_blocks
    ADD CONSTRAINT memory_blocks_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: memory_checkpoints memory_checkpoints_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_checkpoints
    ADD CONSTRAINT memory_checkpoints_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: memory_fact_revisions memory_fact_revisions_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_fact_revisions
    ADD CONSTRAINT memory_fact_revisions_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: memory_fact_revisions memory_fact_revisions_source_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_fact_revisions
    ADD CONSTRAINT memory_fact_revisions_source_message_id_fkey FOREIGN KEY (source_message_id) REFERENCES public.messages(id) ON DELETE CASCADE;


--
-- Name: memory_facts memory_facts_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_facts
    ADD CONSTRAINT memory_facts_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: memory_facts memory_facts_source_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_facts
    ADD CONSTRAINT memory_facts_source_message_id_fkey FOREIGN KEY (source_message_id) REFERENCES public.messages(id) ON DELETE CASCADE;


--
-- Name: memory_notes memory_notes_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_notes
    ADD CONSTRAINT memory_notes_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: messages messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: messages messages_revision_of_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_revision_of_fkey FOREIGN KEY (revision_of) REFERENCES public.messages(id) ON DELETE SET NULL;


--
-- Name: player_personas player_personas_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_personas
    ADD CONSTRAINT player_personas_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: scenario_versions scenario_versions_scenario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scenario_versions
    ADD CONSTRAINT scenario_versions_scenario_id_fkey FOREIGN KEY (scenario_id) REFERENCES public.scenarios(id) ON DELETE CASCADE;


--
-- Name: scenarios scenarios_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scenarios
    ADD CONSTRAINT scenarios_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: state_events state_events_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_events
    ADD CONSTRAINT state_events_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: state_events state_events_turn_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_events
    ADD CONSTRAINT state_events_turn_id_fkey FOREIGN KEY (turn_id) REFERENCES public.turns(id) ON DELETE SET NULL;


--
-- Name: turn_checkpoints turn_checkpoints_turn_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turn_checkpoints
    ADD CONSTRAINT turn_checkpoints_turn_id_fkey FOREIGN KEY (turn_id) REFERENCES public.turns(id) ON DELETE CASCADE;


--
-- Name: turns turns_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turns
    ADD CONSTRAINT turns_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: turns turns_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turns
    ADD CONSTRAINT turns_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: turns turns_user_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turns
    ADD CONSTRAINT turns_user_message_id_fkey FOREIGN KEY (user_message_id) REFERENCES public.messages(id) ON DELETE SET NULL;


--
-- Name: user_preferences user_preferences_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT user_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: version_lore_checkpoints version_lore_checkpoints_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.version_lore_checkpoints
    ADD CONSTRAINT version_lore_checkpoints_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.scenario_versions(id) ON DELETE CASCADE;


--
-- Name: websocket_tickets websocket_tickets_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.websocket_tickets
    ADD CONSTRAINT websocket_tickets_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: websocket_tickets websocket_tickets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.websocket_tickets
    ADD CONSTRAINT websocket_tickets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--



-- Discovery configuration; no user content or credentials.
INSERT INTO public.catalog_terms(kind,slug,label,description,aliases,position,active,requires_adult_cast) VALUES ('gender','female','Female','','{female,woman,women}',10,true,false),
('gender','male','Male','','{male,man,men}',20,true,false),
('gender','nonbinary','Nonbinary','','{nonbinary,non-binary,"non binary",enby}',30,true,false),
('gender','unspecified','Not specified','','{""}',40,true,false),
('genre','adventure','Adventure','','{}',50,true,false),
('genre','comedy','Comedy','','{}',80,true,false),
('genre','drama','Drama','','{}',70,true,false),
('genre','fantasy','Fantasy','','{}',20,true,false),
('genre','historical','Historical','','{}',90,true,false),
('genre','mystery','Mystery','','{}',40,true,false),
('genre','romance','Romance','','{}',10,true,true),
('genre','sci_fi','Science fiction','','{}',60,true,false),
('genre','slice_of_life','Slice of life','','{}',30,true,false),
('life_stage','adult','Adult life','','{}',30,true,true),
('life_stage','any','Any life stage','','{}',0,true,false),
('life_stage','young_adult','Young adults (18+)','University life, first jobs and first love with adult characters.','{}',20,true,true),
('life_stage','youthful','Youthful themes','','{}',10,true,false),
('tone','cozy','Cozy','','{}',10,true,false),
('tone','dramatic','Dramatic','','{}',40,true,false),
('tone','lighthearted','Lighthearted','','{}',30,true,false),
('tone','slow_burn','Slow burn','','{}',20,true,false),
('tone','suspenseful','Suspenseful','','{}',50,true,false);

-- Register the schema versions already included above.
INSERT INTO public.schema_migrations(version,checksum) VALUES
    ('001_reliability.sql', 'ab5ba177d63e849188f4d8cf0d4828424650193aaeef9022d2fa34f991d7ed76'),
    ('002_durable_turns.sql', '94e147f82ebab868a8eae10856f7a80d82635f30908c5779951d2725cc466e07'),
    ('003_memory_and_rules.sql', '89fa4add952ce48ef27ad4f5de12447dabe611b37f27dd56e28447c84eacd624'),
    ('004_playthroughs.sql', 'f54f9eb69c2e3827452c31eb133a8f3d3fe861e6130cdc0135244dbea5d6ac08'),
    ('005_playthrough_integrity.sql', '6ec982f392c63d7118cef0b8fe989b83641a790b0a2b4e42b0f9a4582b88107e'),
    ('006_start_contract.sql', '1e51f96d840d137aac74239aa809a26f39bbe2d8d2760a82cba245e4a6cea882'),
    ('007_state_constraints.sql', 'ff8ea388d0f541afd4d7661f17366bac6cc8082d9a2d015d295498efb60ff971'),
    ('008_version_lore_index.sql', '63e14febc39bf61653f2fb4b1ce15d15528e4e8a6fee6521716d402d6441e672'),
    ('009_turn_checkpoints.sql', 'e4e32a2329ad065c0dc71ef32f53ff5da4b2ed2f322cba68708a7ab06dc9bcf5'),
    ('010_catalog_discovery.sql', '4137825900d7d44598cd61babb1a4ca1b9445229a18e08d028862ec043743285'),
    ('011_semantic_catalog.sql', '436349aeab21d7034ac228663536dee50f6df0b15522bdbbf4a7fb8fb2deef4b');
COMMIT;
