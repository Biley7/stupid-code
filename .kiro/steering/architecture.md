# Architecture (authoritative)

Strict hexagonal architecture. Dependencies point inward: delivery layers (`api`, `mcp_server`) call `engines`, which use `domain`. `domain` depends on nothing in this project.

## Layers

### `backend/domain/`
- Pure Pydantic/SQLModel schemas, entities, value structures, state machines, domain validation, shared contracts.
- No FastAPI or HTTP imports, no frontend dependencies, no provider-specific API dependencies.
- Independent of delivery mechanisms.

### `backend/engines/`
Core analysis and application engines. Planned modules: `ingestion.py`, `ast_parser.py`, `graph_engine.py`, `dsa_scanner.py`, `spec_grounder.py`, `topology.py`, `pedagogy.py`, `mastery.py`, `llm_router.py`.
- Each engine has one clear responsibility.
- Anything derivable from source, AST, graph structures, or repository metadata must be computed deterministically. The LLM must never replace deterministic analysis.

### `backend/mcp_server/`
- FastMCP tool wrappers and MCP protocol integration.
- Wrappers call `backend/engines/` directly. No duplicated analysis or business logic in MCP handlers. MCP is not a second implementation of the app.

### `backend/api/`
- FastAPI app, routers, HTTP endpoints, SSE streaming, Hosted Web App integration, Kiro Crew HMAC proxy authentication.
- HTTP concerns stay here. Routes orchestrate engines; they do not contain core analysis logic.
- Authentication and request-boundary concerns stay separate from domain logic.

### `power/` (reserved)
Kiro Agent Plugin / Kiro Power. Future: `plugin.json`, `skills/`, `mcp.json`.

### `crew/` (reserved)
Kiro Crew App. Future: `app.json`, `agents/`, `skills/`.

### `ui/` (reserved)
Frontend. Intended stack: React, TypeScript, Tailwind CSS, React Flow.

## Static-Analysis Safety (non-negotiable)
Analyzed repositories may be untrusted or malicious.
- Never execute, import, or run analyzed repository code, scripts, or package install scripts.
- Never treat source code as executable input to an LLM or shell.
- Use static parsing and structural inspection only.
- Prefer shallow clones for remote ingestion.
- Enforce file-count, per-file-size, and total-repository-size limits, plus time/resource guardrails.
- Treat repository content and LLM responses as untrusted data.

## Structured LLM Outputs
- All LLM responses must conform to explicit Pydantic schemas and be validated before use.
- Handle malformed or incomplete output safely.
- Never use raw prose as an internal data contract.
- Keep deterministic analysis separate from probabilistic interpretation.

## Configuration
Settings come from environment variables (see `.env.example`). `LLM_PROVIDER` is one of `gemini`, `ollama`, `mock`. Secrets never go in code, logs, or Git.
