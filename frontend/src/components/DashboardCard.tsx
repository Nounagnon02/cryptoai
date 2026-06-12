"use client";

import { ReactNode } from "react";
import { clsx } from "clsx";
import { TrendingUp, TrendingDown, Minus, LucideIcon } from "lucide-react";

interface DashboardCardProps {
  title: string;
  value: string;
  change?: number;
  changeType?: "positive" | "negative" | "neutral";
  icon?: LucideIcon;
  loading?: boolean;
  suffix?: string;
}

export default function DashboardCard({
  title,
  value,
  change,
  changeType,
  icon: Icon,
  loading = false,
  suffix,
}: DashboardCardProps) {
  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="h-4 bg-surface-hover rounded w-24 mb-3" />
        <div className="h-8 bg-surface-hover rounded w-32 mb-2" />
        <div className="h-3 bg-surface-hover rounded w-20" />
      </div>
    );
  }

  const ChangeIcon =
    changeType === "positive"
      ? TrendingUp
      : changeType === "negative"
        ? TrendingDown
        : Minus;

  const changeColor =
    changeType === "positive"
      ? "text-crypto-green"
      : changeType === "negative"
        ? "text-crypto-red"
        : "text-gray-400";

  return (
    <div className="card flex items-start justify-between group">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-400 truncate">{title}</p>
        <p className="mt-1 text-2xl font-bold text-white tabular-nums">
          {value}
          {suffix && <span className="text-sm font-normal text-gray-400 ml-1">{suffix}</span>}
        </p>
        {change !== undefined && (
          <div className={clsx("mt-1 flex items-center gap-1 text-sm", changeColor)}>
            <ChangeIcon className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="font-medium">{Math.abs(change).toFixed(2)}%</span>
          </div>
        )}
      </div>
      {Icon && (
        <div className="flex-shrink-0 p-2 rounded-lg bg-surface-hover group-hover:bg-surface-border transition-colors">
          <Icon className="h-5 w-5 text-crypto-blue" aria-hidden="true" />
        </div>
      )}
    </div>
  );
}
