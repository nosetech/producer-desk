import type { ProjectIssue } from "./types";

/** この時間内のキャッシュは新鮮とみなし、取得せずにそのまま表示する。 */
export const ISSUE_CACHE_TTL_MS = 60_000;

export interface IssueCacheEntry {
  issues: ProjectIssue[];
  fetchedAt: number;
}

/** キャッシュ参照の結果。`fresh`=TTL内、`stale`=TTL超過（表示しつつ再取得）、`miss`=なし。 */
export type IssueCacheLookup =
  | { kind: "fresh"; entry: IssueCacheEntry }
  | { kind: "stale"; entry: IssueCacheEntry }
  | { kind: "miss" };

export function lookupIssueCache(
  cache: ReadonlyMap<string, IssueCacheEntry>,
  repo: string,
  now: number,
  ttlMs: number = ISSUE_CACHE_TTL_MS,
): IssueCacheLookup {
  const entry = cache.get(repo);
  if (!entry) return { kind: "miss" };
  return now - entry.fetchedAt <= ttlMs
    ? { kind: "fresh", entry }
    : { kind: "stale", entry };
}

export function storeIssueCache(
  cache: Map<string, IssueCacheEntry>,
  repo: string,
  issues: ProjectIssue[],
  now: number,
): void {
  cache.set(repo, { issues, fetchedAt: now });
}

/** repo省略時は全リポジトリ分を破棄する。 */
export function invalidateIssueCache(
  cache: Map<string, IssueCacheEntry>,
  repo?: string,
): void {
  if (repo === undefined) cache.clear();
  else cache.delete(repo);
}
