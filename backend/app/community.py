"""Coarse anonymous community signals; private request text never enters public feeds."""
import os
from datetime import timedelta
import httpx


async def collect_community(client, record, at):
    base=os.getenv('SPACETIME_INGEST_URL','').removesuffix('/ingest')
    secret=os.getenv('SPACETIME_INGEST_SECRET')
    if not base or not secret: raise ValueError('Spacetime ingestion credentials required for community signals')
    try:
        response=await client.post(base+'/community-signals',headers={'x-ingest-secret':secret},json={})
        if response.status_code!=200: raise ValueError(f'Community signals HTTP {response.status_code}')
        clusters=response.json()['clusters']
    except httpx.HTTPError as exc: raise ValueError(f'Community signal connection error: {type(exc).__name__}') from None
    items=[]
    for cluster in clusters:
        count=cluster['report_count']
        if not isinstance(count,int) or count<2: continue
        types=', '.join(f'{name.replace("_"," ")}: {number}' for name,number in sorted(cluster['help_types'].items()))
        item=record('community_reports',cluster['id'],f'{count} community assistance reports — hackathon assumption',
            f'{count} distinct reporter identities have active assistance requests in this approximate area. Help types: {types}. '
            'Hackathon assumption: reported needs are treated as accurate for prioritization, not independently verified. No common cause or dispatch is established.',
            {'type':'Point','coordinates':[cluster['longitude'],cluster['latitude']]},kind='incident',event_category='community_need',
            expires_at=(at+timedelta(minutes=2)).isoformat(),
            attributes={'report_count':count,'help_types':cluster['help_types'],'demo_assumption':True,
                        'verification':'assumed_true_for_hackathon_not_verified','location_accuracy':'approximate_5km_area',
                        'reporters':'distinct connection identities, not verified distinct people'})
        if item:
            item['location_accuracy']='approximate_5km_area'
            items.append(item)
    return items
