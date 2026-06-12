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
  onchain_score: number;
  sentiment_score: number;
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
