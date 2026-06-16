"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Play, RefreshCw, TrendingUp, BarChart3, Activity, Target } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

interface BacktestRunRequest {
  strategy: string;
  symbol: string;
  timeframe: string;
  start_date?: string;
  end_date?: string;
  initial_capital: number;
}

interface TradeLogEntry {
  timestamp: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  pnl: number;
  pnl_pct: number;
}

interface BacktestResult {
  run_id: string;
  status: string;
  config: BacktestRunRequest;
  metrics: Record<string, number> | null;
  equity_curve: { timestamp: string; equity: number }[];
  trades: TradeLogEntry[];
  benchmark_return_pct: number;
  started_at: string;
  completed_at: string | null;
}

interface BacktestStatus {
  run_id: string;
  status: string;
  progress_pct: number;
  started_at: string;
  completed_at: string | null;
}

const STRATEGIES = [
  { value: "trend_following", label: "Trend Following (EMA crossover)" },
  { value: "momentum", label: "Momentum (RSI + ROC)" },
  { value: "mean_reversion", label: "Mean Reversion (Bollinger Bands)" },
  { value: "swing_trading", label: "Swing Trading" },
];

const SYMBOLS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "ADA/USDT", "XRP/USDT"];
const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];

function formatUSD(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(2)}`;
}

function formatPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export default function BacktestPage() {
  const [strategy, setStrategy] = useState("trend_following");
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [capital, setCapital] = useState("10000");
  const [running, setRunning] = useState(false);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Poll for result
  const { data: result, refetch: refetchResult } = useQuery<BacktestResult | null>({
    queryKey: ["backtest-result", currentRunId],
    queryFn: async () => {
      if (!currentRunId) return null;
      const res = await fetch(`${API_BASE}/backtest/result/${currentRunId}`);
      if (!res.ok) return null;
      return res.json();
    },
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.status === "running") return 2000;
      return false;
    },
    enabled: !!currentRunId,
  });

  // Recent backtests
  const { data: recentRuns } = useQuery<BacktestStatus[] | null>({
    queryKey: ["backtest-results"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/backtest/results?limit=10`);
      if (!res.ok) return null;
      return res.json();
    },
    refetchInterval: 10000,
  });

  async function handleRun() {
    setError(null);
    setRunning(true);
    try {
      const body: BacktestRunRequest = {
        strategy,
        symbol,
        timeframe,
        initial_capital: Number(capital) || 10000,
      };
      if (startDate) body.start_date = startDate;
      if (endDate) body.end_date = endDate;

      const res = await fetch(`${API_BASE}/backtest/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Backtest failed");
      }

      const data = await res.json();
      setCurrentRunId(data.run_id);
    } catch (e: any) {
      setError(e.message || "Backtest failed to start");
    } finally {
      setRunning(false);
      refetchResult();
    }
  }

  const isCompleted = result?.status === "completed";
  const isRunning = result?.status === "running" || running;
  const metrics = result?.metrics;
  const equityCurve = result?.equity_curve ?? [];
  const trades = result?.trades ?? [];

  // Equity chart values (simple bar visualization)
  const maxEquity = equityCurve.length > 0
    ? Math.max(...equityCurve.map((p) => p.equity))
    : Number(capital) || 10000;
  const minEquity = equityCurve.length > 0
    ? Math.min(...equityCurve.map((p) => p.equity))
    : Number(capital) || 10000;
  const equityRange = maxEquity - minEquity || 1;

  function loadRecentRun(runId: string) {
    setCurrentRunId(runId);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Backtest</h1>
        <p className="text-sm text-gray-400 mt-1">
          Test your strategies against historical data
        </p>
      </div>

      {/* Configuration Form */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-4">Configuration</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Strategy */}
          <div>
            <label className="label" htmlFor="bt-strategy">Strategy</label>
            <select
              id="bt-strategy"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="input"
              disabled={isRunning}
            >
              {STRATEGIES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          {/* Symbol */}
          <div>
            <label className="label" htmlFor="bt-symbol">Symbol</label>
            <select
              id="bt-symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="input"
              disabled={isRunning}
            >
              {SYMBOLS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {/* Timeframe */}
          <div>
            <label className="label" htmlFor="bt-timeframe">Timeframe</label>
            <select
              id="bt-timeframe"
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="input"
              disabled={isRunning}
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
          </div>

          {/* Start Date */}
          <div>
            <label className="label" htmlFor="bt-start">Start Date</label>
            <input
              id="bt-start"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="input"
              disabled={isRunning}
            />
          </div>

          {/* End Date */}
          <div>
            <label className="label" htmlFor="bt-end">End Date</label>
            <input
              id="bt-end"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="input"
              disabled={isRunning}
            />
          </div>

          {/* Capital */}
          <div>
            <label className="label" htmlFor="bt-capital">Initial Capital (USD)</label>
            <input
              id="bt-capital"
              type="number"
              min={100}
              max={1000000}
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
              className="input"
              disabled={isRunning}
            />
          </div>
        </div>

        {error && (
          <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-400">
            {error}
          </div>
        )}

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={handleRun}
            disabled={isRunning}
            className="btn-primary inline-flex items-center gap-2"
          >
            {isRunning ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                Run Backtest
              </>
            )}
          </button>

          {isRunning && (
            <span className="text-sm text-crypto-blue tabular-nums animate-pulse">
              Processing...
            </span>
          )}
        </div>
      </div>

      {/* Results */}
      {isCompleted && metrics && (
        <>
          {/* Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="card py-4 px-4">
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                <TrendingUp className="h-3.5 w-3.5" />
                Total Return
              </div>
              <p className={`text-xl font-bold tabular-nums ${metrics.total_return_pct >= 0 ? "text-crypto-green" : "text-crypto-red"}`}>
                {formatPercent(metrics.total_return_pct)}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                vs B&H: {formatPercent(result.benchmark_return_pct)}
              </p>
            </div>

            <div className="card py-4 px-4">
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                <Activity className="h-3.5 w-3.5" />
                Sharpe Ratio
              </div>
              <p className={`text-xl font-bold tabular-nums ${metrics.sharpe_ratio >= 1 ? "text-crypto-green" : metrics.sharpe_ratio >= 0 ? "text-crypto-yellow" : "text-crypto-red"}`}>
                {metrics.sharpe_ratio.toFixed(2)}
              </p>
            </div>

            <div className="card py-4 px-4">
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                <Target className="h-3.5 w-3.5" />
                Win Rate
              </div>
              <p className={`text-xl font-bold tabular-nums ${metrics.win_rate >= 50 ? "text-crypto-green" : "text-crypto-red"}`}>
                {metrics.win_rate.toFixed(1)}%
              </p>
              <p className="text-xs text-gray-500 mt-1">
                {metrics.total_trades} trades
              </p>
            </div>

            <div className="card py-4 px-4">
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                <BarChart3 className="h-3.5 w-3.5" />
                Max Drawdown
              </div>
              <p className={`text-xl font-bold tabular-nums text-crypto-red`}>
                -{metrics.max_drawdown_pct.toFixed(1)}%
              </p>
              <p className="text-xs text-gray-500 mt-1">
                PF: {metrics.profit_factor.toFixed(2)}
              </p>
            </div>
          </div>

          {/* Equity Curve */}
          {equityCurve.length > 0 && (
            <div className="card">
              <h3 className="text-sm font-medium text-gray-400 mb-4">Equity Curve</h3>
              <div className="h-48 flex items-end gap-[2px]">
                {equityCurve.filter((_, i) => i % Math.max(1, Math.floor(equityCurve.length / 80)) === 0).map((point, i) => {
                  const height = ((point.equity - minEquity) / equityRange) * 100;
                  return (
                    <div
                      key={i}
                      className="flex-1 rounded-t-sm transition-colors"
                      style={{
                        height: `${Math.max(1, height)}%`,
                        backgroundColor: point.equity >= Number(capital) ? "#00C853" : "#FF1744",
                        opacity: 0.8,
                        minWidth: "2px",
                      }}
                      title={`${new Date(point.timestamp).toLocaleDateString()}: ${formatUSD(point.equity)}`}
                    />
                  );
                })}
              </div>
              <div className="flex justify-between text-xs text-gray-500 mt-2">
                <span>{formatUSD(minEquity)}</span>
                <span>{formatUSD(maxEquity)}</span>
              </div>
            </div>
          )}

          {/* Trade Log */}
          {trades.length > 0 && (
            <div className="card">
              <h3 className="text-sm font-medium text-gray-400 mb-4">
                Trade Log ({trades.length} trades)
              </h3>
              <div className="overflow-x-auto max-h-64 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-surface-card">
                    <tr className="border-b border-surface-border">
                      <th className="py-2 pr-4 text-left text-xs font-medium text-gray-500">Date</th>
                      <th className="py-2 pr-4 text-left text-xs font-medium text-gray-500">Side</th>
                      <th className="py-2 pr-4 text-right text-xs font-medium text-gray-500">Qty</th>
                      <th className="py-2 pr-4 text-right text-xs font-medium text-gray-500">Price</th>
                      <th className="py-2 text-right text-xs font-medium text-gray-500">P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t, i) => (
                      <tr key={i} className="border-b border-surface-border last:border-0 hover:bg-surface-hover">
                        <td className="py-2 pr-4 text-gray-400 tabular-nums whitespace-nowrap">
                          {new Date(t.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                        </td>
                        <td className="py-2 pr-4">
                          <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                            t.side === "buy" ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"
                          }`}>
                            {t.side.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-right tabular-nums text-gray-300">{t.quantity.toFixed(4)}</td>
                        <td className="py-2 pr-4 text-right tabular-nums text-gray-300">{formatUSD(t.price)}</td>
                        <td className={`py-2 text-right tabular-nums font-medium ${t.pnl >= 0 ? "text-crypto-green" : "text-crypto-red"}`}>
                          {t.pnl !== 0 ? formatPercent(t.pnl_pct) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Running state */}
      {isRunning && (
        <div className="card text-center py-12">
          <RefreshCw className="h-8 w-8 text-crypto-blue animate-spin mx-auto mb-3" />
          <p className="text-sm text-gray-400">Backtest in progress...</p>
          <p className="text-xs text-gray-500 mt-1">Fetching historical data and running strategy simulation</p>
        </div>
      )}

      {/* Failed state */}
      {result?.status === "failed" && (
        <div className="card text-center py-12">
          <p className="text-sm text-red-400">Backtest failed.</p>
          <p className="text-xs text-gray-500 mt-1">Check the symbol and date range, then try again.</p>
        </div>
      )}

      {/* Recent Runs */}
      {recentRuns && recentRuns.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-medium text-gray-400 mb-3">Recent Backtests</h3>
          <div className="space-y-2">
            {recentRuns.slice(0, 5).map((run) => (
              <button
                key={run.run_id}
                onClick={() => loadRecentRun(run.run_id)}
                className={`w-full flex items-center justify-between py-2 px-3 rounded-lg text-left transition-colors ${
                  currentRunId === run.run_id
                    ? "bg-crypto-blue/10 border border-crypto-blue/30"
                    : "hover:bg-surface-hover"
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className={`w-2 h-2 rounded-full ${
                    run.status === "completed" ? "bg-crypto-green" :
                    run.status === "running" ? "bg-crypto-blue animate-pulse" :
                    "bg-crypto-red"
                  }`} />
                  <span className="text-sm text-gray-300 font-mono text-xs">{run.run_id}</span>
                </div>
                <div className="flex items-center gap-3 text-xs text-gray-500">
                  <span>{run.status}</span>
                  <span>{new Date(run.started_at).toLocaleTimeString()}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
