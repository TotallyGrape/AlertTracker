import concurrent.futures, urllib.request, urllib.error, json, time
checks = {
 'NIFC perimeters': 'https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query?where=1%3D1&outFields=*&resultRecordCount=1&returnGeometry=false&f=json',
 'USGS earthquakes': 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson',
 'NWS alerts': 'https://api.weather.gov/alerts/active?area=TX',
 'NWS forecast discovery': 'https://api.weather.gov/points/32.7767,-96.7970',
 'NOAA NWPS Dallas gauge': 'https://api.water.noaa.gov/nwps/v1/gauges/dalt2',
 'USGS latest water': 'https://api.waterdata.usgs.gov/ogcapi/v1/collections/latest-continuous/items?f=json&limit=3&bbox=-97.65,32.45,-96.25,33.3',
 'Dallas police': 'https://www.dallasopendata.com/resource/9fxf-t2tr.json?$limit=3',
 'IEM storm reports': 'https://mesonet.agron.iastate.edu/geojson/lsr.php?sts=2026-11-06T00:00Z&ets=2026-11-08T00:00Z&wfo=FWD',
 'FEMA shelters metadata': 'https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0?f=pjson',
 'FEMA shelters query': 'https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0/query?where=1%3D1&outFields=*&resultRecordCount=2&f=geojson',
 'Dallas GIS boundary': 'https://gis.dallascityhall.com/arcgis/rest/services/Basemap/CityLimits/MapServer/0/query?where=1%3D1&outFields=CITY&outSR=4326&geometryPrecision=5&f=geojson',
 'OpenFreeMap style': 'https://tiles.openfreemap.org/styles/liberty',
 'Overpass facilities': 'https://overpass-api.de/api/interpreter?data=%5Bout%3Ajson%5D%5Btimeout%3A20%5D%3Bnwr%5Bamenity%3Dfire_station%5D%2832.75%2C-96.85%2C32.85%2C-96.75%29%3Bout%20center%203%3B',
}
def check(item):
 name,url=item; start=time.monotonic()
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'TexasResponse-HackUTD-IntegrationCheck/0.1','Accept':'application/json, application/geo+json, */*'})
  with urllib.request.urlopen(req,timeout=40) as r:
   raw=r.read(); result={'name':name,'url':url,'status':r.status,'seconds':round(time.monotonic()-start,2),'bytes':len(raw),'content_type':r.headers.get('Content-Type'),'cors':r.headers.get('Access-Control-Allow-Origin')}
  try:
   data=json.loads(raw); result['keys']=list(data)[:15] if isinstance(data,dict) else 'array'; result['count']=len(data) if isinstance(data,list) else len(data.get('features',data.get('elements',[])))
   if isinstance(data,dict) and 'error' in data:result['api_error']=data['error']
   result['sample']=str(data)[:1800]
   if name=='OpenFreeMap style':result['sources']=data.get('sources'); result['glyphs']=data.get('glyphs');result['sprite']=data.get('sprite')
  except Exception: result['sample']=raw[:250].decode('utf-8',errors='replace')
  return result
 except Exception as e:return {'name':name,'url':url,'error':str(e),'seconds':round(time.monotonic()-start,2)}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool: results=list(pool.map(check,checks.items()))
with open('api-readiness-results.json','w',encoding='utf-8') as f:json.dump(results,f,indent=2)
for result in results:print(json.dumps(result))
