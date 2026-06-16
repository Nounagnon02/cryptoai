"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { clsx } from "clsx";
import { Download, Filter } from "lucide-react";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

interface TradeEntry {
  trade_id: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  value_usd: number;
  fee: number;
  pnl: number;
  pnl_pct: number;
  timestamp: string;
  strategy: string;
  status: string;
}

interface TradeHistoryResponse {
  trades: TradeEntry[];
  total: number;
}

function formatUSD(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(2)}`;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("fr-FR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

const SYMBOLS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT"];

export default function TradesPage() {
  const [filterSymbol, setFilterSymbol] = useState<string>("");
  const [filterSide, setFilterSide] = useState<string>("");

  const { data, isLoading } = useQuery<TradeHistoryResponse | null>({
    queryKey: ["trade-history", filterSymbol],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set("limit", "100");
      if (filterSymbol) params.set("symbol", filterSymbol);
      const url = `${API_BASE_URL}/trades/history?${params.toString()}`;
      const res = await fetch(url);
      if (!res.ok) return null;
      return res.json() as Promise<TradeHistoryResponse>;
    },
    refetchInterval: 15_000,
  });

  const trades = (data?.trades ?? []).filter(
    (t) => !filterSide || t.side === filterSide
  );

  const totalPnl = trades
    .filter((t) => t.status === "closed")
    .reduce((sum, t) => sum + t.pnl, 0);
  const winningTrades = trades.filter(
    (t) => t.pnl > 0 && t.status === "closed"
  ).length;
  const closedTrades = trades.filter((t) => t.status === "closed").length;
  const winRate = closedTrades > 0 ? (winningTrades / closedTrades) * 100 : 0;

  function handleExportCsv() {
    const params = new URLSearchParams();
    params.set("format", "csv");
    params.set("limit", "500");
    if (filterSymbol) params.set("symbol", filterSymbol);
    window.open(`${API_BASE_URL}/trades/export?${params.toString()}`, "_blank");
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Trade History</h1>
          <p className="text-sm text-gray-400 mt-1">
            Historique complet des trades papier
          </p>
        </div>
        <button onClick={handleExportCsv} className="btn-primary flex items-center gap-2 text-sm">
          <Download className="h-4 w-4" />
          Export CSV
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card py-3 px-4">
          <p className="text-xs text-gray-500">Total Trades</p>
          <p className="text-xl font-bold text-white tabular-nums">
            {isLoading ? "—" : data?.total ?? 0}
          </p>
        </div>
        <div className="card py-3 px-4">
          <p className="text-xs text-gray-500">Total P&L</p>
          <p
            className={`text-xl font-bold tabular-nums ${
              totalPnl >= 0 ? "text-green-400" : "text-red-400"
            }`}
          >
            {isLoading ? "—" : formatUSD(totalPnl)}
          </p>
        </div>
        <div className="card py-3 px-4">
          <p className="text-xs text-gray-500">Win Rate</p>
          <p className="text-xl font-bold text-white tabular-nums">
            {isLoading ? "—" : `${winRate.toFixed(1)}%`}
          </p>
        </div>
        <div className="card py-3 px-4">
          <p className="text-xs text-gray-500">Closed Trades</p>
          <p className="text-xl font-bold text-white tabular-nums">
            {isLoading ? "—" : closedTrades}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-gray-500" />
          <span className="text-xs text-gray-500">Filters:</span>
        </div>
        <select
          value={filterSymbol}
          onChange={(e) => setFilterSymbol(e.target.value)}
          className="input w-auto text-sm py-1.5"
        >
          <option value="">All Symbols</option>
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={filterSide}
          onChange={(e) => setFilterSide(e.target.value)}
          className="input w-auto text-sm py-1.5"
        >
          <option value="">All Sides</option>
          <option value="buy">Buy</option>
          <option value="sell">Sell</option>
        </select>
        {trades.length > 0 && (
          <span className="text-xs text-gray-500 ml-auto">
            {trades.length} trade{trades.length > 1 ? "s" : ""} shown
          </span>
        )}
      </div>

      {/* Trades table */}
      <div className="card overflow-x-auto">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-8 bg-surface-hover rounded animate-pulse"
              />
            ))}
          </div>
        ) : trades.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <p className="text-sm">Aucun trade enregistré</p>
            <p className="text-xs mt-2">
              Les trades apparaîtront ici après que le système ait commencé à trader
            </p>
          </div>
        ) : (
          <table className="w-full text-sm" role="table">
            <thead>
              <tr className="border-b border-surface-border">
                {[
                  "Date",
                  "Symbol",
                  "Side",
                  "Qty",
                  "Price",
                  "Value",
                  "Fee",
                  "P&L",
                  "Status",
                ].map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="py-2.5 pr-4 text-left text-xs font-medium text-gray-500"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr
                  key={t.trade_id}
                  className="border-b border-surface-border last:border-0 hover:bg-surface-hover transition-colors"
                >
                  <td className="py-2.5 pr-4 text-gray-400 whitespace-nowrap tabular-nums">
                    {formatTime(t.timestamp)}
                  </td>
                  <td className="py-2.5 pr-4 font-medium text-white">
                    {t.symbol.replace("/USDT", "")}
                  </td>
                  <td className="py-2.5 pr-4">
                    <span
                      className={clsx(
                        "px-2 py-0.5 rounded text-xs font-medium",
                        t.side === "buy"
                          ? "bg-green-500/10 text-green-400"
                          : "bg-red-500/10 text-red-400"
                      )}
                    >
                      {t.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="py-2.5 pr-4 text-gray-300 tabular-nums">
                    {t.quantity.toFixed(4)}
                  </td>
                  <td className="py-2.5 pr-4 text-gray-300 tabular-nums">
                    ${t.price.toFixed(2)}
                  </td>
                  <td className="py-2.5 pr-4 text-gray-300 tabular-nums">
                    {formatUSD(t.value_usd)}
                  </td>
                  <td className="py-2.5 pr-4 text-gray-500 tabular-nums text-xs">
                    {formatUSD(t.fee)}
                  </td>
                  <td className="py-2.5 pr-4 tabular-nums">
                    <span
                      className={clsx(
                        "font-medium",
                        t.pnl >= 0 ? "text-green-400" : "text-red-400"
                      )}
                    >
                      {t.pnl >= 0 ? "+" : ""}
                      {formatUSD(t.pnl)}
                      <span className="text-xs ml-1">
                        ({t.pnl_pct >= 0 ? "+" : ""}
                        {t.pnl_pct.toFixed(2)}%)
                      </span>
                    </span>
                  </td>
                  <td className="py-2.5">
                    <span
                      className={clsx(
                        "px-2 py-0.5 rounded text-xs font-medium",
                        t.status === "open"
                          ? "bg-blue-500/10 text-blue-400"
                          : "bg-gray-500/10 text-gray-400"
                      )}
                    >
                      {t.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
