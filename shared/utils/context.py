"""Token budgets preserve essential state and the complete latest input."""
import os

def token_count(text,model=None):
    try:
        import tiktoken
        return len(tiktoken.encoding_for_model(model or os.getenv('LLM_MODEL','')).encode(text))
    except (ImportError,KeyError):
        return len(text.encode('utf-8'))

def budget_messages(messages,max_chars=None):
    limit=int(os.getenv('MODEL_CONTEXT_TOKENS','8192'))-int(os.getenv('LLM_MAX_TOKENS','512'))-256
    if max_chars is not None:
        limit=min(limit,max_chars//4)
    remaining=limit-token_count(messages[0]['content'])-8
    if remaining<=0:
        raise ValueError('Essential scenario/state exceeds model context budget')
    tail=[]
    for message in reversed(messages[1:]):
        cost=token_count(message['content'])+8
        if cost>remaining:
            if not tail: raise ValueError('Latest player input exceeds remaining model context')
            break
        tail.append(message)
        remaining-=cost
    return [messages[0]]+list(reversed(tail))
