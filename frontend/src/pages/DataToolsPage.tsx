import { useEffect, useState } from 'react';
import { commitImport, createBackup, exportCsv, listBackups, previewImport, restoreBackup } from '../api/client';
import type { BackupInfo, ImportPreview } from '../api/client';

export function DataToolsPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  async function loadBackups() { try { setBackups(await listBackups()); } catch (cause) { setError(cause instanceof Error ? cause.message : 'Backup list unavailable.'); } }
  useEffect(() => { void loadBackups(); }, []);
  async function handlePreview() {
    if (!file) return;
    setBusy(true); setError(''); setNotice('');
    try { setPreview(await previewImport(file)); } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not preview CSV.'); }
    finally { setBusy(false); }
  }
  async function handleImport() {
    if (!preview || !window.confirm(`Import ${preview.valid_count} validated rows? Invalid rows will be skipped and reported.`)) return;
    setBusy(true); setError('');
    try { const result = await commitImport(preview.preview_token); setNotice(`Imported ${result.created} positions; skipped ${result.skipped_invalid} invalid rows.`); setPreview(null); setFile(null); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Import failed. Preview the CSV again.'); }
    finally { setBusy(false); }
  }
  async function handleExport() {
    setBusy(true); setError('');
    try { const blob = await exportCsv(); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'tryedveo-trades.csv'; anchor.click(); URL.revokeObjectURL(url); setNotice('CSV export downloaded.'); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Export failed.'); }
    finally { setBusy(false); }
  }
  async function handleBackup() {
    setBusy(true); setError('');
    try { const info = await createBackup(); setNotice(`Backup created with ${info.trade_count} positions.`); await loadBackups(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Backup failed.'); }
    finally { setBusy(false); }
  }
  async function handleRestore(backup: BackupInfo) {
    if (!window.confirm(`Restore ${backup.trade_count} positions from ${new Date(backup.created_at).toLocaleString()}? Current data will first be backed up automatically.`)) return;
    setBusy(true); setError('');
    try { const result = await restoreBackup(backup.backup_id); setNotice(`Restored ${result.restored_count} positions. A pre-restore backup was also saved.`); await loadBackups(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Restore failed.'); }
    finally { setBusy(false); }
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">YOUR DATA, YOUR DEVICE</p><h1>Import &amp; backup</h1><p className="page-subtitle">CSV is the portable journal format. Backups are private ZIP snapshots saved locally.</p></div></div>
    {error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="privacy-note" role="status">{notice}</p>}
    <div className="data-tools-grid">
      <section className="tool-card"><p className="eyebrow">PORTABLE FORMAT</p><h2>CSV</h2><p>Export your full journal or preview a canonical TRYEDVEO CSV before importing. Import requires a second confirmation.</p><button className="button button-primary" disabled={busy} onClick={() => void handleExport()}>Export all trades</button><div className="import-field"><label className="field">Choose CSV file<input type="file" accept=".csv,text/csv" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setPreview(null); }} /></label><button className="button button-quiet" disabled={!file || busy} onClick={() => void handlePreview()}>{busy ? 'Working…' : 'Preview import'}</button></div>
        {preview && <div className="preview-panel"><h3>Import preview</h3><p>{preview.valid_count} valid of {preview.row_count} rows · {preview.errors.length} with errors</p>{preview.errors.length > 0 && <ul>{preview.errors.slice(0, 10).map((item) => <li key={`${item.row}-${item.error}`}>Row {item.row}: {item.error}</li>)}</ul>}{preview.errors.length > 10 && <p>Plus {preview.errors.length - 10} more row errors.</p>}<button className="button button-primary" disabled={busy || preview.valid_count === 0} onClick={() => void handleImport()}>Confirm valid rows</button></div>}
      </section>
      <section className="tool-card"><p className="eyebrow">RECOVERABLE LOCAL SNAPSHOT</p><h2>Backups</h2><p>Restore always creates a fresh pre-restore backup first. Review the selected snapshot and confirm before replacing your journal.</p><button className="button button-primary" disabled={busy} onClick={() => void handleBackup()}>Create backup now</button><h3>Available backups</h3>{backups.length ? <ul className="backup-list">{backups.map((backup) => <li key={backup.backup_id}><div><strong>{new Date(backup.created_at).toLocaleString()}</strong><span>{backup.trade_count} positions · {(backup.size_bytes / 1024).toFixed(1)} KB</span></div><button className="button button-quiet" disabled={busy} onClick={() => void handleRestore(backup)}>Restore</button></li>)}</ul> : <p>No backups yet.</p>}</section>
    </div>
  </>;
}
