import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SettingsPage } from './SettingsPage';

const api = vi.hoisted(() => ({
  getAiProvider: vi.fn(), getAiStatus: vi.fn(), getOllamaModels: vi.fn(), saveAiProvider: vi.fn(),
  saveAiCredential: vi.fn(), clearAiCredential: vi.fn(),
}));
vi.mock('../api/client', () => api);

afterEach(() => { cleanup(); vi.clearAllMocks(); });
const config = { version: 1 as const, provider: 'openai' as const, models: { openai: 'gpt-5.4-mini', anthropic: '', ollama: '' }, custom_endpoint: { base_url: '', model: '' } };

describe('provider settings', () => {
  it('offers all supported providers and provider selection does not analyze a chart', async () => {
    api.getAiProvider.mockResolvedValue(config);
    api.getAiStatus.mockResolvedValue({ provider: 'openai', configured: false, model: 'gpt-5.4-mini', credential_source: 'none' });
    render(<SettingsPage />);
    const user = userEvent.setup();
    const selector = await screen.findByLabelText('Provider');
    expect(selector).toHaveTextContent('OpenAI');
    expect(selector).toHaveTextContent('Anthropic / Claude');
    expect(selector).toHaveTextContent('Ollama (local)');
    expect(selector).toHaveTextContent('Custom OpenAI-compatible endpoint');
    await user.selectOptions(selector, 'anthropic');
    expect(screen.getByLabelText('Anthropic / Claude API key')).toBeInTheDocument();
    expect(api.saveAiProvider).not.toHaveBeenCalled();
    expect(api.saveAiCredential).not.toHaveBeenCalled();
  });

  it('shows custom endpoint and model settings only for custom provider', async () => {
    api.getAiProvider.mockResolvedValue(config);
    api.getAiStatus.mockResolvedValue({ provider: 'openai', configured: false, model: 'gpt-5.4-mini', credential_source: 'none' });
    render(<SettingsPage />);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText('Provider'), 'custom_openai_compatible');
    expect(screen.getByLabelText('Base endpoint URL')).toBeInTheDocument();
    expect(screen.getByLabelText('Model')).toBeInTheDocument();
    expect(screen.getByLabelText('Custom OpenAI-compatible endpoint API key')).toBeInTheDocument();
  });

  it('saves selected provider configuration but does not initiate analysis', async () => {
    api.getAiProvider.mockResolvedValue(config);
    api.getAiStatus.mockResolvedValue({ provider: 'openai', configured: false, model: 'gpt-5.4-mini', credential_source: 'none' });
    api.saveAiProvider.mockImplementation(async (next) => next);
    render(<SettingsPage />);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText('Provider'), 'anthropic');
    await user.type(screen.getByLabelText('Add a model'), 'claude-vision-test');
    await user.click(screen.getByRole('button', { name: 'Add model' }));
    await user.click(screen.getByRole('button', { name: 'Save provider settings' }));
    await waitFor(() => expect(api.saveAiProvider).toHaveBeenCalled());
    expect(api.saveAiProvider.mock.calls[0][0].models.anthropic).toBe('claude-vision-test');
    expect(api.saveAiProvider.mock.calls[0][0].models.anthropic_choices).toEqual(['claude-vision-test']);
    expect(api.saveAiCredential).not.toHaveBeenCalled();
  });

  it('adds, selects, and removes custom models from the dropdown', async () => {
    api.getAiProvider.mockResolvedValue({
      ...config,
      provider: 'custom_openai_compatible',
      custom_endpoint: { base_url: 'https://integrate.api.nvidia.com/v1', model: 'z-ai/glm-5.3' },
    });
    api.getAiStatus.mockResolvedValue({ provider: 'custom_openai_compatible', configured: true, model: 'z-ai/glm-5.3', credential_source: 'credential_manager' });
    api.saveAiProvider.mockImplementation(async (next) => next);
    render(<SettingsPage />);
    const user = userEvent.setup();
    const selector = await screen.findByLabelText('Model');
    expect(selector).toHaveValue('z-ai/glm-5.3');
    await user.type(screen.getByLabelText('Add a model'), 'z-ai/glm-5.3-flash');
    await user.click(screen.getByRole('button', { name: 'Add model' }));
    expect(selector).toHaveValue('z-ai/glm-5.3-flash');
    await user.selectOptions(selector, 'z-ai/glm-5.3');
    expect(selector).toHaveValue('z-ai/glm-5.3');
    await user.selectOptions(selector, 'z-ai/glm-5.3-flash');
    await user.click(screen.getByRole('button', { name: 'Remove model' }));
    expect(selector).toHaveValue('z-ai/glm-5.3');
    expect(screen.queryByRole('option', { name: 'z-ai/glm-5.3-flash' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Save provider settings' }));
    await waitFor(() => expect(api.saveAiProvider).toHaveBeenCalled());
    expect(api.saveAiProvider.mock.calls[0][0].custom_endpoint).toMatchObject({ model: 'z-ai/glm-5.3', choices: ['z-ai/glm-5.3'] });
  });
});
