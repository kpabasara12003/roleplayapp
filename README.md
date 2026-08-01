# Multi-Agent Real-Time Roleplay Engine

A decoupled, event-driven microservice architecture for hosting immersive, AI-driven text roleplaying experiences. This system leverages WebSockets for real-time streaming, Core NATS JetStream for pub/sub messaging and RPC, PostgreSQL for strict state management, and Qdrant for Retrieval-Augmented Generation (RAG) long-term memory.

---

## Architecture Overview

The platform is designed around a central FastAPI WebSocket gateway that routes asynchronous events to specialized backend AI agents. By decoupling the architecture, each agent scales independently and communicates strictly through NATS topics, ensuring high availability and clean separation of concerns.

### Tech Stack

* **Backend Framework:** FastAPI (Python)
* **Message Broker & RPC:** NATS / NATS JetStream
* **Relational Database:** PostgreSQL (Game states, chat logs, user data)
* **Vector Database:** Qdrant (Long-term memory, lorebook, RAG)
* **Data Validation:** Pydantic

---

## Core Microservices

### 1. Main Gateway (`fastapi_server`)

Acts as the edge router for client connections.

* Manages stateful WebSocket tunnels for real-time text streaming.
* Uses NATS JetStream to track stream sequences, allowing clients to recover missed messages upon reconnection (`DeliverPolicy.BY_START_SEQUENCE`).
* Intercepts inbound user messages and routes them through the Director Agent's RPC gate before persisting changes via the Game Engine.

### 2. Director Agent (`director_agent`)

The dungeon master and rules engine.

* **Action Validation:** Listens to NATS RPC (`roleplay.director.validate_action`) to evaluate if a user's action is logically permitted within the current scenario.
* **State Mutation:** Generates validated Pydantic models mapping out game state changes (e.g., inventory additions, affinity shifts, quest updates) to be applied to PostgreSQL.
* **Environmental Interventions:** Periodically generates autonomous world updates and sensory descriptions, broadcasting them back to the chat stream.

### 3. Actor Agent (`actor_agent`)

The persona engine responsible for generating character dialogue.

* Ingests strict system prompts detailing character persona, scenario context, and user traits.
* Receives passive background lore from Qdrant RAG queries, bound by strict instruction guardrails to prevent unprompted "lore dumping."
* Streams token-by-token character responses back to the frontend over NATS, strictly adhering to roleplay formatting (italics for actions, plain text for dialogue) and token length limits to prevent mid-sentence cutoffs.

### 4. Chronicler Agent (`chronicler_agent`)

The background data pipeline and archivist.

* **Real-time Logging:** Listens to all user, AI, and Director messages, securely persisting them into the PostgreSQL `messages` table.
* **Automated Summarization:** Monitors conversation lengths and automatically triggers LLM-driven summaries of message blocks.
* **Vector Storage:** Converts summaries into deterministic UUIDv5 payloads and indexes them into Qdrant (`lorebook` collection) for future retrieval by the Actor Agent.

---

## Key Features

* **Event-Driven Streaming:** Zero-polling architecture. Responses flow directly from LLM inference through NATS to the user's browser via WebSockets.
* **Strict State Management:** Uses PostgreSQL `ON CONFLICT DO UPDATE` constraints and Pydantic validation to ensure game logic (inventory, relationships) never corrupts.
* **Memory Catch-Up:** In-memory tracking ensures that if the Chronicler service restarts, it retroactively processes un-summarized chat logs to prevent amnesia.
* **RAG Guardrails:** Specialized prompt engineering prevents the AI Actor from hallucinating retrieved vector context directly into the chat unless logically triggered.

---

## Prerequisites

* Python 3.10+
* PostgreSQL 15+
* Qdrant
* BGM3 
* NATS Server with JetStream enabled

---

## Database Initialization

Ensure your PostgreSQL `messages` table schema accommodates all required sender types to avoid `CHECK` constraint violations:

```sql
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_sender_check;
ALTER TABLE messages ADD CONSTRAINT messages_sender_check 
CHECK (sender IN ('user', 'ai', 'director', 'system'));

```

## Running the Architecture

Due to the microservice design, services should be started in the following order:

1. **Infrastructure:** Start PostgreSQL, Qdrant, and NATS.
2. **Main Gateway:** Boot the `fastapi_server` application.
3. **Background Agents:** Start the `chronicler_agent` to ensure no messages are missed.
4. **Active Agents:** Start the `director_agent` and `actor_agent`.
