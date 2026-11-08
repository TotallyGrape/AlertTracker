import { expect, it } from 'vitest';
import { ConnectionId, Timestamp } from 'spacetimedb';
import { residentPins, REQUEST_LIFETIME_MS } from '../../src/residentPins';
import { aggregateCommunity } from './community';
import { createModuleTestHarness, TestAuth } from 'spacetimedb/server/test-utils';
import spacetimedb, * as exports from './index';

const alice = TestAuth.fromJwtPayload(JSON.stringify({ iss: 'test', sub: 'alice' }), new ConnectionId(1n));
const bob = TestAuth.fromJwtPayload(JSON.stringify({ iss: 'test', sub: 'bob' }), new ConnectionId(2n));
const report = { name: 'Test assistance', description: 'Test only', latitude: 32.8, longitude: -96.8 };

it('shares only coarse multi-owner counts, deduplicates an owner and excludes withdrawn/expired requests',()=>{
  const make=(owner:string,extra={})=>({...report,owner:{toHexString:()=>owner},status:'submitted',createdAt:new Timestamp(0n),helpType:'shelter',peopleAffected:2,...extra});
  expect(aggregateCommunity([make('a'),make('a')],1n)).toHaveLength(0);
  const clusters=aggregateCommunity([make('a'),make('b'),make('c',{status:'withdrawn'})],1n);
  expect(clusters).toHaveLength(1);
  expect(clusters[0].report_count).toBe(2);
  expect(Object.keys(clusters[0])).not.toContain('description');
  expect(Object.keys(clusters[0])).not.toContain('owner');
  expect(clusters[0].latitude).not.toBe(report.latitude);
  expect(aggregateCommunity([make('a'),make('b')],86_400_000_000n)).toHaveLength(0);
});

it('renders private report pins until expiry and removes withdrawn pins', () => {
  const row = { ...report, id: 1n, status: 'submitted', createdAt: new Timestamp(1_000_000n), helpType: 'shelter', peopleAffected: 2, aiStatus: 'pending', aiSummary: '', aiUrgency: '' };
  expect(residentPins([row], 1000, true)).toHaveLength(1);
  expect(residentPins([row], 1000+REQUEST_LIFETIME_MS-1, true)).toHaveLength(1);
  expect(residentPins([row], 1000+REQUEST_LIFETIME_MS, true)).toHaveLength(0);
  expect(residentPins([{ ...row, status: 'withdrawn' }], 1000, true)).toHaveLength(0);
});

it('expires stored reports, cancels pending AI and installs only one recurring timer', () => {
  const test = createModuleTestHarness(spacetimedb, exports);
  test.withReducerTx(alice, ctx => exports.submitAssistanceRequest(ctx, { ...report, helpType: 'shelter', peopleAffected: 2, locationText: 'Test landmark' }));
  test.clock.set(new Timestamp(86_400_000_000n));
  test.withReducerTx(alice, ctx => exports.ensureReportExpiry(ctx));
  test.withReducerTx(alice, ctx => exports.ensureReportExpiry(ctx));
  const saved = [...test.db.residentReport.iter()][0];
  expect(saved.status).toBe('expired');
  expect(saved.aiStatus).toBe('cancelled');
  expect(test.db.reportExpiryTimer.count()).toBe(1n);
  expect(exports.myReports(test.viewContext(alice))).toHaveLength(1);
});

it('saves structured assistance requests privately and queues AI without changing review status', () => {
  const test = createModuleTestHarness(spacetimedb, exports);
  test.withReducerTx(alice, ctx => exports.submitAssistanceRequest(ctx, { ...report, helpType: 'evacuation', peopleAffected: 3, locationText: 'Test landmark' }));
  const saved = exports.myReports(test.viewContext(alice))[0];
  expect(saved.helpType).toBe('evacuation');
  expect(saved.peopleAffected).toBe(3);
  expect(saved.aiStatus).toBe('pending');
  expect(saved.status).toBe('submitted');
  expect(exports.myReports(test.viewContext(bob))).toHaveLength(0);
  test.withReducerTx(alice, ctx => exports.withdrawReport(ctx, { id: saved.id }));
  expect(test.db.residentReport.id.find(saved.id)?.aiStatus).toBe('cancelled');
});

it('rejects missing locations, unsupported help types and invalid people counts atomically', () => {
  const test = createModuleTestHarness(spacetimedb, exports);
  const args = { ...report, helpType: 'shelter', peopleAffected: 2, locationText: 'Test landmark' };
  for (const override of [{ peopleAffected: 0 }, { peopleAffected: 1001 }, { locationText: ' ' }, { helpType: 'unrecognized' }])
    expect(() => test.withReducerTx(alice, ctx => exports.submitAssistanceRequest(ctx, { ...args, ...override }))).toThrow();
  expect(test.db.residentReport.count()).toBe(0n);
});

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
