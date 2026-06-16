"use client";

import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";
import { getPerformanceSummary, PerformanceSummary } from "@/lib/api";

interface MetricCardProps {
  label: string;
  value: string;
  positive?: boolean;
  negative?: boolean;
}

function MetricCard({ label, value, positive, negative }: MetricCardProps) {
  const color = positive ? "text-crypto-green" : negative ? "text-crypto-red" : "text-white";
  return (
    <div className="card">
      <p className="text-xs font-medium text-gray-400 mb-1">{label}</p>
      <p className={`text-xl font-bold ${color} tabular-nums`}>{value}</p>
    </div>
  );
}

function formatRatio(v: number): string {
  if (v === 0 || isNaN(v)) return "—";
  return v.toFixed(2);
}

function formatPercent(v: number): string {
  if (v === 0 || isNaN(v)) return "—";
  return `${v.toFixed(2)}%`;
}

export default function PerformancePage() {
  const { data: perf, isLoading } = useQuery<PerformanceSummary | null>({
    queryKey: ["performance-summary"],
    queryFn: getPerformanceSummary,
    refetchInterval: 60_000,
  });

  const monthlyData = (perf?.monthly_returns ?? []).map((m) => ({
    month: m.month,
    return: m.return_pct,
  }));

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <div className="h-7 bg-surface-hover rounded w-48 mb-2 animate-pulse" />
          <div className="h-4 bg-surface-hover rounded w-64 animate-pulse" />
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="card animate-pulse">
              <div className="h-3 bg-surface-hover rounded w-20 mb-2" />
              <div className="h-6 bg-surface-hover rounded w-24" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Performance</h1>
        <p className="text-sm text-gray-400 mt-1">
          Métriques avancées et analyse de performance
        </p>
      </div>

      {/* Key metrics grid */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <MetricCard
          label="Sharpe Ratio"
          value={formatRatio(perf?.sharpe_ratio ?? 0)}
          positive={(perf?.sharpe_ratio ?? 0) > 1}
          negative={(perf?.sharpe_ratio ?? 0) < 0}
        />
        <MetricCard
          label="Sortino Ratio"
          value={formatRatio(perf?.sortino_ratio ?? 0)}
          positive={(perf?.sortino_ratio ?? 0) > 1}
          negative={(perf?.sortino_ratio ?? 0) < 0}
        />
        <MetricCard
          label="Calmar Ratio"
          value={formatRatio(perf?.calmar_ratio ?? 0)}
          positive={(perf?.calmar_ratio ?? 0) > 1}
          negative={(perf?.calmar_ratio ?? 0) < 0}
        />
        <MetricCard
          label="Max Drawdown"
          value={formatPercent(perf?.max_drawdown_pct ?? 0)}
          negative
        />
        <MetricCard
          label="Profit Factor"
          value={formatRatio(perf?.profit_factor ?? 0)}
          positive={(perf?.profit_factor ?? 0) > 1.5}
          negative={(perf?.profit_factor ?? 0) < 1}
        />
        <MetricCard
          label="CAGR"
          value={formatPercent(perf?.cagr ?? 0)}
          positive={(perf?.cagr ?? 0) > 0}
          negative={(perf?.cagr ?? 0) < 0}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Equity curve */}
        <div className="card">
          <h3 className="text-sm font-medium text-gray-400 mb-4">Equity Curve</h3>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={perf?.equity_curve ?? []} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <defs>
                <linearGradient id="perfEquityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2979FF" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#2979FF" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2b3e" vertical={false} />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(v: string) => {
                  try { return new Date(v).toLocaleDateString("en-US", { month: "short", day: "numeric" }); }
                  catch { return v; }
                }}
                stroke="#4a4b5e"
                tick={{ fill: "#6a6b7e", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tickFormatter={(v: number) => v >= 1000 ? `$${(v/1000).toFixed(0)}K` : `$${v.toFixed(0)}`}
                stroke="#4a4b5e"
                tick={{ fill: "#6a6b7e", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={60}
              />
              <Tooltip
                contentStyle={{ background: "#1a1b2e", border: "1px solid #2a2b3e", borderRadius: "8px", fontSize: "12px" }}
                formatter={(v: number) => [`$${v.toLocaleString("en-US", { minimumFractionDigits: 2 })}`, "Equity"]}
              />
              <Area type="monotone" dataKey="equity" stroke="#2979FF" strokeWidth={2} fill="url(#perfEquityGrad)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Monthly returns bar chart */}
        <div className="card">
          <h3 className="text-sm font-medium text-gray-400 mb-4">Monthly Returns</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={monthlyData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2b3e" vertical={false} />
              <XAxis dataKey="month" stroke="#4a4b5e" tick={{ fill: "#6a6b7e", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                tickFormatter={(v: number) => `${v.toFixed(1)}%`}
                stroke="#4a4b5e"
                tick={{ fill: "#6a6b7e", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={45}
              />
              <Tooltip
                contentStyle={{ background: "#1a1b2e", border: "1px solid #2a2b3e", borderRadius: "8px", fontSize: "12px" }}
                formatter={(v: number) => [`${v >= 0 ? "+" : ""}${v.toFixed(2)}%`, "Return"]}
              />
              <Bar dataKey="return" radius={[4, 4, 0, 0]} maxBarSize={40}>
                {monthlyData.map((entry, i) => (
                  <rect key={i} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Total return */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-400">Total Return</p>
            <p className={`text-3xl font-bold mt-1 ${(perf?.total_return_pct ?? 0) >= 0 ? "text-crypto-green" : "text-crypto-red"}`}>
              {perf ? `${perf.total_return_pct >= 0 ? "+" : ""}${perf.total_return_pct.toFixed(2)}%` : "—"}
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm font-medium text-gray-400">Win Rate</p>
            <p className="text-2xl font-bold text-white">
              {perf ? `${perf.win_rate.toFixed(1)}%` : "—"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
