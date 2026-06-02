"""OpenAI Chat Completions adapter with function-calling loop."""

from __future__ import annotations

import json
from typing import Any

import openai

from context_jobs.providers.base import (
    ExecutionEnvelope,
    ProviderAdapter,
    ProviderResponse,
    ToolCall,
    ToolDefinition,
    ToolExecutor,
)


class OpenAIAdapter(ProviderAdapter):
    def translate_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.id,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]

    async def execute(
        self,
        envelope: ExecutionEnvelope,
        api_key: str,
        tool_executor: ToolExecutor,
    ) -> ProviderResponse:
        client = openai.OpenAI(api_key=api_key)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": envelope.system_prompt},
            {"role": "user", "content": envelope.user_message},
        ]
        total_input = 0
        total_output = 0
        turns = 0
        native_tools = self.translate_tools(envelope.tools) if envelope.tools else None

        while turns < envelope.max_turns:
            turns += 1
            kwargs: dict[str, Any] = {
                "model": envelope.model,
                "messages": messages,
                "max_tokens": envelope.max_tokens,
                "temperature": envelope.temperature,
            }
            if native_tools:
                kwargs["tools"] = native_tools

            response = client.chat.completions.create(**kwargs)
            if response.usage:
                total_input += response.usage.prompt_tokens or 0
                total_output += response.usage.completion_tokens or 0

            message = response.choices[0].message
            tool_calls = message.tool_calls or []
            if not tool_calls:
                return ProviderResponse(
                    content=message.content or "",
                    input_tokens=total_input,
                    output_tokens=total_output,
                    model=envelope.model,
                    stop_reason="end_turn",
                    agent_turns=turns,
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                raw_args = tc.function.arguments or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    args = {}
                result = await tool_executor(
                    ToolCall(
                        id=tc.id,
                        tool_id=tc.function.name,
                        tool_name=tc.function.name,
                        arguments=args if isinstance(args, dict) else {},
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result.content,
                    }
                )

        return ProviderResponse(
            content="Agent stopped: maximum turns reached.",
            input_tokens=total_input,
            output_tokens=total_output,
            model=envelope.model,
            stop_reason="budget_exceeded",
            agent_turns=turns,
        )
