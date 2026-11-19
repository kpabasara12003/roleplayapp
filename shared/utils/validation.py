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
    scene = await fetch_one('SELECT s.rules,s.introduction FROM scenarios s JOIN conversations c ON c.scenario_id=s.id WHERE c.id=%s', (data['conversation_id'],))
    cast = await fetch_all('SELECT name FROM characters WHERE scenario_id=(SELECT scenario_id FROM conversations WHERE id=%s)', (data['conversation_id'],))
    state['scenario_rules'] = scene['rules']
    state['cast'] = [c['name'] for c in cast]
    state['premise'] = scene['introduction']
    state['recent_scene'] = await fetch_all('SELECT sender,content FROM messages WHERE conversation_id=%s AND id<=%s ORDER BY id DESC LIMIT 6',(data['conversation_id'],data['message_id']))
    evaluation = await evaluator(data['content'], state)
    try:
        evaluation = authorize(evaluation,data['content'],state,scene['rules'],[c['name'] for c in cast])
    except RuleViolation as exc:
        evaluation = DirectorEvaluation(reasoning='Rule validation rejected proposed changes',is_action_allowed=False,failure_explanation=str(exc),mutations=[])
    async with transaction():
        current=await fetch_one('SELECT s.rules FROM scenarios s JOIN conversations c ON c.scenario_id=s.id WHERE c.id=%s',(data['conversation_id'],))
        if not current or current['rules']!=scene['rules']:
            raise RuntimeError('Scenario rules changed during evaluation; retry required')
        if not evaluation.is_action_allowed:
            await complete_job(blocked=evaluation.failure_explanation or 'Action rejected')
            return
        await engine.apply_mutations(data['conversation_id'],evaluation,state)
        await complete_job()
