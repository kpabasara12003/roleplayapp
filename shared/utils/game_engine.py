#roleplay_backend/app/utils/game_engine.py
import json
import copy
from shared.schemas.engine import DirectorEvaluation, MutationType
from shared.db.postgres import execute, fetch_one, transaction
from shared.utils.nats_client import NATSPublisher

class GameEngine:
    def __init__(self, nats_publisher: NATSPublisher):
        self.nats = nats_publisher

    async def get_state(self, conversation_id: int) -> dict:
        """Retrieves and normalizes the active game state matrix."""
        query = """
            SELECT gs.inventory, gs.relationships, gs.quest_flags, gs.runtime, c.current_place, c."current_time",c.state_version
            FROM conversations c
            LEFT JOIN game_states gs ON c.id = gs.conversation_id
            WHERE c.id = %s
        """
        # Explicitly passing a single-item tuple matching your signature requirements
        row = await fetch_one(query, (conversation_id,))

        if not row:
            return {"inventory": [], "relationships": {}, "quest_flags": [], "place": "Unknown", "time": "Unknown"}

        return {
            "state_version": row['state_version'],
            "runtime": row.get('runtime') or {'executed_rules':[],'quest_progress':{},'characters':{},'clock_minutes':0},
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

        current_state = copy.deepcopy(current_state)
        from shared.utils.playthroughs import scene_for
        scene=await scene_for(conversation_id)
        rules=scene.get('rules',{})
        runtime=current_state.setdefault('runtime',{})
        runtime.setdefault('executed_rules',[])
        runtime['executed_rules']=sorted(set(runtime['executed_rules']) | {f for f in current_state['quest_flags'] if f.startswith(('rule:','world:'))})
        current_state['quest_flags']=[f for f in current_state['quest_flags'] if not f.startswith(('rule:','world:'))]
        runtime.setdefault('quest_progress',{})
        runtime.setdefault('characters',{})
        runtime.setdefault('clock_minutes',0)
        # Turn list into dictionary mapping to handle additions/deletions cleanly
        inventory = {item["id"]: item for item in current_state["inventory"]}
        relationships = current_state["relationships"]
        quest_flags = set(current_state["quest_flags"])
        new_place = current_state["place"]
        new_time = current_state["time"]

        # Aggregate once per character before applying per-action repetition controls.
        totals={}
        for mutation in evaluation.mutations:
            if mutation.type==MutationType.AFFINITY_CHANGED:
                totals[mutation.target]=totals.get(mutation.target,0)+(mutation.value_change or 0)
        mutations=[]
        emitted=set()
        for mutation in evaluation.mutations:
            if mutation.type==MutationType.AFFINITY_CHANGED:
                if mutation.target in emitted or not totals[mutation.target]:continue
                emitted.add(mutation.target)
                mutation=mutation.model_copy(update={'value_change':totals[mutation.target]})
            mutations.append(mutation)
        evaluation=evaluation.model_copy(update={'mutations':mutations})
        for mutation in evaluation.mutations:
            if mutation.type == MutationType.CHARACTER_UPDATED:
                from shared.schemas.playthrough import CharacterRuntime
                if mutation.target not in {c['name'] for c in scene['cast']}:
                    raise ValueError('Unknown character')
                old=runtime['characters'].get(mutation.target,{})
                updated=CharacterRuntime.model_validate(mutation.character_state or {}).model_dump()
                runtime['characters'][mutation.target]={**old,**updated}
            elif mutation.type == MutationType.ITEM_ADDED:
                item_id = next((i['id'] for i in inventory.values() if i['id']==mutation.target or i['name']==mutation.target),mutation.target.lower().replace(" ", "_"))
                if item_id in inventory:
                    inventory[item_id]["quantity"] += (mutation.value_change or 1)
                else:
                    catalog=rules.get('items',{}).get(item_id)
                    inventory[item_id] = {**catalog,'quantity':mutation.value_change or 1} if catalog else {
                        "id": item_id,
                        "name": mutation.target,
                        "description": mutation.description,
                        "quantity": mutation.value_change or 1
                    }

            elif mutation.type == MutationType.ITEM_REMOVED:
                item_id = next((i['id'] for i in inventory.values() if i['id']==mutation.target or i['name']==mutation.target),mutation.target.lower().replace(" ", "_"))
                if item_id not in inventory or inventory[item_id]["quantity"] < (mutation.value_change or 1):
                    raise ValueError("Insufficient inventory quantity")
                if item_id in inventory:
                    inventory[item_id]["quantity"] -= (mutation.value_change or 1)
                    if inventory[item_id]["quantity"] <= 0:
                        inventory.pop(item_id)

            elif mutation.type == MutationType.AFFINITY_CHANGED:
                char = mutation.target
                # Repeating the same action does not farm affinity across turns.
                import hashlib
                from shared.utils.turns import job_claim
                claim=job_claim.get()
                turn=await fetch_one('SELECT content FROM turns WHERE id=%s',(claim.turn_id,)) if claim else None
                fingerprint=hashlib.sha256(' '.join(turn['content'].casefold().split()).encode()).hexdigest() if turn else None
                npc=runtime['characters'].setdefault(char,{})
                seen=npc.setdefault('affinity_actions',[])
                if fingerprint and fingerprint in seen:
                    continue
                if fingerprint:
                    seen.append(fingerprint)
                    del seen[:-100]
                score_change = mutation.value_change or 0
                if char not in relationships:
                    relationships[char] = {"character_name": char, "affinity_score": 0, "relationship_status": "Stranger"}

                new_score = max(-100, min(100, relationships[char]["affinity_score"] + score_change))
                relationships[char]["affinity_score"] = new_score
                thresholds=rules.get('relationship_thresholds',{'Rival':-50,'Stranger':-10,'Acquaintance':10,'Friend':40,'Ally':75})
                eligible=[(score,label) for label,score in thresholds.items() if new_score>=score]
                relationships[char]['relationship_status']=max(eligible)[1] if eligible else 'Hostile'

            elif mutation.type == MutationType.FLAG_TRIGGERED:
                if mutation.target.startswith(('rule:','world:')):
                    if mutation.target not in runtime['executed_rules']:
                        runtime['executed_rules'].append(mutation.target)
                else:
                    quest_flags.add(mutation.target)
            elif mutation.type == MutationType.FLAG_CLEARED:
                quest_flags.discard(mutation.target)
            elif mutation.type in (MutationType.QUEST_STARTED,MutationType.QUEST_RESTARTED,MutationType.QUEST_ADVANCED,MutationType.QUEST_PROGRESS,MutationType.QUEST_FAILED):
                from shared.utils.quests import apply_quest
                apply_quest(runtime['quest_progress'],rules,mutation)
            elif mutation.type == MutationType.CLOCK_ADVANCED:
                minutes=mutation.value_change or 0
                if not 1<=minutes<=1440:
                    raise ValueError('Story clock advance must be 1-1440 minutes')
                runtime['clock_minutes']+=minutes

            elif mutation.type == MutationType.LOCATION_CHANGED:
                new_place = mutation.target

            elif mutation.type == MutationType.TIME_CHANGED:
                new_time = mutation.target

        async with transaction():
            version = await fetch_one('SELECT state_version FROM conversations WHERE id=%s FOR UPDATE', (conversation_id,))
            if not version or version['state_version'] != current_state.get('state_version',0):
                raise ValueError('Scene changed while evaluating action')
            # 1. Update Core Conversation Fields (Using your Tuple[Any, ...] style)
            await execute(
                "UPDATE conversations SET current_place = %s, \"current_time\" = %s WHERE id = %s",
                (new_place, new_time, conversation_id)
            )

            # 2. Write/Upsert Game States
            # Note the explicit inline conversions (%s::jsonb, %s::text[]) inside the SQL string!
            # This prevents type mismatch crashes when drivers process stringified elements.
            upsert_query = """
                INSERT INTO game_states (conversation_id, inventory, relationships, quest_flags,runtime)
                VALUES (%s, %s::jsonb, %s::jsonb, %s::text[],%s::jsonb)
                ON CONFLICT (conversation_id) DO UPDATE
                SET inventory = EXCLUDED.inventory,
                    relationships = EXCLUDED.relationships,
                    quest_flags = EXCLUDED.quest_flags, runtime=EXCLUDED.runtime,updated_at=now()
            """
            upsert_params = (
                conversation_id,
                json.dumps(list(inventory.values())),
                json.dumps(relationships),
                list(quest_flags)
                ,json.dumps(runtime)
            )

            await execute(upsert_query, upsert_params)
            await execute('UPDATE conversations SET state_version=state_version+1 WHERE id=%s',(conversation_id,))
            from shared.utils.turns import job_claim
            claim = job_claim.get()
            if claim:
                await execute('UPDATE turns SET state_version=state_version+1 WHERE id=%s',(claim.turn_id,))
            from shared.schemas.playthrough import InitialState
            InitialState.model_validate({'inventory':list(inventory.values()),'relationships':relationships,'quest_flags':list(quest_flags)})
            snapshot={'inventory':list(inventory.values()),'relationships':relationships,'quest_flags':sorted(quest_flags),'runtime':runtime,'place':new_place,'time':new_time,'state_version':version['state_version']+1}
            import uuid
            operation=(claim.id+':'+str(claim.fence)) if claim else str(uuid.uuid4())
            await execute('INSERT INTO state_events(conversation_id,turn_id,operation_id,state_version,snapshot,changes) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb)',(conversation_id,claim.turn_id if claim else None,operation,snapshot['state_version'],json.dumps(snapshot),json.dumps([m.model_dump() for m in evaluation.mutations])))

        # 3. Broadcast execution state details via NATS stream pipeline channel
        ui_package = {
            "event": "engine_state_updated",
            "conversation_id": conversation_id,
            "mutations": [m.model_dump() for m in evaluation.mutations],
            "state_version": snapshot['state_version'],
            "current_state": {
                "place": new_place,
                "time": new_time,
                "inventory": list(inventory.values()),
                "relationships": relationships,
                "quest_flags":sorted(quest_flags),"runtime":runtime,
                "state_version":snapshot['state_version']
            }
        }
        await self.nats.publish(f"roleplay.chat.stream.{conversation_id}", json.dumps(ui_package).encode())
