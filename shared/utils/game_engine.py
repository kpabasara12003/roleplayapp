#roleplay_backend/app/utils/game_engine.py
import json
from typing import Dict, List, Optional, Any, Tuple
from shared.schemas.engine import DirectorEvaluation, MutationType
from shared.db.postgres import execute, fetch_one
from shared.utils.nats_client import NATSPublisher

class GameEngine:
    def __init__(self, nats_publisher: NATSPublisher):
        self.nats = nats_publisher

    async def get_state(self, conversation_id: int) -> dict:
        """Retrieves and normalizes the active game state matrix."""
        query = """
            SELECT gs.inventory, gs.relationships, gs.quest_flags, c.current_place, c."current_time"
            FROM conversations c
            LEFT JOIN game_states gs ON c.id = gs.conversation_id
            WHERE c.id = %s
        """
        # Explicitly passing a single-item tuple matching your signature requirements
        row = await fetch_one(query, (conversation_id,))
        
        if not row:
            return {"inventory": [], "relationships": {}, "quest_flags": [], "place": "Unknown", "time": "Unknown"}
        
        return {
            "inventory": row.get("inventory") or [],
            "relationships": row.get("relationships") or {},
            "quest_flags": row.get("quest_flags") or [],
            "place": row.get("current_place") or "Unknown",
            "time": row.get("current_time") or "Unknown"
        }

    async def apply_mutations(self, conversation_id: int, evaluation: DirectorEvaluation, current_state: dict):
        """Applies tactical alterations, commits to DB, and alerts the UI via NATS."""
        if not evaluation.is_action_allowed:
            return

        # Turn list into dictionary mapping to handle additions/deletions cleanly
        inventory = {item["id"]: item for item in current_state["inventory"]}
        relationships = current_state["relationships"]
        quest_flags = set(current_state["quest_flags"])
        new_place = current_state["place"]
        new_time = current_state["time"]

        for mutation in evaluation.mutations:
            if mutation.type == MutationType.ITEM_ADDED:
                item_id = mutation.target.lower().replace(" ", "_")
                if item_id in inventory:
                    inventory[item_id]["quantity"] += (mutation.value_change or 1)
                else:
                    inventory[item_id] = {
                        "id": item_id,
                        "name": mutation.target,
                        "description": mutation.description,
                        "quantity": mutation.value_change or 1
                    }
            
            elif mutation.type == MutationType.ITEM_REMOVED:
                item_id = mutation.target.lower().replace(" ", "_")
                if item_id in inventory:
                    inventory[item_id]["quantity"] -= (mutation.value_change or 1)
                    if inventory[item_id]["quantity"] <= 0:
                        inventory.pop(item_id)

            elif mutation.type == MutationType.AFFINITY_CHANGED:
                char = mutation.target
                score_change = mutation.value_change or 0
                if char not in relationships:
                    relationships[char] = {"character_name": char, "affinity_score": 0, "relationship_status": "Stranger"}
                
                new_score = max(-100, min(100, relationships[char]["affinity_score"] + score_change))
                relationships[char]["affinity_score"] = new_score

            elif mutation.type == MutationType.FLAG_TRIGGERED:
                quest_flags.add(mutation.target)

            elif mutation.type == MutationType.LOCATION_CHANGED:
                new_place = mutation.target

            elif mutation.type == MutationType.TIME_CHANGED:
                new_time = mutation.target

        # 1. Update Core Conversation Fields (Using your Tuple[Any, ...] style)
        await execute(
            "UPDATE conversations SET current_place = %s, \"current_time\" = %s WHERE id = %s",
            (new_place, new_time, conversation_id)
        )
        
        # 2. Write/Upsert Game States 
        # Note the explicit inline conversions (%s::jsonb, %s::text[]) inside the SQL string!
        # This prevents type mismatch crashes when drivers process stringified elements.
        upsert_query = """  
            INSERT INTO game_states (conversation_id, inventory, relationships, quest_flags)
            VALUES (%s, %s::jsonb, %s::jsonb, %s::text[])
            ON CONFLICT (conversation_id) DO UPDATE 
            SET inventory = EXCLUDED.inventory, 
                relationships = EXCLUDED.relationships, 
                quest_flags = EXCLUDED.quest_flags
        """
        upsert_params = (
            conversation_id, 
            json.dumps(list(inventory.values())), 
            json.dumps(relationships), 
            list(quest_flags)
        )
        
        await execute(upsert_query, upsert_params)

        # 3. Broadcast execution state details via NATS stream pipeline channel
        ui_package = {
            "event": "engine_state_updated",
            "conversation_id": conversation_id,
            "mutations": [m.model_dump() for m in evaluation.mutations],
            "current_state": {
                "place": new_place,
                "time": new_time,
                "inventory": list(inventory.values()),
                "relationships": relationships
            }
        }
        await self.nats.publish(f"roleplay.chat.engine.{conversation_id}", json.dumps(ui_package).encode())