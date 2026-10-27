import type { AiProviderConfig, AiStatus, AnalyticsSummary, CalendarFilters, CalendarMonth, ChartAnalysisResult, OllamaModels, ProviderId, Trade, TradeFilters, TradeInput, TradeList } from './types';

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); this.name = 'ApiError'; }
}
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, credentials: 'same-origin', headers: { ...(init?.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...init?.headers } });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const body = (await response.json()) as { detail?: string }; if (body.detail) message = body.detail; } catch { /* Keep status fallback. */ }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
export function listTrades(filters: TradeFilters = {}): Promise<TradeList> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value !== undefined && value !== '') params.set(key, String(value));
  return request<TradeList>(`/api/trades${params.size ? `?${params}` : ''}`);
}
export function getAnalyticsSummary(filters: { from?: string; to?: string; instrument?: string; market?: string; strategy?: string } = {}): Promise<AnalyticsSummary> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
  return request<AnalyticsSummary>(`/api/analytics/summary${params.size ? `?${params}` : ''}`);
}
export function getCalendar(year: number, month: number, filters: CalendarFilters = {}): Promise<CalendarMonth> {
  const params = new URLSearchParams({ year: String(year), month: String(month) });
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
  return request<CalendarMonth>(`/api/calendar?${params}`);
}
export function createTrade(input: TradeInput): Promise<Trade> { return request<Trade>('/api/trades', { method: 'POST', body: JSON.stringify(input) }); }
export function updateTrade(id: string, input: TradeInput): Promise<Trade> { return request<Trade>(`/api/trades/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(input) }); }
export function deleteTrade(id: string): Promise<void> { return request<void>(`/api/trades/${encodeURIComponent(id)}`, { method: 'DELETE' }); }

export function getAiStatus(): Promise<AiStatus> { return request<AiStatus>('/api/ai/status'); }
export function getAiProvider(): Promise<AiProviderConfig> { return request<AiProviderConfig>('/api/ai/provider'); }
export function saveAiProvider(config: AiProviderConfig): Promise<AiProviderConfig> {
  return request<AiProviderConfig>('/api/ai/provider', { method: 'PUT', body: JSON.stringify(config) });
}
export function getOllamaModels(): Promise<OllamaModels> { return request<OllamaModels>('/api/ai/models'); }
export function saveAiCredential(api_key: string, provider: ProviderId = 'openai'): Promise<{ configured: boolean; credential_source: string; provider: ProviderId }> {
  return request('/api/ai/credential', { method: 'PUT', body: JSON.stringify({ api_key, provider }) });
}
export function clearAiCredential(provider: ProviderId = 'openai'): Promise<{ configured: boolean }> {
  const params = new URLSearchParams({ provider });
  return request(`/api/ai/credential?${params}`, { method: 'DELETE' });
}
export async function analyzeChart(image: File): Promise<ChartAnalysisResult> {
  const form = new FormData();
  form.append('image', image);
  form.append('consent', 'true');
  return request<ChartAnalysisResult>('/api/chart-analysis', { method: 'POST', body: form });
}

export interface ImportPreview {
  preview_token: string;
  headers: string[];
  row_count: number;
  valid_count: number;
  errors: { row: number; error: string }[];
}
export interface BackupInfo { backup_id: string; created_at: string; trade_count: number; size_bytes: number }
export async function previewImport(file: File): Promise<ImportPreview> {
  const form = new FormData(); form.append('file', file);
  return request<ImportPreview>('/api/import/preview', { method: 'POST', body: form });
}
export function commitImport(preview_token: string): Promise<{ created: number; skipped_invalid: number }> {
  return request('/api/import/commit', { method: 'POST', body: JSON.stringify({ preview_token, confirm_valid_rows: true }) });
}
export async function exportCsv(filters: TradeFilters = {}): Promise<Blob> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value !== undefined && value !== '') params.set(key, String(value));
  const response = await fetch(`/api/export.csv${params.size ? `?${params}` : ''}`, { credentials: 'same-origin' });
  if (!response.ok) throw new ApiError(`CSV export failed (${response.status})`, response.status);
  return response.blob();
}
export function createBackup(): Promise<BackupInfo> { return request('/api/backups', { method: 'POST' }); }
export function listBackups(): Promise<BackupInfo[]> { return request('/api/backups'); }
export function restoreBackup(backup_id: string): Promise<{ restored_count: number; pre_restore_backup_id: string }> {
  return request('/api/backups/restore', { method: 'POST', body: JSON.stringify({ backup_id, confirm: true }) });
}
