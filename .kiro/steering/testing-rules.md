# Testing Rules

## Frameworks
- `pytest` for unit and integration tests.
- `hypothesis` for property-based tests.

Layout: `backend/tests/unit/` and `backend/tests/properties/`.

## Deterministic Engines
Each of these engines needs conventional unit tests and, where applicable, property-based tests:
`ast_parser`, `graph_engine`, `dsa_scanner`, `topology`, `mastery`.

Property tests check invariants, not repeated examples. Important invariants include:
- AST hash stability and idempotency.
- Graph integrity and dependency relationships.
- Blast-radius consistency.
- Structural detection invariants.
- Valid mastery state transitions.
- Deterministic output for equivalent inputs.

## Offline Rule
The whole suite must run offline.
- Use deterministic mock LLM providers.
- No live Gemini or Ollama calls, no external network services, no API keys.
- External provider behavior must be mockable.
- Running `pytest` must never trigger a paid API request or external model call.
- Tests must not read a real `.env`; default to `LLM_PROVIDER=mock`.
