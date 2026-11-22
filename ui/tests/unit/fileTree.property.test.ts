import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import type { FileAnalysis } from '../../src/api/types';
import {
  ancestorsOf,
  buildFileTree,
  flattenVisible,
  type FolderNode,
  type TreeRow,
} from '../../src/core/fileTree';
import { compareSymbols } from '../../src/core/snapshotIndex';
import { snapshotResponseArb } from '../fixtures/arbitraries';

const RUNS = { numRuns: 100, seed: 7 };

const filesArb = snapshotResponseArb.map((r) => r.snapshot.files);
const filesAndShuffleArb = filesArb.chain((files) =>
  fc.tuple(fc.constant(files), fc.shuffledSubarray(files, { minLength: files.length, maxLength: files.length })),
);

const strictlyAscending = (xs: string[]): boolean => xs.every((x, i) => i === 0 || (xs[i - 1] as string) < x);

function walk(folder: FolderNode, visit: (f: FolderNode) => void): void {
  visit(folder);
  folder.folders.forEach((f) => walk(f, visit));
}

const allFolders = (root: FolderNode): FolderNode[] => {
  const out: FolderNode[] = [];
  walk(root, (f) => out.push(f));
  return out;
};

const copy = (files: FileAnalysis[]): FileAnalysis[] => [...files];

describe('Property 7: file tree structure and ordering', () => {
  /** **Validates: Requirements 12.1, 12.2** */
  it('Property 7: file tree structure and ordering', () => {
    // Step 1: has folders only for path prefixes and exactly one row per file
    {
    fc.assert(
      fc.property(filesArb, (files) => {
        const root = buildFileTree(copy(files));
        const expectedFolders = new Set(files.flatMap((f) => ancestorsOf(f.file_path)));
        const folderPaths = allFolders(root)
          .map((f) => f.path)
          .filter((p) => p !== '');
        expect(new Set(folderPaths)).toEqual(expectedFolders);
        expect(folderPaths.length).toBe(expectedFolders.size);

        const leafPaths: string[] = [];
        walk(root, (f) => f.files.forEach((l) => leafPaths.push(l.path)));
        expect([...leafPaths].sort()).toEqual(files.map((f) => f.file_path).sort());
      }),
      RUNS,
    );
    }

  /** **Validates: Requirements 12.2, 12.4** */
    // Step 2: orders folders before files, each group ascending, symbols by start_line then id
    {
    fc.assert(
      fc.property(filesArb, (files) => {
        const root = buildFileTree(copy(files));
        const expanded = new Set(allFolders(root).map((f) => f.path));
        files.forEach((f) => expanded.add(f.file_path));
        const rows = flattenVisible(root, expanded);

        walk(root, (folder) => {
          expect(strictlyAscending(folder.folders.map((f) => f.name))).toBe(true);
          expect(strictlyAscending(folder.files.map((f) => f.name))).toBe(true);
        });

        // In display order, each directory lists its folder rows before its file rows.
        const lastKindByParent = new Map<string, TreeRow['kind']>();
        for (const row of rows) {
          if (row.kind === 'symbol') continue;
          const parent = row.path.includes('/') ? row.path.slice(0, row.path.lastIndexOf('/')) : '';
          if (row.kind === 'folder') expect(lastKindByParent.get(parent)).not.toBe('file');
          lastKindByParent.set(parent, row.kind);
        }

        const byPath = new Map(files.map((f) => [f.file_path, f]));
        walk(root, (folder) =>
          folder.files.forEach((leaf) => {
            const expected = [...(byPath.get(leaf.path)?.symbols ?? [])].sort(compareSymbols).map((s) => s.id);
            expect(leaf.symbols.map((s) => s.id)).toEqual(expected);
          }),
        );
      }),
      RUNS,
    );
    }

  /** **Validates: Requirements 12.1, 12.8** */
    // Step 3: is identical for any permutation of the input
    {
    fc.assert(
      fc.property(filesAndShuffleArb, ([files, shuffled]) => {
        const a = buildFileTree(copy(files));
        const b = buildFileTree(copy(shuffled));
        expect(b).toEqual(a);
        const expanded = new Set(allFolders(a).map((f) => f.path));
        files.forEach((f) => expanded.add(f.file_path));
        expect(flattenVisible(b, expanded)).toEqual(flattenVisible(a, expanded));
      }),
      RUNS,
    );
    }

  /** **Validates: Requirements 12.4, 12.8** */
    // Step 4: shows a row only if all of its ancestors are expanded
    {
    fc.assert(
      fc.property(
        filesArb.chain((files) => {
          const candidates = [
            ...new Set(files.flatMap((f) => [...ancestorsOf(f.file_path), f.file_path])),
          ].sort();
          return fc.tuple(
            fc.constant(files),
            candidates.length > 0
              ? fc.subarray(candidates)
              : fc.constant([] as string[]),
          );
        }),
        ([files, open]) => {
          const root = buildFileTree(copy(files));
          const expanded = new Set(open);
          const rows = flattenVisible(root, expanded);

          for (const row of rows) {
            const path = row.kind === 'symbol' ? row.filePath : row.path;
            const needed = row.kind === 'symbol' ? [...ancestorsOf(path), path] : ancestorsOf(path);
            for (const p of needed) expect(expanded.has(p)).toBe(true);
          }

          // Completeness: every file whose ancestors are all open is shown.
          const shown = new Set(rows.filter((r) => r.kind === 'file').map((r) => r.path));
          for (const f of files) {
            const visible = ancestorsOf(f.file_path).every((p) => expanded.has(p));
            expect(shown.has(f.file_path)).toBe(visible);
          }
        },
      ),
      RUNS,
    );
    }
  });
});
