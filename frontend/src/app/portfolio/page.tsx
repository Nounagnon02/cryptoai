"use client";

import { useQuery } from "@tanstack/react-query";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { AlertTriangle } from "lucide-react";
import PositionsTable from "@/components/PositionsTable";
import {
  getPortfolioState,
  getPortfolioSummary,
  getRiskStatus,
  PortfolioState,
  PortfolioSummary,
  RiskStatus,
} from "@/lib/api";

const COLORS = ["#2979FF", "#00C853", "#FFD600", "#FF1744", "#7C4DFF", "#FF6D00"];

function formatUSD(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

const statusConfig: Record<string, { color: string; label: string }> = {
  safe: { color: "#00C853", label: "Safe" },
  warning: { color: "#FFD600", label: "Warning" },
  critical: { color: "#FF1744", label: "Critical" },
};

export default function PortfolioPage() {
  const { data: state, isLoading: loadingState } = useQuery<PortfolioState | null>({
    queryKey: ["portfolio-state"],
    queryFn: getPortfolioState,
    refetchInterval: 30_000,
  });

  const { data: summary } = useQuery<PortfolioSummary | null>({
    queryKey: ["portfolio-summary"],
    queryFn: getPortfolioSummary,
    refetchInterval: 30_000,
  });

  const { data: risk } = useQuery<RiskStatus | null>({
    queryKey: ["risk-status"],
    queryFn: getRiskStatus,
    refetchInterval: 15_000,
  });

  const allocations = state?.allocations ?? [];
  const positions = state?.positions ?? [];
  const status = risk?.status ?? "safe";
  const cfg = statusConfig[status] ?? statusConfig.safe;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Portfolio</h1>
        <p className="text-sm text-gray-400 mt-1">
          Positions, allocations et exposition
        </p>
      </div>

      {/* Summary & Risk row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card">
          <p className="text-sm font-medium text-gray-400">Total Value</p>
          <p className="mt-1 text-2xl font-bold text-white">
            {summary ? formatUSD(summary.total_usd) : "—"}
          </p>
        </div>
        <div className="card">
          <p className="text-sm font-medium text-gray-400">Cash Remaining</p>
          <p className="mt-1 text-2xl font-bold text-white">
            {state ? formatUSD(state.cash_remaining) : "—"}
          </p>
        </div>
        <div className="card">
          <p className="text-sm font-medium text-gray-400">Drawdown</p>
          <p className="mt-1 text-2xl font-bold text-crypto-red">
            {summary ? `${summary.drawdown_pct.toFixed(2)}%` : "—"}
          </p>
        </div>
        <div className="card">
          <p className="text-sm font-medium text-gray-400">Risk Status</p>
          <div className="mt-1 flex items-center gap-2">
            <span className="relative flex h-3 w-3">
              <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${
                status === "critical" ? "animate-ping" : ""
              }`} style={{ backgroundColor: cfg.color }} />
              <span className="relative inline-flex rounded-full h-3 w-3" style={{ backgroundColor: cfg.color }} />
            </span>
            <span className="text-lg font-bold" style={{ color: cfg.color }}>
              {cfg.label}
            </span>
          </div>
          {risk && risk.circuit_breaker_active && (
            <div className="mt-2 flex items-center gap-1 text-xs text-crypto-red">
              <AlertTriangle className="h-3 w-3" />
              Circuit breaker active
            </div>
          )}
        </div>
      </div>

      {/* Positions & Allocation */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Positions table */}
        <div className="lg:col-span-2">
          <PositionsTable positions={positions} loading={loadingState} />
        </div>

        {/* Allocation donut */}
        <div className="card">
          <h3 className="text-sm font-medium text-gray-400 mb-4">
            Strategy Allocation
          </h3>
          {allocations.length === 0 ? (
            <div className="h-[250px] flex items-center justify-center text-gray-500 text-sm">
              No allocations
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={allocations}
                  dataKey="allocation_pct"
                  nameKey="strategy"
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={3}
                  stroke="none"
                >
                  {allocations.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: "#1a1b2e",
                    border: "1px solid #2a2b3e",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                  formatter={(value: number, name: string) => [`${value.toFixed(1)}%`, name]}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
          {/* Legend */}
          <div className="mt-3 space-y-1.5">
            {allocations.map((a, i) => (
              <div key={a.strategy} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <div
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: COLORS[i % COLORS.length] }}
                  />
                  <span className="text-gray-400 capitalize">{a.strategy.replace(/_/g, " ")}</span>
                </div>
                <span className="text-gray-300 tabular-nums">
                  {a.allocation_pct.toFixed(1)}%
                  <span className={a.pnl_pct >= 0 ? "text-crypto-green ml-2" : "text-crypto-red ml-2"}>
                    {a.pnl_pct >= 0 ? "+" : ""}{a.pnl_pct.toFixed(1)}%
                  </span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
