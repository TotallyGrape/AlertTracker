# Dallas city limits

`dallas-city-limits.geojson` is a snapshot downloaded on 2026-11-07 from City of Dallas GIS Services:

https://gis.dallascityhall.com/arcgis/rest/services/Basemap/CityLimits/MapServer/0

Query: `where=1%3D1&outFields=CITY&outSR=4326&geometryPrecision=5&f=geojson`

The GeoJSON uses longitude/latitude (EPSG:4326), five-decimal coordinate precision, and includes the city's polygon holes and outlying areas. It is served locally to avoid a GIS network request on every map visit. Refresh the snapshot when city limits change. Attribution is included on the map.
