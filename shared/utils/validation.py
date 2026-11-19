"""Director validation stage: infer outside SQL, then apply a fenced commit."""
import json
from shared.db.postgres import fetch_one, fetch_all, execute, transaction
from shared.schemas.engine import DirectorEvaluation
from shared.utils.game_engine import GameEngine
from shared.utils.turns import complete_job
from shared.utils.rules import authorize, RuleViolation

async def validate_turn(publisher, data, evaluator):
    engine = GameEngine(publisher)
    state = await engine.get_state(data['conversation_id'])
    from shared.utils.playthroughs import scene_for
    scene=await scene_for(data['conversation_id'])
    cast=scene['cast']
    state['scenario_rules'] = scene['rules']
    state['cast'] = [c['name'] for c in cast]
    state['premise'] = scene['introduction']
    state['recent_scene'] = await fetch_all('SELECT sender,content FROM messages WHERE conversation_id=%s AND id<=%s AND NOT superseded ORDER BY id DESC LIMIT 6',(data['conversation_id'],data['message_id']))
    if scene['rules'].get('mode','freeform')=='freeform' and not scene['rules'].get('transitions') and not scene['rules'].get('track_relationships',True):
        evaluation=DirectorEvaluation(reasoning='Freeform dialogue without tracked mechanics',is_action_allowed=True,failure_explanation=None)
    else:
        evaluation = await evaluator(data['content'], state)
    try:
        evaluation = authorize(evaluation,data['content'],state,scene['rules'],[c['name'] for c in cast])
    except RuleViolation as exc:
        evaluation = DirectorEvaluation(reasoning='Rule validation rejected proposed changes',is_action_allowed=False,failure_explanation=str(exc),mutations=[])
    async with transaction():
        if not evaluation.is_action_allowed:
            await complete_job(blocked=evaluation.failure_explanation or 'Action rejected')
            return
        await engine.apply_mutations(data['conversation_id'],evaluation,state)
        await complete_job()
