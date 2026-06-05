---
name: Backend Implementation Plan
overview: Complete backend implementation plan for Jet Prompt Optimizer Context Jobs — covering provider-native orchestration (Option B), BYOK + Jet-managed key storage, Guardrail Gateway, all 5 tool implementations, enhanced validation engine, memory system, context assembly pipeline, and Firebase auth integration. This document serves as a standalone handoff reference.
todos:
  - id: phase-1-foundation
    content: "Phase 1: ORM model updates/table creation, BYOK encryption, key management API, Firebase auth on all endpoints"
    status: pending
  - id: phase-2-providers
    content: "Phase 2: Provider adapters (Claude/OpenAI/Gemini), rewrite orchestrator, context assembly engine"
    status: pending
  - id: phase-3-tools
    content: "Phase 3: All 5 tool implementations, Guardrail Gateway, tool execution audit logging"
    status: pending
  - id: phase-4-retrieval-validation
    content: "Phase 4: Enhanced retrieval (rewrite/rerank/hybrid/sources), pluggable validation engine with LLM-as-judge"
    status: pending
  - id: phase-5-memory-polish
    content: "Phase 5: Memory system, ROP builder extraction, contract verification, comprehensive E2E tests"
    status: pending
isProject: false
---


# Jet Prompt Optimizer — Backend Implementation Plan

**Version:** 1.0 | **Date:** June 2, 2026 | **Strategy:** Approach 2 (BYOK) + Approach 3 (Jet-Managed Keys) | **MCP:** Deferred

---

## 1. Executive Summary

This plan covers everything remaining to turn the current FastAPI backend into the full Option B product. The Replit prototype defines **what** the product looks like (UI contract, ROP, status machine). The Complementary Integration Strategy defines **how** execution works (providers own reasoning; Jet owns context, governance, and trust). This plan bridges the two.

**Core principle:** Providers (Claude, OpenAI, Gemini) = execution engines. Jet = workflow definition, context assembly, guardrail enforcement, output validation, evidence packaging, human-in-the-loop.

**What exists today (~65% of Jet-side, ~20% of execution):**
- Job/Run/Asset CRUD APIs aligned with Replit contract
- 5 retrieval adapters (Pinecone, Qdrant, Weaviate, pgvector, Jet KB)
- Ingestion pipeline with pre-flight validation
- Single OpenAI `chat.completions` call (not agent loop)
- Basic citation validation + ROP assembly
- Vector connections with encrypted config
- Embedding service (multi-provider)

**What this plan builds:**
- Provider adapter system (Claude Messages, OpenAI Responses, Gemini)
- BYOK encrypted key storage + Jet-managed keys
- Provider-native agent loops with tool-use
- Guardrail Gateway (tool allowlist, budget, audit)
- All 5 tool implementations (web-search, doc-reader, calculator, code-exec, api-caller)
- Enhanced validation engine (pluggable checkers, LLM-as-judge)
- Memory system (session, project, user profile)
- Full context assembly pipeline (query rewrite, hybrid retrieval, reranking)
- Firebase auth integration on all context jobs endpoints
- ORM-model-first schema creation for all context jobs tables on first deployment (`Base.metadata.create_all`)
- No placeholder or dummy implementation scope: all planned systems are intended to be fully production-ready

---

## 2. Architecture Overview

```
User Request
     |
     v
[Firebase Auth Middleware] -----> reject if unauthorized
     |
     v
[Context Jobs API] (FastAPI routers)
     |
     v
[Context Assembly Engine]
  - Load job definition (9 fields)
  - Build system prompt (goal, instructions, role, glossary, relationships, semantic blueprint)
  - Execute retrieval (query rewrite -> hybrid search -> rerank -> dedup)
  - Apply trusted sources filtering
  - Load memory context (session + project + user profile)
  - Resolve tool permissions -> tool definitions
  - Build execution envelope
     |
     v
[Provider Dispatcher]
  - Select provider adapter based on job.execution_provider
  - Decrypt BYOK key or use platform key
  - Translate execution envelope -> provider-native format
     |
     v
[Provider Adapter] (Claude Messages / OpenAI Responses / Gemini)
  - Send system + user messages with tool definitions
  - Enter provider-native agent loop
  - On each tool_use response:
     |
     v
   [Guardrail Gateway]
     - Check tool allowlist (job.tool_permissions)
     - Check budget (tokens, cost, latency, tool call count)
     - Validate arguments
     - Log event (allow/deny)
     - If approved -> execute tool -> return result to provider
     - If denied -> return denial message to provider
     |
     v
  - Provider continues loop until final response or budget exceeded
     |
     v
[Validation Engine]
  - Run enabled validation rules (format, groundedness, citation, policy, custom)
  - Determine outcome using priority tree:
    1. Blocking fail -> blocked_by_policy
    2. Error fail OR grounded violation -> needs_repair
    3. Human review needed -> needs_human_review
    4. Warning fails -> completed_with_warnings
    5. Clean -> completed
     |
     v
[ROP Builder]
  - Assemble 10-section RunOutputPackage
  - Map status -> next_action
  - Persist run state, events, ROP
     |
     v
[Response to Frontend] (poll via GET /runs/:id)
```

---

## 3. Database Schema Changes

### 3.1 New ORM Model: `LlmProviderKeyModel` (`llm_provider_keys`)

Stores BYOK and Jet-managed provider API keys with AES-128 Fernet encryption.

Define this as a SQLAlchemy model (not raw SQL scripts) with:

- `id` UUID primary key
- `owner` (user/org identifier)
- `provider` (`anthropic` | `openai` | `google`)
- `key_label` (user-friendly name)
- `encrypted_key` (Fernet-encrypted API key)
- `key_last_four` (masked display suffix)
- `is_platform_key` boolean (Approach 3 key)
- `status` (`active` | `revoked` | `expired`)
- `last_verified_at`, `last_error`, `usage_count`
- `created_at`, `updated_at`
- unique constraint on (`owner`, `provider`, `key_label`)
- indexes on `owner` and (`owner`, `provider`)

**Encryption approach** (same pattern as vector connections, but real encryption):
- Master key: `LLM_KEY_ENCRYPTION_KEY` env var (Fernet key)
- Encrypt on write: `fernet.encrypt(api_key.encode())`
- Decrypt on read: in-memory only, never logged, never returned in API responses
- Display: only `key_last_four` shown in UI

### 3.2 New ORM Model: `ToolExecutionModel` (`tool_executions`)

Audit log for every tool call during runs (whether approved or denied by gateway).

Define this as a SQLAlchemy model with:

- `id` UUID primary key
- `run_id` FK to `job_runs.id`
- `tool_id`, `tool_name`
- `action` (`execute` | `denied`)
- `status` (`success` | `error` | `denied` | `timeout`)
- `arguments` JSONB (sanitized args)
- `result_summary`, `denial_reason`
- `tokens_used`, `cost_usd`, `latency_ms`
- `created_at`
- index on `run_id`

### 3.3 New ORM Model: `RunMemoryEntryModel` (`run_memory_entries`)

Persistent memory across runs.

Define this as a SQLAlchemy model with:

- `id` UUID primary key
- `owner`
- `job_id` FK to `context_jobs.id` (nullable for user-profile memory)
- `memory_type` (`session` | `project` | `user_profile`)
- `key`, `value` (JSONB)
- `source_run_id` FK to `job_runs.id`
- `expires_at`
- `created_at`, `updated_at`
- indexes on (`owner`, `job_id`), `memory_type`, and `expires_at`

### 3.4 New ORM Model: `ToolRegistryModel` (`tool_registry`)

Admin-managed tool catalog.

Define this as a SQLAlchemy model with:

- `id` (string PK, e.g. `web-search`)
- `name`, `description`, `category`
- `input_schema` JSONB, `output_schema` JSONB
- `is_read_only`, `requires_approval`, `max_timeout_ms`, `enabled`
- `provider_support` JSONB
- `created_at`

### 3.5 ORM Updates: `ContextJobModel` (`context_jobs`)

Update the existing `ContextJobModel` to include provider execution fields:

- `execution_provider` with default `openai` (`openai` | `anthropic` | `google`)
- `execution_model`
- `llm_key_id` FK to `llm_provider_keys.id` (nullable; `NULL` = platform key fallback)
- `max_agent_turns` default `10`

### 3.6 ORM Updates: `JobRunModel` (`job_runs`)

Update the existing `JobRunModel` to include execution metadata:

- `execution_provider`
- `execution_model`
- `total_provider_tokens` default `0`
- `total_tool_calls` default `0`
- `estimated_cost_usd` default `0`
- `agent_turns` default `0`

### 3.7 Schema Creation Strategy (ORM-first)

The context jobs module has **not** been deployed to any live environment yet, so there are no existing context jobs tables in production. When the new code is first deployed, the ORM models will be responsible for creating all required tables for this module.

Because there is no existing production data to preserve or migrate for context jobs, we do **not** need to plan specific Alembic revision files for these tables right now. Alembic migrations only become necessary if, in the future, we need to change tables that have already been deployed (for example, adding or removing columns on `context_jobs` or `job_runs` after the module is live).

For now, the plan is:

- Define/adjust SQLAlchemy ORM models for all context jobs tables (`context_jobs`, `context_assets`, `job_runs`, `context_vector_connections`, `managed_jet_kb_namespaces`, and any new tables like `llm_provider_keys`, `tool_registry`, `tool_executions`, `run_memory_entries`).
- Let the initial deployment create these tables via the ORM metadata.
- Only introduce Alembic migrations later if we need to update tables that are already running in a deployed environment.

---

## 4. Provider Adapter System

### 4.1 Base Adapter Interface

**File:** `context_jobs/providers/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator

@dataclass
class ExecutionEnvelope:
    """Everything Jet assembles before handing to a provider."""
    system_prompt: str           # assembled from job fields
    user_message: str            # user_request + retrieved context
    tools: list[ToolDefinition]  # from tool_registry, filtered by job.tool_permissions
    max_tokens: int              # from budget_settings
    max_turns: int               # from job.max_agent_turns
    temperature: float           # default 0.2
    model: str                   # execution_model
    metadata: dict               # job_id, run_id, owner for tracing

@dataclass
class ToolCall:
    """A tool call requested by the provider."""
    id: str
    tool_id: str
    tool_name: str
    arguments: dict

@dataclass
class ToolResult:
    """Result returned to provider after tool execution."""
    tool_call_id: str
    content: str
    is_error: bool = False

@dataclass
class ProviderResponse:
    """Final or intermediate response from provider."""
    content: str | None
    tool_calls: list[ToolCall]
    stop_reason: str             # 'end_turn' | 'tool_use' | 'max_tokens' | 'budget_exceeded'
    input_tokens: int
    output_tokens: int
    model: str

class ProviderAdapter(ABC):
    """Base class for all LLM provider adapters."""

    @abstractmethod
    async def execute(
        self,
        envelope: ExecutionEnvelope,
        api_key: str,
        tool_executor: "ToolExecutor",  # callback for Guardrail Gateway
    ) -> ProviderResponse:
        """Run the full agent loop until completion or budget exhaustion."""
        ...

    @abstractmethod
    def translate_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        """Convert Jet tool definitions to provider-native format."""
        ...
```

### 4.2 Claude Adapter (Anthropic Messages API)

**File:** `context_jobs/providers/anthropic_adapter.py`

Uses `anthropic` Python SDK. Agent loop pattern:

```python
class ClaudeAdapter(ProviderAdapter):
    async def execute(self, envelope, api_key, tool_executor):
        client = anthropic.Anthropic(api_key=api_key)
        messages = [{"role": "user", "content": envelope.user_message}]
        total_input = total_output = 0
        turns = 0

        while turns < envelope.max_turns:
            response = client.messages.create(
                model=envelope.model,
                max_tokens=envelope.max_tokens,
                system=envelope.system_prompt,
                tools=self.translate_tools(envelope.tools),
                messages=messages,
            )
            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens
            turns += 1

            if response.stop_reason == "end_turn":
                # Extract text content
                text = "".join(b.text for b in response.content if b.type == "text")
                return ProviderResponse(content=text, tool_calls=[], ...)

            if response.stop_reason == "tool_use":
                # Extract tool_use blocks
                tool_blocks = [b for b in response.content if b.type == "tool_use"]
                # Add assistant message
                messages.append({"role": "assistant", "content": response.content})
                # Execute each tool through Guardrail Gateway
                tool_results = []
                for block in tool_blocks:
                    call = ToolCall(id=block.id, tool_id=block.name, ...)
                    result = await tool_executor(call)  # Gateway decides
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result.content,
                        "is_error": result.is_error,
                    })
                messages.append({"role": "user", "content": tool_results})
        # Max turns reached
        return ProviderResponse(content="...", stop_reason="budget_exceeded", ...)
```

**Tool format translation:** Jet `ToolDefinition` -> Claude `{"name", "description", "input_schema"}` (JSON Schema format, native to Claude).

### 4.3 OpenAI Adapter (Responses API)

**File:** `context_jobs/providers/openai_adapter.py`

Uses `openai` Python SDK with the Responses API (not legacy Chat Completions).

```python
class OpenAIAdapter(ProviderAdapter):
    async def execute(self, envelope, api_key, tool_executor):
        client = openai.OpenAI(api_key=api_key)
        tools_native = self.translate_tools(envelope.tools)
        turns = 0
        previous_response_id = None

        while turns < envelope.max_turns:
            params = {
                "model": envelope.model,
                "instructions": envelope.system_prompt,
                "input": envelope.user_message if turns == 0 else tool_results_input,
                "tools": tools_native,
                "max_output_tokens": envelope.max_tokens,
                "temperature": envelope.temperature,
            }
            if previous_response_id:
                params["previous_response_id"] = previous_response_id

            response = client.responses.create(**params)
            previous_response_id = response.id
            turns += 1

            # Check output items for function_call vs message
            function_calls = [i for i in response.output if i.type == "function_call"]
            messages = [i for i in response.output if i.type == "message"]

            if not function_calls:
                text = messages[0].content[0].text if messages else ""
                return ProviderResponse(content=text, ...)

            # Execute tools through gateway
            tool_results_input = []
            for fc in function_calls:
                call = ToolCall(id=fc.call_id, tool_id=fc.name, ...)
                result = await tool_executor(call)
                tool_results_input.append({
                    "type": "function_call_output",
                    "call_id": fc.call_id,
                    "output": result.content,
                })
```

**Tool format:** Jet `ToolDefinition` -> OpenAI `{"type": "function", "name", "description", "parameters"}`.

### 4.4 Gemini Adapter (Google Generative AI)

**File:** `context_jobs/providers/google_adapter.py`

Uses `google-genai` Python SDK.

```python
class GeminiAdapter(ProviderAdapter):
    async def execute(self, envelope, api_key, tool_executor):
        client = genai.Client(api_key=api_key)
        tools_native = self.translate_tools(envelope.tools)
        turns = 0
        contents = [{"role": "user", "parts": [{"text": envelope.user_message}]}]

        while turns < envelope.max_turns:
            response = client.models.generate_content(
                model=envelope.model,
                contents=contents,
                config={
                    "system_instruction": envelope.system_prompt,
                    "tools": tools_native,
                    "max_output_tokens": envelope.max_tokens,
                    "temperature": envelope.temperature,
                },
            )
            turns += 1

            # Check for function calls in response
            function_calls = []
            for part in response.candidates[0].content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    function_calls.append(part.function_call)

            if not function_calls:
                text = response.text
                return ProviderResponse(content=text, ...)

            # Add model response to contents
            contents.append({"role": "model", "parts": response.candidates[0].content.parts})
            # Execute tools, add results
            function_responses = []
            for fc in function_calls:
                call = ToolCall(id=fc.id, tool_id=fc.name, ...)
                result = await tool_executor(call)
                function_responses.append(
                    genai.types.Part.from_function_response(fc.name, {"result": result.content})
                )
            contents.append({"role": "user", "parts": function_responses})
```

**Tool format:** Jet `ToolDefinition` -> Gemini `genai.types.Tool(function_declarations=[...])`.

### 4.5 Provider Registry

**File:** `context_jobs/providers/__init__.py`

```python
PROVIDER_REGISTRY = {
    "anthropic": {
        "adapter_class": ClaudeAdapter,
        "default_model": "claude-sonnet-4-20250514",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-haiku-3-5",
        ],
    },
    "openai": {
        "adapter_class": OpenAIAdapter,
        "default_model": "gpt-4.1",
        "models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o4-mini"],
    },
    "google": {
        "adapter_class": GeminiAdapter,
        "default_model": "gemini-2.5-pro",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
    },
}

def get_provider_adapter(provider: str) -> ProviderAdapter:
    entry = PROVIDER_REGISTRY.get(provider)
    if not entry:
        raise ValueError(f"Unknown provider: {provider}")
    return entry["adapter_class"]()
```

---

## 5. BYOK Key Management

### 5.1 Encryption Service

**File:** `context_jobs/security/key_encryption.py`

```python
from cryptography.fernet import Fernet
import os

ENCRYPTION_KEY = os.environ.get("LLM_KEY_ENCRYPTION_KEY")
# Generate with: Fernet.generate_key().decode()

def encrypt_api_key(plaintext: str) -> str:
    f = Fernet(ENCRYPTION_KEY.encode())
    return f.encrypt(plaintext.encode()).decode()

def decrypt_api_key(ciphertext: str) -> str:
    f = Fernet(ENCRYPTION_KEY.encode())
    return f.decrypt(ciphertext.encode()).decode()

def mask_key(plaintext: str) -> str:
    return plaintext[-4:] if len(plaintext) >= 4 else "****"
```

### 5.2 Key Management API Endpoints

**File:** `apis/routers/llm_provider_keys.py`

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/context-jobs/llm-keys` | List user's keys (masked, never plaintext) |
| POST | `/context-jobs/llm-keys` | Add a key (encrypt + verify with provider) |
| DELETE | `/context-jobs/llm-keys/{key_id}` | Revoke a key |
| POST | `/context-jobs/llm-keys/{key_id}/verify` | Re-verify key works |
| GET | `/context-jobs/providers` | List available providers + models + pricing hints |

**Request/Response shapes:**

```python
class LlmKeyCreate(BaseModel):
    provider: str         # 'anthropic' | 'openai' | 'google'
    key_label: str        # "My Claude Key"
    api_key: str          # plaintext (encrypted before storage, never returned)

class LlmKeyOut(BaseModel):
    id: str
    provider: str
    key_label: str
    key_last_four: str    # "xK9m"
    is_platform_key: bool
    status: str
    last_verified_at: str | None
    created_at: str

class ProviderInfo(BaseModel):
    provider: str
    display_name: str
    models: list[ModelInfo]
    has_platform_key: bool  # whether Jet has a managed key for this provider
```

### 5.3 Key Resolution at Runtime

When a run starts, the orchestrator resolves the API key:

1. If `job.llm_key_id` is set -> decrypt that BYOK key
2. Else if platform key exists for `job.execution_provider` -> use `.env` key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`)
3. Else -> fail run with `MISSING_API_KEY` exception

This covers both Approach 2 (BYOK) and Approach 3 (Jet-managed via platform env vars).

---

## 6. Context Assembly Pipeline

### 6.1 Overview

The context assembly engine transforms a Context Job + user request into an `ExecutionEnvelope` for the provider adapter. This is Jet's core value — the provider never sees raw job config, only the assembled context.

**File:** `context_jobs/assembly/context_assembler.py`

### 6.2 System Prompt Assembly

Build from job fields in this order:

```python
def build_system_prompt(job: ContextJobModel) -> str:
    sections = []

    # 1. Role
    if job.role_configuration:
        sections.append(f"## Your Role\n{job.role_configuration}")

    # 2. Goal
    if job.goal:
        sections.append(f"## Objective\n{job.goal}")

    # 3. Instructions
    if job.stable_instructions:
        sections.append(f"## Instructions\n{job.stable_instructions}")

    # 4. Output Structure
    if job.semantic_blueprint:
        sections.append(f"## Expected Output Format\n{job.semantic_blueprint}")

    # 5. Glossary (domain terms the model must use correctly)
    if job.glossary_terms:
        terms = job.glossary_terms  # list of {term, definition, synonyms, required}
        term_text = "\n".join(
            f"- **{t['term']}**: {t['definition']}"
            + (f" (synonyms: {', '.join(t['synonyms'])})" if t.get('synonyms') else "")
            + (" [REQUIRED - must use this term]" if t.get('required') else "")
            for t in terms
        )
        sections.append(f"## Domain Glossary\n{term_text}")

    # 6. Relationships (entity relationships the model must respect)
    if job.relationships:
        rel_text = "\n".join(
            f"- {r['fromTerm']} {r['relation']} {r['toTerm']}"
            for r in job.relationships
        )
        sections.append(f"## Entity Relationships\n{rel_text}")

    # 7. Escalation policy
    if job.escalation_policy:
        sections.append(f"## Escalation Policy\n{job.escalation_policy}")

    # 8. Budget constraints
    if job.budget_settings:
        bs = job.budget_settings
        sections.append(
            f"## Constraints\n"
            f"- Max output tokens: {bs.get('maxTokens', 4096)}\n"
            f"- Target latency: {bs.get('maxLatencyMs', 30000)}ms\n"
            f"- Cost limit: ${bs.get('maxCostUsd', 0.50)}"
        )

    return "\n\n".join(sections)
```

### 6.3 Retrieval Pipeline (Enhanced)

**Current:** Direct vector search with `goal + user_request` as query.

**Enhanced pipeline** (file: `context_jobs/assembly/retrieval_pipeline.py`):

```
user_request + job.goal
        |
        v
[Query Rewriter] (if retrievalConfig.queryRewriting = true)
  - Use LLM to expand/rephrase query for better retrieval
  - Generate 2-3 query variants
        |
        v
[Hybrid Search] (if retrievalConfig.hybridRetrieval = true)
  - Vector similarity search (existing adapters)
  - Keyword/BM25 search (where adapter supports it)
  - Merge results with reciprocal rank fusion
        |
        v
[Trusted Sources Filter]
  - Filter results against job.trusted_sources
  - Apply trustLevel weighting (required > preferred > optional)
  - Apply freshness filtering (recent_only, prefer_recent, any)
        |
        v
[Reranker] (if retrievalConfig.reranking = true)
  - Use cross-encoder or LLM to rerank top-N results
  - Default: Cohere rerank or LLM-based reranking
        |
        v
[Top-K Selection]
  - Take top maxDocuments results (default 8, max 50)
  - Build RAG context string
  - Build source_trace_events for each source used
        |
        v
[User Message Assembly]
  - Combine: user_request + retrieved_context + citation_instructions
```

### 6.4 Memory Context Loading

**File:** `context_jobs/assembly/memory_loader.py`

```python
def load_memory_context(owner: str, job_id: str, memory_config: dict, db) -> str:
    sections = []

    if memory_config.get("sessionMemory"):
        # Load recent memory entries for this job (session scope)
        entries = db.query(RunMemoryEntry).filter(
            owner=owner, job_id=job_id, memory_type="session",
            expires_at > now()
        ).order_by(created_at.desc()).limit(20).all()
        if entries:
            sections.append("## Session Memory\n" + format_memories(entries))

    if memory_config.get("projectMemory"):
        entries = db.query(RunMemoryEntry).filter(
            owner=owner, job_id=job_id, memory_type="project",
            expires_at > now()
        ).order_by(created_at.desc()).limit(10).all()
        if entries:
            sections.append("## Project Memory\n" + format_memories(entries))

    if memory_config.get("userProfileMemory"):
        entries = db.query(RunMemoryEntry).filter(
            owner=owner, job_id=None, memory_type="user_profile",
            expires_at > now()
        ).order_by(created_at.desc()).limit(10).all()
        if entries:
            sections.append("## User Profile\n" + format_memories(entries))

    return "\n\n".join(sections)
```

### 6.5 Tool Definition Resolution

**File:** `context_jobs/assembly/tool_resolver.py`

```python
def resolve_tools(job_permissions: list[dict], db) -> list[ToolDefinition]:
    """Match job.tool_permissions against tool_registry to build provider tool defs."""
    enabled_tools = [tp for tp in (job_permissions or []) if tp.get("enabled")]
    if not enabled_tools:
        return []

    tool_ids = [tp["toolId"] for tp in enabled_tools]
    registry_tools = db.query(ToolRegistryModel).filter(
        ToolRegistryModel.id.in_(tool_ids),
        ToolRegistryModel.enabled == True
    ).all()

    definitions = []
    for rt in registry_tools:
        perm = next(tp for tp in enabled_tools if tp["toolId"] == rt.id)
        definitions.append(ToolDefinition(
            id=rt.id,
            name=rt.name,
            description=rt.description,
            input_schema=rt.input_schema,
            is_read_only=perm.get("readOnly", True),
        ))
    return definitions
```

---

## 7. Orchestration Engine (Rewritten)

### 7.1 New Orchestrator

**File:** `context_jobs/orchestrator.py` (replace current implementation)

The orchestrator is the central coordinator. It does NOT do LLM reasoning — it coordinates Jet's pipeline stages and delegates execution to the provider adapter.

```python
async def execute_run(run_id: str, job: ContextJobModel, user_request: str, db):
    """Main orchestration pipeline — runs in worker thread."""
    run = db.query(JobRunModel).get(run_id)
    budget_tracker = BudgetTracker(job.budget_settings or {})

    try:
        # === STAGE 1: PLANNING ===
        update_run_state(run, "planning", db)
        log_step(run, "planning", "running", "Assembling context from job definition")

        system_prompt = build_system_prompt(job)
        memory_context = load_memory_context(run.owner, job.id, job.memory_config or {}, db)
        tools = resolve_tools(job.tool_permissions, db)

        log_step(run, "planning", "completed", f"Assembled {len(tools)} tools, system prompt ready")

        # === STAGE 2: RETRIEVING ===
        update_run_state(run, "retrieving", db)
        log_step(run, "retrieving", "running", "Executing retrieval pipeline")

        rag_context, retrieval_events, source_traces = await execute_retrieval(
            job=job, user_request=user_request, db=db
        )
        run.retrieval_events = [e.to_dict() for e in retrieval_events]
        run.source_trace_events = [s.to_dict() for s in source_traces]
        db.commit()

        log_step(run, "retrieving", "completed",
                 f"Retrieved {len(retrieval_events)} sources, {len(source_traces)} traces")

        # === STAGE 3: EXECUTING ===
        update_run_state(run, "executing", db)
        log_step(run, "executing", "running", "Sending to provider for execution")

        # Build execution envelope
        user_message = assemble_user_message(user_request, rag_context, memory_context)
        envelope = ExecutionEnvelope(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=tools,
            max_tokens=job.budget_settings.get("maxTokens", 4096) if job.budget_settings else 4096,
            max_turns=job.max_agent_turns or 10,
            temperature=0.2,
            model=job.execution_model or get_default_model(job.execution_provider),
            metadata={"job_id": str(job.id), "run_id": str(run.id), "owner": job.owner},
        )

        # Resolve API key
        api_key = resolve_api_key(job, db)

        # Create tool executor (wraps Guardrail Gateway)
        tool_executor = GatewayToolExecutor(
            job=job, run=run, budget_tracker=budget_tracker, db=db
        )

        # Get provider adapter and execute
        adapter = get_provider_adapter(job.execution_provider or "openai")
        response = await adapter.execute(envelope, api_key, tool_executor)

        # Persist execution metadata
        run.output_text = response.content
        run.execution_provider = job.execution_provider
        run.execution_model = response.model
        run.total_provider_tokens = response.input_tokens + response.output_tokens
        run.total_tool_calls = len(tool_executor.executed_calls)
        run.agent_turns = tool_executor.turns
        run.tool_events = [tc.to_dict() for tc in tool_executor.executed_calls]
        db.commit()

        log_step(run, "executing", "completed",
                 f"Provider returned after {tool_executor.turns} turns, "
                 f"{response.input_tokens + response.output_tokens} tokens")

        # === STAGE 4: VALIDATING ===
        update_run_state(run, "validating", db)
        log_step(run, "validating", "running", "Running validation rules")

        validation_events, validation_summary = await run_validation(
            output_text=response.content,
            job=job,
            source_traces=source_traces,
            api_key=api_key,        # for LLM-as-judge validators
            provider=job.execution_provider,
        )
        run.validation_events = [v.to_dict() for v in validation_events]
        db.commit()

        log_step(run, "validating", "completed",
                 f"Validation: {validation_summary.overall_decision}")

        # === BUILD ROP ===
        rop = build_run_output_package(
            run=run, job=job,
            validation_summary=validation_summary,
            source_traces=source_traces,
            tool_executor=tool_executor,
            budget_tracker=budget_tracker,
            response=response,
        )

        # === FINALIZE ===
        state, outcome = determine_terminal_state(rop["status"])
        run.state = state
        run.outcome = outcome
        run.run_output_package = rop
        run.ended_at = datetime.utcnow()
        run.latency_ms = int((run.ended_at - run.started_at).total_seconds() * 1000)
        db.commit()

        # === PERSIST MEMORY ===
        if job.memory_config:
            await persist_memory_updates(run, job, response.content, db)

    except Exception as e:
        # Build failed ROP
        handle_run_failure(run, e, db)
```

### 7.2 Worker Pool

Keep the current threaded worker pool pattern (2 workers, max 50 queue) but rename from `mock_run` to `run`:

```python
RUN_QUEUE: queue.Queue = queue.Queue(maxsize=50)
WORKERS: list[threading.Thread] = []
MAX_WORKERS = 2

def enqueue_run(run_id: str):
    RUN_QUEUE.put(run_id)

def start_run_workers():
    for i in range(MAX_WORKERS):
        t = threading.Thread(target=_run_worker, daemon=True, name=f"run-worker-{i}")
        t.start()
        WORKERS.append(t)

def _run_worker():
    while True:
        run_id = RUN_QUEUE.get()
        try:
            asyncio.run(execute_run(run_id, ...))
        except Exception:
            logger.exception(f"Worker error for run {run_id}")
        finally:
            RUN_QUEUE.task_done()
```

### 7.3 Terminal State Determination

Directly from Replit `simulateRun` logic (must match exactly):

```python
def determine_terminal_state(rop_status: str) -> tuple[str, str]:
    """Map ROP status -> (job_runs.state, job_runs.outcome)"""
    mapping = {
        "completed":               ("completed", "accepted"),
        "completed_with_warnings": ("completed", "accepted_with_warnings"),
        "needs_repair":            ("repair",    "needs_review"),
        "needs_human_review":      ("escalated", "needs_review"),
        "blocked_by_policy":       ("escalated", "escalated"),
        "failed":                  ("failed",    "error"),
    }
    return mapping.get(rop_status, ("failed", "error"))
```

---

## 8. Guardrail Gateway

### 8.1 Purpose

The gateway sits between the provider's tool-use requests and actual tool execution. The provider decides **what** to call; Jet decides **whether** it's allowed.

**File:** `context_jobs/gateway/guardrail_gateway.py`

### 8.2 Gateway Checks (in order)

```python
class GuardrailGateway:
    def __init__(self, job, run, budget_tracker, db):
        self.job = job
        self.run = run
        self.budget = budget_tracker
        self.db = db
        self.executed_calls = []
        self.turns = 0

    async def check_and_execute(self, tool_call: ToolCall) -> ToolResult:
        """Process a tool call through all gateway checks."""

        # 1. Tool Allowlist Check
        if not self._is_tool_allowed(tool_call.tool_id):
            return self._deny(tool_call, "TOOL_NOT_PERMITTED",
                f"Tool '{tool_call.tool_id}' is not in this job's allowed tools")

        # 2. Read-Only Check
        tool_perm = self._get_permission(tool_call.tool_id)
        if tool_perm.get("readOnly") and self._is_write_action(tool_call):
            return self._deny(tool_call, "WRITE_DENIED",
                f"Tool '{tool_call.tool_id}' is read-only for this job")

        # 3. Budget Check
        if self.budget.is_exceeded():
            return self._deny(tool_call, "BUDGET_EXCEEDED",
                f"Budget limit reached: {self.budget.reason()}")

        # 4. Argument Sanitization
        sanitized_args, issues = self._sanitize_arguments(tool_call)
        if issues:
            return self._deny(tool_call, "UNSAFE_ARGUMENTS",
                f"Arguments failed sanitization: {'; '.join(issues)}")

        # 5. Execute Tool
        try:
            tool_impl = get_tool_implementation(tool_call.tool_id)
            result = await tool_impl.execute(sanitized_args)
            self.budget.record_tool_call()
            self._log_execution(tool_call, result, "success")
            return ToolResult(tool_call_id=tool_call.id, content=result, is_error=False)
        except Exception as e:
            self._log_execution(tool_call, str(e), "error")
            return ToolResult(tool_call_id=tool_call.id, content=f"Tool error: {e}", is_error=True)

    def _deny(self, tool_call, code, reason):
        self._log_execution(tool_call, reason, "denied")
        return ToolResult(tool_call_id=tool_call.id, content=reason, is_error=True)
```

### 8.3 Budget Tracker

**File:** `context_jobs/gateway/budget_tracker.py`

```python
class BudgetTracker:
    def __init__(self, budget_settings: dict):
        self.max_tokens = budget_settings.get("maxTokens", 4096)
        self.max_latency_ms = budget_settings.get("maxLatencyMs", 30000)
        self.max_cost_usd = budget_settings.get("maxCostUsd", 0.50)
        self.max_tool_calls = budget_settings.get("maxToolCalls", 20)  # added

        self.tokens_used = 0
        self.cost_usd = 0.0
        self.tool_calls = 0
        self.start_time = time.time()

    def is_exceeded(self) -> bool:
        if self.tool_calls >= self.max_tool_calls: return True
        if self.tokens_used >= self.max_tokens: return True
        if self.cost_usd >= self.max_cost_usd: return True
        elapsed_ms = (time.time() - self.start_time) * 1000
        if elapsed_ms >= self.max_latency_ms: return True
        return False

    def record_tool_call(self):
        self.tool_calls += 1

    def record_tokens(self, input_tokens, output_tokens, model):
        self.tokens_used += input_tokens + output_tokens
        self.cost_usd += estimate_cost(input_tokens, output_tokens, model)
```

---

## 9. Tool System

### 9.1 Tool Interface

**File:** `context_jobs/tools/base.py`

```python
class BaseTool(ABC):
    id: str
    name: str
    description: str
    input_schema: dict  # JSON Schema

    @abstractmethod
    async def execute(self, arguments: dict) -> str:
        """Execute the tool and return result as string."""
        ...
```

### 9.2 Tool Implementations

#### web-search

**File:** `context_jobs/tools/web_search.py`

Uses the Tavily API (or fallback to SerpAPI / Google Custom Search).

```python
class WebSearchTool(BaseTool):
    id = "web-search"
    name = "Web Search"
    description = "Search the web for current information on a topic"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {"type": "integer", "default": 5, "maximum": 10},
        },
        "required": ["query"]
    }

    async def execute(self, arguments: dict) -> str:
        query = arguments["query"]
        num = arguments.get("num_results", 5)
        # Use Tavily API
        client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        results = client.search(query, max_results=num)
        formatted = []
        for r in results["results"]:
            formatted.append(f"**{r['title']}**\nURL: {r['url']}\n{r['content'][:500]}")
        return "\n\n---\n\n".join(formatted)
```

**Env var:** `TAVILY_API_KEY`

#### doc-reader

**File:** `context_jobs/tools/doc_reader.py`

Fetches and extracts text from URLs or uploaded documents.

```python
class DocReaderTool(BaseTool):
    id = "doc-reader"
    name = "Document Reader"
    description = "Read and extract text content from a URL or document"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to read"},
            "max_chars": {"type": "integer", "default": 5000},
        },
        "required": ["url"]
    }

    async def execute(self, arguments: dict) -> str:
        url = arguments["url"]
        max_chars = arguments.get("max_chars", 5000)
        # Use httpx + BeautifulSoup for HTML, or trafilatura for article extraction
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
        # Extract clean text
        text = trafilatura.extract(resp.text) or ""
        return text[:max_chars]
```

**Dependencies:** `httpx`, `trafilatura`, `beautifulsoup4`

#### calculator

**File:** `context_jobs/tools/calculator.py`

Safe mathematical expression evaluator.

```python
class CalculatorTool(BaseTool):
    id = "calculator"
    name = "Calculator"
    description = "Evaluate mathematical expressions safely"
    input_schema = {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Math expression to evaluate (e.g., '2 * pi * 5.3')"},
        },
        "required": ["expression"]
    }

    async def execute(self, arguments: dict) -> str:
        expr = arguments["expression"]
        # Use simpleeval for safe evaluation (no exec/eval)
        from simpleeval import simple_eval
        import math
        result = simple_eval(expr, functions={
            "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
            "tan": math.tan, "log": math.log, "log10": math.log10,
            "abs": abs, "round": round, "pow": pow,
        }, names={"pi": math.pi, "e": math.e})
        return str(result)
```

**Dependencies:** `simpleeval`

#### code-exec

**File:** `context_jobs/tools/code_executor.py`

Sandboxed Python code execution using a subprocess with timeout.

```python
class CodeExecutorTool(BaseTool):
    id = "code-exec"
    name = "Code Executor"
    description = "Execute Python code in a sandboxed environment and return output"
    input_schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute"},
            "timeout_seconds": {"type": "integer", "default": 10, "maximum": 30},
        },
        "required": ["code"]
    }

    async def execute(self, arguments: dict) -> str:
        code = arguments["code"]
        timeout = min(arguments.get("timeout_seconds", 10), 30)
        # Run in subprocess with restricted imports
        # Use RestrictedPython or subprocess with --isolated flag
        result = subprocess.run(
            [sys.executable, "-I", "-c", code],
            capture_output=True, text=True, timeout=timeout,
            env={"PATH": os.environ.get("PATH", "")},  # minimal env
        )
        output = result.stdout[:3000]
        if result.stderr:
            output += f"\n[stderr]: {result.stderr[:1000]}"
        return output or "(no output)"
```

**Security:** `-I` flag (isolated mode), minimal env, timeout, output truncation. For production: consider Docker sandbox or Firecracker.

#### api-caller

**File:** `context_jobs/tools/api_caller.py`

Make HTTP requests to external APIs.

```python
class ApiCallerTool(BaseTool):
    id = "api-caller"
    name = "API Caller"
    description = "Make HTTP requests to external APIs"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "API endpoint URL"},
            "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET"},
            "headers": {"type": "object", "description": "Request headers"},
            "body": {"type": "object", "description": "Request body (for POST)"},
            "timeout_seconds": {"type": "integer", "default": 10},
        },
        "required": ["url"]
    }

    async def execute(self, arguments: dict) -> str:
        url = arguments["url"]
        method = arguments.get("method", "GET")
        headers = arguments.get("headers", {})
        body = arguments.get("body")
        timeout = min(arguments.get("timeout_seconds", 10), 30)

        # Domain allowlist check (prevent SSRF)
        parsed = urllib.parse.urlparse(url)
        if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
            return "Error: localhost requests are not allowed"
        if not parsed.scheme.startswith("http"):
            return "Error: only HTTP/HTTPS URLs are allowed"

        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "POST":
                resp = await client.post(url, headers=headers, json=body)
            else:
                resp = await client.get(url, headers=headers)

        return f"Status: {resp.status_code}\n\n{resp.text[:3000]}"
```

### 9.3 Tool Registry Seeding

**File:** `context_jobs/tools/seed_registry.py`

On startup, seed the `tool_registry` table with the 5 tools if they don't exist. Each entry includes the full JSON Schema for `input_schema`.

### 9.4 Tool Implementation Registry

**File:** `context_jobs/tools/__init__.py`

```python
TOOL_IMPLEMENTATIONS = {
    "web-search": WebSearchTool(),
    "doc-reader": DocReaderTool(),
    "calculator": CalculatorTool(),
    "code-exec": CodeExecutorTool(),
    "api-caller": ApiCallerTool(),
}

def get_tool_implementation(tool_id: str) -> BaseTool:
    impl = TOOL_IMPLEMENTATIONS.get(tool_id)
    if not impl:
        raise ValueError(f"No implementation for tool: {tool_id}")
    return impl
```

---

## 10. Validation Engine

### 10.1 Pluggable Checker Architecture

**File:** `context_jobs/validation/engine.py`

```python
class ValidationChecker(ABC):
    rule_type: str

    @abstractmethod
    async def check(self, output_text: str, job: ContextJobModel,
                    source_traces: list, api_key: str, provider: str) -> ValidationResult:
        ...

CHECKER_REGISTRY = {
    "format": FormatChecker(),
    "groundedness": GroundednessChecker(),
    "citation": CitationChecker(),
    "policy": PolicyChecker(),
    "custom": CustomChecker(),
}

async def run_validation(output_text, job, source_traces, api_key, provider):
    """Run all enabled validation rules through their checkers."""
    rules = [r for r in (job.validation_rules or []) if r.get("enabled")]
    events = []
    for rule in rules:
        checker = CHECKER_REGISTRY.get(rule["type"])
        if checker:
            result = await checker.check(output_text, job, source_traces, api_key, provider)
            events.append(ValidationEvent(
                rule=rule["name"], passed=result.passed,
                message=result.message, severity=rule["severity"]
            ))
    summary = build_validation_summary(events, source_traces, job)
    return events, summary
```

### 10.2 Checker Implementations

#### FormatChecker

Checks output structure against `semantic_blueprint` (if defined). Uses basic heuristics (section headers present, length bounds) or LLM-as-judge for complex templates.

#### GroundednessChecker

Uses LLM-as-judge: sends output + source_traces to a secondary LLM call asking "Is every factual claim in this output supported by the provided sources?" Returns pass/fail with specific ungrounded claims.

#### CitationChecker

Checks for `[source:...]` or `[1]` citation patterns in output. Can be regex-based (fast) or LLM-assisted (for natural citations).

#### PolicyChecker

Checks against `policy_profile` rules. For `strict_compliance`: no speculative language, no disclaimers about AI limitations in output, all required glossary terms used correctly.

#### CustomChecker

Evaluates user-defined rule descriptions using LLM-as-judge. Sends rule `description` + output to LLM and asks for pass/fail judgment.

### 10.3 Validation Summary Builder

Implements the exact Replit priority tree:

```python
def build_validation_summary(events, source_traces, job):
    blocking_fails = [e for e in events if not e.passed and e.severity == "blocking"]
    error_fails = [e for e in events if not e.passed and e.severity == "error"]
    warning_fails = [e for e in events if not e.passed and e.severity == "warning"]

    # Grounded mode check
    grounded_mode = bool(
        (job.retrieval_config or {}).get("hybridRetrieval") or
        (job.trusted_sources and len(job.trusted_sources) > 0)
    )
    grounded_violation = False
    if grounded_mode:
        required_sources = [s for s in (job.trusted_sources or []) if s.get("trustLevel") == "required"]
        for rs in required_sources:
            trace = find_trace(source_traces, rs)
            if not trace or trace.evidence_strength == "weak":
                grounded_violation = True
                break

    # Priority determination
    if blocking_fails:
        status = "blocked_by_policy"
        decision = "blocked"
        confidence = "high"
    elif error_fails or grounded_violation:
        status = "needs_repair"
        decision = "failed"
        confidence = "medium"
    elif (job.escalation_policy == "always_review" or
          majority_weak_evidence(source_traces)):
        status = "needs_human_review"
        decision = "passed_with_warnings"
        confidence = "low"
    elif warning_fails:
        status = "completed_with_warnings"
        decision = "passed_with_warnings"
        confidence = "medium"
    else:
        status = "completed"
        decision = "passed"
        confidence = "high"

    return ValidationSummary(
        overall_decision=decision, confidence_level=confidence,
        checks=[...], status=status
    )
```

---

## 11. Memory System

### 11.1 Memory Write (Post-Run)

**File:** `context_jobs/memory/memory_service.py`

After a successful run, extract key facts/decisions and persist to `run_memory_entries`:

```python
async def persist_memory_updates(run, job, output_text, db):
    memory_config = job.memory_config or {}
    retention_days = memory_config.get("retentionDays", 30)
    expires_at = datetime.utcnow() + timedelta(days=retention_days)

    if memory_config.get("sessionMemory"):
        # Extract session-relevant facts from output using LLM
        facts = await extract_memory_facts(output_text, "session", job)
        for fact in facts:
            entry = RunMemoryEntry(
                owner=job.owner, job_id=job.id, memory_type="session",
                key=fact["key"], value=fact["value"],
                source_run_id=run.id, expires_at=expires_at,
            )
            db.add(entry)

    if memory_config.get("projectMemory"):
        facts = await extract_memory_facts(output_text, "project", job)
        for fact in facts:
            entry = RunMemoryEntry(
                owner=job.owner, job_id=job.id, memory_type="project",
                key=fact["key"], value=fact["value"],
                source_run_id=run.id, expires_at=expires_at,
            )
            db.add(entry)

    db.commit()
```

### 11.2 Memory Expiration

A periodic cleanup task deletes expired entries:

```python
def cleanup_expired_memory(db):
    db.query(RunMemoryEntry).filter(
        RunMemoryEntry.expires_at < datetime.utcnow()
    ).delete()
    db.commit()
```

Run via a startup background task on a 1-hour interval.

---

## 12. Run Output Package (ROP) Builder

### 12.1 Full ROP Assembly

**File:** `context_jobs/rop/builder.py`

Must produce the exact 10-section structure defined in `shared/schema.ts`. Maps 1:1 with the Replit prototype contract.

```python
def build_run_output_package(run, job, validation_summary, source_traces,
                              tool_executor, budget_tracker, response):
    status = validation_summary.status

    # Result type mapping (from Replit)
    RESULT_TYPE_MAP = {
        "standard": "text_output",
        "analysis": "structured_summary",
        "research": "citation_backed_answer",
        "generation": "formatted_prompt",
        "decision": "decision_memo",
        "extraction": "extracted_fields",
        "review": "recommendation",
        "monitoring": "checklist",
    }

    # Status -> Next Action mapping (from Replit)
    NEXT_ACTION_MAP = {
        "completed": ("use_result", "Result is ready to use"),
        "completed_with_warnings": ("review_result", "Review result before using"),
        "needs_repair": ("repair_and_rerun", "Fix validation issues and re-run"),
        "needs_human_review": ("request_approval", "Request approval to proceed"),
        "blocked_by_policy": ("escalate", "Escalate for policy review"),
        "failed": ("retry_later", "Retry when issue is resolved"),
    }

    next_type, next_label = NEXT_ACTION_MAP.get(status, ("retry_later", "Retry"))

    return {
        "status": status,
        "primaryResult": {
            "resultType": RESULT_TYPE_MAP.get(job.workflow_type, "text_output"),
            "title": f"{job.name} — Run Result",
            "content": response.content or "",
        },
        "validationSummary": {
            "overallDecision": validation_summary.overall_decision,
            "confidenceLevel": validation_summary.confidence_level,
            "checks": validation_summary.checks,
            "repairReason": validation_summary.repair_reason,
        },
        "sourceSummary": build_source_summary(source_traces, job),
        "warnings": build_warnings(validation_summary, source_traces),
        "exceptions": build_exceptions(validation_summary),
        "nextAction": {"type": next_type, "label": next_label},
        "traceSummary": {
            "stages": [log.to_dict() for log in run.step_logs_parsed],
            "toolEvents": tool_executor.total_calls,
            "retrievalEvents": len(run.retrieval_events or []),
            "repairCycles": 0,  # TODO: implement repair loops
            "replayAvailable": True,
        },
        "memoryStateChanges": {
            "updated": bool(job.memory_config and any(
                job.memory_config.get(k) for k in
                ["sessionMemory", "projectMemory", "userProfileMemory"]
            )),
            "changes": [],
        },
        "costTimeSummary": {
            "startedAt": run.started_at.isoformat(),
            "endedAt": datetime.utcnow().isoformat(),
            "runtimeSeconds": round((datetime.utcnow() - run.started_at).total_seconds(), 2),
            "estimatedCost": f"${budget_tracker.cost_usd:.4f}",
            "modelUsageSummary": f"{response.model}: {response.input_tokens}in/{response.output_tokens}out",
            "toolUsageCount": tool_executor.total_calls,
            "retrievalUsageCount": len(run.retrieval_events or []),
        },
        "auditMetadata": {
            "runId": str(run.id),
            "jobId": str(job.id),
            "jobVersion": job.version,
            "workspaceId": "default",
            "actor": job.owner,
            "environment": os.environ.get("ENVIRONMENT", "development"),
            "approvalState": "pending" if job.approval_required else "not_required",
            "policyProfile": job.policy_profile,
        },
    }
```

---

## 13. Firebase Auth Integration

### 13.1 Current Auth System

The backend already has Firebase auth in `dependencies/auth.py` and `firebse/firebase_setup.py`. It uses Firebase ID tokens verified server-side.

### 13.2 Apply to Context Jobs Routes

Add the existing `get_current_user` dependency to all context jobs routers:

**File changes:** `apis/routers/context_jobs.py`, `apis/routers/context_vector_connections.py`, new `apis/routers/llm_provider_keys.py`

```python
from dependencies.auth import get_current_user

@router.get("/jobs")
async def list_jobs(user = Depends(get_current_user), db = Depends(get_db)):
    # Filter by user.id as owner
    return services.list_jobs(owner=user.id, db=db)
```

Replace all `owner="current_user"` defaults with the authenticated user's ID from Firebase.

### 13.3 Multi-Tenancy

- All queries filtered by `owner = authenticated_user.id`
- BYOK keys scoped to owner
- Memory entries scoped to owner
- Tool executions linked to runs (which are linked to jobs with owner)

---

## 14. API Endpoint Summary (Complete)

### Existing (keep, update with auth)

| Method | Path | Change |
|--------|------|--------|
| GET | `/context-jobs/jobs` | Add auth, filter by owner |
| GET | `/context-jobs/jobs/{id}` | Add auth, verify owner |
| POST | `/context-jobs/jobs` | Add auth, set owner from token |
| PATCH | `/context-jobs/jobs/{id}` | Add auth, verify owner |
| POST | `/context-jobs/jobs/{id}/duplicate` | Add auth |
| GET | `/context-jobs/jobs/{id}/stats` | Add auth |
| POST | `/context-jobs/jobs/{id}/run` | Add auth; **use new orchestrator** |
| GET | `/context-jobs/runs` | Add auth, filter by owner |
| GET | `/context-jobs/runs/queue-status` | Add auth |
| GET | `/context-jobs/runs/{id}` | Add auth, verify owner |
| PATCH | `/context-jobs/runs/{id}/decision` | Add auth |
| GET/POST/PATCH/DELETE | `/context-jobs/assets[...]` | Add auth |
| GET | `/context-jobs/stats` | Add auth, scope to owner |
| POST | `/context-jobs/jobs/{id}/ingest` | Add auth |
| GET/POST/PATCH/DELETE/POST test | `/context-jobs/vector-connections[...]` | Add auth |

### New Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/context-jobs/llm-keys` | List user's provider keys (masked) |
| POST | `/context-jobs/llm-keys` | Add BYOK key |
| DELETE | `/context-jobs/llm-keys/{id}` | Revoke key |
| POST | `/context-jobs/llm-keys/{id}/verify` | Re-verify key |
| GET | `/context-jobs/providers` | List providers + models + platform key availability |
| GET | `/context-jobs/tools` | List tool registry (available tools) |
| GET | `/context-jobs/runs/{id}/tool-executions` | Tool execution audit log for a run |

---

## 15. New Dependencies

Add to `requirements.txt`:

```
anthropic>=0.45.0          # Claude Messages API
google-genai>=1.0.0        # Gemini API
cryptography>=43.0.0       # Fernet encryption for BYOK
tavily-python>=0.5.0       # Web search tool
trafilatura>=1.12.0        # Doc reader (article extraction)
beautifulsoup4>=4.12.0     # Doc reader (HTML parsing)
simpleeval>=1.0.0          # Calculator (safe math eval)
httpx>=0.27.0              # Async HTTP (api-caller, doc-reader)
```

`openai` is already in requirements.

---

## 16. Environment Variables (New)

```
# BYOK encryption
LLM_KEY_ENCRYPTION_KEY=       # Fernet.generate_key() output

# Provider platform keys (Approach 3 / development)
OPENAI_API_KEY=               # already exists
ANTHROPIC_API_KEY=            # already exists
GEMINI_API_KEY=               # already exists

# Tool: Web Search
TAVILY_API_KEY=               # for web-search tool

# Optional
MAX_RUN_WORKERS=2             # worker pool size
MAX_RUN_QUEUE=50              # queue depth
MAX_AGENT_TURNS_DEFAULT=10    # default max provider loop iterations
```

---

## 17. File Structure (New/Modified)

```
context_jobs/
├── __init__.py
├── orchestrator.py              # REWRITE — new pipeline
├── schemas.py                   # UPDATE — add execution fields
├── services.py                  # UPDATE — pass execution fields
├── managed_jet_kb.py            # KEEP
├── vector_connection_schemas.py # KEEP
├── vector_connection_services.py# KEEP
│
├── providers/                   # NEW — provider adapter system
│   ├── __init__.py              # registry + get_provider_adapter()
│   ├── base.py                  # ExecutionEnvelope, ProviderAdapter ABC
│   ├── anthropic_adapter.py     # Claude Messages API
│   ├── openai_adapter.py        # OpenAI Responses API
│   └── google_adapter.py        # Gemini API
│
├── assembly/                    # NEW — context assembly pipeline
│   ├── __init__.py
│   ├── context_assembler.py     # top-level assembler
│   ├── prompt_builder.py        # system prompt from job fields
│   ├── retrieval_pipeline.py    # query rewrite + hybrid + rerank
│   ├── memory_loader.py         # load memory context
│   └── tool_resolver.py         # resolve tool definitions
│
├── gateway/                     # NEW — guardrail gateway
│   ├── __init__.py
│   ├── guardrail_gateway.py     # check + execute
│   └── budget_tracker.py        # token/cost/time/call tracking
│
├── tools/                       # NEW — tool implementations
│   ├── __init__.py              # tool registry
│   ├── base.py                  # BaseTool ABC
│   ├── web_search.py            # Tavily
│   ├── doc_reader.py            # trafilatura
│   ├── calculator.py            # simpleeval
│   ├── code_executor.py         # subprocess sandbox
│   ├── api_caller.py            # httpx
│   └── seed_registry.py         # DB seeding
│
├── validation/                  # NEW — pluggable validation
│   ├── __init__.py
│   ├── engine.py                # run_validation()
│   ├── format_checker.py
│   ├── groundedness_checker.py
│   ├── citation_checker.py
│   ├── policy_checker.py
│   └── custom_checker.py
│
├── memory/                      # NEW — memory persistence
│   ├── __init__.py
│   ├── memory_service.py        # persist + load + cleanup
│   └── memory_extractor.py      # LLM-based fact extraction
│
├── rop/                         # NEW — ROP builder (extracted)
│   ├── __init__.py
│   └── builder.py               # build_run_output_package()
│
├── security/                    # NEW — key encryption
│   ├── __init__.py
│   └── key_encryption.py        # encrypt/decrypt/mask
│
├── embeddings/                  # KEEP
├── ingestion/                   # KEEP
└── retrieval/                   # KEEP

apis/routers/
├── context_jobs.py              # UPDATE — auth + new fields
├── context_vector_connections.py # UPDATE — auth
└── llm_provider_keys.py         # NEW

schemas/
├── context_jobs_model.py        # UPDATE — add execution columns
├── context_vector_connection_model.py  # KEEP
├── managed_jet_kb_namespace_model.py   # KEEP
├── llm_provider_key_model.py    # NEW
├── tool_registry_model.py       # NEW
├── tool_execution_model.py      # NEW
└── run_memory_entry_model.py    # NEW

alembic/versions/
└── (No new context-jobs migration files in initial rollout)
   Create/adjust ORM models and rely on initial ORM metadata table creation.
```

---

## 18. (Reserved for Testing Strategy)

Testing details for this module (unit tests, integration tests, and contract tests) will be defined later once the implementation has stabilized and we know which parts of the system are most critical to cover. For now, this section is intentionally left as a placeholder.

---

## 19. Implementation Phases

### Phase 1: Foundation (Database + Auth + BYOK)
- Define/update all context-jobs ORM models for initial deployment table creation
- New tables: `llm_provider_keys`, `tool_registry`, `tool_executions`, `run_memory_entries`
- Add execution columns to `context_jobs` and `job_runs`
- BYOK encryption service
- Key management API endpoints
- Firebase auth on all context jobs endpoints
- Provider catalog endpoint
- Ensure models are loaded before `Base.metadata.create_all()` during app startup

### Phase 2: Provider Adapters + Orchestrator
- Base adapter interface
- Claude adapter (Anthropic Messages API with tool loop)
- OpenAI adapter (Responses API with tool loop)
- Gemini adapter (generateContent with tool loop)
- Provider registry
- Rewrite orchestrator to use new pipeline
- Context assembly engine (prompt builder, tool resolver)
- API key resolution (BYOK + platform)
- Budget tracker

### Phase 3: Tools + Guardrail Gateway
- Tool base interface
- All 5 tool implementations (web-search, doc-reader, calculator, code-exec, api-caller)
- Tool registry seeding
- Guardrail Gateway (allowlist, budget, sanitization, logging)
- Tool execution audit table writes
- Tool-related API endpoints

### Phase 4: Retrieval Enhancement + Validation Engine
- Query rewriting (LLM-based)
- Trusted sources filtering
- Reranking
- Hybrid retrieval support
- Pluggable validation checkers (format, groundedness, citation, policy, custom)
- LLM-as-judge for groundedness/citation/custom
- Full validation summary with priority tree
- Source evidence strength calculation

### Phase 5: Memory + ROP + Polish
- Memory extraction from run outputs
- Memory loading into context
- Memory expiration cleanup
- Extract ROP builder into dedicated module
- Verify ROP contract matches Replit schema.ts exactly
- Update Pydantic schemas for new fields (execution_provider, execution_model, etc.)
- Comprehensive E2E tests for full pipeline
- Error handling and edge cases

---

## 20. Key Design Decisions

1. **Provider owns the agent loop.** Jet never implements its own planner or step sequencer. The provider API handles reasoning, tool sequencing, and stop conditions. Jet only provides context in and validates output out.

2. **Gateway is synchronous on the tool-call path.** Each tool_use from the provider hits the gateway before execution. This adds latency per tool call but ensures policy enforcement.

3. **BYOK keys are encrypted at rest with Fernet.** Same pattern as vector connection `encrypted_config` but with real encryption (not base64). Master key in env var; for production, move to AWS KMS / GCP KMS / Azure Key Vault.

4. **Polling, not streaming.** Frontend polls `GET /runs/:id` every 2 seconds. This matches the Replit prototype and avoids WebSocket complexity. Step logs update in the database as the run progresses, so the frontend sees intermediate states.

5. **Tool implementations are server-side.** All tools execute on the Jet server, not on the provider's infrastructure. This gives Jet full control over tool execution, audit, and budget enforcement.

6. **Validation may use secondary LLM calls.** Groundedness and custom checkers invoke the same provider (or a cheaper model) for evaluation. This is a cost trade-off but necessary for reliable validation.

7. **Memory uses LLM extraction.** Rather than storing raw output, we extract key facts and decisions using a lightweight LLM call. This keeps memory concise and queryable.

8. **No MCP in this plan.** Approach 1 (Jet as MCP server) is explicitly deferred. The tool system is internal only.

---

## 21. Provider Multi-Agent Orchestration + Artifact Tools (Implemented)

### 21.1 Design Principles

1. **Provider decides routing.** Jet compiles a bounded specialist catalog; the main provider agent chooses direct tool calls or `delegate-to-agent` per turn. Jet does not hardcode step plans.
2. **No forced multi-agency.** Orchestrator instructions are neutral: use direct tools when sufficient; delegate only when isolated specialist context materially helps. No minimum delegation quota and no ban on delegation.
3. **Single-agent remains default.** `executionMode: "single_agent"` preserves current behavior (one agent loop + tools only).
4. **Multi-agent is opt-in per job.** `executionMode: "provider_multi_agent"` exposes `delegate-to-agent` alongside regular tools.
5. **PRD alignment.** Bounded catalog (max 5 specialists), no open-ended swarm, provider-native loop, Jet owns gateway + ROP.

### 21.2 Execution Modes

| Mode | Value | Behavior |
|------|-------|----------|
| Default | `single_agent` | One provider agent loop; tools only; no delegation |
| Multi-agent | `provider_multi_agent` | Main agent + `delegate-to-agent` + direct tools |

**Job field:** `execution_mode` / `executionMode` on `context_jobs` (default `single_agent`).

### 21.3 Specialist Agent Catalog (Bounded)

Compiled from job `toolPermissions` — specialists are included only when their tools are enabled.

| Specialist | Tools | When provider may delegate |
|------------|-------|----------------------------|
| `researcher` | web-search, doc-reader | Deep multi-source investigation |
| `analyst` | calculator, code-exec | Calculation / Python analysis loops |
| `producer` | file-write, docx-generate, doc-reader | Long-form deliverables and file artifacts |
| `integrator` | api-caller | External HTTP API tasks |
| `validator` | doc-reader, web-search (read-only) | Read-only verification / QA |

**Delegation primitive:** `delegate-to-agent` meta-tool with `{ agent_name, task }`. Gateway runs nested provider execution via `AgentDelegateRunner` with isolated context; parent receives summary only.

### 21.4 Orchestrator Prompt Guidance (Neutral)

When `provider_multi_agent`, system prompt adds:

- Direct tools are always available.
- `delegate-to-agent` is optional.
- Choose simplest correct approach; no requirement to delegate.

Jet does **not** add quotas, mandates, or prohibitions on delegation.

### 21.5 New Artifact Tools

#### `file-write`

- **Purpose:** Create/update text artifacts in per-run workspace.
- **Extensions:** `.md`, `.txt`, `.py`, `.ts`, `.tsx`, `.js`, `.json`, `.yaml`, `.yml`, `.sql`, `.html`, `.css`, `.sh`, `.csv`
- **Input:** `path` (relative), `content`, `mode` (`overwrite` | `append`)
- **Output path:** `{RUN_ARTIFACT_ROOT}/{owner}/{runId}/{path}`

#### `docx-generate`

- **Purpose:** Generate Word documents from structured JSON spec.
- **Output:** `.docx` only.
- **Input spec:** `path`, `title`, `subtitle?`, `sections[]`, `tables[]?`

#### Code execution (existing `code-exec`)

- **Language:** Python only (`CODE_EXEC_DOCKER_IMAGE`, default `python:3.11-alpine`).
- **Dependencies:** Fixed image contents only; no per-run `pip install`.

### 21.6 Implementation Files

| Area | Path |
|------|------|
| Specialist catalog | `context_jobs/agents/catalog.py` |
| Delegation runner | `context_jobs/agents/delegate_runner.py` |
| Artifact path safety | `context_jobs/tools/artifact_paths.py` |
| File write tool | `context_jobs/tools/file_write.py` |
| DOCX tool | `context_jobs/tools/docx_generate.py` |
| Gateway delegation | `context_jobs/gateway/guardrail_gateway.py` |
| Run wiring | `context_jobs/run_engine.py` |
| Prompt guidance | `context_jobs/assembly/prompt_builder.py` |
| ROP artifacts | `context_jobs/rop/builder.py` |
| Registry seed | `context_jobs/tools/seed_registry.py` |

### 21.7 Env Vars

```env
RUN_ARTIFACT_ROOT=data/run-artifacts
CODE_EXEC_DOCKER_IMAGE=python:3.11-alpine
```

### 21.8 ROP Additions

- `artifacts[]` — paths written by `file-write` / `docx-generate`
- Delegation events appended to `toolEvents` when specialists run

### 21.9 What Jet Is NOT Building

- Not a competitor to Claude Code / Cursor / OpenAI Agents SDK
- Not unlimited runtime agent creation
- Not Jet-side step sequencer (CrewAI-style)
- Not multi-language code-exec (Python only for now)
- Not PDF export in this pass (future `pdf-export` tool)
