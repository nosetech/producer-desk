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

export type ChartMetric = "total" | "in" | "out";

export const METRIC_LABEL: Record<ChartMetric, string> = {
  total: "入力+出力",
  in: "入力",
  out: "出力",
};

function metricValue(e: DailyUsage, metric: ChartMetric): number {
  if (metric === "in") return e.input_tokens;
  if (metric === "out") return e.output_tokens;
  return e.input_tokens + e.output_tokens;
}

export function formatTokens(n: number): string {
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 1 : 2) + "M";
  if (n >= 1e3) return Math.round(n / 1e3) + "K";
  return String(n);
}

/** チャートY軸の目盛りラベル用（Mへの丸めは行わない。デザインのfmtKに対応）。 */
export function formatK(n: number): string {
  return n >= 1e3 ? Math.round(n / 1e3) + "K" : String(n);
}

export function formatCost(n: number): string {
  return `$${n.toFixed(2)}`;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function shortDate(date: string): string {
  const [, month, day] = date.split("-");
  return `${pad2(Number(month))}/${pad2(Number(day))}`;
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

export interface ChartTick {
  y: number;
  textY: number;
  label: string;
}

export interface ChartGeometry {
  series: ChartSeries[];
  yTicks: ChartTick[];
  xLabels: { x: number; label: string }[];
}

const CHART_X0 = 40;
const CHART_X1 = 312;
const CHART_Y0 = 12;
const CHART_Y1 = 98;

/** グラフの最大値を切りのいい値（1/2/5/10のべき乗）に丸める。デザインのniceStep/niceMaxに対応。 */
function niceScale(rawMax: number): { step: number; max: number } {
  const rough = rawMax / 3;
  const pow = Math.pow(10, Math.floor(Math.log10(rough)));
  const n = rough / pow;
  const step = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow;
  const max = Math.max(step, Math.ceil(rawMax / step) * step);
  return { step, max };
}

export function buildChartGeometry(
  daily: DailyUsage[],
  colors: ModelColorMap,
  metric: ChartMetric,
): ChartGeometry {
  const models = [...new Set(daily.map((e) => e.model))].sort();
  const dates = [...new Set(daily.map((e) => e.date))].sort();
  const byDateModel: Record<string, Record<string, number>> = {};
  daily.forEach((e) => {
    (byDateModel[e.date] ??= {})[e.model] = metricValue(e, metric);
  });
  const rawMax = Math.max(
    1,
    ...dates.map((date) =>
      Math.max(...models.map((model) => byDateModel[date]?.[model] ?? 0)),
    ),
  );
  const { step: niceStep, max: niceMax } = niceScale(rawMax);

  const xAt = (i: number) =>
    dates.length > 1
      ? CHART_X0 + (i * (CHART_X1 - CHART_X0)) / (dates.length - 1)
      : (CHART_X0 + CHART_X1) / 2;
  const yAt = (value: number) =>
    CHART_Y1 - (value / niceMax) * (CHART_Y1 - CHART_Y0);

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

  const yTicks: ChartTick[] = [];
  for (let v = 0; v <= niceMax + 1; v += niceStep) {
    const y = Number(yAt(v).toFixed(1));
    yTicks.push({ y, textY: Number((y + 3).toFixed(1)), label: formatK(v) });
  }

  return {
    series,
    yTicks,
    xLabels: dates.map((date, i) => ({
      x: Number(xAt(i).toFixed(1)),
      label: shortDate(date),
    })),
  };
}

export interface TodayUsage {
  dateText: string;
  inText: string;
  outText: string;
  totalText: string;
  costText: string;
  models: {
    model: string;
    colorVar: string;
    inText: string;
    outText: string;
  }[];
}

export function buildTodayUsage(
  daily: DailyUsage[],
  today: string,
  colors: ModelColorMap,
): TodayUsage {
  const entries = daily.filter((e) => e.date === today);
  const totalIn = entries.reduce((sum, e) => sum + e.input_tokens, 0);
  const totalOut = entries.reduce((sum, e) => sum + e.output_tokens, 0);
  return {
    dateText: today ? shortDate(today) : "-",
    inText: formatTokens(totalIn),
    outText: formatTokens(totalOut),
    totalText: formatTokens(totalIn + totalOut),
    costText: formatCost(entries.reduce((sum, e) => sum + e.total_cost_usd, 0)),
    models: entries
      .slice()
      .sort(
        (a, b) =>
          b.input_tokens + b.output_tokens - (a.input_tokens + a.output_tokens),
      )
      .map((e) => ({
        model: e.model,
        colorVar: colors[e.model],
        inText: formatTokens(e.input_tokens),
        outText: formatTokens(e.output_tokens),
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
  metric: ChartMetric,
): ModelBreakdown[] {
  const agg: Record<string, { tokens: number; cost: number }> = {};
  daily.forEach((e) => {
    const a = (agg[e.model] ??= { tokens: 0, cost: 0 });
    a.tokens += metricValue(e, metric);
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
