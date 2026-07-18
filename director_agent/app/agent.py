#director_agent/app/agent.py
import os
import sys
import json
import httpx
import asyncio
import selectors
from typing import Optional, List, Any
from datetime import datetime
from nats.aio.client import Client as NATS

from shared.db.postgres import fetch_one, fetch_all, execute_returning
from shared.db.qdrant import embed_texts, search_similar, rerank_documents
from shared.utils.nats_client import NATSPublisher
from shared.utils.logger import get_logger
from director_agent.app.config import settings
from shared.schemas.engine import DirectorEvaluation, EngineMutation, MutationType

logger = get_logger(__name__)

def _build_evaluation_prompt(content: str, game_state: dict) -> str:
    """
    Builds a strict JSON-generation prompt for evaluating gameplay mutations and validating rule-checking (godmoding, item ownership, cheat prevention).
    """
    inventory_list = game_state.get("inventory", [])
    relationships = game_state.get("relationships", {})
    quest_flags = game_state.get("quest_flags", [])
    place = game_state.get("place", "Unknown")
    time = game_state.get("time", "Unknown")

    prompt = f"""You are the Game Engine Rules Director for an immersive roleplaying game.
Your task is to analyze the player's latest action against the current world state and determine two things:
1. Is the action legally allowed? (Set to false if the player is godmoding, cheating, acting impossibly, or trying to use/spend an item they do not possess in their inventory).
2. Does the action cause any game state mutations? (Adding/removing inventory items, shifting character affinity scores, triggering quest flags, or changing location/time).

=== Current World State ===
- Location: {place}
- Time: {time}
- Inventory: {json.dumps(inventory_list)}
- Relationships: {json.dumps(relationships)}
- Active Quest Flags: {json.dumps(quest_flags)}

=== Player Action ===
"{content}"

=== Instructions ===
Respond ONLY with a valid JSON object matching this exact schema:
{{
  "reasoning": "Briefly explain your logic for allowing/blocking the action and why mutations occurred.",
  "is_action_allowed": true,
  "failure_explanation": null,
  "mutations": [
    {{
      "type": "ITEM_ADDED | ITEM_REMOVED | AFFINITY_CHANGED | FLAG_TRIGGERED | LOCATION_CHANGED | TIME_CHANGED",
      "target": "Exact name of item, character, quest flag, or new location/time string",
      "description": "Short UI notice message (e.g., 'Found Rusty Key' or 'Evelyn liked that (+5 Affinity)')",
      "value_change": 1
    }}
  ]
}}
If no mutations occur and the action is normal, return an empty list `[]` for "mutations". Do not wrap your response in markdown code blocks if possible; output pure JSON."""
    return prompt


async def _evaluate_action(content: str, game_state: dict) -> DirectorEvaluation:
    """
    Executes a fast, non-streaming LLM call to evaluate game state mutations.
    Enforces a strict 3.2s timeout to prevent triggering FastAPI's 4.0s NATS RPC timeout.
    """
    prompt = _build_evaluation_prompt(content, game_state)
    messages = [
        {"role": "system", "content": "You are a strict game engine rules validator that outputs ONLY valid JSON."},
        {"role": "user", "content": prompt}
    ]

    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "max_tokens": 400,
        "temperature": 0.1,  # Low temperature for deterministic JSON structuring
        "stream": False,
        # Uncomment the line below if using OpenAI or vLLM to enforce JSON mode natively:
        # "response_format": {"type": "json_object"}
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.llm_api_key}",
    }

    try:
        #  FastAPI's 4.0s NATS request limit[cite: 2]
        async with httpx.AsyncClient(timeout=3.2) as client:
            resp = await client.post(settings.llm_api_url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            raw_content = data["choices"][0]["message"]["content"].strip()

            # Clean markdown code formatting if the LLM wraps JSON in ```json ... ```
            if raw_content.startswith("```"):
                raw_content = raw_content.strip("`").replace("json\n", "", 1).strip()

            parsed_dict = json.loads(raw_content)
            return DirectorEvaluation(**parsed_dict)

    except Exception as e:
        logger.warning("LLM action evaluation failed or timed out (falling back to default): %s", e)
        # Return a safe fallback schema so gameplay continues smoothly without crashing
        return DirectorEvaluation(
            reasoning="Action automatically accepted due to Director LLM evaluation timeout or syntax error.",
            is_action_allowed=True,
            failure_explanation="",
            mutations=[]
        )


def _build_director_prompt(
    scenario: dict,
    ai_char: dict,
    user_char: Optional[dict],
    current_place: str,
    current_time: str,
    recent_turns: List[dict],
) -> str:
    lines = [
        "You are the Director Agent, an omniscient narrator and world engine for an immersive roleplay system.",
        "Your job is to analyze the recent conversation history and determine if the physical environment, plot progression, or timeline needs to advance or react to the characters' actions.",
        "You do not speak as a character. You narrate environmental shifts, structural changes, external events, or secondary world reactions.",
        "",
        f"Active Scenario: {scenario.get('title', 'Untitled')}",
        f"Current Place Context: {current_place}",
        f"Current Time Context: {current_time}",
    ]
    if scenario.get("introduction"):
        lines.append(f"Scenario Rules/Context: {scenario['introduction']}")

    lines.extend([
        "",
        "=== Cast Profiles ===",
        f"AI Actor: {ai_char.get('name', 'Unknown')} ({ai_char.get('role_description', 'No explicit role')})",
    ])
    if user_char:
        lines.append(f"User Actor: {user_char.get('name', 'User')} ({user_char.get('role_description', 'No explicit role')})")

    lines.extend([
        "",
        "Instructions:",
        "- Evaluate the last few turns of dialogue.",
        "- If a structural world update is needed (e.g., characters moving locations, hours passing, a sudden weather change, or an unpredicted event occurring), write a descriptive narrative block.",
        "- Wrap all direct narrative interventions inside asterisks like **this** to maintain environmental narration styling.",
        "- Keep your interventions concise, impactful, and designed to propel the interaction forward.",
        "- If the scene is flowing naturally and requires absolutely zero external interference or environmental updates, respond with exactly: [NO_INTERVENTION]",
    ])
    return "\n".join(lines)


async def _stream_llm(messages: List[dict]):
    """
    Executes a streaming inference call for director narrations, yielding tokens 
    one by one with built-in exponential backoff for rate limits.
    """
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
        "stream": True,
    }
    
    max_retries = 4
    backoff_factor = 2.0
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.llm_api_key}",
    }

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", settings.llm_api_url, headers=headers, json=payload) as resp:
                    if resp.status_code == 429:
                        sleep_time = backoff_factor ** attempt
                        logger.warning("Director LLM returned 429 Rate Limit. Retrying in %.1fs...", sleep_time)
                        await asyncio.sleep(sleep_time)
                        continue
                    
                    resp.raise_for_status()
                    
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_json = json.loads(data_str)
                                token = chunk_json["choices"][0]["delta"].get("content", "")
                                if token:
                                    yield token
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
                    return
        except httpx.HTTPError as e:
            if attempt == max_retries - 1:
                logger.error("Director LLM pipeline failed permanently after maximum retries: %s", e)
                raise e
            await asyncio.sleep(backoff_factor ** attempt)


class DirectorAgent:
    def __init__(self):
        self.nats_publisher = NATSPublisher()

    async def run(self):
        """Bind consumer loops to JetStream and core NATS subjects."""
        await self.nats_publisher.connect()
        assert self.nats_publisher.js is not None
        nc = self.nats_publisher.nc

        # 1. Subscribe to the synchronous RPC validation gate
        rpc_sub = await nc.subscribe("roleplay.director.validate_action")
        logger.info("Director Agent listening for pre-flight RPC requests on 'roleplay.director.validate_action'")

        # 2. Subscribe to your existing background JetStream worker
        sub = await self.nats_publisher.js.subscribe(
            "roleplay.chat.ai_reply_completed", 
            durable="director_agent_stream_worker"
        )
        logger.info("Director Agent listening continuously on 'roleplay.chat.ai_reply_completed'")

        # Task to handle inbound RPC pre-flight checks concurrently
        async def handle_rpc_requests():
            async for msg in rpc_sub.messages:
                try:
                    req_data = json.loads(msg.data.decode())
                    content = req_data.get("content", "")
                    game_state = req_data.get("game_state", {})

                    #  SOLVED: Dynamically evaluate the action using the LLM & Pydantic schema
                    evaluation_model = await _evaluate_action(content, game_state)
                    
                    # Return the serialized model directly back over NATS RPC
                    await msg.respond(evaluation_model.model_dump_json().encode())
                except Exception as rpc_err:
                    logger.error("Failed to process validation RPC: %s", rpc_err)
                    # Safe schema fallback if serialization or communication fails
                    fallback = DirectorEvaluation(
                        reasoning="Fallback due to internal RPC processing exception.",
                        is_action_allowed=True,
                        mutations=[]
                    )
                    await msg.respond(fallback.model_dump_json().encode())

        # Fire off the RPC listener sub-loop background task
        asyncio.create_task(handle_rpc_requests())

        # 3. Your existing background stream worker main loop remains exactly the same
        while True:
            try:
                msg = await sub.next_msg(timeout=2.0)
                try:
                    data = json.loads(msg.data.decode()) if msg.data else {}
                    await self.handle_ai_reply_completed(data)
                    await msg.ack()
                except Exception as e:
                    logger.error("Error processing Director narrative pipeline: %s", e)
                    await msg.nak()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Director lifecycle main loop error caught: %s", e)
                await asyncio.sleep(2)

    async def handle_ai_reply_completed(self, data: dict):
        conversation_id = data.get("conversation_id")
        user_id = data.get("user_id")
        
        if not conversation_id:
            logger.error("Malformed Director NATS payload; missing 'conversation_id'")
            return

        try:
            # PIPELINE STATE 1: Broadcast 'evaluating_narrative' over ephemeral core NATS subjects
            await self._send_ui_state(conversation_id, "evaluating_narrative", "Director assessing environmental and scenario state updates...")

            # Pull system architecture metrics mapping
            conv = await fetch_one(
                """SELECT c.id, c.scenario_id, c.ai_character_id, c.user_character_id,
                          c.current_place, c."current_time", s.title, s.introduction
                   FROM conversations c 
                   JOIN scenarios s ON c.scenario_id = s.id WHERE c.id = %s
                """,
                (conversation_id,),
            )
            if not conv:
                logger.error("Aborting Director pass: Conversation ID %s not found in DB.", conversation_id)
                return

            # Resolve character asset sheets concurrently
            ai_char_task = fetch_one("SELECT * FROM characters WHERE id = %s", (conv["ai_character_id"],))
            user_char_task = (
                fetch_one("SELECT * FROM characters WHERE id = %s", (conv["user_character_id"],))
                if conv["user_character_id"] else asyncio.sleep(0, result=None)
            )
            ai_char, user_char = await asyncio.gather(ai_char_task, user_char_task)

            # Retrieve the latest conversation sequence window to check context metrics
            recent_messages = await fetch_all(
                """SELECT sender, content FROM messages
                   WHERE conversation_id = %s
                   ORDER BY created_at DESC LIMIT 6
                """,
                (conversation_id,),
            )
            recent_messages.reverse()

            # Compile context prompt blueprints
            system_prompt = _build_director_prompt(
                scenario=conv,
                ai_char=ai_char,
                user_char=user_char,
                current_place=conv["current_place"] or "Unknown",
                current_time=conv["current_time"] or "Unknown",
                recent_turns=recent_messages,
            )

            messages = [{"role": "system", "content": system_prompt}]
            for m in recent_messages:
                role = "user" if m["sender"] == "user" else "assistant"
                messages.append({"role": role, "content": m["content"]})

            # PIPELINE STATE 2: Process streaming narration if required
            full_narration_text = ""
            index = 0
            is_first_token = True
            should_stream_ui = True

            async for token in _stream_llm(messages):
                full_narration_text += token
                
                # Fast evaluation check: If the LLM bypasses changes, do not push blank stream frames to user UI
                if is_first_token:
                    is_first_token = False
                    if "[NO_INTERVENTION]" in full_narration_text or "NO_INTERVENTION" in full_narration_text:
                        should_stream_ui = False
                        break
                    # Trigger director typing bubble representation layout on frontend connection
                    await self._send_ui_state(conversation_id, "director_typing", "World state altering...")

                if should_stream_ui:
                    await self._send_ui_chunk(conversation_id, token, index)
                    index += 1

            # Clean tracking check evaluation handling
            if not should_stream_ui or "[NO_INTERVENTION]" in full_narration_text:
                logger.info("Director determined no environmental changes required for conversation_id=%s", conversation_id)
                await self._send_ui_state(conversation_id, "completed", "Narrative assessment complete. No world state change.")
                return

            # PIPELINE STATE 3: Hand off structural updates to Chronicler for database persistence out-of-band
            director_completed_payload = {
                "event": "director_intervention_completed",
                "conversation_id": conversation_id,
                "user_id": user_id,
                "content": full_narration_text.strip(),
                "metadata": {"director_version": "1.0-streaming", "intervention_executed": True},
                "timestamp": str(datetime.utcnow())
            }

            await self.nats_publisher.publish(
                "roleplay.chat.director_update_completed",
                json.dumps(director_completed_payload).encode()
            )

            # Signal transaction completion sequence cleanly to UI layers
            await self._send_ui_state(conversation_id, "completed", "Director world state adjustment parsed and distributed.")
            logger.info("Director intervention completed successfully for conversation_id=%s", conversation_id)

        except Exception as e:
            logger.error("Fatal failure running Director Agent processing loop segment: %s", e)
            await self._send_ui_error(conversation_id, str(e))

    async def _send_ui_state(self, conversation_id: int, state: str, message: str):
        packet = {
            "event": "director_state_change",
            "conversation_id": conversation_id,
            "timestamp": str(datetime.utcnow()),
            "payload": {
                "state": state,
                "message": message
            }
        }
        await self.nats_publisher.publish_ephemeral(
            f"roleplay.chat.stream.{conversation_id}", 
            json.dumps(packet).encode()
        )

    async def _send_ui_chunk(self, conversation_id: int, chunk: str, index: int):
        packet = {
            "event": "director_text_chunk",
            "conversation_id": conversation_id,
            "timestamp": str(datetime.utcnow()),
            "payload": {
                "chunk": chunk,
                "index": index
            }
        }
        await self.nats_publisher.publish_ephemeral(
            f"roleplay.chat.stream.{conversation_id}", 
            json.dumps(packet).encode()
        )

    async def _send_ui_error(self, conversation_id: int, error_msg: str):
        packet = {
            "event": "director_state_change",
            "conversation_id": conversation_id,
            "timestamp": str(datetime.utcnow()),
            "payload": {
                "state": "error",
                "error_detail": error_msg
            }
        }
        await self.nats_publisher.publish_ephemeral(
            f"roleplay.chat.stream.{conversation_id}", 
            json.dumps(packet).encode()
        )


if __name__ == "__main__":
    agent = DirectorAgent()
    try:
        if sys.platform == "win32":
            def win_loop_factory():
                return asyncio.SelectorEventLoop(selectors.SelectSelector())
            asyncio.run(agent.run(), loop_factory=win_loop_factory)
        else:
            asyncio.run(agent.run())
    except KeyboardInterrupt:
        logger.info("Director Agent shutting down cleanly via interface break request...")