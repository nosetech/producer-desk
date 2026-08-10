"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchUsage } from "@/lib/api";
import {
  assignModelColors,
  buildChartGeometry,
  buildLimitWarning,
  buildModelBreakdown,
  buildTodayUsage,
} from "@/lib/usage";
import type { UsageResponse } from "@/lib/types";
import styles from "./UsageMonitor.module.css";

const POLL_INTERVAL_MS = 30_000;
const EMPTY_USAGE: UsageResponse = { daily: [], currentLimit: null };

export default function UsageMonitor() {
  const [usage, setUsage] = useState<UsageResponse>(EMPTY_USAGE);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    fetchUsage()
      .then((data) => {
        setUsage(data);
        setError(null);
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "利用量の取得に失敗しました"),
      );
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  const { daily, currentLimit } = usage;
  const colors = assignModelColors(daily);
  const today = daily.length > 0 ? daily[daily.length - 1].date : "";
  const todayUsage = buildTodayUsage(daily, today, colors);
  const chart = buildChartGeometry(daily, colors);
  const modelBreakdown = buildModelBreakdown(daily, colors);
  const warn = buildLimitWarning(currentLimit);

  return (
    <div className={styles.panel}>
      <div className={styles.headerRow}>
        <span className={styles.title}>利用量 / トークン</span>
        <span className={styles.endpoint}>GET /api/usage</span>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {warn.active && (
        <div className={styles.warning}>
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--accent-red)"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className={styles.warningIcon}
            aria-hidden="true"
          >
            <path d="M12 9v4M12 17h.01"></path>
            <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h16.9a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"></path>
          </svg>
          <div>
            <div className={styles.warningText}>
              利用上限に到達しました。
              <strong>Agent Runner は待機中</strong>です。
            </div>
            <div className={styles.warningReset}>
              解除予定 <strong>{warn.resetText}</strong>
            </div>
            <div className={styles.warningMeta}>
              {warn.repoLabel} · HTTP {warn.statusText}
            </div>
          </div>
        </div>
      )}

      <div className={styles.todayCard}>
        <div className={styles.todayHeader}>
          <span className={styles.todayLabel}>
            本日の使用量 · {todayUsage.dateText}
          </span>
          <span className={styles.todayCost}>{todayUsage.costText}</span>
        </div>
        <div className={styles.todayTotalRow}>
          <span className={styles.todayTotal}>{todayUsage.totalText}</span>
          <span className={styles.todayUnit}>tokens</span>
        </div>
        <div className={styles.todayModels}>
          {todayUsage.models.map((m) => (
            <span key={m.model} className={styles.todayModelChip}>
              <span
                className={styles.dot}
                style={{ backgroundColor: `var(${m.colorVar})` }}
              />
              <span className={styles.todayModelName}>{m.model}</span>
              <span className={styles.todayModelTokens}>{m.tokensText}</span>
            </span>
          ))}
        </div>
      </div>

      <div className={styles.chartSection}>
        <div className={styles.chartHeader}>
          <span className={styles.chartLabel}>過去7日間の日次トークン</span>
          <div className={styles.chartLegend}>
            {chart.series.map((s) => (
              <span key={s.model} className={styles.legendItem}>
                <span
                  className={styles.legendSwatch}
                  style={{ backgroundColor: `var(${s.colorVar})` }}
                />
                <span className={styles.legendName}>{s.shortName}</span>
              </span>
            ))}
          </div>
        </div>
        <svg
          viewBox="0 0 320 118"
          width="100%"
          className={styles.chartSvg}
          role="img"
          aria-label="過去7日間の日次トークン推移"
        >
          {chart.gridLines.map((y) => (
            <line
              key={y}
              x1={10}
              y1={y}
              x2={310}
              y2={y}
              className={styles.chartGrid}
            />
          ))}
          {chart.series.map((s) => (
            <polyline
              key={s.model}
              points={s.points}
              fill="none"
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              style={{ stroke: `var(${s.colorVar})` }}
            />
          ))}
          {chart.series.map((s) =>
            s.dots.map((pt) => (
              <circle
                key={`${s.model}-${pt.cx}-${pt.cy}`}
                cx={pt.cx}
                cy={pt.cy}
                r={2.6}
                style={{ fill: `var(${s.colorVar})` }}
              />
            )),
          )}
          {chart.labels.map((xl) => (
            <text
              key={xl.x}
              x={xl.x}
              y={115}
              textAnchor="middle"
              fontSize={8}
              className={styles.chartAxisLabel}
            >
              {xl.label}
            </text>
          ))}
        </svg>
      </div>

      <div>
        <div className={styles.breakdownLabel}>モデル別内訳 · 7日間累計</div>
        <div className={styles.breakdownList}>
          {modelBreakdown.map((m) => (
            <div key={m.model}>
              <div className={styles.breakdownRow}>
                <span className={styles.breakdownName}>
                  <span
                    className={styles.dot}
                    style={{ backgroundColor: `var(${m.colorVar})` }}
                  />
                  <span className={styles.breakdownModel}>{m.model}</span>
                </span>
                <span className={styles.breakdownValues}>
                  <span className={styles.breakdownTokens}>{m.tokensText}</span>
                  <span className={styles.breakdownCost}>{m.costText}</span>
                </span>
              </div>
              <div className={styles.breakdownTrack}>
                <div
                  className={styles.breakdownFill}
                  style={{
                    width: `${m.barPercent}%`,
                    backgroundColor: `var(${m.colorVar})`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
