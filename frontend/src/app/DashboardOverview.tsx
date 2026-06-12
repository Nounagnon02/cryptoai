"use client";

import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  DollarSign,
  TrendingUp,
  BarChart3,
  Activity,
} from "lucide-react";
import DashboardCard from "@/components/DashboardCard";
import ScoreCard from "@/components/ScoreCard";
import PerformanceChart from "@/components/PerformanceChart";
import {
  getPortfolioSummary,
  getPerformanceSummary,
  getAIScores,
  getRecentDecisions,
  PortfolioSummary,
  PerformanceSummary,
  AIScore,
  DecisionRecord,
} from "@/lib/api";

function formatUSD(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

function formatPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export default function DashboardOverview() {
  const { data: summary, isLoading: loadingSummary } = useQuery<PortfolioSummary | null>({
    queryKey: ["portfolio-summary"],
    queryFn: getPortfolioSummary,
    refetchInterval: 30_000,
  });

  const { data: perf, isLoading: loadingPerf } = useQuery<PerformanceSummary | null>({
    queryKey: ["performance-summary"],
    queryFn: getPerformanceSummary,
    refetchInterval: 60_000,
  });

  const { data: aiScore, isLoading: loadingScore } = useQuery<AIScore | null>({
    queryKey: ["ai-scores"],
    queryFn: () => getAIScores("BTC/USDT"),
    refetchInterval: 30_000,
  });

  const { data: decisions, isLoading: loadingDecisions } = useQuery<DecisionRecord[] | null>({
    queryKey: ["recent-decisions"],
    queryFn: () => getRecentDecisions(5),
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-sm text-gray-400 mt-1">
          Real-time portfolio overview and AI trading signals
        </p>
      </div>

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
          title="24h P&L"
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
          <p className="text-sm text-gray-500">No decisions recorded yet.</p>
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
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-crypto-blue/10 text-crypto-blue">
                        {d.action}
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
