"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface EquityPoint {
  timestamp: string;
  equity: number;
}

interface PerformanceChartProps {
  data: EquityPoint[];
  height?: number;
  color?: string;
  loading?: boolean;
}

function formatCurrency(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

function formatDate(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return ts;
  }
}

export default function PerformanceChart({
  data,
  height = 300,
  color = "#2979FF",
  loading = false,
}: PerformanceChartProps) {
  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="h-4 bg-surface-hover rounded w-32 mb-4" />
        <div className="h-[300px] bg-surface-hover rounded" />
      </div>
    );
  }

  if (!data.length) {
    return (
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-4">Equity Curve</h3>
        <div className="h-[300px] flex items-center justify-center text-gray-500 text-sm">
          No data available
        </div>
      </div>
    );
  }

  const gradientId = "equityGradient";
  const isPositive = data[data.length - 1]?.equity >= data[0]?.equity;

  return (
    <div className="card">
      <h3 className="text-sm font-medium text-gray-400 mb-4">Equity Curve</h3>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2b3e" vertical={false} />
          <XAxis
            dataKey="timestamp"
            tickFormatter={formatDate}
            stroke="#4a4b5e"
            tick={{ fill: "#6a6b7e", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            minTickGap={30}
          />
          <YAxis
            tickFormatter={formatCurrency}
            stroke="#4a4b5e"
            tick={{ fill: "#6a6b7e", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={60}
          />
          <Tooltip
            contentStyle={{
              background: "#1a1b2e",
              border: "1px solid #2a2b3e",
              borderRadius: "8px",
              fontSize: "12px",
            }}
            labelStyle={{ color: "#a0a0b8" }}
            formatter={(value: number) => [`$${value.toLocaleString("en-US", { minimumFractionDigits: 2 })}`, "Equity"]}
            labelFormatter={formatDate}
          />
          <Area
            type="monotone"
            dataKey="equity"
            stroke={color}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            dot={false}
            activeDot={{ r: 4, fill: color, stroke: "#1a1b2e", strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
