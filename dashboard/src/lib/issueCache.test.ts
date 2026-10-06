import { describe, expect, it } from "vitest";
import {
  ISSUE_CACHE_TTL_MS,
  invalidateIssueCache,
  lookupIssueCache,
  storeIssueCache,
  type IssueCacheEntry,
} from "./issueCache";
import type { ProjectIssue } from "./types";

const issues = [{ number: 1 }] as unknown as ProjectIssue[];

describe("issueCache", () => {
  it("キャッシュが無ければmiss", () => {
    expect(lookupIssueCache(new Map(), "a/b", 0).kind).toBe("miss");
  });

  it("TTL内はfresh、境界を超えるとstale", () => {
    const cache = new Map<string, IssueCacheEntry>();
    storeIssueCache(cache, "a/b", issues, 1000);
    expect(lookupIssueCache(cache, "a/b", 1000 + ISSUE_CACHE_TTL_MS).kind).toBe(
      "fresh",
    );
    const stale = lookupIssueCache(cache, "a/b", 1001 + ISSUE_CACHE_TTL_MS);
    expect(stale.kind).toBe("stale");
    if (stale.kind === "stale") expect(stale.entry.issues).toBe(issues);
  });

  it("リポジトリごとに独立している", () => {
    const cache = new Map<string, IssueCacheEntry>();
    storeIssueCache(cache, "a/b", issues, 0);
    expect(lookupIssueCache(cache, "a/c", 0).kind).toBe("miss");
  });

  it("invalidateは指定リポジトリのみ、省略時は全件破棄する", () => {
    const cache = new Map<string, IssueCacheEntry>();
    storeIssueCache(cache, "a/b", issues, 0);
    storeIssueCache(cache, "a/c", issues, 0);
    invalidateIssueCache(cache, "a/b");
    expect(lookupIssueCache(cache, "a/b", 0).kind).toBe("miss");
    expect(lookupIssueCache(cache, "a/c", 0).kind).toBe("fresh");
    invalidateIssueCache(cache);
    expect(cache.size).toBe(0);
  });

  it("再保存でfetchedAtが更新される", () => {
    const cache = new Map<string, IssueCacheEntry>();
    storeIssueCache(cache, "a/b", issues, 0);
    storeIssueCache(cache, "a/b", issues, 100_000);
    expect(lookupIssueCache(cache, "a/b", 100_000).kind).toBe("fresh");
  });
});
