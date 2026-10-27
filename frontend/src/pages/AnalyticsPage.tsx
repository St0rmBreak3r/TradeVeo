import { useEffect, useState } from 'react';
import { getAnalyticsSummary } from '../api/client';
import { formatCurrencyDecimal } from '../api/decimal';
import type { AnalyticsSummary } from '../api/types';

const empty: AnalyticsSummary = { currencies: [], equity: [], open_count: 0 };

export function AnalyticsPage() {
  const [summary, setSummary] = useState(empty);
  const [instrument, setInstrument] = useState('');
  const [strategy, setStrategy] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setBusy(true);
    setError('');
    try {
      setSummary(await getAnalyticsSummary({
        instrument: instrument.trim() || undefined,
        strategy: strategy.trim() || undefined,
        from: from ? `${from}T00:00:00Z` : undefined,
        to: to ? `${to}T23:59:59Z` : undefined,
      }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Analytics could not be loaded.');
    } finally { setBusy(false); }
  }
  useEffect(() => { void load(); }, []);

  return <>
    <div className="page-heading"><div><p className="eyebrow">MEASURE WHAT YOU CAN REVIEW</p><h1>Analytics</h1><p className="page-subtitle">Realized results stay grouped by currency. Open positions are not counted as wins or losses.</p></div></div>
    <form className="filter-panel" onSubmit={(event) => { event.preventDefault(); void load(); }} aria-label="Analytics filters">
      <label className="field">From<input aria-label="From date" type="date" value={from} onChange={(event) => setFrom(event.target.value)} /></label>
      <label className="field">To<input aria-label="To date" type="date" value={to} onChange={(event) => setTo(event.target.value)} /></label>
      <label className="field">Instrument<input aria-label="Instrument filter" value={instrument} onChange={(event) => setInstrument(event.target.value)} placeholder="All instruments" /></label>
      <label className="field">Strategy<input aria-label="Strategy filter" value={strategy} onChange={(event) => setStrategy(event.target.value)} placeholder="All strategies" /></label>
      <button className="button button-primary" type="submit" disabled={busy}>{busy ? 'Updating…' : 'Apply filters'}</button>
    </form>
    {error && <p className="form-error" role="alert">{error}</p>}
    <section className="section-block" aria-live="polite">
      <div className="section-heading"><div><p className="eyebrow">CURRENCY-SEGREGATED</p><h2>Performance summary</h2></div><span className="section-meta">{summary.open_count} open positions excluded</span></div>
      {summary.currencies.length ? <div className="currency-results">{summary.currencies.map((item) => <article className="currency-card" key={item.currency}>
        <div className="currency-heading"><span>{item.currency}</span><span className="currency-trades">{item.closed_count} closed</span></div>
        <p className={`currency-pnl ${item.net_pnl.startsWith('-') ? 'negative' : 'positive'}`}>{formatCurrencyDecimal(item.net_pnl, item.currency)}</p>
        <div className="currency-foot"><span>Win rate</span><span>{item.win_rate === null ? '—' : `${(Number(item.win_rate) * 100).toFixed(1)}%`}</span></div>
        <dl className="stats-list">
          <div><dt>Wins / losses / flat</dt><dd>{item.wins} / {item.losses} / {item.breakeven}</dd></div>
          <div><dt>Average win</dt><dd>{item.average_win === null ? '—' : formatCurrencyDecimal(item.average_win, item.currency)}</dd></div>
          <div><dt>Average loss</dt><dd>{item.average_loss === null ? '—' : formatCurrencyDecimal(item.average_loss, item.currency)}</dd></div>
          <div><dt>Profit factor</dt><dd>{item.profit_factor ?? 'Undefined'}</dd></div>
        </dl>
      </article>)}</div> : <div className="empty-state"><h2>No closed positions in this view</h2><p>Close a position or adjust the filters to see realized performance.</p></div>}
    </section>
    {summary.equity.length > 0 && <section className="section-block"><div className="section-heading"><div><p className="eyebrow">CUMULATIVE REALIZED P&amp;L</p><h2>Equity timeline</h2></div><span className="section-meta">Separate series for each currency</span></div>
      <div className="table-panel table-scroll"><table><caption className="sr-only">Cumulative realized P&amp;L by close time and currency</caption><thead><tr><th scope="col">Closed</th><th scope="col">Currency</th><th scope="col">Trade P&amp;L</th><th scope="col">Running total</th></tr></thead><tbody>{summary.equity.map((point, index) => <tr key={`${point.currency}-${point.at}-${index}`}><td>{new Date(point.at).toLocaleString()}</td><td>{point.currency}</td><td>{formatCurrencyDecimal(point.net_pnl, point.currency)}</td><td>{formatCurrencyDecimal(point.cumulative_pnl, point.currency)}</td></tr>)}</tbody></table></div>
    </section>}
  </>;
}
