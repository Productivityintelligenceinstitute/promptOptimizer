"""Google Gemini adapter with function-calling loop."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from google import genai
from google.genai import types

from context_jobs.providers.base import (
    ExecutionEnvelope,
    ProviderAdapter,
    ProviderResponse,
    ToolCall,
    ToolDefinition,
    ToolExecutor,
    is_fatal_tool_denial,
)


class GeminiAdapter(ProviderAdapter):
    def translate_tools(self, tools: list[ToolDefinition]) -> list[types.Tool]:
        declarations = [
            types.FunctionDeclaration(
                name=t.id,
                description=t.description,
                parameters=t.input_schema,
            )
            for t in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    async def execute(
        self,
        envelope: ExecutionEnvelope,
        api_key: str,
        tool_executor: ToolExecutor,
    ) -> ProviderResponse:
        # TODO: migrate to async client when google-genai SDK supports it
        use_async_client = hasattr(genai, "AsyncClient")
        client = genai.AsyncClient(api_key=api_key) if use_async_client else genai.Client(api_key=api_key)
        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part(text=envelope.user_message)])
        ]
        total_input = 0
        total_output = 0
        turns = 0
        native_tools = self.translate_tools(envelope.tools) if envelope.tools else None

        while turns < envelope.max_turns:
            turns += 1
            config_kwargs: dict[str, Any] = {
                "system_instruction": envelope.system_prompt,
                "temperature": envelope.temperature,
                "max_output_tokens": envelope.max_tokens,
            }
            if native_tools:
                config_kwargs["tools"] = native_tools

            if use_async_client:
                response = await client.models.generate_content(  # type: ignore[union-attr]
                    model=envelope.model,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
            else:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: client.models.generate_content(
                        model=envelope.model,
                        contents=contents,
                        config=types.GenerateContentConfig(**config_kwargs),
                    ),
                )

            usage = getattr(response, "usage_metadata", None)
            if usage:
                total_input += getattr(usage, "prompt_token_count", 0) or 0
                total_output += getattr(usage, "candidates_token_count", 0) or 0

            candidate = response.candidates[0] if response.candidates else None
            if not candidate or not candidate.content or not candidate.content.parts:
                return ProviderResponse(
                    content=response.text or "",
                    input_tokens=total_input,
                    output_tokens=total_output,
                    model=envelope.model,
                    stop_reason="end_turn",
                    agent_turns=turns,
                )

            function_calls = [
                p.function_call
                for p in candidate.content.parts
                if getattr(p, "function_call", None)
            ]
            if not function_calls:
                text = response.text or ""
                return ProviderResponse(
                    content=text,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    model=envelope.model,
                    stop_reason="end_turn",
                    agent_turns=turns,
                )

            contents.append(candidate.content)
            response_parts: list[types.Part] = []
            fatal_denial = False
            for fc in function_calls:
                args = dict(fc.args) if fc.args else {}
                result = await tool_executor(
                    ToolCall(
                        id=f"{fc.name}-{uuid.uuid4().hex[:8]}",
                        tool_id=fc.name,
                        tool_name=fc.name,
                        arguments=args,
                    )
                )
                response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": result.content, "is_error": result.is_error},
                    )
                )
                if is_fatal_tool_denial(result):
                    fatal_denial = True
            contents.append(types.Content(role="user", parts=response_parts))
            if fatal_denial:
                return ProviderResponse(
                    content="Agent stopped: run budget exceeded.",
                    input_tokens=total_input,
                    output_tokens=total_output,
                    model=envelope.model,
                    stop_reason="budget_exceeded",
                    agent_turns=turns,
                )

        return ProviderResponse(
            content="Agent stopped: maximum turns reached.",
            input_tokens=total_input,
            output_tokens=total_output,
            model=envelope.model,
            stop_reason="budget_exceeded",
            agent_turns=turns,
        )
