"""Dissection_Service: one explanation plus its blast radius, shared by every surface.

``DissectionService.dissect_many`` validates the lens, asks the Pedagogy_Engine for each
explanation, builds the call graph once from the stored Snapshot, traces each Target's
blast radius with the Graph_Engine, and, for L1 or L2 with Study Mode on, records the
views through the Mastery_Engine in one transaction after every result exists. When any
step fails, the error propagates and no result is returned.

The Pedagogy_Engine and the Snapshot read use public ``CacheStore`` methods, so they run
outside any transaction. ``MasteryEngine.record_views`` opens its own transaction
afterwards (baseline mismatch M2).

For an L3 Target (the ``repo_id`` or a directory), the blast radius is traced on a copy of
the graph that holds the scope as an isolated ``node_type="scope"`` node, which gives
empty caller and callee lists and ``impact_score`` 0.0 (decision D6).

This module contains no parsing, call resolution, or graph logic of its own and imports
no web framework or MCP module.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import networkx as nx

from backend.domain.models import (
    BlastRadius,
    ExplanationEnvelope,
    PedagogyLens,
    RepoGraphSnapshot,
)
from backend.engines.cache_store import CacheStore
from backend.engines.graph_engine import build_graph, trace_blast_radius
from backend.engines.mastery import MasteryEngine, trackable_symbols
from backend.engines.pedagogy import (
    PedagogyEngine,
    PedagogyError,
    PedagogyErrorKind,
    build_symbol_index,
)

__all__ = [
    "DEFAULT_MAX_DEPTH",
    "DissectionResult",
    "DissectionService",
    "InvalidLensError",
]

DEFAULT_MAX_DEPTH = 3

_MAX_TARGET_ECHO = 200
_VIEW_LENSES = frozenset({PedagogyLens.L1_SYNTAX, PedagogyLens.L2_FLOW})


class InvalidLensError(ValueError):
    """The lens is not ``L1_SYNTAX``, ``L2_FLOW``, or ``L3_ARCHITECTURE``."""


@dataclass(frozen=True)
class DissectionResult:
    """The explanation of one Target and its blast radius."""

    envelope: ExplanationEnvelope
    blast_radius: BlastRadius


def _parse_lens(lens: object) -> PedagogyLens:
    try:
        return PedagogyLens(lens)
    except ValueError:
        raise InvalidLensError(
            "lens must be one of L1_SYNTAX, L2_FLOW, or L3_ARCHITECTURE"
        ) from None


def _echo(value: str) -> str:
    return value if len(value) <= _MAX_TARGET_ECHO else value[:_MAX_TARGET_ECHO] + "..."


def _missing_snapshot(repo_id: str) -> PedagogyError:
    return PedagogyError(
        PedagogyErrorKind.MISSING_DATA,
        f"missing cached data for repo {_echo(repo_id)!r}: snapshot",
    )


def _unknown_symbol(target_id: str) -> PedagogyError:
    return PedagogyError(
        PedagogyErrorKind.UNKNOWN_TARGET,
        f"unknown target: {_echo(target_id)!r} is not a symbol in the snapshot",
    )


def _scope_blast_radius(graph: nx.DiGraph, scope_id: str, max_depth: int) -> BlastRadius:
    """Trace an L3 scope as an isolated ``scope`` node on a copy of ``graph`` (D6)."""
    scoped = graph.copy()
    if scope_id in scoped:
        scoped.remove_node(scope_id)
    scoped.add_node(scope_id, node_type="scope")
    return trace_blast_radius(scoped, scope_id, max_depth)


class DissectionService:
    """Explains Targets and measures their blast radius over one shared Cache_Store."""

    def __init__(self, cache: CacheStore, pedagogy: PedagogyEngine, mastery: MasteryEngine) -> None:
        self._cache = cache
        self._pedagogy = pedagogy
        self._mastery = mastery

    def _load_snapshot(self, repo_id: str) -> RepoGraphSnapshot:
        snapshot = self._cache.get_snapshot(repo_id)
        if snapshot is None:
            raise _missing_snapshot(repo_id)
        return snapshot

    async def dissect(
        self,
        repo_id: str,
        target_id: str,
        lens: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> DissectionResult:
        """Explain one Target under ``lens`` and trace its blast radius."""
        results = await self.dissect_many(repo_id, [target_id], lens, max_depth)
        return results[0]

    async def dissect_many(
        self,
        repo_id: str,
        target_ids: Sequence[str],
        lens: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> list[DissectionResult]:
        """Explain every Target under ``lens`` and trace each blast radius.

        Raises ``InvalidLensError`` before any engine call. A ``PedagogyError``, a
        Graph_Engine ``InvalidArgumentError``, a ``CacheStoreError``, or a
        ``MasteryError`` propagates unchanged and no result is returned. Views are
        recorded once, for every L1 or L2 Target, only while Study Mode is on.
        """
        parsed_lens = _parse_lens(lens)
        ids = list(target_ids)

        envelopes = [
            await self._pedagogy.explain_target(repo_id, target_id, parsed_lens)
            for target_id in ids
        ]

        snapshot = self._load_snapshot(repo_id)
        graph = build_graph(snapshot.files)
        if parsed_lens is PedagogyLens.L3_ARCHITECTURE:
            radii = [_scope_blast_radius(graph, target_id, max_depth) for target_id in ids]
        else:
            symbols = build_symbol_index(snapshot)
            radii = []
            for target_id in ids:
                if target_id not in symbols:
                    raise _unknown_symbol(target_id)
                radii.append(trace_blast_radius(graph, target_id, max_depth))

        results = [
            DissectionResult(envelope=envelope, blast_radius=radius)
            for envelope, radius in zip(envelopes, radii, strict=True)
        ]

        if parsed_lens in _VIEW_LENSES and ids:
            # Symbols with ids over 500 characters carry no mastery (decision D7).
            trackable = trackable_symbols(snapshot)
            view_ids = [target_id for target_id in ids if target_id in trackable]
            if view_ids and self._mastery.get_study_mode(repo_id):
                self._mastery.record_views(repo_id, view_ids)

        return results

    def blast_radius(self, repo_id: str, target_id: str, max_depth: int) -> BlastRadius:
        """Trace the blast radius of a Snapshot symbol.

        Raises ``PedagogyError(MISSING_DATA)`` when no Snapshot is stored and
        ``PedagogyError(UNKNOWN_TARGET)`` for an id that is not a Snapshot symbol (a file
        path is a graph node but not a symbol). A Graph_Engine ``InvalidArgumentError``
        for a bad ``max_depth`` propagates.
        """
        snapshot = self._load_snapshot(repo_id)
        if target_id not in build_symbol_index(snapshot):
            raise _unknown_symbol(target_id)
        return trace_blast_radius(build_graph(snapshot.files), target_id, max_depth)
