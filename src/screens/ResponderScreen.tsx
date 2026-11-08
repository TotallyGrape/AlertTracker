import { useEffect, useMemo, useState } from 'react';
import { useSpacetimeDB, useTable } from 'spacetimedb/react';
import { tables } from '../module_bindings';
import { ScreenIntro } from '../components/WorkspaceParts';
import { REQUEST_LIFETIME_MS } from '../residentPins';

type Level = 'critical' | 'active_threat' | 'caution' | 'informational';
type Evidence = { id: string; source: string; name: string; description: string; observed_at?: string; priority?: { score: number; basis?: string } };
type Issue = { id: string; title: string; summary: string; level: Level; ai_status: string; model?: string; uncertainty: string; evidence: Evidence[];
  evidence_ids: string[]; evidence_quotes: { id: string; quote: string }[]; evidence_count: number; generated_at: string; expires_at: string; latitude?: number; longitude?: number;
  measured_trends: { id: string; direction: string; change: number; unit: string; samples: number }[];
  rule_reasons: string[]; rule_minimum: string; rule_maximum: string; guardrail_adjusted?: boolean; verification: string };
const labels: Record<Level, string> = { critical: 'Critical', active_threat: 'Active threat', caution: 'Caution', informational: 'Informational' };
const rank: Record<Level, number> = { critical: 3, active_threat: 2, caution: 1, informational: 0 };

function ConnectedIssues() {
  const { isActive } = useSpacetimeDB();
  const [rows, ready] = useTable(tables.issueCard);
  const [requests] = useTable(tables.myReports);
  const [clock, setClock] = useState(Date.now());
  const [filter, setFilter] = useState('all');
  const [limit, setLimit] = useState(40);
  useEffect(() => { const timer=setInterval(()=>setClock(Date.now()),15000); return ()=>clearInterval(timer); },[]);
  const issues=useMemo(()=>rows.flatMap(row=>{
    try { const issue=JSON.parse(row.payloadJson) as Issue;
      return issue.level in labels && Date.parse(row.expiresAt)>clock && Array.isArray(issue.evidence) ? [issue] : [];
    } catch { return []; }
  }).sort((a,b)=>rank[b.level]-rank[a.level] || a.id.localeCompare(b.id)),[rows,clock]);
  const visible=issues.filter(issue=>filter==='all' || (filter==='pending' ? issue.ai_status!=='complete' : issue.ai_status==='complete' && issue.level===filter));
  const personal=requests.filter(row=>row.status==='submitted' && Number(row.createdAt.microsSinceUnixEpoch/1000n)+REQUEST_LIFETIME_MS>clock);
  return <>
    <div className="issue-toolbar" role="group" aria-label="Filter issue cards">
      {['all',...Object.keys(labels),'pending'].map(level=><button key={level} className="glass-button glass-button--small" aria-pressed={filter===level} onClick={()=>{setFilter(level);setLimit(40);}}>
        {level==='all'?'All issues':level==='pending'?'Awaiting AI':labels[level as Level]} ({level==='all'?issues.length:level==='pending'?issues.filter(issue=>issue.ai_status!=='complete').length:issues.filter(issue=>issue.ai_status==='complete' && issue.level===level).length})
      </button>)}
    </div>
    <p className="screen-note" role="status">{!isActive?'Disconnected — displayed assessments may be stale.':!ready?'Loading shared issue cards…':`${issues.filter(issue=>issue.ai_status==='complete').length} Nemotron assessments · ${issues.filter(issue=>issue.ai_status!=='complete').length} groups awaiting an accepted assessment`}</p>
    <p className="screen-note">Rules screen fresh public pins across the region, excluding facilities. Nemotron synthesizes related evidence and suggests a level. Nearby reports may describe different events or duplicate the same event. These cards are not dispatch instructions or verified emergencies.</p>
    <div className="issue-scroll" role="region" aria-label="Current issue cards" tabIndex={0}>
      {ready && visible.length===0 && <div className="panel glass issue-card"><h2>No current cards in this category</h2><p>Analysis may still be loading, evidence may be stale, or nothing matches this filter. Missing cards do not establish safety.</p></div>}
      {visible.slice(0,limit).map(issue=><article key={issue.id} className={`panel glass issue-card issue-${issue.level}`}>
        <div className="issue-card-heading"><span className={`issue-level issue-level-${issue.level}`}>{issue.ai_status==='complete'?labels[issue.level]:'Awaiting AI assessment'}</span><span>{issue.ai_status==='complete'?'Nemotron assessment':`Rule floor: ${labels[issue.level]}`}</span></div>
        <h2>{issue.title}</h2><p>{issue.summary}</p>
        <p className="issue-meta">{issue.latitude!=null && issue.longitude!=null?`${issue.latitude.toFixed(3)}, ${issue.longitude.toFixed(3)}`:'Location unknown'} · {issue.evidence_count} records · {new Date(issue.generated_at).toLocaleTimeString()}</p>
        <p><strong>Uncertainty:</strong> {issue.uncertainty}</p>
        <details><summary>Evidence and guardrails</summary>
          <p>{issue.verification}. {issue.model?`Model: ${issue.model}.`:''} Rule range: {issue.rule_minimum.replace(/_/g,' ')} to {issue.rule_maximum.replace(/_/g,' ')}.{issue.guardrail_adjusted?' The model level was adjusted to stay within the evidence limits.':''}</p>
          <ul>{issue.rule_reasons.map((reason,index)=><li key={index}>{reason}</li>)}</ul>
          {issue.measured_trends.length>0 && <ul>{issue.measured_trends.map(trend=><li key={trend.id}>{trend.direction}: {trend.change} {trend.unit} across {trend.samples} measurements. Measurement trend only; not proof of danger.</li>)}</ul>}
          <p>Showing {issue.evidence.length} selected records of {issue.evidence_count}. Evidence citations identify supporting records, not independent confirmation.</p>
          {issue.evidence_quotes?.map((quote,index)=><blockquote key={index}>“{quote.quote}” <small>— {quote.id}</small></blockquote>)}
          <ul className="issue-evidence">{issue.evidence.map(evidence=><li key={evidence.id}><strong>{evidence.name}</strong> · {evidence.source}{issue.evidence_ids.includes(evidence.id)?' · cited by Nemotron':''}
            {evidence.priority && <span> · Priority {evidence.priority.score}/10 ({evidence.priority.basis?.startsWith('nemotron:')?'Nemotron':'rules'})</span>}
            <p>{evidence.description}</p><small>{evidence.observed_at?new Date(evidence.observed_at).toLocaleString():'Event time unknown'} · {evidence.id}</small>
          </li>)}</ul>
        </details>
      </article>)}
      {visible.length>limit && <button className="glass-button" onClick={()=>setLimit(value=>value+40)}>Show more ({visible.length-limit} remaining)</button>}
    </div>
    <h2 className="private-issue-heading">Your private assistance requests ({personal.length})</h2>
    <p className="screen-note">Kept separate from shared public analysis. Other browser identities cannot see these requests.</p>
    <div className="issue-scroll issue-scroll-private" role="region" aria-label="Your private request cards" tabIndex={0}>
      {personal.length===0?<p className="screen-note">No active private requests.</p>:personal.map(request=><article className="panel glass issue-card" key={String(request.id)}>
        <h2>{request.name}</h2><p>{request.description}</p><p>{request.peopleAffected} people · {request.helpType.replace(/_/g,' ')} · {request.status}</p>
        <p>{request.aiStatus==='complete'?`Nemotron suggested urgency: ${request.aiUrgency}. ${request.aiSummary}`:`AI assessment: ${request.aiStatus}`}</p><small>Unverified request. No assignment or dispatch has occurred.</small>
      </article>)}
    </div>
  </>;
}
export function ResponderScreen() {
  return <>
    <ScreenIntro eyebrow="EVIDENCE INTO ACTION" title="Current issues, in context." description="Nemotron combines current public evidence into reviewable issue cards, with rule-based limits and the original reports attached." />
    {import.meta.env.VITE_SPACETIMEDB_ENABLED==='true'?<ConnectedIssues/>:<p className="screen-note">Connect Spacetime to receive shared issue cards.</p>}
  </>;
}
