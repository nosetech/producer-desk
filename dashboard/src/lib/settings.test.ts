import { describe, expect, it } from "vitest";
import { DEFAULT_DASHBOARD_SETTINGS, parseDashboardSettings } from "./settings";

describe("parseDashboardSettings", () => {
  it("秒をミリ秒に変換する", () => {
    expect(
      parseDashboardSettings({
        issue_cache_ttl_seconds: 120,
        dashboard_poll_interval_seconds: 10,
        sync_tick_interval_seconds: 5,
      }),
    ).toEqual({
      issueCacheTtlMs: 120_000,
      pollIntervalMs: 10_000,
      syncTickIntervalMs: 5_000,
    });
  });

  it("欠落・不正値は項目ごとに既定値へフォールバックする", () => {
    expect(
      parseDashboardSettings({
        issue_cache_ttl_seconds: 0,
        dashboard_poll_interval_seconds: "x",
      }),
    ).toEqual(DEFAULT_DASHBOARD_SETTINGS);
  });

  it("オブジェクト以外でも既定値を返す", () => {
    expect(parseDashboardSettings(null)).toEqual(DEFAULT_DASHBOARD_SETTINGS);
    expect(parseDashboardSettings("oops")).toEqual(DEFAULT_DASHBOARD_SETTINGS);
  });
});
