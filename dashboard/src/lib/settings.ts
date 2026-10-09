/** オーケストレータの`GET /api/settings`（config/projects.yamlのタイミング系設定、issue #201）。 */
export interface DashboardSettings {
  issueCacheTtlMs: number;
  pollIntervalMs: number;
  syncTickIntervalMs: number;
}

/** 設定の取得に失敗した場合・値が不正な場合のフォールバック（従来の固定値）。 */
export const DEFAULT_DASHBOARD_SETTINGS: DashboardSettings = {
  issueCacheTtlMs: 60_000,
  pollIntervalMs: 30_000,
  syncTickIntervalMs: 30_000,
};

function secondsToMs(value: unknown, fallbackMs: number): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? value * 1000
    : fallbackMs;
}

export function parseDashboardSettings(raw: unknown): DashboardSettings {
  const obj = (raw && typeof raw === "object" ? raw : {}) as Record<
    string,
    unknown
  >;
  return {
    issueCacheTtlMs: secondsToMs(
      obj.issue_cache_ttl_seconds,
      DEFAULT_DASHBOARD_SETTINGS.issueCacheTtlMs,
    ),
    pollIntervalMs: secondsToMs(
      obj.dashboard_poll_interval_seconds,
      DEFAULT_DASHBOARD_SETTINGS.pollIntervalMs,
    ),
    syncTickIntervalMs: secondsToMs(
      obj.sync_tick_interval_seconds,
      DEFAULT_DASHBOARD_SETTINGS.syncTickIntervalMs,
    ),
  };
}
