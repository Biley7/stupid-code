"""Topology profiler (Spec #02): directory roles and boundary metrics.

Every function here is a pure function of a ``RepoGraphSnapshot``. It performs
no I/O, makes no LLM or network call, and imports only ``backend.domain`` and the
standard library. Results do not depend on the order of files or edges.

Derived sets (design.md, "Topology Metric Formulas"):

* ``F``: the Snapshot file paths.
* ``D``: every non-empty ancestor directory of every file.
* ``E``: the ``(source, target)`` pairs of ``imports`` edges whose endpoints are
  both in ``F`` and differ from each other. Invalid-endpoint, non-import, and
  self edges are dropped silently.
"""

import posixpath
from collections import Counter
from collections.abc import Collection, Iterable, Mapping
from typing import Final, cast

from backend.domain.models import RepoGraphSnapshot, TopologyProfile

__all__ = [
    "METRIC_KEYS",
    "compute_boundary_metrics",
    "compute_directory_roles",
    "derive_directories",
    "derive_files",
    "derive_import_edges",
    "is_entry_point_file",
    "parent_dir",
    "profile_topology",
    "segments",
    "under_directory",
]

METRIC_KEYS = (
    "max_depth",
    "cross_folder_import_ratio",
    "domain_isolation_score",
    "entry_point_count",
)

_PLACES = 4

# Role names tested in order against ``name.lower()`` of a directory's last segment.
_ROLE_NAMES: tuple[tuple[str, frozenset[str]], ...] = (
    ("tests", frozenset({"tests", "test", "__tests__", "e2e"})),
    ("domain", frozenset({"domain", "entities", "entity", "models", "model"})),
    (
        "engines",
        frozenset({"engines", "engine", "application", "usecases", "use_cases", "interactors"}),
    ),
    (
        "api",
        frozenset(
            {
                "api",
                "routes",
                "routers",
                "controllers",
                "handlers",
                "endpoints",
                "mcp_server",
                "delivery",
            }
        ),
    ),
    (
        "ui",
        frozenset({"ui", "frontend", "web", "views", "components", "pages", "templates", "client"}),
    ),
    ("services", frozenset({"services", "service"})),
    (
        "infrastructure",
        frozenset(
            {
                "infrastructure",
                "infra",
                "db",
                "database",
                "persistence",
                "repositories",
                "adapters",
                "migrations",
                "storage",
            }
        ),
    ),
    ("config", frozenset({"config", "configs", "conf", "settings"})),
    ("entry_points", frozenset({"bin", "cmd", "scripts", "cli"})),
)

_ENTRY_POINT_BASENAMES = frozenset(
    {
        "main.py",
        "__main__.py",
        "app.py",
        "manage.py",
        "wsgi.py",
        "asgi.py",
        "cli.py",
        "main.ts",
        "main.js",
        "index.ts",
        "index.js",
        "server.ts",
        "server.js",
        "Main.java",
        "Application.java",
    }
)
_ENTRY_POINT_DIRS = frozenset({"bin", "cmd", "scripts", "cli"})

_TEST_SUFFIXES = (".test.ts", ".spec.ts", ".test.js", ".spec.js")


def parent_dir(path: str) -> str:
    """Return the POSIX parent directory of ``path`` (``""`` for a root-level file)."""
    return posixpath.dirname(path)


def segments(path: str) -> list[str]:
    """Return the directory segments of a file path, excluding the file name."""
    return path.split("/")[:-1]


def under_directory(path: str, directory: str) -> bool:
    """Return True if ``path`` lies somewhere beneath ``directory``."""
    return bool(directory) and path.startswith(directory + "/")


def derive_files(snapshot: RepoGraphSnapshot) -> frozenset[str]:
    """Return ``F``, the set of Snapshot file paths."""
    return frozenset(analysis.file_path for analysis in snapshot.files)


def derive_directories(files: Iterable[str]) -> frozenset[str]:
    """Return ``D``, every non-empty ancestor directory of every file in ``files``."""
    directories: set[str] = set()
    for path in files:
        parts = segments(path)
        for end in range(1, len(parts) + 1):
            directories.add("/".join(parts[:end]))
    return frozenset(directories)


def derive_import_edges(
    snapshot: RepoGraphSnapshot, files: frozenset[str] | None = None
) -> frozenset[tuple[str, str]]:
    """Return ``E``: valid, non-self ``imports`` edges between Snapshot files."""
    known = derive_files(snapshot) if files is None else files
    return frozenset(
        (edge.source, edge.target)
        for edge in snapshot.edges
        if edge.edge_type == "imports"
        and edge.source in known
        and edge.target in known
        and edge.source != edge.target
    )


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _is_test_file(path: str) -> bool:
    name = _basename(path)
    return (
        (name.startswith("test_") and name.endswith(".py"))
        or name.endswith("_test.py")
        or name.endswith(_TEST_SUFFIXES)
    )


def is_entry_point_file(path: str) -> bool:
    """Return True if ``path`` is an entry-point file.

    A file is an entry point when its base name is a known entry-point name, or
    when it lies directly in a directory named ``bin``, ``cmd``, ``scripts``, or
    ``cli`` (compared case-insensitively).
    """
    if _basename(path) in _ENTRY_POINT_BASENAMES:
        return True
    return posixpath.basename(parent_dir(path)).lower() in _ENTRY_POINT_DIRS


def _role_by_name(directory: str) -> str | None:
    name = directory.rsplit("/", 1)[-1].lower()
    for role, names in _ROLE_NAMES:
        if name in names:
            return role
    return None


def _role_by_contents(direct: list[str]) -> str:
    if not direct:
        return "other"
    if all(_is_test_file(path) for path in direct):
        return "tests"
    if 2 * sum(1 for path in direct if path.endswith(".tsx")) >= len(direct):
        return "ui"
    if all(is_entry_point_file(path) for path in direct):
        return "entry_points"
    return "other"


def compute_directory_roles(snapshot: RepoGraphSnapshot) -> dict[str, str]:
    """Assign exactly one Directory_Role to every directory in ``D``.

    The role comes from the directory name first, then from the files directly
    in the directory, and defaults to ``other``. The result is keyed in
    ascending path order.
    """
    files = derive_files(snapshot)
    direct_files: dict[str, list[str]] = {}
    for path in files:
        direct_files.setdefault(parent_dir(path), []).append(path)

    roles: dict[str, str] = {}
    for directory in sorted(derive_directories(files)):
        role = _role_by_name(directory)
        if role is None:
            role = _role_by_contents(sorted(direct_files.get(directory, [])))
        roles[directory] = role
    return roles


def _outermost_domain_dir(path: str, roles: Mapping[str, str]) -> str | None:
    """Return the outermost ancestor directory of ``path`` with role ``domain``."""
    parts = segments(path)
    for end in range(1, len(parts) + 1):
        ancestor = "/".join(parts[:end])
        if roles.get(ancestor) == "domain":
            return ancestor
    return None


def compute_boundary_metrics(
    snapshot: RepoGraphSnapshot, roles: Mapping[str, str]
) -> dict[str, float]:
    """Compute the four boundary metrics, rounded to 4 places, all as floats.

    ``roles`` is the result of :func:`compute_directory_roles` for ``snapshot``.
    Zero denominators yield 0.0 for the cross-folder ratio and 1.0 for domain
    isolation, so no division by zero can occur.
    """
    files = derive_files(snapshot)
    edges = derive_import_edges(snapshot, files)

    max_depth = max((len(segments(path)) for path in files), default=0)
    entry_points = sum(1 for path in files if is_entry_point_file(path))

    cross = sum(1 for source, target in edges if parent_dir(source) != parent_dir(target))
    cross_ratio = cross / len(edges) if edges else 0.0

    from_domain = 0
    leaving = 0
    for source, target in edges:
        domain_dir = _outermost_domain_dir(source, roles)
        if domain_dir is None:
            continue
        from_domain += 1
        if not under_directory(target, domain_dir):
            leaving += 1
    isolation = 1.0 - leaving / from_domain if from_domain else 1.0

    return {
        "max_depth": round(float(max_depth), _PLACES),
        "cross_folder_import_ratio": round(float(cross_ratio), _PLACES),
        "domain_isolation_score": round(float(isolation), _PLACES),
        "entry_point_count": round(float(entry_points), _PLACES),
    }


# ---------------------------------------------------------------------------
# Pattern scoring and classification
# ---------------------------------------------------------------------------

HEXAGONAL: Final = "Hexagonal / Clean Architecture"
LAYERED_MVC: Final = "Layered MVC"
FEATURE_SLICED: Final = "Feature-Sliced"
MODULAR_MONOLITH: Final = "Modular Monolith"
FLAT_SCRIPT: Final = "Flat / Script"

_THRESHOLD = 0.3
_SINGLE_SIGNAL_CAP = 0.5
_CLOSE_MARGIN = 0.1
_CLOSE_MARGIN_CAP = 0.6
_MAX_EVIDENCE_LEN = 200
_MAX_ROLE_EVIDENCE = 20
_MAX_IMPORT_EVIDENCE = 10
_MAX_ENTRY_EVIDENCE = 10

_HEX_DOMAIN = frozenset({"domain", "entities", "entity"})
_HEX_APP = frozenset({"engines", "engine", "application", "usecases", "use_cases", "interactors"})
_HEX_EDGE = frozenset(
    {"api", "adapters", "infrastructure", "infra", "ports", "mcp_server", "delivery"}
)
_HEX_UI = frozenset({"ui", "frontend"})
_HEX_GROUPS = (_HEX_DOMAIN, _HEX_APP, _HEX_EDGE, _HEX_UI)
_HEX_DISTRIBUTION_ROLES = frozenset({"domain", "engines", "api", "infrastructure", "services"})
_HEX_RANKS = {
    "api": 3,
    "ui": 3,
    "engines": 2,
    "services": 2,
    "infrastructure": 2,
    "domain": 1,
}

_MVC_MODELS = frozenset({"models", "model"})
_MVC_VIEWS = frozenset({"views", "view", "templates"})
_MVC_CONTROLLERS = frozenset({"controllers", "controller", "routes", "routers", "handlers"})
_MVC_GROUPS = (_MVC_MODELS, _MVC_VIEWS, _MVC_CONTROLLERS)

_FSD_NAMES = frozenset({"features", "entities", "shared", "widgets", "pages"})
_MODULE_CONTAINERS = frozenset({"modules", "apps", "packages"})

# (naming, imports, distribution) weights.
_ARCH_WEIGHTS = (0.4, 0.4, 0.2)
_FLAT_WEIGHTS = (0.3, 0.3, 0.4)

Signals = tuple[float, float, float]


def _name(directory: str) -> str:
    return directory.rsplit("/", 1)[-1].lower()


def _ancestors(path: str) -> list[str]:
    """Return the ancestor directories of ``path``, deepest first."""
    parts = segments(path)
    return ["/".join(parts[:end]) for end in range(len(parts), 0, -1)]


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _round(value: float) -> float:
    return round(_clamp(value), _PLACES)


def _share(files: Collection[str], predicate_dirs: Collection[str], total: int) -> float:
    """Share of ``files`` lying under at least one directory of ``predicate_dirs``."""
    if total == 0 or not predicate_dirs:
        return 0.0
    dirs = set(predicate_dirs)
    hit = sum(1 for path in files if any(anc in dirs for anc in _ancestors(path)))
    return hit / total


def _nearest(path: str, lookup: Mapping[str, object]) -> object | None:
    """Return ``lookup`` value of the deepest ancestor directory of ``path`` in it."""
    for ancestor in _ancestors(path):
        if ancestor in lookup:
            return lookup[ancestor]
    return None


def _combine(signals: Signals, weights: tuple[float, float, float]) -> float:
    return _round(sum(w * v for w, v in zip(weights, signals, strict=True)))


def _hexagonal(
    directories: frozenset[str],
    scoped: frozenset[str],
    edges: frozenset[tuple[str, str]],
    roles: Mapping[str, str],
    metrics: Mapping[str, float],
) -> Signals:
    names = {_name(d) for d in directories}
    n_signal = 0.0
    if names & _HEX_DOMAIN:
        groups = sum(1 for group in _HEX_GROUPS if names & group)
        n_signal = min(1.0, (groups - 1) / 2)

    i_signal = 0.0
    if any(role == "domain" for role in roles.values()):
        ranked = {d: _HEX_RANKS[r] for d, r in roles.items() if r in _HEX_RANKS}
        total = 0
        conforming = 0
        for source, target in edges:
            if parent_dir(source) == parent_dir(target):
                continue
            src_rank = _nearest(source, ranked)
            tgt_rank = _nearest(target, ranked)
            if src_rank is None or tgt_rank is None:
                continue
            total += 1
            if cast(int, src_rank) >= cast(int, tgt_rank):
                conforming += 1
        conformity = conforming / total if total else 0.0
        i_signal = conformity * metrics["domain_isolation_score"]

    dist_dirs = [d for d, r in roles.items() if r in _HEX_DISTRIBUTION_ROLES]
    d_signal = _share(scoped, dist_dirs, len(scoped))
    return (_round(n_signal), _round(i_signal), _round(d_signal))


def _layered_mvc(
    directories: frozenset[str],
    scoped: frozenset[str],
    edges: frozenset[tuple[str, str]],
) -> Signals:
    names = {_name(d) for d in directories}
    present = sum(1 for group in _MVC_GROUPS if names & group)
    n_signal = 0.0 if present < 2 else (present - 1) / 2

    group_of: dict[str, int] = {}
    for directory in directories:
        for index, group in enumerate(_MVC_GROUPS):
            if _name(directory) in group:
                group_of[directory] = index

    mixed = 0
    from_models = 0
    for source, target in edges:
        if parent_dir(source) == parent_dir(target):
            continue
        src = _nearest(source, group_of)
        tgt = _nearest(target, group_of)
        if src is None or tgt is None or src == tgt:
            continue
        mixed += 1
        if src == 0:
            from_models += 1
    i_signal = 1.0 - from_models / mixed if mixed else 0.0

    d_signal = _share(scoped, list(group_of), len(scoped))
    return (_round(n_signal), _round(i_signal), _round(d_signal))


def _feature_sliced(
    directories: frozenset[str],
    scoped: frozenset[str],
    edges: frozenset[tuple[str, str]],
) -> Signals:
    feature_dirs = {d for d in directories if _name(d) == "features"}
    slices = {d for d in directories if parent_dir(d) in feature_dirs}
    if not slices:
        return (0.0, 0.0, 0.0)
    present = {_name(d) for d in directories} & _FSD_NAMES
    n_signal = min(1.0, len(present) / 3)

    slice_lookup = {d: d for d in slices}
    from_slices = 0
    crossing = 0
    for source, target in edges:
        src = _nearest(source, slice_lookup)
        if src is None:
            continue
        from_slices += 1
        tgt = _nearest(target, slice_lookup)
        if tgt is not None and tgt != src:
            crossing += 1
    i_signal = 1.0 - crossing / from_slices if from_slices else 0.0

    d_signal = _share(scoped, feature_dirs, len(scoped)) if len(slices) >= 2 else 0.0
    return (_round(n_signal), _round(i_signal), _round(d_signal))


def _modular_monolith(
    directories: frozenset[str],
    scoped: frozenset[str],
    edges: frozenset[tuple[str, str]],
) -> Signals:
    best: tuple[int, str] | None = None
    for container in sorted(d for d in directories if _name(d) in _MODULE_CONTAINERS):
        count = sum(1 for d in directories if parent_dir(d) == container)
        if count >= 2 and (best is None or count > best[0]):
            best = (count, container)
    if best is None:
        return (0.0, 0.0, 0.0)
    count, container = best
    n_signal = min(1.0, count / 3)

    modules = {d for d in directories if parent_dir(d) == container}
    module_lookup = {d: d for d in modules}
    from_modules = 0
    crossing = 0
    for source, target in edges:
        src = _nearest(source, module_lookup)
        if src is None:
            continue
        from_modules += 1
        tgt = _nearest(target, module_lookup)
        if tgt is not None and tgt != src:
            crossing += 1
    i_signal = 1.0 - crossing / from_modules if from_modules else 0.0

    d_signal = _share(scoped, [container], len(scoped))
    return (_round(n_signal), _round(i_signal), _round(d_signal))


def _flat_script(
    directories: frozenset[str],
    scoped: frozenset[str],
    edges: frozenset[tuple[str, str]],
    roles: Mapping[str, str],
    metrics: Mapping[str, float],
) -> Signals:
    if directories:
        roled = sum(1 for role in roles.values() if role not in ("other", "tests"))
        n_signal = 1.0 - roled / max(1, len(directories))
    else:
        n_signal = 1.0
    i_signal = 1.0 - metrics["cross_folder_import_ratio"] if edges else 0.5
    shallow = sum(1 for path in scoped if len(segments(path)) <= 1)
    d_signal = shallow / len(scoped) if scoped else 0.0
    return (_round(n_signal), _round(i_signal), _round(d_signal))


def _truncate(text: str) -> str:
    if len(text) <= _MAX_EVIDENCE_LEN:
        return text
    return text[: _MAX_EVIDENCE_LEN - 3] + "..."


def _display_dir(directory: str) -> str:
    return directory or "."


def _build_evidence(
    pattern: str,
    score: float,
    signals: Signals,
    roles: Mapping[str, str],
    edges: frozenset[tuple[str, str]],
    files: frozenset[str],
) -> list[str]:
    n_signal, i_signal, d_signal = signals
    items = [
        f"pattern {pattern} score {score:.4f} "
        f"(naming {n_signal:.4f}, imports {i_signal:.4f}, distribution {d_signal:.4f})"
    ]
    named = sorted(d for d, role in roles.items() if role != "other")
    items.extend(f"directory {d} has role {roles[d]}" for d in named[:_MAX_ROLE_EVIDENCE])

    pairs = Counter(
        (parent_dir(s), parent_dir(t)) for s, t in edges if parent_dir(s) != parent_dir(t)
    )
    top_pairs = sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))[:_MAX_IMPORT_EVIDENCE]
    items.extend(
        f"imports {_display_dir(src)} -> {_display_dir(tgt)} ({count} files)"
        for (src, tgt), count in top_pairs
    )

    entries = sorted(path for path in files if is_entry_point_file(path))
    items.extend(f"entry point {path}" for path in entries[:_MAX_ENTRY_EVIDENCE])
    return sorted({_truncate(item) for item in items})


def profile_topology(snapshot: RepoGraphSnapshot) -> TopologyProfile:
    """Classify the architecture pattern of ``snapshot`` and describe its boundaries.

    Pure and deterministic: the result depends only on the set of file paths and
    valid import edges, never on their order. Never raises for a valid Snapshot.
    """
    files = derive_files(snapshot)
    if not files:
        return TopologyProfile(
            repo_id=snapshot.repo_id,
            detected_pattern=FLAT_SCRIPT,
            confidence=0.0,
            directory_roles={},
            boundary_metrics=compute_boundary_metrics(snapshot, {}),
            evidence=[],
        )

    directories = derive_directories(files)
    edges = derive_import_edges(snapshot, files)
    roles = compute_directory_roles(snapshot)
    metrics = compute_boundary_metrics(snapshot, roles)

    test_dirs = {d for d, role in roles.items() if role == "tests"}
    scoped = (
        frozenset(path for path in files if not any(anc in test_dirs for anc in _ancestors(path)))
        or files
    )

    all_signals: dict[str, Signals] = {
        HEXAGONAL: _hexagonal(directories, scoped, edges, roles, metrics),
        LAYERED_MVC: _layered_mvc(directories, scoped, edges),
        FEATURE_SLICED: _feature_sliced(directories, scoped, edges),
        MODULAR_MONOLITH: _modular_monolith(directories, scoped, edges),
        FLAT_SCRIPT: _flat_script(directories, scoped, edges, roles, metrics),
    }
    scores: dict[str, float] = {}
    for name, signals in all_signals.items():
        if name == FLAT_SCRIPT:
            scores[name] = _combine(signals, _FLAT_WEIGHTS)
        elif signals[0] == 0.0:
            scores[name] = 0.0
        else:
            scores[name] = _combine(signals, _ARCH_WEIGHTS)

    ranking = sorted(scores, key=lambda name: (-scores[name], name))
    top, runner_up = ranking[0], ranking[1]
    detected = top if scores[top] >= _THRESHOLD else FLAT_SCRIPT

    confidence = scores[detected]
    if sum(1 for value in all_signals[detected] if value >= _THRESHOLD) <= 1:
        confidence = min(confidence, _SINGLE_SIGNAL_CAP)
    if scores[top] - scores[runner_up] < _CLOSE_MARGIN:
        confidence = min(confidence, _CLOSE_MARGIN_CAP)

    return TopologyProfile(
        repo_id=snapshot.repo_id,
        detected_pattern=detected,  # type: ignore[arg-type]
        confidence=_round(confidence),
        directory_roles=roles,  # type: ignore[arg-type]
        boundary_metrics=metrics,
        evidence=_build_evidence(
            detected, scores[detected], all_signals[detected], roles, edges, files
        ),
    )
