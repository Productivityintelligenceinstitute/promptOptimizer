"""Run specialist sub-agents through the same provider adapter and gateway."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from context_jobs.agents.types import SubAgentDefinition
from context_jobs.assembly.prompt_safety import (
    append_prompt_injection_policy,
    assemble_delegate_user_message,
)
from context_jobs.gateway.budget_tracker import BudgetTracker
from context_jobs.gateway.guardrail_gateway import GatewayToolExecutor
from context_jobs.providers.base import ExecutionEnvelope, ToolDefinition
from context_jobs.providers.registry import get_provider_adapter
from schemas.context_jobs_model import ContextJobModel, JobRunModel
from sqlalchemy.orm import Session


@dataclass
class AgentDelegateRunner:
    job: ContextJobModel
    run: JobRunModel
    db: Session
    budget_tracker: BudgetTracker
    provider: str
    model: str
    api_key: str
    catalog: dict[str, SubAgentDefinition]
    base_tool_definitions: list[ToolDefinition]
    delegation_events: list[dict[str, Any]] = field(default_factory=list)

    async def delegate(self, agent_name: str, task: str, parent_executor: GatewayToolExecutor) -> str:
        spec = self.catalog.get(agent_name)
        if not spec:
            available = ", ".join(sorted(self.catalog.keys())) or "(none)"
            raise ValueError(f"Unknown specialist '{agent_name}'. Available: {available}")

        specialist_tools = [
            t for t in self.base_tool_definitions if t.id in set(spec.tool_ids)
        ]
        if not specialist_tools:
            raise ValueError(f"Specialist '{agent_name}' has no enabled tools for this job")

        nested_executor = GatewayToolExecutor(
            job=self.job,
            run=self.run,
            budget_tracker=self.budget_tracker,
            db=self.db,
            agent_catalog={},
            delegate_runner=None,
            allow_delegation=False,
        )

        envelope = ExecutionEnvelope(
            system_prompt=append_prompt_injection_policy(spec.system_prompt),
            user_message=assemble_delegate_user_message(task),
            tools=specialist_tools,
            max_tokens=int((self.job.budget_settings or {}).get("maxTokens") or 4096),
            max_turns=spec.max_turns,
            temperature=0.2,
            model=self.model,
            metadata={
                "job_id": str(self.job.id),
                "run_id": str(self.run.id),
                "owner": self.job.owner,
                "subagent": agent_name,
            },
        )

        adapter = get_provider_adapter(self.provider)
        response = await adapter.execute(envelope, self.api_key, nested_executor)
        self.budget_tracker.record_tokens(response.input_tokens, response.output_tokens, response.model)

        parent_executor.executed_calls.extend(nested_executor.executed_calls)
        parent_executor.artifacts.extend(nested_executor.artifacts)

        summary = (response.content or "").strip() or "(no content returned)"
        if len(summary) > 6000:
            summary = summary[:6000] + "\n...[truncated for parent context]"

        self.delegation_events.append(
            {
                "agentName": agent_name,
                "taskPreview": task[:240],
                "turns": response.agent_turns,
                "toolCalls": nested_executor.total_calls,
                "status": "success",
            }
        )
        return f"[{agent_name} specialist result]\n{summary}"
