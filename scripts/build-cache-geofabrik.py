#!/usr/bin/env python3
# Generator statycznych kafelków hałasu z ekstraktu Geofabrik (BEZ Overpassa).
# Czyta pomorskie-latest.osm.pbf, filtruje do obszaru Trójmiasta i dzieli na
# kafelki siatki (komórka STATIC_CELL). Przeglądarka czyta kafelek zanim
# uderzy do live Overpassa -> Trójmiasto działa w 100% offline.
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
# Trójmiasto + margines (zgodne z index.html / build-cache.mjs)
BBOX = (54.30, 54.62, 18.38, 18.82)   # latMin, latMax, lonMin, lonMax

HW = {'motorway','trunk','primary','secondary','tertiary','residential',
      'unclassified','living_street','service','motorway_link','trunk_link',
      'primary_link','secondary_link','tertiary_link'}
RW = {'rail','narrow_gauge','funicular','light_rail','tram','subway'}

def cell_of(lat, lon):
    return (round((lon - ORIGIN_LON) / CELL), round((lat - ORIGIN_LAT) / CELL))

gxMin = round((BBOX[2] - ORIGIN_LON) / CELL); gxMax = round((BBOX[3] - ORIGIN_LON) / CELL)
gyMin = round((BBOX[0] - ORIGIN_LAT) / CELL); gyMax = round((BBOX[1] - ORIGIN_LAT) / CELL)

tiles = defaultdict(lambda: {'ways': [], 'buildings': [], 'poi': []})

def in_bbox(lat, lon):
    return BBOX[2] <= lon <= BBOX[3] and BBOX[0] <= lat <= BBOX[1]

class Handler(osmium.SimpleHandler):
    def node(self, n):
        if not n.location.valid():
            return
        lat, lon = n.location.lat, n.location.lon
        if not in_bbox(lat, lon):
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
        # przecina się z obszarem Trójmiasta?
        if max(lons) < BBOX[2] or min(lons) > BBOX[3] or max(lats) < BBOX[0] or min(lats) > BBOX[1]:
            return
        tags = dict(w.tags)
        if not (tags.get('highway') or tags.get('railway') or tags.get('building')):
            return
        geom = [{'lat': la, 'lon': lo} for lo, la in coords]
        gx0, gy0 = cell_of(min(lats), min(lons))
        gx1, gy1 = cell_of(max(lats), max(lons))
        for gx in range(max(gx0, gxMin), min(gx1, gxMax) + 1):
            for gy in range(max(gy0, gyMin), min(gy1, gyMax) + 1):
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
            os.path.join(ROOT, 'pomorskie.osm.pbf'),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pomorskie.osm.pbf'),
            os.path.join(tempfile.gettempdir(), 'pomorskie.osm.pbf'),
        ):
            if os.path.exists(cand):
                src = cand
                break
    if not src or not os.path.exists(src):
        print('Brak pliku PBF (ustaw GEOFABRIK_PBF lub pobierz pomorskie-latest.osm.pbf).')
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
        manifest = {
            'generated': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'originLat': ORIGIN_LAT, 'originLon': ORIGIN_LON,
            'cell': CELL, 'radius': RADIUS, 'bbox': {
                'latMin': BBOX[0], 'latMax': BBOX[1], 'lonMin': BBOX[2], 'lonMax': BBOX[3]},
            'tiles': count, 'source': 'geofabrik:pomorskie-latest.osm.pbf'
        }
        with open(os.path.join(TILES_DIR, 'manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        print('Manifest zapisany.')

if __name__ == '__main__':
    main()
