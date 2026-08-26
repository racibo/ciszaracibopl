#!/usr/bin/env python3
# Generator statycznych kafelków hałasu z ekstraktów Geofabrik (BEZ Overpassa).
# Czyta extract(y) wojewódzkie Geofabrik i dzieli wybrane obszary (REGIONS)
# na kafelki siatki (komórka STATIC_CELL). Przeglądarka czyta kafelek zanim
# uderzy do live Overpassa -> wybrane miejsca działają w 100% offline.
#
# Stałe STATIC_ORIGIN_* i STATIC_CELL MUSZĄ być zgodne z index.html!
# Zmienna środowiskowa TILES_OUT pozwala zapisać kafelki do katalogu
# tymczasowego (etapowanie per-województwo w matrix CI); domyślnie ./tiles.
import osmium, json, os, sys, tempfile, datetime
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILES_DIR = os.environ.get('TILES_OUT') or os.path.join(ROOT, 'tiles')

ORIGIN_LAT = 54.30
ORIGIN_LON = 18.40
CELL = 0.02            # ~2.2 km
RADIUS = 2000

# Obszar, dla którego budujemy kafelki. Cała Polska – dzięki temu każdy punkt
# w kraju działa offline (BEZ Overpassa). Wystarczy, by extracty Geofabrik
# pokrywały cały kraj (wszystkie 16 województw w GEOFABRIK_PBFS).
# (nazwa, latMin, latMax, lonMin, lonMax)
REGIONS = [
    ('Polska', 49.0, 54.9, 14.0, 24.2),
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

def resolve_sources():
    raw = os.environ.get('GEOFABRIK_PBFS')
    if raw:
        files = [s.strip() for s in raw.split(os.pathsep) if s.strip()]
    else:
        single = os.environ.get('GEOFABRIK_PBF')
        files = [single] if single else []
    resolved = [f for f in files if f and os.path.exists(f)]
    if resolved:
        return resolved
    for cand in (
        os.path.join(ROOT, 'poland.osm.pbf'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'poland.osm.pbf'),
        os.path.join(tempfile.gettempdir(), 'poland.osm.pbf'),
    ):
        if os.path.exists(cand):
            return [cand]
    return []

def main():
    os.makedirs(TILES_DIR, exist_ok=True)
    sources = resolve_sources()
    if not sources:
        print('Brak pliku PBF (ustaw GEOFABRIK_PBFS lub pobierz extracty Geofabrik).')
        sys.exit(1)
    h = Handler()
    for src in sources:
        print('Czytam', src, '...')
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
            'tiles': count, 'source': 'geofabrik:voivodeship-latest.osm.pbf'
        }
        with open(os.path.join(TILES_DIR, 'manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        print('Manifest zapisany.')

if __name__ == '__main__':
    main()
