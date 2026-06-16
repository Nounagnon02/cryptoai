"use client";

import { useState, useEffect } from "react";
import {
  Save, AlertTriangle, Shield, Key, Trash2, Play, CheckCircle, XCircle, RefreshCw,
} from "lucide-react";
import {
  getSettings, updateSettings, addApiKey as saveApiKey, deleteApiKey, testApiKey,
  StrategySetting, RiskSetting, ApiKeySetting,
} from "@/lib/api";

const EXCHANGES = ["binance", "bybit", "coinbase", "kraken", "kucoin"];

export default function SettingsPage() {
  const [strategies, setStrategies] = useState<StrategySetting[]>([]);
  const [risk, setRisk] = useState<RiskSetting>({ max_drawdown_pct: 25, max_position_size_pct: 10 });
  const [apiKeys, setApiKeys] = useState<ApiKeySetting[]>([]);
  const [tradingMode, setTradingMode] = useState("paper");
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);

  // API Key form
  const [addExchange, setAddExchange] = useState("binance");
  const [addApiKey, setAddApiKey] = useState("");
  const [addApiSecret, setAddApiSecret] = useState("");
  const [keySubmitting, setKeySubmitting] = useState(false);
  const [keyDeleting, setKeyDeleting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [testing, setTesting] = useState(false);

  // Confirm live mode
  const [showLiveConfirm, setShowLiveConfirm] = useState(false);

  useEffect(() => {
    getSettings().then((data) => {
      if (data) {
        setStrategies(data.strategies);
        setRisk(data.risk);
        setApiKeys(data.api_keys);
        setTradingMode(data.trading_mode || "paper");
      }
      setLoading(false);
    });
  }, []);

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

  async function handleSave() {
    await updateSettings({ strategies, risk, trading_mode: tradingMode });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  async function handleToggleMode() {
    if (tradingMode === "paper") {
      // Going to live — show confirmation
      setShowLiveConfirm(true);
      return;
    }
    // Going back to paper
    const newMode = "paper";
    setTradingMode(newMode);
    await updateSettings({ trading_mode: newMode });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  async function confirmLiveMode() {
    const newMode = "live";
    setTradingMode(newMode);
    setShowLiveConfirm(false);
    await updateSettings({ trading_mode: newMode });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  async function handleAddKey() {
    if (!addApiKey || !addApiSecret) return;
    setKeySubmitting(true);
    const result = await saveApiKey({
      exchange: addExchange,
      api_key: addApiKey,
      api_secret: addApiSecret,
    });
    if (result) {
      setApiKeys(result.api_keys);
      setAddApiKey("");
      setAddApiSecret("");
    }
    setKeySubmitting(false);
  }

  async function handleDeleteKey(exchange: string) {
    setKeyDeleting(exchange);
    const result = await deleteApiKey(exchange);
    if (result) {
      setApiKeys(result.api_keys);
    }
    setKeyDeleting(null);
  }

  async function handleTestConnection() {
    if (!addApiKey || !addApiSecret) return;
    setTesting(true);
    setTestResult(null);
    const result = await testApiKey(addExchange, addApiKey, addApiSecret);
    setTestResult(result ? { success: result.success, message: result.message } : { success: false, message: "Test request failed" });
    setTesting(false);
  }

  const totalAllocation = strategies.reduce((sum, s) => sum + (s.enabled ? s.allocation : 0), 0);

  if (loading) {
    return (
      <div className="space-y-6 max-w-3xl">
        <div>
          <div className="h-7 bg-surface-hover rounded w-48 mb-2 animate-pulse" />
          <div className="h-4 bg-surface-hover rounded w-64 animate-pulse" />
        </div>
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="card animate-pulse h-40" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Settings</h1>
          <p className="text-sm text-gray-400 mt-1">
            Configuration des stratégies et paramètres de risque
          </p>
        </div>
        {/* Trading mode badge */}
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold ${
          tradingMode === "live"
            ? "bg-red-500/10 border border-red-500/30 text-red-400 animate-pulse"
            : "bg-green-500/10 border border-green-500/30 text-green-400"
        }`}>
          <span className={`w-2 h-2 rounded-full ${tradingMode === "live" ? "bg-red-400" : "bg-green-400"}`} />
          {tradingMode === "live" ? "🔴 LIVE TRADING" : "🟢 PAPER TRADING"}
        </div>
      </div>

      {/* ── Trading Mode ── */}
      <div className="card">
        <div className="flex items-start gap-3">
          <Shield className={`h-5 w-5 mt-0.5 ${tradingMode === "live" ? "text-red-400" : "text-green-400"}`} />
          <div className="flex-1">
            <h3 className="text-sm font-medium text-white">Trading Mode</h3>
            <p className="text-xs text-gray-500 mt-1">
              {tradingMode === "paper"
                ? "Paper trading uses simulated execution. No real funds at risk."
                : "Live trading uses real exchange credentials with actual funds."}
            </p>
            <button
              onClick={handleToggleMode}
              className={`mt-3 relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-crypto-blue focus:ring-offset-2 focus:ring-offset-surface-card ${
                tradingMode === "live" ? "bg-red-500" : "bg-surface-border"
              }`}
              role="switch"
              aria-checked={tradingMode === "live"}
              aria-label="Toggle trading mode"
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  tradingMode === "live" ? "translate-x-[26px]" : "translate-x-[3px]"
                }`}
              />
            </button>
          </div>
        </div>

        {tradingMode === "live" && (
          <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-400 flex-shrink-0" />
              <p className="text-xs text-red-400 font-medium">
                ⚠️ LIVE TRADING ACTIVE — Real funds are at risk. Ensure API keys have appropriate permissions and daily withdrawal limits are set.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Live mode confirmation modal */}
      {showLiveConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="card max-w-md mx-4 border border-red-500/30">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle className="h-6 w-6 text-red-400" />
              <h3 className="text-lg font-bold text-white">Enable Live Trading?</h3>
            </div>
            <p className="text-sm text-gray-400 mb-4">
              You are about to switch from paper trading to <span className="text-red-400 font-semibold">LIVE TRADING</span>.
              This will execute real trades using your exchange API keys with real funds.
            </p>
            <ul className="text-xs text-gray-500 space-y-2 mb-4">
              <li>• Verify your API keys have correct permissions</li>
              <li>• Set daily withdrawal limits on your exchange</li>
              <li>• Start with small position sizes</li>
              <li>• Monitor the system closely for the first 24h</li>
            </ul>
            <div className="flex gap-3">
              <button
                onClick={() => setShowLiveConfirm(false)}
                className="flex-1 px-4 py-2 rounded-lg bg-surface-hover text-gray-300 text-sm font-medium hover:bg-surface-border transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmLiveMode}
                className="flex-1 px-4 py-2 rounded-lg bg-red-500 text-white text-sm font-medium hover:bg-red-600 transition-colors"
              >
                I Understand — Enable Live
              </button>
            </div>
          </div>
        </div>
      )}

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
          <div>
            <div className="flex justify-between mb-2">
              <label className="label" htmlFor="max-drawdown">Max Drawdown</label>
              <span className="text-sm font-bold text-crypto-red tabular-nums">{risk.max_drawdown_pct}%</span>
            </div>
            <input
              id="max-drawdown"
              type="range"
              min={5}
              max={50}
              value={risk.max_drawdown_pct}
              onChange={(e) => setRisk((r) => ({ ...r, max_drawdown_pct: Number(e.target.value) }))}
              className="w-full h-1.5 bg-surface-border rounded-lg appearance-none cursor-pointer
                         accent-crypto-red focus:outline-none focus:ring-2 focus:ring-crypto-blue"
              aria-label="Maximum drawdown percentage"
            />
            <div className="flex justify-between text-xs text-gray-600 mt-1">
              <span>5%</span>
              <span>50%</span>
            </div>
          </div>

          <div>
            <div className="flex justify-between mb-2">
              <label className="label" htmlFor="max-position">Max Position Size</label>
              <span className="text-sm font-bold text-crypto-blue tabular-nums">{risk.max_position_size_pct}%</span>
            </div>
            <input
              id="max-position"
              type="range"
              min={2}
              max={30}
              value={risk.max_position_size_pct}
              onChange={(e) => setRisk((r) => ({ ...r, max_position_size_pct: Number(e.target.value) }))}
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

      {/* ── API Key Management ── */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Key className="h-4 w-4 text-gray-400" />
          <h3 className="text-sm font-medium text-gray-400">Exchange API Keys</h3>
        </div>
        <p className="text-xs text-gray-500 mb-4">
          Keys are encrypted at rest (AES-256-GCM) and never logged. Use API keys with trading permissions restricted to your IP.
        </p>

        {/* Existing keys */}
        <div className="space-y-2 mb-6">
          {apiKeys.length === 0 ? (
            <p className="text-xs text-gray-500 italic">No API keys configured</p>
          ) : (
            apiKeys.map((entry) => (
              <div
                key={entry.exchange}
                className="flex items-center justify-between py-2 px-3 rounded-lg bg-surface/40 border border-surface-border"
              >
                <div>
                  <span className="text-sm font-medium text-white capitalize">{entry.exchange}</span>
                  {entry.has_key && (
                    <code className="ml-2 text-xs text-gray-500 font-mono">{entry.key_preview || "••••••••••••••••"}</code>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className={entry.has_key ? "text-xs text-crypto-green" : "text-xs text-gray-500"}>
                    {entry.has_key ? "✓ Connected" : "— Not set"}
                  </span>
                  <button
                    onClick={() => handleDeleteKey(entry.exchange)}
                    disabled={keyDeleting === entry.exchange}
                    className="p-1 rounded hover:bg-red-500/10 text-gray-500 hover:text-red-400 transition-colors"
                    aria-label={`Delete ${entry.exchange} API key`}
                  >
                    {keyDeleting === entry.exchange ? (
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Add new key form */}
        <div className="border-t border-surface-border pt-4">
          <h4 className="text-xs font-medium text-gray-400 mb-3">Add / Update Key</h4>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
            <div>
              <label className="label" htmlFor="key-exchange">Exchange</label>
              <select
                id="key-exchange"
                value={addExchange}
                onChange={(e) => setAddExchange(e.target.value)}
                className="input"
              >
                {EXCHANGES.map((ex) => (
                  <option key={ex} value={ex}>{ex.charAt(0).toUpperCase() + ex.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="key-api-key">API Key</label>
              <input
                id="key-api-key"
                type="password"
                value={addApiKey}
                onChange={(e) => setAddApiKey(e.target.value)}
                className="input"
                placeholder="Enter API key"
                autoComplete="off"
              />
            </div>
            <div>
              <label className="label" htmlFor="key-api-secret">API Secret</label>
              <input
                id="key-api-secret"
                type="password"
                value={addApiSecret}
                onChange={(e) => setAddApiSecret(e.target.value)}
                className="input"
                placeholder="Enter API secret"
                autoComplete="off"
              />
            </div>
          </div>

          {testResult && (
            <div className={`flex items-center gap-2 p-3 rounded-lg text-xs mb-3 ${
              testResult.success
                ? "bg-green-500/10 border border-green-500/30 text-green-400"
                : "bg-red-500/10 border border-red-500/30 text-red-400"
            }`}>
              {testResult.success ? (
                <CheckCircle className="h-4 w-4 flex-shrink-0" />
              ) : (
                <XCircle className="h-4 w-4 flex-shrink-0" />
              )}
              {testResult.message}
            </div>
          )}

          <div className="flex items-center gap-2">
            <button
              onClick={handleAddKey}
              disabled={keySubmitting || !addApiKey || !addApiSecret}
              className="btn-primary inline-flex items-center gap-2 text-xs"
            >
              {keySubmitting ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Key className="h-3.5 w-3.5" />
              )}
              Save Key
            </button>
            <button
              onClick={handleTestConnection}
              disabled={testing || !addApiKey || !addApiSecret}
              className="px-3 py-2 bg-surface-hover text-gray-300 rounded-lg text-xs font-medium hover:bg-surface-border transition-colors inline-flex items-center gap-2"
            >
              {testing ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              Test Connection
            </button>
          </div>
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
