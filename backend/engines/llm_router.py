"""LLM router for the pedagogy engine (Spec #02).

The router hides the choice of language-model provider behind one method,
``generate_structured``. Provider SDKs (``google.genai``, ``openai``) are imported
lazily inside the provider code paths, so importing this module never loads them.
This module imports no web framework and no other engine module.

Logging policy: the router logs only the provider name and the error category, at
WARNING. It never logs API keys, headers, prompts, or response bodies.

Context_Slice JSON shape (single source of truth for the mock provider and for
``pedagogy.py``)
-----------------------------------------------------------------------------
The user prompt is ``MOCK_SLICE_MARKER + canonical_json(slice)``, where the marker is
``"CONTEXT_SLICE_JSON:\\n"`` and ``canonical_json`` is
``json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))``. The
mock splits at the first marker, ignores everything before it, and parses the rest
as one JSON object. Keys the mock reads are listed below. Other keys are allowed and
ignored. Every key listed for a lens is required for that lens.

L1 and L2 slice::

    {
      "target": {
        "id": str,            # file_path + "::" + qualname
        "kind": str,          # SymbolKind value
        "qualname": str,
        "signature": str,
        "language": str,      # Language value
        "file_path": str,
        "start_line": int,    # 1-based, inclusive
        "end_line": int,
        "ast_hash": str,      # symbol ast_hash; the mock embeds ast_hash[:12]
        "source_lines": [{"line": int, "text": str}, ...],  # real 1-based numbers
        "truncated": bool,
      },
      "callers": [{"id": str, "signature": str}, ...],      # direct callers, sorted
      "callees": [{"id": str, "signature": str}, ...],      # direct callees, sorted
      "dsa_signals": [DSASignal.model_dump(mode="json"), ...],
      "spec_links": [SpecLink.model_dump(mode="json"), ...],  # not read by the mock
      "topology": TopologyProfile.model_dump(mode="json"),    # not read by the mock
      "commits": [str, ...],                                  # not read by the mock
    }

L3 slice::

    {
      "scope": str,           # repo_id or a directory key; the L3 target_id
      "ast_hash": str,        # the L3 Target_AST_Hash (sha256 hex); mock embeds [:12]
      "topology": TopologyProfile.model_dump(mode="json"),
      "spec_links": [SpecLink.model_dump(mode="json"), ...],  # report order, first is used
      "eligible_paths": [str, ...],                           # sorted
      "drift_items": [SpecDriftItem.model_dump(mode="json"), ...],  # not read by the mock
    }

Socratic grading slice (Spec #03; response model ``SocraticGrade``)::

    {
      "kind": "socratic_grade",                               # not read by the mock
      "target": {                                             # not read by the mock
        "id": str, "qualname": str, "signature": str, "file_path": str,
        "start_line": int, "end_line": int,
        "source_lines": [{"line": int, "text": str}, ...],  # at most 400 lines
      },
      "questions": [
        {
          "question_id": str,                                 # not read by the mock
          "prompt": str,                                      # not read by the mock
          "line_reference": str,                              # not read by the mock
          "expected_concepts": [str, ...],
        },
        ...
      ],
      "answers": [{"question_id": str, "answer": str}, ...],  # mock reads "answer"
    }

The mock grade is deterministic: ``score = hits / len(concepts)`` with no rounding,
where ``concepts`` is the set of distinct ``expected_concepts`` over all questions and
a hit is a concept that occurs case-insensitively as a substring of any answer. An
empty concept set is a shape error (category ``validation``).
"""

import asyncio
import inspect
import json
import logging
from collections.abc import Callable, Mapping
from typing import Any, Literal, NoReturn, Protocol, TypeVar, cast

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.domain.models import (
    AlternativeArchitecture,
    DSACard,
    FlowStep,
    L1SyntaxExplanation,
    L2FlowExplanation,
    L3ArchitectureExplanation,
    Language,
    SocraticGrade,
    SyntaxAnnotation,
)

__all__ = [
    "LLMConfigError",
    "LLMRouter",
    "LLMRouterError",
    "LLMSettings",
    "MOCK_SLICE_MARKER",
    "StructuredLLM",
]

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

ErrorCategory = Literal["validation", "connection", "timeout", "provider", "configuration"]

_CATEGORIES: frozenset[str] = frozenset(
    {"validation", "connection", "timeout", "provider", "configuration"}
)

_PROVIDERS: tuple[str, ...] = ("mock", "gemini", "ollama")


class LLMRouterError(Exception):
    """A router failure. ``str(error)`` is the message and never holds a prompt or key."""

    provider: str
    category: ErrorCategory

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        category: ErrorCategory = "provider",
    ) -> None:
        if category not in _CATEGORIES:
            raise ValueError(f"unknown LLMRouterError category: {category!r}")
        super().__init__(message)
        self.provider = provider
        self.category = category


class LLMConfigError(LLMRouterError):
    """Invalid router configuration. The category is always ``configuration``."""

    def __init__(self, message: str, *, provider: str = "") -> None:
        super().__init__(message, provider=provider, category="configuration")


class LLMSettings(BaseSettings):
    """Router settings read from environment variables.

    The class never reads a ``.env`` file by default. A delivery layer that wants one
    passes ``LLMSettings(_env_file=".env")``. A variable set to the empty string stays
    empty; only an unset variable takes the default.
    """

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        populate_by_name=True,
        case_sensitive=True,
    )

    llm_provider: str = Field("mock", validation_alias="LLM_PROVIDER")
    gemini_api_key: SecretStr = Field(SecretStr(""), validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-2.5-flash", validation_alias="GEMINI_MODEL")
    ollama_base_url: str = Field("http://localhost:11434/v1", validation_alias="OLLAMA_BASE_URL")
    ollama_model: str = Field("qwen3.5", validation_alias="OLLAMA_MODEL")


class StructuredLLM(Protocol):
    """Anything that turns two prompts into a validated instance of ``response_model``."""

    async def generate_structured(
        self, system_prompt: str, user_prompt: str, response_model: type[T]
    ) -> T: ...


class LLMRouter:
    """Dispatches structured generation to the configured provider."""

    def __init__(self, settings: LLMSettings | None = None) -> None:
        self._settings = settings if settings is not None else LLMSettings()
        self._provider = self._validate(self._settings)

    @property
    def provider(self) -> str:
        return self._provider

    @staticmethod
    def _validate(settings: LLMSettings) -> str:
        provider = settings.llm_provider
        if provider not in _PROVIDERS:
            _log_failure(provider="invalid", category="configuration")
            raise LLMConfigError(
                "LLM_PROVIDER must be exactly one of: " + ", ".join(_PROVIDERS),
                provider="invalid",
            )
        if provider == "gemini":
            if not settings.gemini_api_key.get_secret_value().strip():
                _fail_config("GEMINI_API_KEY is missing", provider)
            if not settings.gemini_model.strip():
                _fail_config("GEMINI_MODEL must not be empty", provider)
        elif provider == "ollama":
            if not settings.ollama_model.strip():
                _fail_config("OLLAMA_MODEL must not be empty", provider)
            if not settings.ollama_base_url.strip():
                _fail_config("OLLAMA_BASE_URL must not be empty", provider)
        return provider

    async def generate_structured(
        self, system_prompt: str, user_prompt: str, response_model: type[T]
    ) -> T:
        try:
            if self._provider == "mock":
                return await self._generate_mock(system_prompt, user_prompt, response_model)
            if self._provider == "gemini":
                return await self._generate_gemini(system_prompt, user_prompt, response_model)
            return await self._generate_ollama(system_prompt, user_prompt, response_model)
        except LLMRouterError as exc:
            _log_failure(provider=exc.provider or self._provider, category=exc.category)
            raise

    # Provider paths. SDK imports belong inside these methods, never at module level.

    async def _generate_mock(
        self, system_prompt: str, user_prompt: str, response_model: type[T]
    ) -> T:
        builder = _MOCK_BUILDERS.get(response_model)
        if builder is None:
            raise LLMRouterError(
                f"unsupported response model: {response_model.__name__}",
                provider="mock",
                category="validation",
            )
        _head, marker, payload = user_prompt.partition(MOCK_SLICE_MARKER)
        if not marker:
            raise _mock_error("context slice marker is missing")
        try:
            context = json.loads(payload)
        except ValueError:
            raise _mock_error("context slice is not valid JSON") from None
        if not isinstance(context, dict):
            raise _mock_error("context slice must be a JSON object")
        try:
            return cast(T, builder(context))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            # Pydantic's ValidationError is a ValueError. The original message can hold
            # slice values, so it is not copied into the router error.
            raise _mock_error("context slice does not match the expected shape") from None

    async def _generate_gemini(
        self, system_prompt: str, user_prompt: str, response_model: type[T]
    ) -> T:
        # One attempt only. The schema sent to Gemini is sanitized; the reply is still
        # validated against the original strict model.
        client: Any = None
        try:
            try:
                client = _make_gemini_client(self._settings)
                from google.genai import types
            except ImportError:
                raise _provider_error("gemini", "provider", "SDK is not available") from None
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=_gemini_schema(response_model),
            )
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=self._settings.gemini_model,
                    contents=user_prompt,
                    config=config,
                ),
                _PROVIDER_TIMEOUT_SECONDS,
            )
        except LLMRouterError:
            raise
        except Exception as exc:
            raise _map_sdk_error("gemini", exc) from None
        finally:
            await _close_quietly(client)
        try:
            text = response.text
        except Exception:
            text = None
        parsed = _parse_model(text, response_model)
        if parsed is None:
            raise _provider_error("gemini", "validation", "parsing or validation failed")
        return parsed

    async def _generate_ollama(
        self, system_prompt: str, user_prompt: str, response_model: type[T]
    ) -> T:
        # At most two attempts with identical prompts, each with its own timeout.
        schema_text = json.dumps(response_model.model_json_schema(), sort_keys=True)
        messages = [
            {
                "role": "system",
                "content": (
                    f"{system_prompt}\n\nRespond with one JSON object that conforms to this "
                    f"JSON Schema and nothing else:\n{schema_text}"
                ),
            },
            {"role": "user", "content": user_prompt},
        ]
        client: Any = None
        try:
            try:
                client = _make_ollama_client(self._settings)
            except ImportError:
                raise _provider_error("ollama", "provider", "SDK is not available") from None
            for _attempt in range(_OLLAMA_ATTEMPTS):
                try:
                    response = await asyncio.wait_for(
                        client.chat.completions.create(
                            model=self._settings.ollama_model,
                            messages=messages,
                            response_format={"type": "json_object"},
                        ),
                        _PROVIDER_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    raise _map_sdk_error("ollama", exc) from None
                try:
                    text = response.choices[0].message.content
                except (AttributeError, IndexError, KeyError, TypeError):
                    text = None
                parsed = _parse_model(text, response_model)
                if parsed is not None:
                    return parsed
        finally:
            await _close_quietly(client)
        raise _provider_error(
            "ollama", "validation", "parsing or validation failed after one retry"
        )


_PROVIDER_TIMEOUT_SECONDS = 60
_GEMINI_TIMEOUT_MS = 60_000
_OLLAMA_ATTEMPTS = 2  # the first call plus exactly one retry

_TIMEOUT_CLASS_NAMES: frozenset[str] = frozenset(
    {
        "TimeoutError",
        "APITimeoutError",
        "TimeoutException",
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
    }
)
_CONNECTION_CLASS_NAMES: frozenset[str] = frozenset({"APIConnectionError", "TransportError"})


def _make_gemini_client(settings: LLMSettings) -> Any:
    """Build the ``google-genai`` client. Tests replace this with a fake factory."""
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(timeout=_GEMINI_TIMEOUT_MS),
    )


def _make_ollama_client(settings: LLMSettings) -> Any:
    """Build the OpenAI-compatible async client. Tests replace this with a fake factory."""
    import openai

    return openai.AsyncOpenAI(
        base_url=settings.ollama_base_url,
        api_key="ollama",  # fixed placeholder the OpenAI client requires, not a secret
        timeout=_PROVIDER_TIMEOUT_SECONDS,
    )


def _gemini_schema(response_model: type[BaseModel]) -> dict[str, Any]:
    """Return the model's JSON schema without any ``additionalProperties`` key.

    Strict models (``extra="forbid"``) emit ``additionalProperties: false``, which the
    Gemini API rejects. The result is a new structure; the model's own schema is not
    changed. ``$defs``/``$ref`` are kept: the SDK inlines them when it builds the request.
    """
    return cast(dict[str, Any], _strip_additional_properties(response_model.model_json_schema()))


def _strip_additional_properties(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: _strip_additional_properties(value)
            for key, value in node.items()
            if key != "additionalProperties"
        }
    if isinstance(node, list):
        return [_strip_additional_properties(item) for item in node]
    return node


def _parse_model[M: BaseModel](text: object, response_model: type[M]) -> M | None:
    """Validate provider text against the strict model. ``None`` means unusable output."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        return response_model.model_validate_json(text)
    except ValueError:  # pydantic's ValidationError is a ValueError
        return None


def _provider_error(provider: str, category: ErrorCategory, detail: str) -> LLMRouterError:
    return LLMRouterError(
        f"{provider} provider {category} error: {detail}", provider=provider, category=category
    )


def _map_sdk_error(provider: str, exc: BaseException) -> LLMRouterError:
    """Map an SDK or transport exception to a router error.

    Only class names are used, so no request detail, header, or key can reach the
    message. Timeouts are checked first because ``APITimeoutError`` is a subclass of
    ``APIConnectionError``.
    """
    names = {cls.__name__ for cls in type(exc).__mro__}
    category: ErrorCategory
    if names & _TIMEOUT_CLASS_NAMES:
        category = "timeout"
    elif names & _CONNECTION_CLASS_NAMES:
        category = "connection"
    else:
        category = "provider"
    return _provider_error(provider, category, type(exc).__name__)


async def _close_quietly(client: Any) -> None:
    """Release a client's resources. Failures here never replace the real outcome."""
    close = getattr(client, "close", None)
    if not callable(close):
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception:
        pass


def _fail_config(message: str, provider: str) -> NoReturn:
    _log_failure(provider=provider, category="configuration")
    raise LLMConfigError(message, provider=provider)


def _log_failure(*, provider: str, category: str) -> None:
    logger.warning("llm router failure: provider=%s category=%s", provider, category)


# --- Deterministic mock provider -------------------------------------------------------
# No randomness, clock, network, or SDK import. Every value comes from the slice.

MOCK_SLICE_MARKER = "CONTEXT_SLICE_JSON:\n"

_MAX_ANNOTATIONS = 3
_MAX_CALL_STEPS = 10
_MAX_SIDE_EFFECTS = 4
_MAX_EVIDENCE = 20
_SPEC_QUOTE_CHARS = 200
_SIDE_EFFECT_MARKERS: tuple[str, ...] = ("open(", "print(", "requests.", "subprocess")
_PATTERNS: tuple[str, ...] = (
    "Feature-Sliced",
    "Flat / Script",
    "Hexagonal / Clean Architecture",
    "Layered MVC",
    "Modular Monolith",
)


def _mock_error(message: str) -> LLMRouterError:
    return LLMRouterError(f"mock provider: {message}", provider="mock", category="validation")


def _text(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _number(mapping: Mapping[str, Any], key: str) -> int:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _items(mapping: Mapping[str, Any], key: str) -> list[Any]:
    value = mapping[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list")
    return value


def _clip(value: str, limit: int) -> str:
    return value[:limit]


def _short_qualname(symbol_id: str) -> str:
    return symbol_id.split("::", 1)[-1]


def _build_l1(context: Mapping[str, Any]) -> L1SyntaxExplanation:
    target = cast(Mapping[str, Any], context["target"])
    qualname = _text(target, "qualname")
    kind = _text(target, "kind")
    language = _text(target, "language")
    digest = _text(target, "ast_hash")[:12]
    lines = _items(target, "source_lines")
    annotations: list[SyntaxAnnotation] = []
    for entry in lines:
        text = _text(entry, "text").strip()
        if not text:
            continue
        annotations.append(
            SyntaxAnnotation(
                line_start=_number(entry, "line"),
                line_end=_number(entry, "line"),
                construct=_clip(text, 2000),
                explanation=f"This line is part of the {kind} {qualname} (ast {digest}).",
                what_if_removed=(
                    f"Removing this line changes the behavior of the {kind} {qualname} "
                    f"(ast {digest})."
                ),
            )
        )
        if len(annotations) == _MAX_ANNOTATIONS:
            break
    return L1SyntaxExplanation(
        target_id=_text(target, "id"),
        language=Language(language),
        summary=f"The {kind} {qualname} is written in {language} (ast {digest}).",
        annotations=annotations,
        key_takeaway=(
            f"{qualname} (ast {digest}) has {len(annotations)} annotated "
            f"line{'' if len(annotations) == 1 else 's'}."
        ),
    )


def _build_l2(context: Mapping[str, Any]) -> L2FlowExplanation:
    target = cast(Mapping[str, Any], context["target"])
    qualname = _text(target, "qualname")
    digest = _text(target, "ast_hash")[:12]
    signature = _text(target, "signature")
    callers = sorted({_text(item, "id") for item in _items(context, "callers")})
    callees = sorted({_text(item, "id") for item in _items(context, "callees")})
    steps = [
        FlowStep(
            step_number=1,
            location=_clip(f"{_text(target, 'file_path')}:{_number(target, 'start_line')}", 1000),
            action=_clip(f"Enter {qualname} ({digest})", 1000),
            data_transformation=_clip(f"Receives the arguments of {signature}", 1000),
        )
    ]
    for callee in callees[:_MAX_CALL_STEPS]:
        callee_name = _short_qualname(callee)
        steps.append(
            FlowStep(
                step_number=len(steps) + 1,
                location=_clip(callee, 1000),
                action=_clip(f"Call {callee_name}", 1000),
                data_transformation=_clip(f"Passes values from {qualname} to {callee_name}", 1000),
            )
        )
    haystack = [signature] + [_text(entry, "text") for entry in _items(target, "source_lines")]
    side_effects = [
        f"possible side effect: {marker} in {qualname}"
        for marker in _SIDE_EFFECT_MARKERS
        if any(marker in chunk for chunk in haystack)
    ][:_MAX_SIDE_EFFECTS]
    cards = [
        DSACard(
            chapter=signal["chapter"],
            pattern_name=_text(signal, "pattern_name"),
            start_line=_number(signal, "start_line"),
            end_line=_number(signal, "end_line"),
            why_used_here="Evidence: " + str(signal["evidence"][0]),
            time_complexity="not determined",
            space_complexity="not determined",
        )
        for signal in _items(context, "dsa_signals")
    ]
    return L2FlowExplanation(
        target_id=_text(target, "id"),
        execution_steps=steps,
        upstream_callers=callers,
        downstream_callees=callees,
        side_effects=side_effects,
        dsa_cards=cards,
    )


def _build_l3(context: Mapping[str, Any]) -> L3ArchitectureExplanation:
    scope = _text(context, "scope")
    digest = _text(context, "ast_hash")[:12]
    topology = cast(Mapping[str, Any], context["topology"])
    pattern = _text(topology, "detected_pattern")
    confidence = float(topology["confidence"])
    metrics = cast(Mapping[str, Any], topology["boundary_metrics"])
    cross_ratio = float(metrics["cross_folder_import_ratio"])
    isolation = float(metrics["domain_isolation_score"])
    profile_evidence = [str(item) for item in _items(topology, "evidence")]
    evidence = profile_evidence[:_MAX_EVIDENCE]
    if not evidence:
        evidence = [str(path) for path in _items(context, "eligible_paths")][:1]
    why = (
        f"The folder structure of {scope} follows the {pattern} pattern "
        f"(confidence {confidence:.2f}, ast {digest})."
    )
    if profile_evidence:
        why += " Evidence: " + "; ".join(profile_evidence[:3]) + "."
    alternatives = [
        AlternativeArchitecture(
            pattern_name=cast(Any, name),
            why_not_chosen=(
                f"{pattern} was detected with confidence {confidence:.2f} (ast {digest}), "
                f"and the structure of {scope} fits {name} less well."
            ),
            when_to_switch=(
                f"Consider {name} if the layout of {scope} changes. The cross-folder import "
                f"ratio is {cross_ratio:.2f} and the domain isolation score is {isolation:.2f}."
            ),
        )
        for name in [p for p in _PATTERNS if p != pattern][:2]
    ]
    links = _items(context, "spec_links")
    rationale = None
    if links:
        rationale = f'Spec excerpt: "{_text(links[0], "excerpt")[:_SPEC_QUOTE_CHARS]}"'
    return L3ArchitectureExplanation(
        target_id=scope,
        topology_pattern=cast(Any, pattern),
        why_this_folder_structure=why,
        structural_evidence=evidence,
        alternatives=alternatives,
        spec_rationale=rationale,
    )


def _build_socratic_grade(context: Mapping[str, Any]) -> SocraticGrade:
    concepts: set[str] = set()
    for question in _items(context, "questions"):
        for concept in _items(question, "expected_concepts"):
            if not isinstance(concept, str):
                raise TypeError("expected_concepts must hold strings")
            concepts.add(concept)
    if not concepts:
        # Checked before the division so the handler reports a validation error.
        raise ValueError("expected_concepts must not be empty")
    answers = [_text(item, "answer").casefold() for item in _items(context, "answers")]
    hits = sum(1 for concept in concepts if any(concept.casefold() in a for a in answers))
    return SocraticGrade(
        score=hits / len(concepts),
        feedback=f"Matched {hits} of {len(concepts)} expected concepts.",
    )


_MOCK_BUILDERS: dict[type[BaseModel], Callable[[Mapping[str, Any]], BaseModel]] = {
    L1SyntaxExplanation: _build_l1,
    L2FlowExplanation: _build_l2,
    L3ArchitectureExplanation: _build_l3,
    SocraticGrade: _build_socratic_grade,
}
