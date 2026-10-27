import { useState } from 'react';
import type { Trade, TradeInput } from '../api/types';

const emptyTrade: TradeInput = {
  instrument: '', market: 'forex', direction: 'long',
  opened_at: new Date().toISOString().slice(0, 16), closed_at: null,
  entry_price: '', exit_price: null, size: '', multiplier: '1', fees: '0', currency: 'USD',
  realized_pnl_override: null, strategy: '', tags: [], notes: '',
};

function decimalField(value: string): string | null {
  const cleaned = value.trim();
  if (!cleaned) return null;
  return /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(cleaned) ? cleaned : null;
}

export function TradeForm({ initialValue, onSave, onCancel }: {
  initialValue?: Trade;
  onSave: (input: TradeInput) => Promise<void>;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<TradeInput>(() => initialValue ? {
    instrument: initialValue.instrument, market: initialValue.market, direction: initialValue.direction,
    opened_at: initialValue.opened_at.slice(0, 16), closed_at: initialValue.closed_at?.slice(0, 16) ?? null,
    entry_price: initialValue.entry_price, exit_price: initialValue.exit_price, size: initialValue.size,
    multiplier: initialValue.multiplier, fees: initialValue.fees, currency: initialValue.currency,
    realized_pnl_override: initialValue.realized_pnl_override, strategy: initialValue.strategy,
    tags: initialValue.tags, notes: initialValue.notes,
  } : emptyTrade);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const set = <K extends keyof TradeInput>(key: K, value: TradeInput[K]) => setForm((current) => ({ ...current, [key]: value }));

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    const entry = decimalField(form.entry_price);
    const size = decimalField(form.size);
    const multiplier = decimalField(form.multiplier);
    const fees = decimalField(form.fees);
    const exit = form.closed_at ? decimalField(form.exit_price ?? '') : null;
    if (!form.instrument.trim() || !entry || !size || !multiplier || fees === null || (form.closed_at && !exit)) {
      setError('Enter an instrument, valid prices and size, and both exit time and exit price for a closed position.');
      return;
    }
    const opened = new Date(form.opened_at);
    const closed = form.closed_at ? new Date(form.closed_at) : null;
    if (Number.isNaN(opened.valueOf()) || (closed && (Number.isNaN(closed.valueOf()) || closed < opened))) {
      setError('Check the trade dates. A position cannot close before it opens.');
      return;
    }
    const override = form.realized_pnl_override ? decimalField(form.realized_pnl_override) : null;
    if (form.realized_pnl_override && !override) {
      setError('Realized P&L must be a plain decimal value.');
      return;
    }
    const payload: TradeInput = {
      ...form,
      instrument: form.instrument.trim().toUpperCase(),
      opened_at: opened.toISOString(),
      closed_at: closed?.toISOString() ?? null,
      entry_price: entry,
      exit_price: exit,
      size,
      multiplier,
      fees,
      currency: form.currency.trim().toUpperCase(),
      realized_pnl_override: override,
      strategy: form.strategy?.trim() || null,
      notes: form.notes?.trim() || null,
      tags: form.tags,
    };
    setSaving(true);
    try { await onSave(payload); } catch (cause) { setError(cause instanceof Error ? cause.message : 'Trade could not be saved.'); }
    finally { setSaving(false); }
  }

  return (
    <form className="trade-form" onSubmit={submit} noValidate>
      <div className="form-heading"><div><p className="eyebrow">JOURNAL ENTRY</p><h2>{initialValue ? 'Edit position' : 'Record a position'}</h2></div><button type="button" className="icon-button" aria-label="Close form" onClick={onCancel}>×</button></div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="form-grid">
        <label className="field span-2">Instrument<input required maxLength={40} value={form.instrument} onChange={(e) => set('instrument', e.target.value)} placeholder="e.g. EURUSD" autoComplete="off" /></label>
        <label className="field">Market<select value={form.market ?? ''} onChange={(e) => set('market', (e.target.value || null) as TradeInput['market'])}><option value="">Other / not set</option><option value="equities">Equities</option><option value="forex">Forex</option><option value="futures">Futures</option><option value="options">Options</option><option value="crypto">Crypto</option><option value="other">Other</option></select></label>
        <label className="field">Direction<select value={form.direction} onChange={(e) => set('direction', e.target.value as TradeInput['direction'])}><option value="long">Long</option><option value="short">Short</option></select></label>
        <label className="field">Opened<input type="datetime-local" required value={form.opened_at} onChange={(e) => set('opened_at', e.target.value)} /></label>
        <label className="field">Closed <span className="field-hint">Leave blank while open</span><input type="datetime-local" value={form.closed_at?.slice(0, 16) ?? ''} onChange={(e) => set('closed_at', e.target.value ? e.target.value : null)} /></label>
        <label className="field">Entry price<input inputMode="decimal" required value={form.entry_price} onChange={(e) => set('entry_price', e.target.value)} placeholder="0.00" /></label>
        <label className="field">Exit price<input inputMode="decimal" value={form.exit_price ?? ''} onChange={(e) => set('exit_price', e.target.value || null)} placeholder={form.closed_at ? 'Required when closed' : '—'} /></label>
        <label className="field">Size<input inputMode="decimal" required value={form.size} onChange={(e) => set('size', e.target.value)} placeholder="0.00" /></label>
        <label className="field">Multiplier<input inputMode="decimal" required value={form.multiplier} onChange={(e) => set('multiplier', e.target.value)} /></label>
        <label className="field">Fees<input inputMode="decimal" required value={form.fees} onChange={(e) => set('fees', e.target.value)} /></label>
        <label className="field">Currency<input required maxLength={3} value={form.currency} onChange={(e) => set('currency', e.target.value)} placeholder="USD" /></label>
        <label className="field span-2">Realized P&amp;L override <span className="field-hint">Optional gross P&amp;L for complex products</span><input inputMode="decimal" value={form.realized_pnl_override ?? ''} onChange={(e) => set('realized_pnl_override', e.target.value || null)} placeholder="Leave blank to calculate" /></label>
        <label className="field span-2">Strategy<input maxLength={120} value={form.strategy ?? ''} onChange={(e) => set('strategy', e.target.value)} placeholder="Optional" /></label>
        <label className="field span-2">Notes<textarea rows={3} maxLength={4000} value={form.notes ?? ''} onChange={(e) => set('notes', e.target.value)} placeholder="What did you notice?" /></label>
      </div>
      <div className="form-actions"><button type="button" className="button button-quiet" onClick={onCancel}>Cancel</button><button type="submit" className="button button-primary" disabled={saving}>{saving ? 'Saving…' : initialValue ? 'Save changes' : 'Save position'}</button></div>
    </form>
  );
}
