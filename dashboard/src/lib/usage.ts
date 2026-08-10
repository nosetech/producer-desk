import type { CurrentLimitStatus, DailyUsage } from "./types";

/**
 * Claude Designの利用量パネル（feature/issue-64-usage-monitor-ui.dc.html）の
 * JSロジックをそのまま移植したもの。モデル色はステータスラベルと同じ
 * --accent-blue/--accent-purple/--accent-green/--accent-amber を使い回す
 * （src/lib/status.ts参照）。
 */
const PALETTE = [
  "--accent-blue",
  "--accent-purple",
  "--accent-green",
  "--accent-amber",
] as const;

function totalTokens(e: DailyUsage): number {
  return e.input_tokens + e.output_tokens;
}

export function formatTokens(n: number): string {
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 1 : 2) + "M";
  if (n >= 1e3) return Math.round(n / 1e3) + "K";
  return String(n);
}

export function formatCost(n: number): string {
  return `$${n.toFixed(2)}`;
}

export function shortDate(date: string): string {
  const [, month, day] = date.split("-");
  return `${Number(month)}/${Number(day)}`;
}

export function shortModelName(model: string): string {
  return model.startsWith("claude-")
    ? model.replace("claude-", "")
    : model.split(":")[0];
}

export type ModelColorMap = Record<string, string>;

export function assignModelColors(daily: DailyUsage[]): ModelColorMap {
  const models = [...new Set(daily.map((e) => e.model))].sort();
  const colors: ModelColorMap = {};
  models.forEach((model, i) => {
    colors[model] = PALETTE[i % PALETTE.length];
  });
  return colors;
}

export interface ChartPoint {
  cx: number;
  cy: number;
}

export interface ChartSeries {
  model: string;
  shortName: string;
  colorVar: string;
  points: string;
  dots: ChartPoint[];
}

export interface ChartGeometry {
  series: ChartSeries[];
  gridLines: number[];
  labels: { x: number; label: string }[];
}

const CHART_X0 = 10;
const CHART_X1 = 310;
const CHART_Y0 = 12;
const CHART_Y1 = 100;

export function buildChartGeometry(
  daily: DailyUsage[],
  colors: ModelColorMap,
): ChartGeometry {
  const models = [...new Set(daily.map((e) => e.model))].sort();
  const dates = [...new Set(daily.map((e) => e.date))].sort();
  const byDateModel: Record<string, Record<string, number>> = {};
  daily.forEach((e) => {
    (byDateModel[e.date] ??= {})[e.model] = totalTokens(e);
  });
  const maxTotal = Math.max(
    1,
    ...dates.map((date) =>
      Math.max(...models.map((model) => byDateModel[date]?.[model] ?? 0)),
    ),
  );

  const xAt = (i: number) =>
    dates.length > 1
      ? CHART_X0 + (i * (CHART_X1 - CHART_X0)) / (dates.length - 1)
      : (CHART_X0 + CHART_X1) / 2;
  const yAt = (value: number) =>
    CHART_Y1 - (value / maxTotal) * (CHART_Y1 - CHART_Y0);

  const series: ChartSeries[] = models.map((model) => {
    const points = dates.map((date, i) => ({
      cx: Number(xAt(i).toFixed(1)),
      cy: Number(yAt(byDateModel[date]?.[model] ?? 0).toFixed(1)),
    }));
    return {
      model,
      shortName: shortModelName(model),
      colorVar: colors[model],
      points: points.map((p) => `${p.cx},${p.cy}`).join(" "),
      dots: points,
    };
  });

  return {
    series,
    gridLines: [CHART_Y0, (CHART_Y0 + CHART_Y1) / 2, CHART_Y1],
    labels: dates.map((date, i) => ({
      x: Number(xAt(i).toFixed(1)),
      label: shortDate(date),
    })),
  };
}

export interface TodayUsage {
  dateText: string;
  totalText: string;
  costText: string;
  models: { model: string; colorVar: string; tokensText: string }[];
}

export function buildTodayUsage(
  daily: DailyUsage[],
  today: string,
  colors: ModelColorMap,
): TodayUsage {
  const entries = daily.filter((e) => e.date === today);
  return {
    dateText: today ? shortDate(today) : "-",
    totalText: formatTokens(
      entries.reduce((sum, e) => sum + totalTokens(e), 0),
    ),
    costText: formatCost(entries.reduce((sum, e) => sum + e.total_cost_usd, 0)),
    models: entries
      .slice()
      .sort((a, b) => totalTokens(b) - totalTokens(a))
      .map((e) => ({
        model: e.model,
        colorVar: colors[e.model],
        tokensText: formatTokens(totalTokens(e)),
      })),
  };
}

export interface ModelBreakdown {
  model: string;
  colorVar: string;
  tokensText: string;
  costText: string;
  barPercent: number;
}

export function buildModelBreakdown(
  daily: DailyUsage[],
  colors: ModelColorMap,
): ModelBreakdown[] {
  const agg: Record<string, { tokens: number; cost: number }> = {};
  daily.forEach((e) => {
    const a = (agg[e.model] ??= { tokens: 0, cost: 0 });
    a.tokens += totalTokens(e);
    a.cost += e.total_cost_usd;
  });
  const models = Object.keys(agg);
  const maxTokens = Math.max(1, ...models.map((m) => agg[m].tokens));
  return models
    .sort((a, b) => agg[b].tokens - agg[a].tokens)
    .map((model) => ({
      model,
      colorVar: colors[model],
      tokensText: formatTokens(agg[model].tokens),
      costText:
        agg[model].cost > 0 ? formatCost(agg[model].cost) : "$0.00 · ローカル",
      barPercent: (agg[model].tokens / maxTokens) * 100,
    }));
}

export interface LimitWarning {
  active: boolean;
  resetText: string;
  repoLabel: string;
  statusText: string;
}

export function buildLimitWarning(
  currentLimit: CurrentLimitStatus | null,
): LimitWarning {
  if (!currentLimit) {
    return { active: false, resetText: "", repoLabel: "", statusText: "" };
  }
  return {
    active: true,
    resetText: currentLimit.reset_at_text ?? currentLimit.error_message,
    repoLabel: `${currentLimit.repo} #${currentLimit.issue_number}`,
    statusText: String(currentLimit.api_error_status ?? ""),
  };
}
