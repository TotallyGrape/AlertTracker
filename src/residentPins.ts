import type { FeatureCollection } from 'geojson';

export const REQUEST_LIFETIME_MS = 24 * 60 * 60 * 1000;
type RequestRow = {
  id: bigint; name: string; description: string; latitude: number; longitude: number; status: string;
  createdAt: { microsSinceUnixEpoch: bigint }; helpType: string; peopleAffected: number;
  aiStatus: string; aiSummary: string; aiUrgency: string;
};

export function residentPins(rows: readonly RequestRow[], at: number, connected: boolean): FeatureCollection['features'] {
  return rows.flatMap(row => {
    const created = Number(row.createdAt.microsSinceUnixEpoch / 1000n);
    if (row.status !== 'submitted' || at >= created + REQUEST_LIFETIME_MS || !Number.isFinite(row.latitude) || !Number.isFinite(row.longitude)) return [];
    return [{ type: 'Feature' as const, id: `resident:${row.id}`, geometry: { type: 'Point' as const, coordinates: [row.longitude, row.latitude] },
      properties: { name: `Your request: ${row.name}`, description: row.description, source: 'resident_request', kind: 'resident_request',
        stale: !connected, observedAt: new Date(created).toISOString(), expiresAt: new Date(created+REQUEST_LIFETIME_MS).toISOString(),
        facts: `${row.helpType.replace(/_/g, ' ')} · ${row.peopleAffected} people · ${row.aiStatus === 'complete' ? `AI suggested urgency: ${row.aiUrgency}` : `AI: ${row.aiStatus}`}`,
        aiHeadline: row.aiStatus === 'complete' ? row.name : '', aiSummary: row.aiStatus === 'complete' ? row.aiSummary : '' } }];
  });
}
