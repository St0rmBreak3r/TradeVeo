export type Market = 'equities' | 'forex' | 'futures' | 'options' | 'crypto' | 'other';
export type Direction = 'long' | 'short';

export interface TradeInput {
  instrument: string;
  market: Market | null;
  direction: Direction;
  opened_at: string;
  closed_at: string | null;
  entry_price: string;
  exit_price: string | null;
  size: string;
  multiplier: string;
  fees: string;
  currency: string;
  realized_pnl_override: string | null;
  strategy: string | null;
  tags: string[];
  notes: string | null;
}

export interface Trade extends TradeInput {
  id: string;
  gross_pnl: string | null;
  net_pnl: string | null;
  created_at: string;
  updated_at: string;
}

export interface TradeList {
  items: Trade[];
  total: number;
  limit: number;
  offset: number;
}

export interface TradeFilters {
  search?: string;
  instrument?: string;
  market?: Market | '';
  direction?: Direction | '';
  strategy?: string;
  status?: 'open' | 'closed' | '';
  currency?: string;
  sort?: string;
  order?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

export interface CurrencySummary {
  currency: string;
  closed_count: number;
  wins: number;
  losses: number;
  breakeven: number;
  win_rate: string | null;
  net_pnl: string;
  average_win: string | null;
  average_loss: string | null;
  profit_factor: string | null;
}

export interface EquityPoint {
  currency: string;
  at: string;
  net_pnl: string;
  cumulative_pnl: string;
}

export interface AnalyticsSummary {
  currencies: CurrencySummary[];
  equity: EquityPoint[];
  open_count: number;
}

export interface CalendarDay {
  date: string;
  currency: string;
  closed_count: number;
  net_pnl: string;
}

export interface CalendarMonth {
  year: number;
  month: number;
  days: CalendarDay[];
}

export interface CalendarFilters {
  currency?: string;
  instrument?: string;
  market?: string;
  strategy?: string;
}

export interface SignalEntry {
  low: number | null;
  high: number | null;
  basis: string | null;
}

export interface SignalPrice {
  price: number;
  basis: string;
}

export interface ChartAnalysisResult {
  decision: 'LONG' | 'SHORT' | 'NO_TRADE';
  symbol: string | null;
  timeframe: string | null;
  setup_type: string | null;
  entry: SignalEntry | null;
  stop_loss: SignalPrice | null;
  targets: SignalPrice[];
  confidence: 'low' | 'medium' | 'high';
  confidence_note: string;
  observations: string[];
  rationale: string;
  invalidation: string | null;
  warnings: string[];
}

export type ProviderId = 'openai' | 'anthropic' | 'ollama' | 'custom_openai_compatible';
export type CredentialSource = 'environment' | 'credential_manager' | 'none' | 'local_service';

export interface AiProviderConfig {
  version: 1;
  provider: ProviderId;
  models: { openai: string; anthropic: string; ollama: string; openai_choices?: string[]; anthropic_choices?: string[] };
  custom_endpoint: { base_url: string; model: string; choices?: string[] };
}

export interface AiStatus {
  provider: ProviderId;
  configured: boolean;
  model: string | null;
  credential_source: CredentialSource;
  endpoint_label?: string;
  warning?: string;
}

export interface OllamaModels {
  available: boolean;
  models: string[];
}
