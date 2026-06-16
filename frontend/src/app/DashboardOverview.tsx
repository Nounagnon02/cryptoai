"use client";

import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  DollarSign,
  TrendingUp,
  BarChart3,
  Activity,
  Coins,
} from "lucide-react";
import DashboardCard from "@/components/DashboardCard";
import ScoreCard from "@/components/ScoreCard";
import PerformanceChart from "@/components/PerformanceChart";
import {
  getLivePortfolioSummary,
  getPerformanceSummary,
  getAIScores,
  getLiveExecutionStats,
  getRecentDecisions,
  getMarketOverview,
  getScreener,
  getSettings,
  PortfolioSummary,
  PerformanceSummary,
  AIScore,
  DecisionRecord,
  MarketOverview,
  MarketSymbolData,
  ScreenerItem,
} from "@/lib/api";

function formatUSD(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

function formatPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function getActionColor(action: string): string {
  switch (action) {
    case "strong_buy":
    case "buy":
      return "bg-green-500/10 text-green-400";
    case "strong_sell":
    case "sell":
      return "bg-red-500/10 text-red-400";
    case "reduce":
      return "bg-orange-500/10 text-orange-400";
    default:
      return "bg-blue-500/10 text-blue-400";
  }
}

export default function DashboardOverview() {
  const { data: marketOv, isLoading: loadingMarket } = useQuery<MarketOverview | null>({
    queryKey: ["market-overview"],
    queryFn: getMarketOverview,
    refetchInterval: 10_000,
  });

  const { data: summary, isLoading: loadingSummary } = useQuery<PortfolioSummary | null>({
    queryKey: ["live-portfolio-summary"],
    queryFn: getLivePortfolioSummary,
    refetchInterval: 15_000,
  });

  const { data: perf, isLoading: loadingPerf } = useQuery<PerformanceSummary | null>({
    queryKey: ["performance-summary"],
    queryFn: getPerformanceSummary,
    refetchInterval: 60_000,
  });

  const { data: aiScore, isLoading: loadingScore } = useQuery<AIScore | null>({
    queryKey: ["ai-scores-live"],
    queryFn: () => getAIScores("BTC/USDT"),
    refetchInterval: 15_000,
  });

  const { data: decisions, isLoading: loadingDecisions } = useQuery<DecisionRecord[] | null>({
    queryKey: ["recent-decisions-live"],
    queryFn: () => getRecentDecisions(5),
    refetchInterval: 15_000,
  });

  const { data: screener } = useQuery<{ top_gainers: ScreenerItem[]; top_losers: ScreenerItem[] } | null>({
    queryKey: ["screener"],
    queryFn: async () => {
      const result = await getScreener(5);
      return result as { top_gainers: ScreenerItem[]; top_losers: ScreenerItem[] } | null;
    },
    refetchInterval: 30_000,
  });

  const { data: settings } = useQuery<{ trading_mode: string } | null>({
    queryKey: ["settings-mode"],
    queryFn: async () => {
      const res = await getSettings();
      return res ? { trading_mode: res.trading_mode } : null;
    },
    refetchInterval: 60_000,
  });

  const tradingMode = settings?.trading_mode || "paper";
  const topSymbols = marketOv?.symbols?.filter(s => s.ticker !== null).slice(0, 4) ?? [];

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-gray-400 mt-1">
            Live {tradingMode === "live" ? "trading" : "paper trading"} · Données Binance mises à jour toutes les 10s
          </p>
        </div>
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold ${
          tradingMode === "live"
            ? "bg-red-500/10 border border-red-500/30 text-red-400"
            : "bg-green-500/10 border border-green-500/30 text-green-400"
        }`}>
          <span className={`w-2 h-2 rounded-full ${tradingMode === "live" ? "bg-red-400 animate-pulse" : "bg-green-400"}`} />
          {tradingMode === "live" ? "LIVE 🔴" : "PAPER 🟢"}
        </div>
      </div>

      {/* Live market prices row */}
      {topSymbols.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {topSymbols.map((s: MarketSymbolData) => (
            <div key={s.symbol} className="card py-3 px-4 flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-gray-500">{s.symbol.replace("/USDT", "")}</p>
                <p className="text-base font-semibold text-white tabular-nums">
                  ${s.ticker!.last.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </p>
              </div>
              <span
                className={`text-xs font-medium tabular-nums ${
                  s.ticker!.change_24h >= 0 ? "text-green-400" : "text-red-400"
                }`}
              >
                {formatPercent(s.ticker!.change_24h)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Top Movers */}
      {(screener?.top_gainers?.length ?? 0) > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Top Gainers */}
          <div className="card">
            <h3 className="text-sm font-medium text-green-400 mb-3 flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              Top Gainers 24h
            </h3>
            <div className="space-y-2">
              {screener?.top_gainers?.slice(0, 5).map((item: ScreenerItem) => (
                <div key={item.symbol} className="flex items-center justify-between text-sm">
                  <span className="text-white font-medium">{item.symbol.replace("/USDT", "")}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-gray-300 tabular-nums">
                      ${item.last_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                    <span className="text-green-400 tabular-nums font-medium w-16 text-right">
                      +{item.change_24h_pct.toFixed(1)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Top Losers */}
          <div className="card">
            <h3 className="text-sm font-medium text-red-400 mb-3 flex items-center gap-2">
              <TrendingUp className="h-4 w-4 rotate-180" />
              Top Losers 24h
            </h3>
            <div className="space-y-2">
              {screener?.top_losers?.slice(0, 5).map((item: ScreenerItem) => (
                <div key={item.symbol} className="flex items-center justify-between text-sm">
                  <span className="text-white font-medium">{item.symbol.replace("/USDT", "")}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-gray-300 tabular-nums">
                      ${item.last_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                    <span className="text-red-400 tabular-nums font-medium w-16 text-right">
                      {item.change_24h_pct.toFixed(1)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Metric cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <DashboardCard
          title="Portfolio Value"
          value={summary ? formatUSD(summary.total_usd) : "—"}
          change={summary?.pnl_24h_pct}
          changeType={
            summary && summary.pnl_24h_pct >= 0 ? "positive" : "negative"
          }
          icon={DollarSign}
          loading={loadingSummary}
        />
        <DashboardCard
          title="Total P&L"
          value={summary ? formatUSD(summary.pnl_24h_usd) : "—"}
          change={summary?.pnl_24h_pct}
          changeType={
            summary && summary.pnl_24h_pct >= 0 ? "positive" : "negative"
          }
          icon={TrendingUp}
          loading={loadingSummary}
        />
        <DashboardCard
          title="Open Positions"
          value={summary ? String(summary.open_positions) : "—"}
          icon={BarChart3}
          loading={loadingSummary}
        />
        <DashboardCard
          title="Win Rate"
          value={summary ? `${summary.win_rate.toFixed(1)}%` : "—"}
          suffix={summary ? `(${summary.total_trades} trades)` : undefined}
          icon={Activity}
          loading={loadingSummary}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Equity curve — spans 2 cols */}
        <div className="lg:col-span-2">
          <PerformanceChart
            data={perf?.equity_curve ?? []}
            loading={loadingPerf}
          />
        </div>

        {/* AI Score */}
        <div>
          <ScoreCard
            score={aiScore?.overall_score ?? 50}
            direction={aiScore?.direction ?? "neutral"}
            confidence={aiScore?.confidence ?? 0}
            reason={aiScore?.reason}
            loading={loadingScore}
          />
        </div>
      </div>

      {/* Recent decisions */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-4">
          Recent AI Decisions
        </h3>
        {loadingDecisions ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-8 bg-surface-hover rounded animate-pulse" />
            ))}
          </div>
        ) : !decisions || decisions.length === 0 ? (
          <p className="text-sm text-gray-500">No decisions recorded yet. The background AI analysis is initializing…</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" role="table">
              <thead>
                <tr className="border-b border-surface-border">
                  <th scope="col" className="py-2 pr-4 text-left text-xs font-medium text-gray-500">Time</th>
                  <th scope="col" className="py-2 pr-4 text-left text-xs font-medium text-gray-500">Symbol</th>
                  <th scope="col" className="py-2 pr-4 text-left text-xs font-medium text-gray-500">Action</th>
                  <th scope="col" className="py-2 pr-4 text-right text-xs font-medium text-gray-500">Score</th>
                  <th scope="col" className="py-2 text-right text-xs font-medium text-gray-500">Direction</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((d, i) => (
                  <tr key={i} className="border-b border-surface-border last:border-0 hover:bg-surface-hover transition-colors">
                    <td className="py-2 pr-4 text-gray-400 tabular-nums">
                      {new Date(d.timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
                    </td>
                    <td className="py-2 pr-4 font-medium text-white">{d.symbol}</td>
                    <td className="py-2 pr-4">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${getActionColor(d.action)}`}>
                        {d.action.replace("_", " ")}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums text-gray-300">{d.score.toFixed(0)}</td>
                    <td className="py-2 text-right capitalize text-gray-300">{d.direction}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
