"use client";

import { useState } from "react";
import { Save, Eye, EyeOff, AlertTriangle } from "lucide-react";

interface StrategyConfig {
  name: string;
  label: string;
  enabled: boolean;
  allocation: number;
}

interface ApiKeyEntry {
  exchange: string;
  key: string;
  masked: boolean;
}

const defaultStrategies: StrategyConfig[] = [
  { name: "trend_following", label: "Trend Following", enabled: true, allocation: 30 },
  { name: "momentum", label: "Momentum", enabled: true, allocation: 25 },
  { name: "mean_reversion", label: "Mean Reversion", enabled: false, allocation: 20 },
  { name: "swing_trading", label: "Swing Trading", enabled: true, allocation: 25 },
];

const defaultApiKeys: ApiKeyEntry[] = [
  { exchange: "Binance", key: "sk-••••••••••••••••", masked: true },
  { exchange: "Bybit", key: "sk-••••••••••••••••", masked: true },
];

export default function SettingsPage() {
  const [strategies, setStrategies] = useState<StrategyConfig[]>(defaultStrategies);
  const [apiKeys, setApiKeys] = useState<ApiKeyEntry[]>(defaultApiKeys);
  const [maxDrawdown, setMaxDrawdown] = useState(25);
  const [maxPositionSize, setMaxPositionSize] = useState(10);
  const [saved, setSaved] = useState(false);

  function toggleStrategy(name: string) {
    setStrategies((prev) =>
      prev.map((s) => (s.name === name ? { ...s, enabled: !s.enabled } : s))
    );
  }

  function updateAllocation(name: string, value: number) {
    setStrategies((prev) =>
      prev.map((s) => (s.name === name ? { ...s, allocation: Math.min(100, Math.max(0, value)) } : s))
    );
  }

  function toggleMask(idx: number) {
    setApiKeys((prev) =>
      prev.map((k, i) => (i === idx ? { ...k, masked: !k.masked } : k))
    );
  }

  function handleSave() {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  const totalAllocation = strategies.reduce((sum, s) => sum + (s.enabled ? s.allocation : 0), 0);

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-gray-400 mt-1">
          Configuration des stratégies et paramètres de risque
        </p>
      </div>

      {/* Strategy config */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-4">Active Strategies</h3>
        {totalAllocation !== 100 && (
          <div className="flex items-center gap-2 p-3 mb-4 rounded-lg bg-crypto-yellow/10 border border-crypto-yellow/30">
            <AlertTriangle className="h-4 w-4 text-crypto-yellow flex-shrink-0" />
            <p className="text-xs text-crypto-yellow">
              Total allocation: {totalAllocation}%. Should equal 100% for balanced portfolio.
            </p>
          </div>
        )}
        <div className="space-y-3">
          {strategies.map((s) => (
            <div
              key={s.name}
              className="flex items-center justify-between py-2 border-b border-surface-border last:border-0"
            >
              <div className="flex items-center gap-3">
                <button
                  role="switch"
                  aria-checked={s.enabled}
                  onClick={() => toggleStrategy(s.name)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-crypto-blue focus:ring-offset-2 focus:ring-offset-surface-card ${
                    s.enabled ? "bg-crypto-blue" : "bg-surface-border"
                  }`}
                >
                  <span
                    className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                      s.enabled ? "translate-x-[18px]" : "translate-x-[3px]"
                    }`}
                  />
                </button>
                <span className="text-sm font-medium text-white">{s.label}</span>
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs text-gray-500">Alloc:</label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={s.allocation}
                  onChange={(e) => updateAllocation(s.name, Number(e.target.value))}
                  disabled={!s.enabled}
                  className="w-16 px-2 py-1 text-xs text-right bg-surface border border-surface-border rounded
                            focus:outline-none focus:ring-1 focus:ring-crypto-blue disabled:opacity-40 tabular-nums text-gray-200"
                  aria-label={`${s.label} allocation percentage`}
                />
                <span className="text-xs text-gray-500">%</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Risk parameters */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-4">Risk Parameters</h3>
        <div className="space-y-6">
          {/* Max drawdown slider */}
          <div>
            <div className="flex justify-between mb-2">
              <label className="label" htmlFor="max-drawdown">Max Drawdown</label>
              <span className="text-sm font-bold text-crypto-red tabular-nums">{maxDrawdown}%</span>
            </div>
            <input
              id="max-drawdown"
              type="range"
              min={5}
              max={50}
              value={maxDrawdown}
              onChange={(e) => setMaxDrawdown(Number(e.target.value))}
              className="w-full h-1.5 bg-surface-border rounded-lg appearance-none cursor-pointer
                         accent-crypto-red focus:outline-none focus:ring-2 focus:ring-crypto-blue"
              aria-label="Maximum drawdown percentage"
            />
            <div className="flex justify-between text-xs text-gray-600 mt-1">
              <span>5%</span>
              <span>50%</span>
            </div>
          </div>

          {/* Max position size */}
          <div>
            <div className="flex justify-between mb-2">
              <label className="label" htmlFor="max-position">Max Position Size</label>
              <span className="text-sm font-bold text-crypto-blue tabular-nums">{maxPositionSize}%</span>
            </div>
            <input
              id="max-position"
              type="range"
              min={2}
              max={30}
              value={maxPositionSize}
              onChange={(e) => setMaxPositionSize(Number(e.target.value))}
              className="w-full h-1.5 bg-surface-border rounded-lg appearance-none cursor-pointer
                         accent-crypto-blue focus:outline-none focus:ring-2 focus:ring-crypto-blue"
              aria-label="Maximum position size percentage"
            />
            <div className="flex justify-between text-xs text-gray-600 mt-1">
              <span>2%</span>
              <span>30%</span>
            </div>
          </div>
        </div>
      </div>

      {/* API Keys */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-4">Exchange API Keys</h3>
        <p className="text-xs text-gray-500 mb-4">
          Keys are encrypted at rest (AES-256-GCM) and never logged.
        </p>
        <div className="space-y-3">
          {apiKeys.map((entry, i) => (
            <div
              key={entry.exchange}
              className="flex items-center justify-between py-2 border-b border-surface-border last:border-0"
            >
              <span className="text-sm font-medium text-white">{entry.exchange}</span>
              <div className="flex items-center gap-2">
                <code className="text-xs text-gray-400 font-mono">
                  {entry.masked ? entry.key : "sk-revealed-••••••••••••"}
                </code>
                <button
                  onClick={() => toggleMask(i)}
                  className="p-1 text-gray-500 hover:text-gray-300 transition-colors"
                  aria-label={entry.masked ? "Show API key" : "Hide API key"}
                >
                  {entry.masked ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Save button */}
      <div className="flex justify-end">
        <button onClick={handleSave} className="btn-primary inline-flex items-center gap-2">
          <Save className="h-4 w-4" />
          {saved ? "Saved!" : "Save Settings"}
        </button>
      </div>
    </div>
  );
}
