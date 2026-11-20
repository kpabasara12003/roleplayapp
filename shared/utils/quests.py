"""Quest lifecycle: terminal outcomes require an explicit authored restart."""
from shared.schemas.engine import MutationType

def apply_quest(progress_by_id,rules,mutation):
    quest,_,objective=mutation.target.partition(':') if mutation.type==MutationType.QUEST_PROGRESS else (mutation.target,'','')
    stages=rules.get('quests',{}).get(quest,[])
    goals=rules.get('quest_objectives',{}).get(quest,{})
    if not stages and not goals:
        raise ValueError('Unknown quest')
    previous=progress_by_id.get(quest,{})
    status=previous.get('status','inactive')
    if mutation.type==MutationType.QUEST_RESTARTED:
        if status not in ('completed','failed'):
            raise ValueError('Only a completed or failed quest can restart')
        progress_by_id[quest]={'status':'active','step':-1,'objectives':{}}
        return
    if status in ('completed','failed'):
        raise ValueError('Terminal quest requires an explicit restart')
    progress={**previous,'status':'active','objectives':dict(previous.get('objectives',{}))}
    if mutation.type==MutationType.QUEST_STARTED:
        if status!='inactive':raise ValueError('Quest is already active')
        progress.setdefault('step',-1)
    elif mutation.type==MutationType.QUEST_FAILED:
        if status!='active':raise ValueError('Only an active quest can fail')
        progress.update(status='failed',reason=mutation.description)
    elif mutation.type==MutationType.QUEST_ADVANCED:
        step=previous.get('step',-1)+1
        if not stages or step>=len(stages):raise ValueError('Invalid quest progression')
        progress.update(step=step,stage=stages[step])
    elif mutation.type==MutationType.QUEST_PROGRESS:
        increment=mutation.value_change or 0
        if objective not in goals or not 1<=increment<=10000:raise ValueError('Invalid quest objective or increment')
        progress['objectives'][objective]=min(goals[objective],progress['objectives'].get(objective,0)+increment)
    if mutation.type in (MutationType.QUEST_ADVANCED,MutationType.QUEST_PROGRESS):
        stage_done=not stages or progress.get('step',-1)==len(stages)-1
        goals_done=all(progress['objectives'].get(key,0)>=value for key,value in goals.items())
        if stage_done and goals_done:progress['status']='completed'
    progress_by_id[quest]=progress
