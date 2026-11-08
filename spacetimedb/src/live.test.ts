import { expect, it } from 'vitest';
import { DbConnection, tables } from '../../src/module_bindings';

const live = process.env.VERIFY_LIVE === 'true';
function connect(): Promise<DbConnection> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Connection timeout')), 30000);
    DbConnection.builder().withUri('wss://maincloud.spacetimedb.com').withDatabaseName('texas-response-zl8x2')
      .onConnect(conn => { clearTimeout(timer); resolve(conn); })
      .onConnectError((_ctx, error) => { clearTimeout(timer); reject(error); }).build();
  });
}
function subscribe(conn: DbConnection) {
  return new Promise<void>((resolve, reject) => conn.subscriptionBuilder().onApplied(() => resolve())
    .onError(() => reject(new Error('Subscription failed'))).subscribe([tables.incident, tables.sourceHealth, tables.myReports]));
}
it.skipIf(!live)('Maincloud streams feeds and isolates resident reports between identities', async () => {
  const alice = await connect();
  const bob = await connect();
  try {
    await Promise.all([subscribe(alice), subscribe(bob)]);
    expect([...alice.db.incident.iter()].length).toBeGreaterThan(100);
    expect([...alice.db.sourceHealth.iter()].length).toBeGreaterThanOrEqual(15);
    await alice.reducers.submitReport({ name: 'Integration test — withdrawn', description: 'Automated setup verification, no assistance needed.', latitude: 32.7767, longitude: -96.7970 });
    const report = [...alice.db.myReports.iter()][0];
    expect(report).toBeDefined();
    expect([...bob.db.myReports.iter()]).toHaveLength(0);
    await expect(bob.reducers.withdrawReport({ id: report.id })).rejects.toThrow();
    await alice.reducers.withdrawReport({ id: report.id });
    expect(alice.db.myReports.id.find(report.id)?.status).toBe('withdrawn');
    await new Promise<void>((resolve, reject) => {
      alice.subscriptionBuilder().onApplied(() => reject(new Error('Private table was exposed')))
        .onError(() => resolve()).subscribe('SELECT * FROM resident_report');
    });
  } finally { alice.disconnect(); bob.disconnect(); }
}, 90000);

it.skipIf(!live)('structured private request receives a saved Nemotron assessment', async () => {
  const alice = await connect(), bob = await connect();
  let reportId: bigint | undefined;
  try {
    await Promise.all([subscribe(alice), subscribe(bob)]);
    await alice.reducers.submitAssistanceRequest({ name: 'SIMULATED integration test: shelter request',
      description: 'SIMULATED DEMO ONLY. Two people need a place to stay tonight after leaving their home. No injury or immediate threat is reported.',
      helpType: 'shelter', peopleAffected: 2, locationText: 'SIMULATED Dallas landmark', latitude: 32.7767, longitude: -96.7970 });
    const report = [...alice.db.myReports.iter()][0];
    reportId = report.id;
    expect(report.peopleAffected).toBe(2);
    expect([...bob.db.myReports.iter()]).toHaveLength(0);
    const deadline = Date.now() + 150000;
    while (Date.now() < deadline && !['complete', 'failed'].includes(alice.db.myReports.id.find(reportId)?.aiStatus ?? ''))
      await new Promise(resolve => setTimeout(resolve, 1000));
    const saved = alice.db.myReports.id.find(reportId)!;
    expect(saved.aiStatus).toBe('complete');
    expect(saved.aiSummary.length).toBeGreaterThan(0);
    expect(['low', 'medium', 'high', 'critical']).toContain(saved.aiUrgency);
    expect(saved.aiModel).toContain('nemotron');
    expect(saved.status).toBe('submitted');
    expect([...bob.db.myReports.iter()]).toHaveLength(0);
    console.log('Resident AI verified:', saved.aiStatus, saved.aiUrgency, saved.aiModel);
  } finally {
    if (reportId !== undefined) await alice.reducers.withdrawReport({ id: reportId }).catch(() => {});
    alice.disconnect(); bob.disconnect();
  }
}, 180000);
