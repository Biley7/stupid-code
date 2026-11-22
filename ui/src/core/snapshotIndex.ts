import type { DirectoryRole, FileAnalysis, RepoGraphSnapshot, SymbolNode, TopologyProfile } from '../api/types';

export type NodeClass = 'file' | 'symbol' | 'directory';

export type ResolvedTarget =
  | { kind: 'file'; path: string }
  | { kind: 'symbol'; id: string; filePath: string };

export interface SnapshotIndex {
  filesByPath: ReadonlyMap<string, FileAnalysis>;
  symbolsById: ReadonlyMap<string, SymbolNode>;
  /** Symbols per file path, sorted by `start_line` then `id`. */
  symbolsByFile: ReadonlyMap<string, readonly SymbolNode[]>;
  directoryRoles: Readonly<Record<string, DirectoryRole>>;
}

export function compareSymbols(a: SymbolNode, b: SymbolNode): number {
  if (a.start_line !== b.start_line) return a.start_line - b.start_line;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

const EMPTY_ROLES: Readonly<Record<string, DirectoryRole>> = Object.freeze({});
const cache = new WeakMap<RepoGraphSnapshot, WeakMap<object, SnapshotIndex>>();
const NO_TOPOLOGY: object = {};

function build(snapshot: RepoGraphSnapshot, topology: TopologyProfile | null | undefined): SnapshotIndex {
  const filesByPath = new Map<string, FileAnalysis>();
  const symbolsById = new Map<string, SymbolNode>();
  const symbolsByFile = new Map<string, readonly SymbolNode[]>();
  for (const file of snapshot.files) {
    filesByPath.set(file.file_path, file);
    const sorted = [...file.symbols].sort(compareSymbols);
    symbolsByFile.set(file.file_path, sorted);
    for (const sym of file.symbols) symbolsById.set(sym.id, sym);
  }
  return {
    filesByPath,
    symbolsById,
    symbolsByFile,
    directoryRoles: topology?.directory_roles ?? EMPTY_ROLES,
  };
}

/** Memoized per snapshot object (and per topology object). */
export function buildSnapshotIndex(
  snapshot: RepoGraphSnapshot,
  topology?: TopologyProfile | null,
): SnapshotIndex {
  let byTopology = cache.get(snapshot);
  if (!byTopology) {
    byTopology = new WeakMap();
    cache.set(snapshot, byTopology);
  }
  const key: object = topology ?? NO_TOPOLOGY;
  let index = byTopology.get(key);
  if (!index) {
    index = build(snapshot, topology);
    byTopology.set(key, index);
  }
  return index;
}

/** Files first, then symbols, then directory keys. Exact, case-sensitive matches. */
export function classifyNode(
  index: SnapshotIndex,
  directoryRoles: Readonly<Record<string, DirectoryRole>> | undefined,
  id: string,
): NodeClass | null {
  if (index.filesByPath.has(id)) return 'file';
  if (index.symbolsById.has(id)) return 'symbol';
  const roles = directoryRoles ?? index.directoryRoles;
  if (Object.prototype.hasOwnProperty.call(roles, id)) return 'directory';
  return null;
}

/** Returns null for an id absent from the snapshot. A symbol's file path comes from the index. */
export function resolveTarget(index: SnapshotIndex, rawTarget: string): ResolvedTarget | null {
  if (index.filesByPath.has(rawTarget)) return { kind: 'file', path: rawTarget };
  const sym = index.symbolsById.get(rawTarget);
  if (sym) return { kind: 'symbol', id: sym.id, filePath: sym.file_path };
  return null;
}
