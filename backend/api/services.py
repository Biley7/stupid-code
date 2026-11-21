"""Shared engine instances for the REST API and the lazy dependency provider.

Importing this module opens no database and builds no LLM_Router. ``Services`` objects
are built by ``Services.from_environment()`` on first use, or injected by tests
(Requirements 9.13, 9.15, decision D9).
"""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from backend.engines.cache_store import CacheStore
from backend.engines.dissection import DissectionService
from backend.engines.ingestion import GitRunner
from backend.engines.llm_router import LLMRouter, StructuredLLM
from backend.engines.mastery import Clock, MasteryEngine, system_clock
from backend.engines.pedagogy import PedagogyEngine

_CREATE_LOCK = threading.Lock()


@dataclass
class Services:
    """The engines one API process shares."""

    cache: CacheStore
    router: StructuredLLM
    clock: Clock
    mastery: MasteryEngine
    pedagogy: PedagogyEngine
    dissection: DissectionService
    git_runner: GitRunner = subprocess.run
    workspace: Path | None = None

    @classmethod
    def build(
        cls,
        cache: CacheStore,
        router: StructuredLLM,
        clock: Clock = system_clock,
        *,
        git_runner: GitRunner = subprocess.run,
        workspace: Path | None = None,
    ) -> Services:
        """Wire the engines over the given cache, router, and clock."""
        mastery = MasteryEngine(cache, router, clock)
        pedagogy = PedagogyEngine(cache, router)
        dissection = DissectionService(cache, pedagogy, mastery)
        return cls(
            cache=cache,
            router=router,
            clock=clock,
            mastery=mastery,
            pedagogy=pedagogy,
            dissection=dissection,
            git_runner=git_runner,
            workspace=workspace,
        )

    @classmethod
    def from_environment(cls) -> Services:
        """Build the engines from the environment (``CacheStore()``, ``LLMRouter()``)."""
        return cls.build(CacheStore(), LLMRouter(), system_clock)


def get_services(request: Request) -> Services:
    """FastAPI dependency: ``app.state.services``, created once under a lock.

    Tests either pass ``services`` to ``create_app`` or override this function through
    ``app.dependency_overrides``.
    """
    state = request.app.state
    services = getattr(state, "services", None)
    if services is not None:
        return services
    with _CREATE_LOCK:
        services = getattr(state, "services", None)
        if services is None:
            services = Services.from_environment()
            state.services = services
            state.services_created_by_app = True
    return services


__all__ = ["Services", "get_services"]
