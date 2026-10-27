import { useEffect, useState } from 'react';
import {
  clearAiCredential,
  getAiProvider,
  getAiStatus,
  getOllamaModels,
  saveAiCredential,
  saveAiProvider,
} from '../api/client';
import type { AiProviderConfig, AiStatus, OllamaModels, ProviderId } from '../api/types';

const PROVIDER_LABELS: Record<ProviderId, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic / Claude',
  ollama: 'Ollama (local)',
  custom_openai_compatible: 'Custom OpenAI-compatible endpoint',
};

const PROVIDER_KEY_LABELS: Record<ProviderId, string> = {
  openai: 'OpenAI API key',
  anthropic: 'Anthropic / Claude API key',
  ollama: '',
  custom_openai_compatible: 'Custom OpenAI-compatible endpoint API key',
};

const CREDENTIAL_PROVIDERS: ProviderId[] = ['openai', 'anthropic', 'custom_openai_compatible'];
const MAX_MODEL_CHOICES = 30;

function modelChoices(selected: string, choices: string[] | undefined): string[] {
  const unique: string[] = [];
  for (const item of choices ?? []) {
    const name = item.trim();
    if (name && !unique.includes(name)) unique.push(name);
  }
  if (selected && !unique.includes(selected)) unique.unshift(selected);
  return unique;
}

function withModelChoices(config: AiProviderConfig): AiProviderConfig {
  return {
    ...config,
    models: {
      ...config.models,
      openai_choices: modelChoices(config.models.openai, config.models.openai_choices),
      anthropic_choices: modelChoices(config.models.anthropic, config.models.anthropic_choices),
    },
    custom_endpoint: {
      ...config.custom_endpoint,
      choices: modelChoices(config.custom_endpoint.model, config.custom_endpoint.choices),
    },
  };
}

function ModelChoices({ id, selected, choices, busy, onChange }: { id: string; selected: string; choices: string[]; busy: boolean; onChange: (selected: string, choices: string[]) => void }) {
  const [draft, setDraft] = useState('');
  const [localError, setLocalError] = useState('');

  function add() {
    const name = draft.trim();
    if (!name || name.length > 200 || /[\u0000-\u001F]/.test(name)) {
      setLocalError('Enter a model id up to 200 characters.');
      return;
    }
    if (!choices.includes(name) && choices.length >= MAX_MODEL_CHOICES) {
      setLocalError('Save up to 30 models for a provider.');
      return;
    }
    onChange(name, choices.includes(name) ? choices : [...choices, name]);
    setDraft('');
    setLocalError('');
  }

  function remove() {
    const next = choices.filter((item) => item !== selected);
    onChange(next[0] ?? '', next);
    setLocalError('');
  }

  return (
    <div className="model-field">
      <label className="field" htmlFor={id}>
        Model
        <select id={id} value={selected} onChange={(event) => onChange(event.target.value, choices)} disabled={busy || choices.length === 0}>
          {choices.length === 0 && <option value="">Add a model</option>}
          {choices.map((model) => <option key={model} value={model}>{model}</option>)}
        </select>
      </label>
      <div className="model-add">
        <label className="field" htmlFor={`${id}-new`}>
          Add a model
          <input
            id={`${id}-new`}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); add(); } }}
            placeholder="model id"
            disabled={busy}
          />
        </label>
        <button className="button button-primary" type="button" onClick={add} disabled={busy}>Add model</button>
        <button className="button button-quiet" type="button" onClick={remove} disabled={busy || !selected}>Remove model</button>
      </div>
      {localError && <p className="form-error" role="alert">{localError}</p>}
      <p className="field-hint">The selected model is used for chart analysis after you save provider settings.</p>
    </div>
  );
}

export function SettingsPage() {
  const [config, setConfig] = useState<AiProviderConfig | null>(null);
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [ollamaModels, setOllamaModels] = useState<OllamaModels>({ available: false, models: [] });
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function refresh() {
    try {
      const [providerConfig, aiStatus, ollama] = await Promise.all([
        getAiProvider(),
        getAiStatus(),
        getOllamaModels(),
      ]);
      setConfig(withModelChoices(providerConfig));
      setStatus(aiStatus);
      setOllamaModels(ollama);
      setError('');
    } catch {
      setConfig(null);
      setStatus(null);
      setOllamaModels({ available: false, models: [] });
      setError('Provider settings could not be loaded.');
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function saveProvider(event: React.FormEvent) {
    event.preventDefault();
    if (!config) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const saved = await saveAiProvider(withModelChoices(config));
      setConfig(saved);
      setNotice('Provider settings saved.');
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save provider settings.');
    } finally {
      setBusy(false);
    }
  }

  async function saveKey() {
    if (!key.trim() || !config) return;
    const provider = config.provider;
    if (!CREDENTIAL_PROVIDERS.includes(provider)) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await saveAiCredential(key, provider);
      setKey('');
      setNotice('Key saved to Windows Credential Manager.');
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save key securely.');
    } finally {
      setBusy(false);
    }
  }

  async function clearKey() {
    if (!config) return;
    const provider = config.provider;
    if (!CREDENTIAL_PROVIDERS.includes(provider)) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await clearAiCredential(provider);
      setNotice('Saved key removed. An environment key, if set, remains available.');
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not remove saved key.');
    } finally {
      setBusy(false);
    }
  }

  function handleProviderChange(provider: ProviderId) {
    setConfig((prev) => {
      if (!prev) return null;
      const models = { ...prev.models };
      const customEndpoint = { ...prev.custom_endpoint };
      // Reset model for the new provider if not set
      if (provider === 'anthropic' && !models.anthropic) models.anthropic = '';
      if (provider === 'ollama' && !models.ollama) models.ollama = '';
      if (provider === 'custom_openai_compatible') {
        if (!customEndpoint.base_url) customEndpoint.base_url = '';
        if (!customEndpoint.model) customEndpoint.model = '';
      }
      return { ...prev, provider, models, custom_endpoint: customEndpoint };
    });
    setKey('');
  }

  function handleModelChoices(field: 'openai' | 'anthropic', selected: string, choices: string[]) {
    setConfig((prev) => {
      if (!prev) return null;
      return { ...prev, models: { ...prev.models, [field]: selected, [`${field}_choices`]: choices } };
    });
  }

  function handleCustomModelChoices(selected: string, choices: string[]) {
    setConfig((prev) => {
      if (!prev) return null;
      return { ...prev, custom_endpoint: { ...prev.custom_endpoint, model: selected, choices } };
    });
  }

  function handleCustomEndpointChange(field: 'base_url' | 'model', value: string) {
    setConfig((prev) => {
      if (!prev) return null;
      return { ...prev, custom_endpoint: { ...prev.custom_endpoint, [field]: value } };
    });
  }

  const provider = config?.provider ?? 'openai';
  const showCustomEndpoint = provider === 'custom_openai_compatible';
  const showOllamaModel = provider === 'ollama';
  const showAnthropicModel = provider === 'anthropic';
  const showOpenAIModel = provider === 'openai';
  const showApiKey = CREDENTIAL_PROVIDERS.includes(provider);
  const apiKeyLabel = PROVIDER_KEY_LABELS[provider];

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">LOCAL PROVIDER SETUP</p>
          <h1>Settings</h1>
          <p className="page-subtitle">Configure chart analysis provider and credentials.</p>
        </div>
      </div>
      {error && <p role="alert" className="form-error">{error}</p>}
      {notice && <p role="status" className="privacy-note">{notice}</p>}

      {!config && !error && <p className="loading-state" role="status">Loading provider settings…</p>}
      {config && <section className="tool-card ai-settings-card">
        <p className="eyebrow">CHART ANALYSIS PROVIDER</p>
        <h2>Provider and model</h2>

        <div className="provider-selector">
          <label className="field" htmlFor="provider-select">
            Provider
            <select
              id="provider-select"
              value={provider}
              onChange={(e) => handleProviderChange(e.target.value as ProviderId)}
              aria-label="Provider"
              disabled={busy}
            >
              {Object.entries(PROVIDER_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <form className="provider-config-form" onSubmit={saveProvider}>
          {showOpenAIModel && config && (
            <ModelChoices id="openai-model" selected={config.models.openai} choices={modelChoices(config.models.openai, config.models.openai_choices)} busy={busy} onChange={(selected, choices) => handleModelChoices('openai', selected, choices)} />
          )}

          {showAnthropicModel && config && (
            <ModelChoices id="anthropic-model" selected={config.models.anthropic} choices={modelChoices(config.models.anthropic, config.models.anthropic_choices)} busy={busy} onChange={(selected, choices) => handleModelChoices('anthropic', selected, choices)} />
          )}

          {showOllamaModel && (
            <div className="model-field">
              <label className="field" htmlFor="ollama-model">
                Model
                <select
                  id="ollama-model"
                  value={config?.models.ollama ?? ''}
                  onChange={(e) => setConfig((prev) => prev ? { ...prev, models: { ...prev.models, ollama: e.target.value } } : prev)}
                  disabled={busy || !ollamaModels.available}
                >
                  <option value="">Choose an installed vision model…</option>
                  {ollamaModels.models.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
                {!ollamaModels.available && (
                  <p className="field-hint">Ollama not reachable at 127.0.0.1:11434. Start Ollama and pull a vision model.</p>
                )}
              </label>
            </div>
          )}

          {showCustomEndpoint && (
            <>
              <div className="model-field">
                <label className="field" htmlFor="custom-base-url">
                  Base endpoint URL
                  <input
                    id="custom-base-url"
                    type="url"
                    value={config?.custom_endpoint.base_url ?? ''}
                    onChange={(e) => handleCustomEndpointChange('base_url', e.target.value)}
                    placeholder="https://api.example.com/v1"
                    disabled={busy}
                  />
                </label>
              </div>
              {config && <ModelChoices id="custom-model" selected={config.custom_endpoint.model} choices={modelChoices(config.custom_endpoint.model, config.custom_endpoint.choices)} busy={busy} onChange={handleCustomModelChoices} />}
            </>
          )}

          <div className="credential-actions">
            <button className="button button-primary" type="submit" disabled={busy}>
              {busy ? 'Saving…' : 'Save provider settings'}
            </button>
          </div>
        </form>

        {showApiKey && apiKeyLabel && (
          <>
            <div className="ai-status-panel">
              <span className={`provider-dot ${status?.configured ? 'ready' : ''}`} />
              <strong>{status?.configured ? 'Configured' : 'Not configured'}</strong>
              {status?.configured && <span>{status.model} · source: {status.credential_source.replace('_', ' ')}</span>}
            </div>
            <form className="credential-form" onSubmit={(event) => { event.preventDefault(); void saveKey(); }}>
              <label className="field">
                {apiKeyLabel}
                <input
                  type="password"
                  autoComplete="new-password"
                  value={key}
                  onChange={(event) => setKey(event.target.value)}
                  placeholder="Paste key; saved only to Windows Credential Manager"
                  aria-describedby="key-storage-note"
                  disabled={busy}
                />
              </label>
              <p id="key-storage-note" className="field-hint">
                The form clears after saving. If Credential Manager is unavailable, saving fails closed.
                Alternatively, set <code>{provider === 'openai' ? 'OPENAI_API_KEY' : provider === 'anthropic' ? 'ANTHROPIC_API_KEY' : 'CUSTOM_OPENAI_API_KEY'}</code> in the backend process environment
                (matching backend environment variable).
              </p>
              <div className="credential-actions">
                <button className="button button-primary" disabled={busy || !key.trim()} type="submit">
                  {busy ? 'Saving…' : 'Save key securely'}
                </button>
                {status?.credential_source === 'credential_manager' && (
                  <button className="button button-quiet" disabled={busy} type="button" onClick={() => void clearKey()}>
                    Remove saved key
                  </button>
                )}
              </div>
            </form>
            <p className="disclaimer">
              {provider === 'openai' ? 'OpenAI processing and retention follow its current API data controls.' :
               provider === 'anthropic' ? 'Anthropic processing and retention follow its current API data controls.' :
               'Custom provider processing and retention follow its current API data controls.'}
              Tradeveo does not save chart images or analysis history.
              Removing a saved key does not remove an environment-configured key.
            </p>
          </>
        )}

        {provider === 'ollama' && (
          <div className="ai-status-panel">
            <span className={`provider-dot ${status?.configured ? 'ready' : ''}`} />
            <strong>{status?.configured ? 'Configured' : 'Not configured'}</strong>
            {status?.configured && <span>{status.model} · source: local service</span>}
          </div>
        )}
      </section>}
    </>
  );
}