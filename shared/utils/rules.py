"""Deterministic authorization of model-proposed world changes."""
import copy
from shared.schemas.engine import DirectorEvaluation, EngineMutation, MutationType

class RuleViolation(ValueError):
    pass

def authorize(evaluation, action, state, rules, cast):
    if not evaluation.is_action_allowed:
        return evaluation
    approved = []
    inventory = {item['id']:item['quantity'] for item in state.get('inventory',[])}
    flags = set(state.get('quest_flags',[])) | set(state.get('runtime',{}).get('executed_rules',[]))
    for transition in rules.get('transitions',[]):
        # Explicit command IDs come from structured inference, never substring matching.
        if transition['id'] not in evaluation.command_ids:
            continue
        marker = 'rule:' + transition['id']
        if transition.get('once', True) and marker in set(state.get('runtime',{}).get('executed_rules',[])) | flags:
            continue
        if any(inventory.get(key,0)<qty for key,qty in transition.get('requires_items',{}).items()):
            raise RuleViolation('This action requires items you do not possess')
        if not set(transition.get('requires_flags',[])).issubset(flags):
            raise RuleViolation('This action has unmet prerequisites')
        approved.extend(EngineMutation.model_validate(m) for m in transition.get('mutations',[]))
        if transition.get('once',True):
            approved.append(EngineMutation(type=MutationType.FLAG_TRIGGERED,target=marker,description='Scenario transition completed'))
    # The model may suggest small relationship reactions, but cannot invent cast members.
    unknown=set(evaluation.command_ids)-{t['id'] for t in rules.get('transitions',[])}
    if unknown:
        raise RuleViolation('Unknown action command')
    affinity={}
    for mutation in evaluation.mutations:
        if mutation.type == MutationType.AFFINITY_CHANGED:
            if mutation.target not in cast or abs(mutation.value_change or 0)>5:
                raise RuleViolation('Unrecognized character or excessive relationship change')
            approved.append(mutation)
            affinity[mutation.target]=affinity.get(mutation.target,0)+(mutation.value_change or 0)
            if abs(affinity[mutation.target])>5:
                raise RuleViolation('Total relationship change exceeds the per-turn limit')
        elif not any(mutation.type==m.type and mutation.target==m.target and mutation.value_change==m.value_change for m in approved):
            raise RuleViolation('The proposed world change is not authorized by scenario rules')
    return evaluation.model_copy(update={'mutations':approved})

def world_event(event_id, rules):
    for event in rules.get('world_events',[]):
        if event.get('id') == event_id:
            return event
    raise RuleViolation('Unknown world event')
