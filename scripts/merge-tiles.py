#!/usr/bin/env python3
# Łączy kafelki wygenerowane per-województwo (etapowanie w matrix CI) w jeden
# zestaw tiles/<gx>_<gy>.json. Odporność na duplikaty (droga na granicy
# województw może być w dwóch extractach) – deduplikacja wg pola 'id'.
#
# Użycie: python scripts/merge-tiles.py <katalog_staged> <katalog_wyjściowy_tiles>
import os, sys, json, glob, datetime

STAGED = sys.argv[1] if len(sys.argv) > 1 else 'staged'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'tiles'

ORIGIN_LAT = 54.30
ORIGIN_LON = 18.40
CELL = 0.02
RADIUS = 2000


def load(p):
    with open(p, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def dedupe(lst):
    seen, out = set(), []
    for it in lst:
        i = it.get('id')
        if i in seen:
            continue
        if i is not None:
            seen.add(i)
        out.append(it)
    return out


cells = {}  # filename -> {'ways':[], 'buildings':[], 'poi':[]}
for path in glob.glob(os.path.join(STAGED, '**', '*.json'), recursive=True):
    name = os.path.basename(path)
    if name == 'manifest.json':
        continue
    t = load(path)
    agg = cells.setdefault(name, {'ways': [], 'buildings': [], 'poi': []})
    agg['ways'].extend(t.get('ways', []))
    agg['buildings'].extend(t.get('buildings', []))
    agg['poi'].extend(t.get('poi', []))

os.makedirs(OUT, exist_ok=True)
count = 0
for name, agg in cells.items():
    agg['ways'] = dedupe(agg['ways'])
    agg['buildings'] = dedupe(agg['buildings'])
    agg['poi'] = dedupe(agg['poi'])
    if not (agg['ways'] or agg['buildings'] or agg['poi']):
        continue
    with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
        json.dump(agg, f, ensure_ascii=False)
    count += 1

manifest = {
    'generated': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'originLat': ORIGIN_LAT, 'originLon': ORIGIN_LON,
    'cell': CELL, 'radius': RADIUS,
    'bbox': {'latMin': 49.0, 'latMax': 54.9, 'lonMin': 14.0, 'lonMax': 24.2},
    'regions': [{'name': 'Polska', 'latMin': 49.0, 'latMax': 54.9,
                 'lonMin': 14.0, 'lonMax': 24.2}],
    'tiles': count, 'source': 'geofabrik:voivodeship-latest.osm.pbf'
}
with open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8') as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print(f'Połączono: {count} kafelków zapisano do {OUT}/')
