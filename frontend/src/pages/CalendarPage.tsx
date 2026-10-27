import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { getCalendar } from '../api/client';
import { formatCurrencyDecimal } from '../api/decimal';
import type { CalendarMonth } from '../api/types';

const empty: CalendarMonth = { year: new Date().getFullYear(), month: new Date().getMonth() + 1, days: [] };
const monthName = new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' });

export function CalendarPage() {
  const [month, setMonth] = useState({ year: empty.year, month: empty.month });
  const [calendar, setCalendar] = useState<CalendarMonth>(empty);
  const [instrument, setInstrument] = useState('');
  const [currency, setCurrency] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const firstDay = new Date(month.year, month.month - 1, 1);
  const daysInMonth = new Date(month.year, month.month, 0).getDate();
  const offsets = (firstDay.getDay() + 6) % 7;
  const cells = useMemo(() => [...Array(offsets).fill(null), ...Array.from({ length: daysInMonth }, (_, index) => index + 1)], [offsets, daysInMonth]);

  async function load() {
    setBusy(true); setError('');
    try { setCalendar(await getCalendar(month.year, month.month, { instrument: instrument.trim() || undefined, currency: currency.trim().toUpperCase() || undefined })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Calendar could not be loaded.'); }
    finally { setBusy(false); }
  }
  useEffect(() => { void load(); }, [month.year, month.month]);
  const byDate = new Map<string, CalendarMonth['days']>();
  for (const day of calendar.days) byDate.set(day.date, [...(byDate.get(day.date) ?? []), day]);
  const shiftMonth = (delta: number) => {
    const date = new Date(month.year, month.month - 1 + delta, 1);
    setMonth({ year: date.getFullYear(), month: date.getMonth() + 1 });
  };

  return <>
    <div className="page-heading"><div><p className="eyebrow">CLOSE DATE IN YOUR LOCAL TIME ZONE</p><h1>Calendar</h1><p className="page-subtitle">Closed-position results by day. When multiple currencies trade on one day, each is shown separately.</p></div></div>
    <section className="calendar-panel" aria-label="Trading calendar">
      <div className="calendar-toolbar"><button className="icon-button" aria-label="Previous month" onClick={() => shiftMonth(-1)}><ChevronLeft size={18} /></button><h2>{monthName.format(firstDay)}</h2><button className="icon-button" aria-label="Next month" onClick={() => shiftMonth(1)}><ChevronRight size={18} /></button><button className="button button-quiet" onClick={() => { const now = new Date(); setMonth({ year: now.getFullYear(), month: now.getMonth() + 1 }); }}>Today</button></div>
      <form className="calendar-filters" onSubmit={(event) => { event.preventDefault(); void load(); }}><label className="field">Instrument<input aria-label="Calendar instrument filter" value={instrument} onChange={(event) => setInstrument(event.target.value)} placeholder="All instruments" /></label><label className="field">Currency<input aria-label="Calendar currency filter" maxLength={3} value={currency} onChange={(event) => setCurrency(event.target.value)} placeholder="All currencies" /></label><button className="button button-primary" disabled={busy}>{busy ? 'Updating…' : 'Filter'}</button></form>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="calendar-grid" role="grid" aria-label={monthName.format(firstDay)}>{['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map((day) => <div className="calendar-weekday" role="columnheader" key={day}>{day.slice(0, 3)}</div>)}{cells.map((day, index) => {
        const key = day ? `${month.year}-${String(month.month).padStart(2, '0')}-${String(day).padStart(2, '0')}` : `blank-${index}`;
        const summaries = day ? byDate.get(key) ?? [] : [];
        return <div className={`calendar-day ${day ? '' : 'calendar-day-empty'}`} role="gridcell" aria-label={day ? `${key}, ${summaries.length} result groups` : undefined} key={key}>{day && <><span className="calendar-day-number">{day}</span>{summaries.map((result) => <div className={`calendar-result ${result.net_pnl.startsWith('-') ? 'negative' : 'positive'}`} key={result.currency}><strong>{formatCurrencyDecimal(result.net_pnl, result.currency)}</strong><span>{result.currency} · {result.closed_count} {result.closed_count === 1 ? 'trade' : 'trades'}</span></div>)}</>}</div>;
      })}</div>
      <p className="calendar-footnote">No result on a day means no recorded closed trades matched these filters.</p>
    </section>
  </>;
}
