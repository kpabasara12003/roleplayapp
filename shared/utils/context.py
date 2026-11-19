"""Conservative character budget when a provider tokenizer is unavailable."""
def budget_messages(messages, max_chars=24000):
    system = messages[0]['content']
    # Preserve the final behavioral rules as well as the scenario/persona header.
    if len(system) > max_chars // 2:
        keep = max_chars // 2
        system = system[:keep-4000] + '\n[Context abbreviated]\n' + system[-4000:]
    remaining = max_chars - len(system)
    tail = []
    for message in reversed(messages[1:]):
        content = message['content']
        if len(content) > remaining:
            if not tail:
                tail.append({**message, 'content': content[-remaining:]})
            break
        tail.append(message)
        remaining -= len(content)
    return [{'role':'system','content':system}] + list(reversed(tail))
