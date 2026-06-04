"""A minimal, auditable Anthropic tool-use loop.

No agent framework on purpose: every step is plain and inspectable, which matters
for a result we want to stand behind. The loop calls the model, executes any
requested tools via `handle_tool`, feeds results back, and stops when the agent
calls `finish` (signalled by handle_tool returning stop=True), emits no tool call,
or hits the iteration cap.
"""

from typing import Callable, List, Tuple

import os

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

_client = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
        if oauth_token.startswith("sk-ant-oat"):
            _client = Anthropic(auth_token=oauth_token)
        else:
            _client = Anthropic(api_key=oauth_token)
    return _client


@retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=2, min=5, max=60))
def _create(**kwargs):
    return _get_client().messages.create(**kwargs)


def _blocks_to_dicts(content) -> List[dict]:
    out = []
    for b in content:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


def run_agent(
    model: str,
    system_prompt: str,
    user_prompt: str,
    tools: list,
    handle_tool: Callable[[str, dict], Tuple[str, bool]],
    max_iters: int = 10,
    temperature: float = 1.0,
    max_tokens: int = 1024,
) -> dict:
    messages = [{"role": "user", "content": user_prompt}]
    transcript = [{"role": "user", "content": user_prompt}]
    stop_reason = "max_iters"

    for _ in range(max_iters):
        resp = _create(
            model=model,
            system=system_prompt,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        assistant_content = _blocks_to_dicts(resp.content)
        messages.append({"role": "assistant", "content": assistant_content})
        transcript.append({"role": "assistant", "content": assistant_content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            stop_reason = "end_turn"
            break

        results = []
        should_stop = False
        for tu in tool_uses:
            output, stop = handle_tool(tu.name, tu.input)
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": output})
            should_stop = should_stop or stop

        tool_msg = {"role": "user", "content": results}
        messages.append(tool_msg)
        transcript.append(tool_msg)

        if should_stop:
            stop_reason = "finished"
            break

    return {"transcript": transcript, "stop_reason": stop_reason}
