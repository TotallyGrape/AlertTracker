import { useState, type FormEvent } from 'react';
import { useSpacetimeDB, useTable } from 'spacetimedb/react';
import { DbConnection, tables } from '../module_bindings';

const aiLabels: Record<string, string> = { pending: 'Queued', processing: 'Processing', complete: 'Complete', failed: 'Unavailable — request remains saved', cancelled: 'Cancelled', not_requested: 'Not requested for this older report' };
export function ResidentReports() {
  const { isActive, getConnection } = useSpacetimeDB();
  const [reports, ready] = useTable(tables.myReports);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [locating, setLocating] = useState(false);
  const [coordinates, setCoordinates] = useState({ latitude: '', longitude: '' });
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget, data = new FormData(form);
    const conn = getConnection() as DbConnection | null;
    if (!conn || !isActive) return;
    setBusy(true); setMessage('');
    try {
      await conn.reducers.submitAssistanceRequest({ name: String(data.get('name')), description: String(data.get('description')),
        helpType: String(data.get('helpType')), peopleAffected: Number(data.get('peopleAffected')), locationText: String(data.get('locationText')),
        latitude: Number(data.get('latitude')), longitude: Number(data.get('longitude')) });
      form.reset(); setCoordinates({ latitude: '', longitude: '' });
      setMessage('Request saved. AI assessment queued; human review and dispatch have not occurred.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to submit. Check your requests before retrying.'); }
    finally { setBusy(false); }
  }
  return <section className="report-panel glass glass-pop-in">
    <h2>Your assistance requests</h2><p>Your details and exact location stay private to this browser identity. Anonymous counts and help types from multiple reporters contribute to approximate-area pins and shared AI concerns. For this hackathon, those reported needs are assumed accurate, not independently verified. Active requests expire after 24 hours. No emergency services are dispatched.</p>
    <form onSubmit={submit}>
      <label>What do you need?<input name="name" required maxLength={160} /></label>
      <label>Type of assistance<select name="helpType" required defaultValue=""><option value="" disabled>Select help needed</option>
        <option value="evacuation">Evacuation</option><option value="medical">Medical assistance</option><option value="shelter">Shelter</option>
        <option value="food_water">Food or water</option><option value="transport">Transportation</option><option value="accessibility">Accessibility assistance</option>
        <option value="welfare">Welfare check</option><option value="other">Other</option></select></label>
      <label>Number of people affected<input name="peopleAffected" type="number" min="1" max="1000" step="1" defaultValue="1" required /></label>
      <label>Relevant details<textarea name="description" required maxLength={3000} placeholder="What is happening, what help is needed, and any time-sensitive details. Avoid unnecessary personal or contact information." /></label>
      <label>Address or nearby landmark<input name="locationText" required maxLength={300} placeholder="Street address, intersection, or recognizable landmark" /></label>
      <button className="glass-button glass-button--small" type="button" disabled={locating} onClick={() => {
        if (!navigator.geolocation) { setMessage('Location unavailable. Enter coordinates manually.'); return; }
        setLocating(true);
        navigator.geolocation.getCurrentPosition(position => {
          setCoordinates({ latitude: position.coords.latitude.toFixed(6), longitude: position.coords.longitude.toFixed(6) });
          setLocating(false); setMessage('Location filled. Confirm it matches where help is needed.');
        }, () => { setLocating(false); setMessage('Could not obtain location. Enter coordinates manually.'); }, { timeout: 10000, maximumAge: 60000 });
      }}>{locating ? 'Finding location…' : 'Use my location'}</button>
      <div className="report-coordinates"><label>Latitude<input name="latitude" type="number" step="any" min="32.45" max="33.3" placeholder="32.7767" value={coordinates.latitude} onChange={e => setCoordinates({ ...coordinates, latitude: e.target.value })} required /></label>
        <label>Longitude<input name="longitude" type="number" step="any" min="-97.65" max="-96.25" placeholder="-96.7970" value={coordinates.longitude} onChange={e => setCoordinates({ ...coordinates, longitude: e.target.value })} required /></label></div>
      <p>Use the location where help is needed, within Greater Dallas. Request text and people count are sent to NVIDIA for AI triage. The separate address, coordinates and account identity are excluded from the AI payload.</p>
      <button className="glass-button glass-button--primary" type="submit" disabled={!isActive || busy}>{busy ? 'Saving…' : 'Submit assistance request'}</button>
    </form>
    <p role="status">{message || (!isActive ? 'Connect to submit a request.' : '')}</p>
    {!ready ? <p>Loading your requests…</p> : reports.length === 0 ? <p>No requests yet.</p> : <ul className="resident-request-list">{[...reports].sort((a, b) => Number(b.createdAt.microsSinceUnixEpoch-a.createdAt.microsSinceUnixEpoch)).map(report => <li key={String(report.id)}>
      <strong>{report.name}</strong><p><strong>Request status:</strong> {report.status === 'submitted' ? 'Submitted — awaiting human review' : report.status}</p>
      <p>{report.helpType.replace(/_/g, ' ')} · {report.peopleAffected} {report.peopleAffected === 1 ? 'person' : 'people'} · {new Date(Number(report.createdAt.microsSinceUnixEpoch / 1000n)).toLocaleString()}</p>
      <p>{report.locationText || 'Coordinates supplied'} · {report.latitude.toFixed(5)}, {report.longitude.toFixed(5)}</p><p>{report.description}</p>
      <div className="resident-ai-assessment" aria-live="polite"><strong>AI assessment: {aiLabels[report.aiStatus] ?? report.aiStatus}</strong>
        {report.aiStatus === 'complete' && <><p><strong>Suggested urgency: {report.aiUrgency}</strong> · Unverified; requires human review</p>
          <p>{report.aiSummary}</p><p>{(() => { try { return (JSON.parse(report.aiReasons) as string[]).join(' · '); } catch { return ''; } })()}</p>
          {report.aiEvidence && <blockquote>Reported evidence: “{report.aiEvidence}”</blockquote>}
          <small>Assessed by {report.aiModel}. This does not confirm danger or mean help has been assigned.</small></>}
      </div>
      {report.status === 'submitted' && <button className="glass-button glass-button--small" disabled={!isActive || busy} onClick={async () => {
        setBusy(true);
        try { await (getConnection() as DbConnection).reducers.withdrawReport({ id: report.id }); }
        catch (error) { setMessage(String(error)); }
        finally { setBusy(false); }
      }}>Withdraw</button>}
    </li>)}</ul>}
  </section>;
}
