"use client";

import { useState } from "react";
import { clsx } from "clsx";
import { ArrowUpDown } from "lucide-react";

interface Position {
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  entry_price: number;
  current_price: number;
  pnl_pct: number;
  value_usd: number;
}

interface PositionsTableProps {
  positions: Position[];
  loading?: boolean;
}

type SortKey = keyof Position;
type SortDir = "asc" | "desc";

function formatPrice(v: number): string {
  if (v >= 1000) return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (v >= 1) return v.toFixed(4);
  return v.toFixed(8);
}

function formatSize(v: number): string {
  if (v >= 1000) return v.toLocaleString("en-US", { minimumFractionDigits: 2 });
  if (v >= 1) return v.toFixed(4);
  return v.toFixed(6);
}

export default function PositionsTable({ positions, loading = false }: PositionsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("value_usd");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const sorted = [...positions].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    const cmp = typeof av === "string" ? String(av).localeCompare(String(bv)) : (av as number) - (bv as number);
    return sortDir === "asc" ? cmp : -cmp;
  });

  const columns: { key: SortKey; label: string; align?: "right" }[] = [
    { key: "symbol", label: "Symbol" },
    { key: "side", label: "Side" },
    { key: "quantity", label: "Qty", align: "right" },
    { key: "entry_price", label: "Entry", align: "right" },
    { key: "current_price", label: "Current", align: "right" },
    { key: "pnl_pct", label: "PnL %", align: "right" },
    { key: "value_usd", label: "Value", align: "right" },
  ];

  if (loading) {
    return (
      <div className="card">
        <div className="h-4 bg-surface-hover rounded w-32 mb-4" />
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-10 bg-surface-hover rounded mb-2 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <h3 className="text-sm font-medium text-gray-400 mb-4">Open Positions</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" role="table">
          <thead>
            <tr className="border-b border-surface-border">
              {columns.map((col) => (
                <th
                  key={col.key}
                  scope="col"
                  className={clsx(
                    "py-2 px-3 text-xs font-medium text-gray-500 cursor-pointer hover:text-gray-300 transition-colors select-none",
                    col.align === "right" && "text-right"
                  )}
                  onClick={() => handleSort(col.key)}
                  aria-sort={sortKey === col.key ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.label}
                    <ArrowUpDown className="h-3 w-3" aria-hidden="true" />
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-gray-500">
                  No open positions
                </td>
              </tr>
            ) : (
              sorted.map((pos) => (
                <tr
                  key={pos.symbol}
                  className="border-b border-surface-border last:border-0 hover:bg-surface-hover transition-colors"
                >
                  <td className="py-2.5 px-3 font-medium text-white">{pos.symbol}</td>
                  <td className="py-2.5 px-3">
                    <span
                      className={clsx(
                        "inline-block px-2 py-0.5 rounded text-xs font-medium",
                        pos.side === "buy"
                          ? "bg-crypto-green/10 text-crypto-green"
                          : "bg-crypto-red/10 text-crypto-red"
                      )}
                    >
                      {pos.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-right tabular-nums text-gray-300">
                    {formatSize(pos.quantity)}
                  </td>
                  <td className="py-2.5 px-3 text-right tabular-nums text-gray-300">
                    ${formatPrice(pos.entry_price)}
                  </td>
                  <td className="py-2.5 px-3 text-right tabular-nums text-gray-300">
                    ${formatPrice(pos.current_price)}
                  </td>
                  <td
                    className={clsx(
                      "py-2.5 px-3 text-right tabular-nums font-medium",
                      pos.pnl_pct >= 0 ? "text-crypto-green" : "text-crypto-red"
                    )}
                  >
                    {pos.pnl_pct >= 0 ? "+" : ""}{pos.pnl_pct.toFixed(2)}%
                  </td>
                  <td className="py-2.5 px-3 text-right tabular-nums text-gray-300">
                    ${pos.value_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
