"""Provider-native multi-agent catalog and delegation."""

from context_jobs.agents.catalog import compile_agent_catalog, is_multi_agent_mode
from context_jobs.agents.delegate_runner import AgentDelegateRunner

__all__ = ["compile_agent_catalog", "is_multi_agent_mode", "AgentDelegateRunner"]
