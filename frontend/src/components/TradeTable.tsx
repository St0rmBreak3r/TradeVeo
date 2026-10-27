import { useMemo, useState } from 'react';
import { ArrowDownUp, Pencil, Trash2 } from 'lucide-react';
import type { Trade } from '../api/types';
import { compareDecimal, formatCurrencyDecimal } from '../api/decimal';

function money(value: string | null, currency: string) {
  if (value === null) return 'Open';
  return formatCurrencyDecimal(value, currency);
}

export function TradeTable({ trades, onEdit, onDelete }: {
  trades: Trade[];
  onEdit: (trade: Trade) => void;
  onDelete: (trade: Trade) => void;
}) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [sort, setSortField] = useState<'opened_at' | 'instrument' | 'net_pnl'>('opened_at');
  const [ascending, setAscending] = useState(false);
  const filtered = useMemo(() => trades.filter((trade) => {
    const matches = `${trade.instrument} ${trade.strategy ?? ''} ${trade.notes ?? ''} ${trade.currency}`.toLowerCase().includes(query.toLowerCase());
    return matches && (status === 'all' || (status === 'open' ? trade.closed_at === null : trade.closed_at !== null));
  }).sort((a, b) => {
    const av = sort === 'net_pnl' ? a.net_pnl : a[sort];
    const bv = sort === 'net_pnl' ? b.net_pnl : b[sort];
    const result = sort === 'net_pnl' && av !== null && bv !== null
      ? compareDecimal(av, bv)
      : av === null ? 1 : bv === null ? -1 : String(av).localeCompare(String(bv));
    return ascending ? result : -result;
  }), [trades, query, status, sort, ascending]);
  const setSort = (value: 'opened_at' | 'instrument' | 'net_pnl') => { setAscending(sort === value ? !ascending : false); setSortField(value); };

  return (
    <section className="table-panel" aria-label="Trade journal">
      <div className="table-toolbar"><label className="search-field"><span className="sr-only">Search trades</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search instrument, strategy, notes…" /></label><label className="sr-only" htmlFor="trade-status">Filter by status</label><select id="trade-status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">All positions</option><option value="open">Open</option><option value="closed">Closed</option></select><span className="result-count">{filtered.length} {filtered.length === 1 ? 'position' : 'positions'}</span></div>
      {filtered.length === 0 ? <div className="empty-state"><span className="empty-icon"><ArrowDownUp size={20} /></span><h3>{trades.length ? 'No matching positions' : 'Your journal starts here'}</h3><p>{trades.length ? 'Try a different search or status filter.' : 'Record a trade to begin reviewing your decisions.'}</p></div> : (
        <div className="table-scroll"><table><thead><tr>
          <th><button className="sort-button" onClick={() => setSort('opened_at')}>Opened <ArrowDownUp size={13} /></button></th>
          <th><button className="sort-button" onClick={() => setSort('instrument')}>Position <ArrowDownUp size={13} /></button></th>
          <th>Side</th><th>Entry / exit</th><th>Size</th>
          <th><button className="sort-button" onClick={() => setSort('net_pnl')}>Net P&amp;L <ArrowDownUp size={13} /></button></th><th>Actions</th>
        </tr></thead><tbody>{filtered.map((trade) => {
          const positive = trade.net_pnl !== null && compareDecimal(trade.net_pnl, '0') > 0;
          const negative = trade.net_pnl !== null && compareDecimal(trade.net_pnl, '0') < 0;
          return <tr key={trade.id}>
            <td className="mono">{new Date(trade.opened_at).toLocaleDateString()}</td>
            <td><strong>{trade.instrument}</strong><span className="cell-subtitle">{trade.strategy || trade.market || 'Uncategorized'}</span></td>
            <td><span className={`side-pill ${trade.direction}`}>{trade.direction}</span></td>
            <td className="mono">{trade.entry_price}<span className="cell-subtitle">{trade.exit_price ?? 'Still open'}</span></td>
            <td className="mono">{trade.size}</td>
            <td className={`mono pnl ${positive ? 'positive' : negative ? 'negative' : ''}`}>{money(trade.net_pnl, trade.currency)}</td>
            <td><div className="row-actions"><button className="icon-button" aria-label={`Edit ${trade.instrument}`} onClick={() => onEdit(trade)}><Pencil size={15} /></button><button className="icon-button danger" aria-label={`Delete ${trade.instrument}`} onClick={() => onDelete(trade)}><Trash2 size={15} /></button></div></td>
          </tr>;
        })}</tbody></table></div>
      )}
    </section>
  );
}
