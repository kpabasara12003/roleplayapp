# chronicler_agent/app/agent.py
import sys
import json
import uuid  
import asyncio
import selectors
from datetime import datetime, timezone

from shared.utils.nats_client import NATSPublisher
from qdrant_client.models import PointStruct
import psycopg.errors as pg_errors

from shared.db.postgres import fetch_one, fetch_all, execute_returning
from shared.db.qdrant import embed_texts, upsert_points
from shared.utils.logger import get_logger
from chronicler_agent.app.config import settings

logger = get_logger(__name__)

# A single unprocessable message must never be redelivered forever: that stalls this
# single-consumer loop and floods PostgreSQL / the log with the same failure.
MAX_DELIVERY_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 5.0

# Subjects this worker publishes itself (UI confirmations, engine state echoes).
# Re-consuming them is pure noise and a poison-message risk.
_IGNORED_SUBJECT_PREFIXES = (
    "roleplay.chat.stream.",
    "roleplay.chat.engine.",
)

# Errors where retrying the exact same payload can never succeed.
_PERMANENT_DB_ERRORS = (
    pg_errors.IntegrityError,   # FK / NOT NULL / CHECK / UNIQUE violations
    pg_errors.DataError,        # malformed or out-of-range values
    pg_errors.UndefinedTable,
    pg_errors.UndefinedColumn,
)


def _is_permanent_error(exc: BaseException) -> bool:
    """Return True when re-delivering the same message can only fail again."""
    if isinstance(exc, json.JSONDecodeError):
        return True
    return isinstance(exc, _PERMANENT_DB_ERRORS)


class ChroniclerAgent:
    def __init__(self):
        self.nats_publisher = NATSPublisher()

    async def _get_message_count(self, conversation_id: int) -> int:
        row = await fetch_one(
            "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = %s",
            (conversation_id,),
        )
        return row["cnt"] if row else 0

    async def _persist_message(self, conversation_id: int, sender: str, content: str, metadata: dict) -> int | None:
        """Idempotently insert a chat message.

        On a JetStream redelivery (nak/retry) the same payload is processed again;
        without a guard this produced duplicate rows. We skip the insert when an
        identical (conversation, sender, content) row already exists and reuse its id.
        """
        meta_json = json.dumps(metadata)
        event_id = metadata.get("event_id")
        msg = await execute_returning(
            """INSERT INTO messages (conversation_id, sender, content, metadata, event_id)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (event_id) DO UPDATE SET event_id=EXCLUDED.event_id RETURNING id""",
            (conversation_id, sender, content, meta_json, event_id),
        )
        return msg["id"] if msg else None

    async def _summarize_range(self, conversation_id: int, ids: list) -> str:
        rows = await fetch_all(
            """
            SELECT sender, content FROM messages
            WHERE conversation_id = %s AND id = ANY(%s)
            ORDER BY id ASC
            """,
            (conversation_id, ids),
        )
        parts = []
        for r in rows:
            prefix = r["sender"].capitalize()
            parts.append(f"{prefix}: {r['content']}")
        summary = " | ".join(parts)
        return summary

    async def handle_message(self, data: dict, subject: str):
        """Processes transactional storage entries and synchronizes client caches."""
        # Skip our own UI confirmations / engine echoes; they never carry a chat row.
        if subject.startswith(_IGNORED_SUBJECT_PREFIXES):
            return

        event = data.get("event")
        conversation_id = data.get("conversation_id")
        user_id = data.get("user_id")
        content = data.get("content", "").strip()

        if not conversation_id:
            logger.warning("Dropped an un-routable pipeline log frame due to missing conversation identifiers.")
            return
        if not await fetch_one('SELECT id FROM conversations WHERE id=%s',(conversation_id,)):
            # Historical broker events may outlive an intentionally deleted session.
            return

        message_saved = False
        inserted_msg_id = None
        sender_type = None

        # CASE 1: Inbound User Message Handling
        if event == "user_message" or "user_message" in subject:
            sender_type = "user"
            if "message_id" not in data:
                logger.info("Offloading WebSocket user string commit for conversation_id=%s", conversation_id)
                new_id = await self._persist_message(conversation_id, "user", content, {"source": "ws"})
                if new_id:
                    inserted_msg_id = new_id
                    message_saved = True
            else:
                inserted_msg_id = data["message_id"]
                message_saved = True

        # CASE 2: Finished AI Generation Handling
        elif event == "ai_message_completed" or "ai_reply_completed" in subject:
            sender_type = "ai"
            logger.info("Persisting completely formulated AI generation block for conversation_id=%s", conversation_id)
            metadata = {**data.get("metadata", {}), "event_id": data.get("event_id")}

            new_id = await self._persist_message(conversation_id, "ai", content, metadata)
            if new_id:
                inserted_msg_id = new_id
                message_saved = True

        # CASE 3: Director Intervention Handling (FIXED: Now Saved to DB!)
        elif event == "director_intervention_completed" or "director_update_completed" in subject:
            sender_type = "director"
            logger.info("Persisting Director environmental world update for conversation_id=%s", conversation_id)
            metadata = {**data.get("metadata", {}), "event_id": data.get("event_id")}

            new_id = await self._persist_message(conversation_id, "director", content, metadata)
            if new_id:
                inserted_msg_id = new_id
                message_saved = True

        # POST-WRITE: Interface Synchronization & Summarization Evaluate
        if message_saved and inserted_msg_id:
            # (The Director is triggered by the Actor's 'roleplay.chat.ai_reply_completed'
            # event, which carries the full reply text; this Chronicler publish was a
            # no-op because nothing subscribes to 'roleplay.chat.ai_response.*'.)

            # Send database index resolution back to the user via the fast durable channel
            await self._send_ui_confirmation(conversation_id, inserted_msg_id, sender_type, content)
            
            # Evaluate if the active message history requires long-term compression/upsert
            # Background indexing is independent of durable chat writes.

    async def _send_ui_confirmation(self, conversation_id: int, message_id: int, sender: str, content: str):
        """Notifies frontend sockets that raw stream contents are safely hard-indexed."""
        packet = {
            "event": "message_completed",
            "conversation_id": conversation_id,
            "payload": {
                "message_id": message_id,
                "sender": sender,
                "full_content": content
            }
        }
        
        # Durable publish forces NATS JetStream to track this packet and assign a sequence id.
        await self.nats_publisher.publish(
            f"roleplay.chat.stream.{conversation_id}", 
            json.dumps(packet).encode()
        )

    async def _check_and_trigger_summarization(self, conversation_id):
        from shared.utils.memory_index import index_conversation
        await index_conversation(conversation_id,settings.summarize_every_n)

    async def _dead_letter(self, msg, error: BaseException):
        """Park an unprocessable message so it can be inspected instead of retried forever."""
        try:
            metadata = getattr(msg, "metadata", None)
            sequence = getattr(getattr(metadata, "sequence", None), "stream", None)
            record = {
                "event": "chronicler_dead_letter",
                "subject": msg.subject,
                "stream_sequence": sequence,
                "error": str(error) or type(error).__name__,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": msg.data.decode("utf-8", errors="replace")[:2000] if msg.data else "",
            }
            await self.nats_publisher.publish(
                "roleplay.events.deadletter.chronicler",
                json.dumps(record).encode(),
            )
            logger.warning(
                "Dead-lettered unprocessable message subject=%s seq=%s for inspection.",
                msg.subject, sequence,
            )
        except Exception as dl_err:
            logger.warning("Could not publish dead-letter record: %s", dl_err)
            raise

    @staticmethod
    def _delivery_attempt(msg) -> int:
        """Best-effort read of how many times JetStream has delivered this message."""
        try:
            return int(msg.metadata.num_delivered)
        except Exception:
            return 1

    async def index_memories(self):
        from shared.utils.memory_index import index_lore,index_versions,reconcile_vectors
        iteration=0
        while True:
            try:
                pending=await fetch_all("SELECT m.conversation_id FROM messages m LEFT JOIN memory_checkpoints c ON c.conversation_id=m.conversation_id WHERE m.id>COALESCE(c.last_message_id,0) GROUP BY m.conversation_id HAVING count(*) >= %s ORDER BY min(m.id) LIMIT 20",(settings.summarize_every_n,))
                for row in pending:
                    try:
                        await self._check_and_trigger_summarization(row['conversation_id'])
                    except Exception:
                        logger.exception('Memory block failed; checkpoint preserved for retry')
                await index_lore()
                await index_versions()
                if iteration%6==0:
                    await reconcile_vectors()
                iteration+=1
            except Exception:
                logger.exception('Memory indexing failed; retrying')
            await asyncio.sleep(5)

    async def delete_vectors(self, data):
        from shared.db.qdrant import get_qdrant_client
        from qdrant_client.models import FilterSelector, Filter, FieldCondition, MatchValue
        client = get_qdrant_client()
        if data.get('lore_ids'):
            from shared.utils.memory_index import point_id
            if await client.collection_exists('lorebook'):
                await client.delete('lorebook',points_selector=[point_id('lore',i) for i in data['lore_ids']],wait=True)
            return
        for collection, key, values in [('conversations','conversation_id',data['conversation_ids']), ('lorebook','scenario_id',[data['scenario_id']])]:
            if await client.collection_exists(collection):
                for value in values:
                    await client.delete(collection, points_selector=FilterSelector(filter=Filter(must=[FieldCondition(key=key,match=MatchValue(value=value))])), wait=True)

    async def run(self):
        """Bind consumer lines and parse all internal workspace event states."""
        await self.nats_publisher.connect()
        assert self.nats_publisher.js is not None
        from shared.utils.worker import consume
        from shared.utils.consumers import pull_consumer
        deletions = await self.nats_publisher.js.pull_subscribe('roleplay.events.scenario_deleted', durable='chronicler_vector_deletions_v3')
        self.deletion_task = asyncio.create_task(consume(self.nats_publisher, deletions, self.delete_vectors, concurrency=1))

        sub = await pull_consumer(self.nats_publisher.js,'roleplay.chat.>','chronicler_chat_v3','roleplay_chat',legacy='chronicler_agent_durable')
        logger.info("Upgraded Chronicler Agent successfully listening to 'roleplay.chat.>'")

        self.indexing_task = asyncio.create_task(self.index_memories())
        while True:
            try:
                msg = (await sub.fetch(batch=1,timeout=2.0))[0]
                try:
                    data = json.loads(msg.data.decode()) if msg.data else {}
                    async with self.nats_publisher.processing(msg):
                        await self.handle_message(data, msg.subject)
                    await msg.ack()
                except Exception as e:
                    attempt = self._delivery_attempt(msg)
                    if _is_permanent_error(e) or attempt >= MAX_DELIVERY_ATTEMPTS:
                        logger.error(
                            "Dropping unprocessable message (subject=%s attempt=%d): %s",
                            msg.subject, attempt, e,
                        )
                        await self._dead_letter(msg, e)
                        # Ack so the poison message stops blocking every later message.
                        await msg.ack()
                    else:
                        logger.warning(
                            "Transient failure (subject=%s attempt=%d/%d); retrying in %.0fs: %s",
                            msg.subject, attempt, MAX_DELIVERY_ATTEMPTS, RETRY_DELAY_SECONDS, e,
                        )
                        await msg.nak(delay=RETRY_DELAY_SECONDS)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Chronicler lifecycle main loop error caught: %s", e)
                await asyncio.sleep(1)


if __name__ == "__main__":
    from shared.utils.worker import run_agent
    agent = ChroniclerAgent()
    try:
        if sys.platform == "win32":
            def win_loop_factory():
                return asyncio.SelectorEventLoop(selectors.SelectSelector())
            asyncio.run(run_agent(agent), loop_factory=win_loop_factory)
        else:
            asyncio.run(run_agent(agent))
    except KeyboardInterrupt:
        logger.info("Chronicler Agent shutting down safely via terminal termination request...")
