#!/usr/bin/env python3
# Generator statycznych kafelków hałasu z ekstraktu Geofabrik (BEZ Overpassa).
# Czyta poland-latest.osm.pbf i dzieli wybrane obszary (REGIONS) na kafelki
# siatki (komórka STATIC_CELL). Przeglądarka czyta kafelek zanim uderzy do
# live Overpassa -> wybrane miejsca działają w 100% offline, nawet gdy
# Overpass jest niedostępny.
#
# Stałe STATIC_ORIGIN_* i STATIC_CELL MUSZĄ być zgodne z index.html!
import osmium, json, os, sys, tempfile, datetime
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILES_DIR = os.path.join(ROOT, 'tiles')

ORIGIN_LAT = 54.30
ORIGIN_LON = 18.40
CELL = 0.02            # ~2.2 km
RADIUS = 2000

# Obszary, dla których budujemy kafelki. Dowolna liczba – wystarczy dopisać
# (nazwa, latMin, latMax, lonMin, lonMax). Dane pochodzą z ekstraktu Geofabrik
# "poland-latest", więc można pokryć dowolne miejsce w Polsce.
REGIONS = [
    ('Trojmiasto',           54.30, 54.64, 18.36, 18.86),
    ('Biskupiec',           53.78, 53.90, 20.86, 21.04),
    ('Ciechocinek',         52.83, 52.94, 18.85, 19.02),
    ('Aleksandrow Kujawski', 52.83, 52.94, 18.62, 18.78),
    ('Krutyń',              53.58, 53.69, 21.25, 21.42),
]

HW = {'motorway','trunk','primary','secondary','tertiary','residential',
       'unclassified','living_street','service','motorway_link','trunk_link',
       'primary_link','secondary_link','tertiary_link'}
RW = {'rail','narrow_gauge','funicular','light_rail','tram','subway'}

def cell_of(lat, lon):
    return (round((lon - ORIGIN_LON) / CELL), round((lat - ORIGIN_LAT) / CELL))

def in_any(lat, lon):
    return any(a <= lat <= b and c <= lon <= d for (_, a, b, c, d) in REGIONS)

def intersects_any(minLat, maxLat, minLon, maxLon):
    return any(not (maxLat < a or minLat > b or maxLon < c or minLon > d)
               for (_, a, b, c, d) in REGIONS)

tiles = defaultdict(lambda: {'ways': [], 'buildings': [], 'poi': []})

class Handler(osmium.SimpleHandler):
    def node(self, n):
        if not n.location.valid():
            return
        lat, lon = n.location.lat, n.location.lon
        if not in_any(lat, lon):
            return
        tags = dict(n.tags)
        a = tags.get('amenity'); le = tags.get('leisure'); sh = tags.get('shop'); of = tags.get('office')
        if (a in ('school','university','kindergarten','restaurant','cafe','bar','pub','fast_food')
                or le in ('stadium','sports_centre','pitch','playground') or sh or of):
            gx, gy = cell_of(lat, lon)
            tiles[(gx, gy)]['poi'].append(
                {'type': 'node', 'id': n.id, 'lat': lat, 'lon': lon, 'tags': tags})

    def way(self, w):
        coords = [(nd.location.lon, nd.location.lat) for nd in w.nodes if nd.location.valid()]
        if len(coords) < 2:
            return
        lons = [c[0] for c in coords]; lats = [c[1] for c in coords]
        if not intersects_any(min(lats), max(lats), min(lons), max(lons)):
            return
        tags = dict(w.tags)
        if not (tags.get('highway') or tags.get('railway') or tags.get('building')):
            return
        geom = [{'lat': la, 'lon': lo} for lo, la in coords]
        gx0, gy0 = cell_of(min(lats), min(lons))
        gx1, gy1 = cell_of(max(lats), max(lons))
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                # zachowujemy tylko komórki leżące wewnątrz któregoś obszaru
                clat = ORIGIN_LAT + gy * CELL
                clon = ORIGIN_LON + gx * CELL
                if not in_any(clat, clon):
                    continue
                t = tiles[(gx, gy)]
                if tags.get('building'):
                    t['buildings'].append({'type': 'way', 'id': w.id, 'geometry': geom, 'tags': tags})
                else:
                    t['ways'].append({'type': 'way', 'id': w.id, 'geometry': geom, 'tags': tags})

def main():
    os.makedirs(TILES_DIR, exist_ok=True)
    src = os.environ.get('GEOFABRIK_PBF')
    if not src or not os.path.exists(src):
        for cand in (
            os.path.join(ROOT, 'poland.osm.pbf'),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'poland.osm.pbf'),
            os.path.join(tempfile.gettempdir(), 'poland.osm.pbf'),
        ):
            if os.path.exists(cand):
                src = cand
                break
    if not src or not os.path.exists(src):
        print('Brak pliku PBF (ustaw GEOFABRIK_PBF lub pobierz poland-latest.osm.pbf).')
        sys.exit(1)
    print('Czytam', src, '...')
    h = Handler()
    h.apply_file(src, locations=True)
    print('Elementy przetworzone. Zapisuję kafelki...')

    count = 0
    for (gx, gy), t in tiles.items():
        if not (t['ways'] or t['buildings'] or t['poi']):
            continue
        with open(os.path.join(TILES_DIR, f'{gx}_{gy}.json'), 'w', encoding='utf-8') as f:
            json.dump(t, f, ensure_ascii=False)
        count += 1
    print(f'Zapisano {count} kafelków.')

    if count > 0:
        lats = [r[1] for r in REGIONS] + [r[2] for r in REGIONS]
        lons = [r[3] for r in REGIONS] + [r[4] for r in REGIONS]
        manifest = {
            'generated': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'originLat': ORIGIN_LAT, 'originLon': ORIGIN_LON,
            'cell': CELL, 'radius': RADIUS,
            'bbox': {'latMin': min(lats), 'latMax': max(lats),
                      'lonMin': min(lons), 'lonMax': max(lons)},
            'regions': [{'name': n, 'latMin': a, 'latMax': b, 'lonMin': c, 'lonMax': d}
                        for (n, a, b, c, d) in REGIONS],
            'tiles': count, 'source': 'geofabrik:poland-latest.osm.pbf'
        }
        with open(os.path.join(TILES_DIR, 'manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        print('Manifest zapisany.')

if __name__ == '__main__':
    main()
