import { expect, it } from 'vitest';
import { ConnectionId } from 'spacetimedb';
import { createModuleTestHarness, TestAuth } from 'spacetimedb/server/test-utils';
import spacetimedb, * as exports from './index';

const alice = TestAuth.fromJwtPayload(JSON.stringify({ iss: 'test', sub: 'alice' }), new ConnectionId(1n));
const bob = TestAuth.fromJwtPayload(JSON.stringify({ iss: 'test', sub: 'bob' }), new ConnectionId(2n));
const report = { name: 'Test assistance', description: 'Test only', latitude: 32.8, longitude: -96.8 };

it('keeps reports private to their owner and denies withdrawal by another identity', () => {
  const test = createModuleTestHarness(spacetimedb, exports);
  test.withReducerTx(alice, ctx => exports.submitReport(ctx, report));
  const rows = [...test.db.residentReport.iter()];
  expect(rows).toHaveLength(1);
  expect(exports.myReports(test.viewContext(alice))).toHaveLength(1);
  expect(exports.myReports(test.viewContext(bob))).toHaveLength(0);
  expect(() => test.withReducerTx(bob, ctx => exports.withdrawReport(ctx, { id: rows[0].id }))).toThrow('Not authorized');
  expect(test.db.residentReport.id.find(rows[0].id)?.status).toBe('submitted');
  test.withReducerTx(alice, ctx => exports.withdrawReport(ctx, { id: rows[0].id }));
  expect(test.db.residentReport.id.find(rows[0].id)?.status).toBe('withdrawn');
});

it('rejects invalid regional coordinates and rate limits duplicate submissions', () => {
  const test = createModuleTestHarness(spacetimedb, exports);
  expect(() => test.withReducerTx(alice, ctx => exports.submitReport(ctx, { ...report, latitude: 0 }))).toThrow();
  expect(test.db.residentReport.count()).toBe(0n);
  test.withReducerTx(alice, ctx => exports.submitReport(ctx, report));
  expect(() => test.withReducerTx(alice, ctx => exports.submitReport(ctx, report))).toThrow('30 seconds');
  expect(test.db.residentReport.count()).toBe(1n);
});
