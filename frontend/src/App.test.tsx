import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';

vi.mock('./api/client', () => ({
  getAiStatus: vi.fn(async () => ({ provider: 'openai', configured: false, model: 'gpt-5.4-mini', credential_source: 'none' })),
  getAiProvider: vi.fn(async () => ({ version: 1, provider: 'openai', models: { openai: 'gpt-5.4-mini', anthropic: '', ollama: '' }, custom_endpoint: { base_url: '', model: '' } })),
  saveAiProvider: vi.fn(async (config) => config), getOllamaModels: vi.fn(async () => ({ available: false, models: [] })),
  analyzeChart: vi.fn(), saveAiCredential: vi.fn(), clearAiCredential: vi.fn(),
}));

afterEach(() => { cleanup(); vi.clearAllMocks(); window.history.replaceState({}, '', '/'); });

describe('TradeVeo chart desk', () => {
  it('opens on chart analysis and hides the journal pages', async () => {
    render(<App />);
    expect(await screen.findByRole('heading', { name: /one screenshot/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /TradeVeo/ })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Overview' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Journal' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Analytics' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Calendar' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Analyze chart' })).toBeDisabled();
  });

  it('opens provider settings from navigation', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole('link', { name: 'Settings' }));
    expect(await screen.findByRole('heading', { name: 'Provider and model' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /import & backup/i })).not.toBeInTheDocument();
  });
});
