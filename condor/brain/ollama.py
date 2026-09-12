"""Native local streaming, including tool calls, with bounded GPU context."""
from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx


class ToolCall(SimpleNamespace):
    def model_dump(self, **_kwargs):
        return vars(self).copy()


def chat_messages(instructions: str, items: list[dict]) -> list[dict]:
    messages = [{"role": "system", "content": instructions}]
    names = {}
    for item in items:
        kind = item.get("type")
        if kind == "function_call":
            args = json.loads(item.get("arguments") or "{}")
            names[item["call_id"]] = item["name"]
            messages.append({"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": item["name"], "arguments": args}}
            ]})
        elif kind == "function_call_output":
            messages.append({"role": "tool", "tool_name": names.get(item["call_id"], ""),
                             "content": item["output"]})
        elif item.get("role") in {"user", "assistant", "system"}:
            content = item.get("content", "")
            if isinstance(content, list):
                content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
            messages.append({"role": item["role"], "content": content})
    return messages


async def responder_ollama(*, endpoint, model, instructions, items, tools,
                           max_tokens, context, temperature, on_token=None, json_mode=False):
    parsed = urlsplit(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Ollama precisa permanecer no loopback")
    url = f"{parsed.scheme}://{parsed.netloc}/api/chat"
    payload = {
        "model": model, "messages": chat_messages(instructions, items),
        "stream": True, "keep_alive": "15m",
        "options": {"num_ctx": context, "num_predict": max_tokens, "temperature": temperature},
        "tools": [{"type": "function", "function": {
            "name": tool["name"], "description": tool.get("description", ""),
            "parameters": tool["parameters"],
        }} for tool in tools],
    }
    if json_mode:
        payload["format"] = "json"
    content, calls, finished = [], [], False
    usage = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5), trust_env=False) as client:
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                event = json.loads(line)
                if event.get("error"):
                    raise RuntimeError("Ollama não concluiu a geração")
                message = event.get("message", {})
                token = message.get("content", "")
                if token:
                    content.append(token)
                    if on_token:
                        await on_token(token)
                for call in message.get("tool_calls", []):
                    function = call["function"]
                    calls.append(ToolCall(type="function_call", call_id=f"local-{len(items)}-{len(calls)}",
                                          name=function["name"], arguments=json.dumps(function["arguments"])))
                if event.get("done"):
                    finished = True
                    usage = SimpleNamespace(input_tokens=event.get("prompt_eval_count", 0),
                                            output_tokens=event.get("eval_count", 0))
    if not finished:
        raise RuntimeError("A resposta local foi interrompida antes de concluir")
    text = "".join(content).strip()
    if not text and not calls:
        raise RuntimeError("O modelo local retornou uma resposta vazia")
    return SimpleNamespace(output_text=text, output=calls, usage=usage)
