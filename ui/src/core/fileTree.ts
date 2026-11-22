import type { FileAnalysis } from '../api/types';
import { computeCounters } from './counters';
import { compareSymbols } from './snapshotIndex';

export type TreeRow =
  | { kind: 'folder'; path: string; name: string; depth: number; expanded: boolean }
  | {
      kind: 'file';
      path: string;
      name: string;
      depth: number;
      language: string;
      parseErrors: boolean;
      expanded: boolean;
      hasSymbols: boolean;
    }
  | { kind: 'symbol'; id: string; qualname: string; symbolKind: string; depth: number; filePath: string };

export interface SymbolLeaf {
  id: string;
  qualname: string;
  symbolKind: string;
}

export interface FolderNode {
  kind: 'folder';
  path: string;
  name: string;
  folders: FolderNode[];
  files: FileLeaf[];
}

export interface FileLeaf {
  kind: 'file';
  path: string;
  name: string;
  language: string;
  parseErrors: boolean;
  symbols: SymbolLeaf[];
}

/** Root folder has path `''` and is never rendered as a row. */
export type TreeNode = FolderNode;

const cmp = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

const cache = new WeakMap<FileAnalysis[], TreeNode>();

function build(files: FileAnalysis[]): TreeNode {
  computeCounters.fileTree += 1;
  const root: FolderNode = { kind: 'folder', path: '', name: '', folders: [], files: [] };
  const folderMap = new Map<string, FolderNode>([['', root]]);

  const ensureFolder = (path: string): FolderNode => {
    const existing = folderMap.get(path);
    if (existing) return existing;
    const slash = path.lastIndexOf('/');
    const parent = ensureFolder(slash < 0 ? '' : path.slice(0, slash));
    const node: FolderNode = {
      kind: 'folder',
      path,
      name: slash < 0 ? path : path.slice(slash + 1),
      folders: [],
      files: [],
    };
    parent.folders.push(node);
    folderMap.set(path, node);
    return node;
  };

  for (const file of files) {
    const p = file.file_path;
    const slash = p.lastIndexOf('/');
    const folder = ensureFolder(slash < 0 ? '' : p.slice(0, slash));
    folder.files.push({
      kind: 'file',
      path: p,
      name: slash < 0 ? p : p.slice(slash + 1),
      language: String(file.language),
      parseErrors: file.parse_errors.length > 0,
      symbols: [...file.symbols].sort(compareSymbols).map((s) => ({
        id: s.id,
        qualname: s.qualname,
        symbolKind: String(s.kind),
      })),
    });
  }

  for (const folder of folderMap.values()) {
    folder.folders.sort((a, b) => cmp(a.name, b.name) || cmp(a.path, b.path));
    folder.files.sort((a, b) => cmp(a.name, b.name) || cmp(a.path, b.path));
  }
  return root;
}

/** Memoized per `files` array (one array per snapshot). */
export function buildFileTree(files: FileAnalysis[]): TreeNode {
  let tree = cache.get(files);
  if (!tree) {
    tree = build(files);
    cache.set(files, tree);
  }
  return tree;
}

/**
 * Visible rows in display order. `expanded` holds folder paths and file paths
 * (a file is expanded when its symbols are shown).
 */
export function flattenVisible(root: TreeNode, expanded: ReadonlySet<string>): TreeRow[] {
  const rows: TreeRow[] = [];
  const walk = (folder: FolderNode, depth: number): void => {
    for (const sub of folder.folders) {
      const isOpen = expanded.has(sub.path);
      rows.push({ kind: 'folder', path: sub.path, name: sub.name, depth, expanded: isOpen });
      if (isOpen) walk(sub, depth + 1);
    }
    for (const file of folder.files) {
      const isOpen = expanded.has(file.path);
      rows.push({
        kind: 'file',
        path: file.path,
        name: file.name,
        depth,
        language: file.language,
        parseErrors: file.parseErrors,
        expanded: isOpen,
        hasSymbols: file.symbols.length > 0,
      });
      if (isOpen) {
        for (const s of file.symbols) {
          rows.push({
            kind: 'symbol',
            id: s.id,
            qualname: s.qualname,
            symbolKind: s.symbolKind,
            depth: depth + 1,
            filePath: file.path,
          });
        }
      }
    }
  };
  walk(root, 0);
  return rows;
}

/** Folder paths containing `path`, outermost first. `a/b/c.py` gives `['a', 'a/b']`. */
export function ancestorsOf(path: string): string[] {
  const parts = path.split('/');
  const out: string[] = [];
  for (let i = 1; i < parts.length; i++) out.push(parts.slice(0, i).join('/'));
  return out;
}
