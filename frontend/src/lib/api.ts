const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

interface FetchOptions extends RequestInit {
  params?: Record<string, string | number | undefined>;
}

async function fetchApi<T>(endpoint: string, options: FetchOptions = {}): Promise<T | null> {
  const { params, ...fetchOpts } = options;

  let url = `${API_BASE_URL}${endpoint}`;
  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) searchParams.set(key, String(value));
    });
    const qs = searchParams.toString();
    if (qs) url += `?${qs}`;
  }

  try {
    const res = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...fetchOpts.headers,
      },
      ...fetchOpts,
    });

    if (!res.ok) {
      console.warn(`API ${res.status}: ${endpoint}`);
      return null;
    }

    return (await res.json()) as T;
  } catch (err) {
    console.error(`API fetch error: ${endpoint}`, err);
    return null;
  }
}

// ---- Types (mirror backend) ----

export interface PortfolioSummary {
  total_usd: number;
  pnl_24h_usd: number;
  pnl_24h_pct: number;
  open_positions: number;
  win_rate: number;
  total_trades: number;
  drawdown_pct: number;
}

export interface PortfolioState {
  positions: Position[];
  allocations: StrategyAllocation[];
  cash_remaining: number;
}

export interface Position {
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  entry_price: number;
  current_price: number;
  pnl_usd: number;
  pnl_pct: number;
  value_usd: number;
  allocation_pct: number;
}

export interface StrategyAllocation {
  strategy: string;
  allocation_pct: number;
  pnl_pct: number;
}

export interface RiskStatus {
  circuit_breaker_active: boolean;
  daily_loss_pct: number;
  weekly_loss_pct: number;
  monthly_loss_pct: number;
  max_drawdown_pct: number;
  status: "safe" | "warning" | "critical";
}

export interface DecisionRecord {
  timestamp: string;
  symbol: string;
  action: string;
  score: number;
  confidence: number;
  direction: string;
  reason: string;
}

export interface AIScore {
  symbol: string;
  overall_score: number;
  direction: string;
  confidence: number;
  technical_score: number;
  onchain_score: number | null;
  sentiment_score: number | null;
  reason: string;
}

export interface ExecutionStats {
  total_orders: number;
  filled_orders: number;
  pending_orders: number;
  cancelled_orders: number;
  avg_fill_time_ms: number;
  total_volume_usd: number;
}

export interface MonthlyReturn {
  month: string;
  return_pct: number;
}

export interface PerformanceSummary {
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown_pct: number;
  profit_factor: number;
  win_rate: number;
  cagr: number;
  total_return_pct: number;
  equity_curve: EquityPoint[];
  monthly_returns: MonthlyReturn[];
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
}

export interface MetricsResponse {
  total_return_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown_pct: number;
  profit_factor: number;
  win_rate: number;
  cagr: number;
}

// ---- Live market types ----

export interface TickerData {
  last: number;
  bid: number;
  ask: number;
  volume_24h: number;
  change_24h: number;
}

export interface OhlcvPoint {
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketSymbolData {
  symbol: string;
  ticker: TickerData | null;
  last_ohlcv: OhlcvPoint | null;
  updated_at: string | null;
}

export interface MarketOverview {
  symbols: MarketSymbolData[];
  count: number;
  timestamp: string;
}

// ---- API functions ----

export function getPortfolioSummary(): Promise<PortfolioSummary | null> {
  return fetchApi<PortfolioSummary>("/portfolio/summary");
}

export function getPortfolioState(): Promise<PortfolioState | null> {
  return fetchApi<PortfolioState>("/portfolio/state");
}

export function getRiskStatus(): Promise<RiskStatus | null> {
  return fetchApi<RiskStatus>("/risk/status");
}

export function getRecentDecisions(limit = 10): Promise<DecisionRecord[] | null> {
  return fetchApi<DecisionRecord[]>("/ai/decisions", {
    params: { limit },
  });
}

export function getAIScores(symbol: string): Promise<AIScore | null> {
  return fetchApi<AIScore>("/ai/scores", {
    params: { symbol },
  });
}

export function getExecutionStats(): Promise<ExecutionStats | null> {
  return fetchApi<ExecutionStats>("/execution/stats");
}

export function getPerformanceSummary(): Promise<PerformanceSummary | null> {
  return fetchApi<PerformanceSummary>("/performance/summary");
}

// ---- Settings types ----

export interface StrategySetting {
  name: string;
  label: string;
  enabled: boolean;
  allocation: number;
}

export interface RiskSetting {
  max_drawdown_pct: number;
  max_position_size_pct: number;
}

export interface ApiKeySetting {
  exchange: string;
  key_preview: string;
  has_key: boolean;
}

export interface SettingsResponse {
  strategies: StrategySetting[];
  risk: RiskSetting;
  api_keys: ApiKeySetting[];
  trading_mode: string;
}

export function getSettings(): Promise<SettingsResponse | null> {
  return fetchApi<SettingsResponse>("/settings");
}

export function updateSettings(data: {
  strategies?: StrategySetting[];
  risk?: RiskSetting;
  trading_mode?: string;
}): Promise<SettingsResponse | null> {
  return fetchApi<SettingsResponse>("/settings", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export interface ApiKeyAddRequest {
  exchange: string;
  api_key: string;
  api_secret: string;
}

export interface ApiKeyTestResult {
  success: boolean;
  message: string;
  exchange: string;
}

export function addApiKey(data: ApiKeyAddRequest): Promise<SettingsResponse | null> {
  return fetchApi<SettingsResponse>("/settings/keys", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function deleteApiKey(exchange: string): Promise<SettingsResponse | null> {
  return fetchApi<SettingsResponse>(`/settings/keys/${exchange}`, {
    method: "DELETE",
  });
}

export function testApiKey(exchange: string, apiKey: string, apiSecret: string): Promise<ApiKeyTestResult | null> {
  return fetchApi<ApiKeyTestResult>("/settings/keys/test", {
    method: "POST",
    body: JSON.stringify({ exchange, api_key: apiKey, api_secret: apiSecret }),
  });
}

// ---- Live data endpoints ----

export function getMarketOverview(): Promise<MarketOverview | null> {
  return fetchApi<MarketOverview>("/market/overview");
}

export function getLiveAIScores(symbol: string): Promise<AIScore | null> {
  return fetchApi<AIScore>(`/ai/live/${symbol}`);
}

export function getLivePortfolioSummary(): Promise<PortfolioSummary | null> {
  return fetchApi<PortfolioSummary>("/portfolio/summary");
}

export function getLivePortfolioState(): Promise<PortfolioState | null> {
  return fetchApi<PortfolioState>("/portfolio/state");
}

export function getLiveExecutionStats(): Promise<ExecutionStats | null> {
  return fetchApi<ExecutionStats>("/execution/stats");
}

// ---- Trade history types ----

export interface TradeEntry {
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

export interface TradeHistoryResponse {
  trades: TradeEntry[];
  total: number;
}

export function getTradeHistory(
  limit = 50,
  symbol?: string
): Promise<TradeHistoryResponse | null> {
  return fetchApi<TradeHistoryResponse>("/trades/history", {
    params: { limit, symbol },
  });
}

export function getTradeExportUrl(symbol?: string): string {
  const params = new URLSearchParams({ format: "csv" });
  if (symbol) params.set("symbol", symbol);
  return `${API_BASE_URL}/trades/export?${params.toString()}`;
}

// ---- Screener types ----

export interface ScreenerItem {
  symbol: string;
  last_price: number;
  change_24h_pct: number;
  volume_24h: number;
  bid: number;
  ask: number;
}

export interface ScreenerResponse {
  top_gainers: ScreenerItem[];
  top_losers: ScreenerItem[];
  timestamp: string;
}

export function getScreener(
  limit = 10,
  sortBy = "change_24h"
): Promise<ScreenerResponse | null> {
  return fetchApi<ScreenerResponse>("/market/screener", {
    params: { limit, sort_by: sortBy },
  });
}

// ---- Backtest types ----

export interface BacktestRunRequest {
  strategy: string;
  symbol: string;
  timeframe: string;
  start_date?: string;
  end_date?: string;
  initial_capital: number;
}

export interface BacktestTradeEntry {
  timestamp: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  pnl: number;
  pnl_pct: number;
}

export interface BacktestResult {
  run_id: string;
  status: string;
  config: BacktestRunRequest;
  metrics: Record<string, number> | null;
  equity_curve: { timestamp: string; equity: number }[];
  trades: BacktestTradeEntry[];
  benchmark_return_pct: number;
  started_at: string;
  completed_at: string | null;
}

export interface BacktestStatus {
  run_id: string;
  status: string;
  progress_pct: number;
  started_at: string;
  completed_at: string | null;
}

export function runBacktest(data: BacktestRunRequest): Promise<BacktestStatus | null> {
  return fetchApi<BacktestStatus>("/backtest/run", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function getBacktestResult(runId: string): Promise<BacktestResult | null> {
  return fetchApi<BacktestResult>(`/backtest/result/${runId}`);
}

export function listBacktestResults(limit = 10): Promise<BacktestStatus[] | null> {
  return fetchApi<BacktestStatus[]>("/backtest/results", {
    params: { limit },
  });
}
