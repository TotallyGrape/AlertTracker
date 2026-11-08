exec(open('api_readiness_check.py',encoding='utf-8-sig').read().split('with concurrent.futures.ThreadPoolExecutor')[0])
checks={
 'NWS Dallas forecast':'https://api.weather.gov/gridpoints/FWD/89,104/forecast',
 'IEM FWD filter':'https://mesonet.agron.iastate.edu/geojson/lsr.php?sts=2026-11-06T00:00Z&ets=2026-11-07T22:00Z&wfos=FWD',
 'Police metadata':'https://www.dallasopendata.com/api/views/9fxf-t2tr.json',
 'NIFC DFW spatial query':'https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query?where=1%3D1&geometry=-97.65,32.45,-96.25,33.3&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&returnCountOnly=true&f=json',
 'FEMA DFW spatial query':'https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0/query?where=1%3D1&geometry=-97.65,32.45,-96.25,33.3&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&returnCountOnly=true&f=json',
 'OpenFreeMap tiles metadata':'https://tiles.openfreemap.org/planet',
 'OpenFreeMap sprite':'https://tiles.openfreemap.org/sprites/ofm_f384/ofm.json',
}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: results=list(pool.map(check,checks.items()))
with open('api-readiness-followup.json','w',encoding='utf-8') as f:json.dump(results,f,indent=2)
for r in results:print(json.dumps(r))
