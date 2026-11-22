/** Empty or undefined means relative URLs; otherwise trailing slashes are removed. */
export function normalizeBaseUrl(raw: string | undefined): string {
  if (raw === undefined || raw === '') return '';
  return raw.replace(/\/+$/, '');
}

/** `path` always starts with "/". */
export function buildUrl(base: string, path: string): string {
  return base + path;
}
