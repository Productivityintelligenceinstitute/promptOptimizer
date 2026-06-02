"""Anthropic Messages API adapter with tool-use loop."""

from __future__ import annotations

import json
from typing import Any

import anthropic

from context_jobs.providers.base import (
    ExecutionEnvelope,
    ProviderAdapter,
    ProviderResponse,
    ToolCall,
    ToolDefinition,
    ToolExecutor,
)


class ClaudeAdapter(ProviderAdapter):
    def translate_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "name": t.id,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]

    async def execute(
        self,
        envelope: ExecutionEnvelope,
        api_key: str,
        tool_executor: ToolExecutor,
    ) -> ProviderResponse:
        client = anthropic.Anthropic(api_key=api_key)
        messages: list[dict[str, Any]] = [{"role": "user", "content": envelope.user_message}]
        total_input = 0
        total_output = 0
        turns = 0
        native_tools = self.translate_tools(envelope.tools) if envelope.tools else None

        while turns < envelope.max_turns:
            turns += 1
            kwargs: dict[str, Any] = {
                "model": envelope.model,
                "max_tokens": envelope.max_tokens,
                "system": envelope.system_prompt,
                "messages": messages,
                "temperature": envelope.temperature,
            }
            if native_tools:
                kwargs["tools"] = native_tools

            response = client.messages.create(**kwargs)
            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens

            if response.stop_reason == "end_turn":
                text = "".join(
                    block.text for block in response.content if getattr(block, "type", "") == "text"
                )
                return ProviderResponse(
                    content=text,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    model=envelope.model,
                    stop_reason="end_turn",
                    agent_turns=turns,
                )

            tool_blocks = [b for b in response.content if getattr(b, "type", "") == "tool_use"]
            if not tool_blocks:
                text = "".join(
                    block.text for block in response.content if getattr(block, "type", "") == "text"
                )
                return ProviderResponse(
                    content=text,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    model=envelope.model,
                    stop_reason=response.stop_reason or "end_turn",
                    agent_turns=turns,
                )

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in tool_blocks:
                args = block.input if isinstance(block.input, dict) else {}
                result = await tool_executor(
                    ToolCall(
                        id=block.id,
                        tool_id=block.name,
                        tool_name=block.name,
                        arguments=args,
                    )
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        return ProviderResponse(
            content="Agent stopped: maximum turns reached.",
            input_tokens=total_input,
            output_tokens=total_output,
            model=envelope.model,
            stop_reason="budget_exceeded",
            agent_turns=turns,
        )
