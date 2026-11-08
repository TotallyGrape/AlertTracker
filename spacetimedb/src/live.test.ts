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
    expect([...alice.db.sourceHealth.iter()].length).toBe(12);
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
