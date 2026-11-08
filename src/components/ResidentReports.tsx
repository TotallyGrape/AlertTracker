import { useState, type FormEvent } from 'react';
import { useSpacetimeDB, useTable } from 'spacetimedb/react';
import { DbConnection, tables } from '../module_bindings';

export function ResidentReports() {
  const { isActive, getConnection } = useSpacetimeDB();
  const [reports, ready] = useTable(tables.myReports);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const conn = getConnection() as DbConnection | null;
    if (!conn || !isActive) return;
    setBusy(true); setMessage('');
    try {
      await conn.reducers.submitReport({ name: String(data.get('name')), description: String(data.get('description')),
        latitude: Number(data.get('latitude')), longitude: Number(data.get('longitude')) });
      form.reset(); setMessage('Saved privately to your requests. This does not contact emergency services.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to submit. Check your requests before retrying.'); }
    finally { setBusy(false); }
  }
  return <section className="report-panel">
    <h2>Your assistance requests</h2><p>Private to this browser identity. Requests are unverified and are not dispatched to emergency services.</p>
    <form onSubmit={submit}>
      <label>What do you need?<input name="name" required maxLength={160} /></label>
      <label>Description<textarea name="description" required maxLength={3000} /></label>
      <div className="report-coordinates"><label>Latitude<input name="latitude" type="number" step="any" min="32.45" max="33.3" placeholder="32.7767" required /></label>
        <label>Longitude<input name="longitude" type="number" step="any" min="-97.65" max="-96.25" placeholder="-96.7970" required /></label></div>
      <button type="submit" disabled={!isActive || busy}>{busy ? 'Saving…' : 'Save request'}</button>
    </form>
    <p role="status">{message || (!isActive ? 'Connect to submit a request.' : '')}</p>
    {!ready ? <p>Loading your requests…</p> : reports.length === 0 ? <p>No requests yet.</p> : <ul>{reports.map(report => <li key={String(report.id)}>
      <strong>{report.name}</strong> · {report.status}<p>{report.description}</p>
      {report.status === 'submitted' && <button disabled={!isActive || busy} onClick={async () => {
        setBusy(true);
        try { await (getConnection() as DbConnection).reducers.withdrawReport({ id: report.id }); }
        catch (error) { setMessage(String(error)); }
        finally { setBusy(false); }
      }}>Withdraw</button>}
    </li>)}</ul>}
  </section>;
}
