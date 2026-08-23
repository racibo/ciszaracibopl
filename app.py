import math
import requests
from flask import Flask, request, jsonify, send_from_directory
import osmnx as ox
import geopandas as gpd
from shapely.geometry import Point, LineString
from shapely.ops import nearest_points

app = Flask(__name__)

# Prosta pamięć podręczna, by nie uderzać w Overpass przy wielokrotnym kliknięciu
CACHE = {}

# Poziom hałasu źródła (w dB) w przybliżeniu dla odległości referencyjnej (10 m).
# Im wyższa wartość, tym głośniej przy samym szlaku.
ROAD_BASE = {
    'motorway': 88, 'motorway_link': 78, 'trunk': 86, 'trunk_link': 76,
    'primary': 80, 'primary_link': 70, 'secondary': 74, 'secondary_link': 66,
    'tertiary': 68, 'tertiary_link': 62, 'residential': 62, 'unclassified': 62,
    'living_street': 55, 'service': 58,
}
RAIL_BASE = {
    'rail': 82, 'narrow_gauge': 70, 'funicular': 55,
    'light_rail': 72, 'tram': 75, 'subway': 60,
}

# Grupowanie szlaków w kategorie z wagami konfigurowalnymi z poziomu UI
ROAD_GROUPS = {
    'szybki': ['motorway', 'motorway_link', 'trunk', 'trunk_link'],
    'krajowa': ['primary', 'primary_link'],
    'wojew': ['secondary', 'secondary_link'],
    'lokalna': ['tertiary', 'tertiary_link', 'residential', 'unclassified',
                'living_street', 'service'],
}
RAIL_GROUPS = {
    'kolej': ['rail', 'narrow_gauge', 'funicular'],
    'miejska': ['light_rail', 'tram', 'subway'],
}

GROUP_LABEL = {
    'szybki': 'Autostrada / Droga ekspresowa',
    'krajowa': 'Droga krajowa',
    'wojew': 'Droga wojewódzka',
    'lokalna': 'Droga lokalna',
    'kolej': 'Kolej (główna)',
    'miejska': 'Kolej miejska / tramwaj',
}
GROUP_TYPE = {
    'szybki': 'Droga', 'krajowa': 'Droga', 'wojew': 'Droga', 'lokalna': 'Droga',
    'kolej': 'Kolej', 'miejska': 'Kolej',
}

# Tło (absolutna cisza) w dB oraz wartość odpowiadająca skrajowi skali (100)
AMBIENT_DB = 30.0
REFERENCE_DB = 80.0
SLOPE = 15.0  # tłumienie w dB na dekadę odległości


def utm_epsg(lat, lon):
    zone = int((lon + 180) // 6) + 1
    return 32600 + zone if lat >= 0 else 32700 + zone


def tag_val(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, list):
        v = v[0] if v else None
    return v


def classify(tag, kind):
    groups = ROAD_GROUPS if kind == 'road' else RAIL_GROUPS
    for g, lst in groups.items():
        if tag in lst:
            return g
    return None


def fetch_elevation(points):
    """Pobiera wysokości n.p.m. z darmowego API Open-Meteo (do 100 pkt na zapytanie)."""
    if not points:
        return None
    lats = ",".join(f"{p[0]:.6f}" for p in points)
    lons = ",".join(f"{p[1]:.6f}" for p in points)
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/elevation",
            params={'latitude': lats, 'longitude': lons},
            timeout=25,
        )
        if r.ok:
            return r.json().get('elevation')
    except Exception:
        return None
    return None


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={'format': 'json', 'q': q, 'limit': 5, 'addressdetails': 0},
            headers={'User-Agent': 'w-poszukiwaniu-ciszy/1.0'},
            timeout=20,
        )
        if not r.ok:
            return jsonify({'error': 'Błąd geokodowania'}), 502
        out = [{'lat': float(i['lat']), 'lon': float(i['lon']),
                'label': i['display_name']} for i in r.json()]
        return jsonify(out)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analyze', methods=['POST'])
def analyze():
    data = request.get_json(force=True)
    try:
        lat = float(data['lat'])
        lon = float(data['lon'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Brak współrzędnych lat/lon'}), 400

    settings = data.get('settings', {}) or {}
    fetch_radius = int(settings.get('fetchRadius', 1500))
    road_w = settings.get('roadWeights', {}) or {}
    rail_w = settings.get('railWeights', {}) or {}
    terrain_on = bool(settings.get('terrain', {}).get('enabled', True))
    barrier_h = float(settings.get('terrain', {}).get('barrierHeight', 20))

    key = (round(lat, 4), round(lon, 4), fetch_radius)
    if key in CACHE:
        gdf = CACHE[key]
    else:
        tags = {'highway': list(ROAD_BASE.keys()),
                'railway': list(RAIL_BASE.keys())}
        try:
            gdf = ox.features_from_point((lat, lon), tags, dist=fetch_radius)
        except Exception as e:
            return jsonify({'error': f'Błąd pobierania danych OSM: {e}'}), 502
        CACHE[key] = gdf

    utm = utm_epsg(lat, lon)
    gdf = gdf[gdf.geometry.type.isin(['LineString', 'MultiLineString'])].copy()
    if gdf.empty:
        return jsonify({
            'score': 0, 'level_db': AMBIENT_DB, 'sources': [],
            'terrain_note': 'Brak dróg i kolei w promieniu analizy – absolutna cisza.',
        })

    gdf_utm = gdf.to_crs(epsg=utm)
    base_geom = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(epsg=utm).iloc[0]

    sources = []
    for _, row in gdf_utm.iterrows():
        geom = row.geometry
        d = geom.distance(base_geom)
        if d > fetch_radius:
            continue

        highway = tag_val(row.get('highway'))
        railway = tag_val(row.get('railway'))
        if highway:
            kind, tag = 'road', highway
            base_map, weights = ROAD_BASE, road_w
        elif railway:
            kind, tag = 'rail', railway
            base_map, weights = RAIL_BASE, rail_w
        else:
            continue

        group = classify(tag, kind)
        if group is None:
            continue
        weight = float(weights.get(group, 1.0))

        base = base_map.get(tag, 60)
        l_i = base - SLOPE * math.log10(1 + d / 10.0)
        energy_i = weight * 10 ** (l_i / 10.0)

        name = tag_val(row.get('name')) or GROUP_LABEL[group]

        sources.append({
            'geom': geom,
            'dist': d,
            'kind': kind,
            'group': group,
            'name': name,
            'weight': weight,
            'energy_i': energy_i,
            'terrain_factor': 1.0,
            'reduction_pct': 0,
            'rise': None,
        })

    # --- Ukształtowanie terenu: czy między nami a szlakiem jest wał (górka)? ---
    terrain_note = 'Ukształtowanie terenu nie zostało uwzględnione.'
    if terrain_on and sources:
        cand = sorted(sources, key=lambda s: -s['energy_i'])
        cand = [s for s in cand if s['dist'] <= 1500][:20]

        loc4326 = gpd.GeoSeries([base_geom], crs=utm).to_crs(4326).iloc[0]
        loc_lat, loc_lon = loc4326.y, loc4326.x

        elev_pts = [(loc_lat, loc_lon)]
        for s in cand:
            p_geom = nearest_points(base_geom, s['geom'])[1]
            g4326 = gpd.GeoSeries([p_geom], crs=utm).to_crs(4326).iloc[0]
            s['p_lat'], s['p_lon'] = g4326.y, g4326.x
            line = LineString([base_geom, p_geom])
            for t in (0.33, 0.66):
                mp = line.interpolate(t, normalized=True)
                m4326 = gpd.GeoSeries([mp], crs=utm).to_crs(4326).iloc[0]
                elev_pts.append((m4326.y, m4326.x))

        elevations = fetch_elevation(elev_pts)
        if elevations is not None:
            e_loc = elevations[0]
            idx = 1
            barriers = 0
            for s in cand:
                e_src = elevations[idx]
                e_m1 = elevations[idx + 1]
                e_m2 = elevations[idx + 2]
                idx += 3
                rise = max(e_m1, e_m2) - min(e_loc, e_src)
                s['rise'] = round(rise, 1)
                if rise >= barrier_h:
                    reduction = min(0.8, 0.3 + (rise - barrier_h) / 100.0)
                    barriers += 1
                else:
                    reduction = 0.0
                s['terrain_factor'] = 1.0 - reduction
                s['reduction_pct'] = round(reduction * 100)
            if barriers:
                terrain_note = (f'Wyznaczono {barriers} szlaków, za którymi teren '
                                f'wynosi się w wał (>{barrier_h:.0f} m) – hałas obniżony.')
            else:
                terrain_note = 'Teren płaski lub łagodny – brak naturalnej osłony akustycznej.'
        else:
            terrain_note = 'Brak dostępu do danych o wysokości terenu (API niedostępne).'

    # --- Sumowanie energetyczne i wynik 0-100 ---
    base_energy = 10 ** (AMBIENT_DB / 10.0)
    energy_total = base_energy + sum(
        s['energy_i'] * s['terrain_factor'] for s in sources)
    level_db = 10 * math.log10(energy_total)
    score = max(0.0, min(100.0, (level_db - AMBIENT_DB) /
                         (REFERENCE_DB - AMBIENT_DB) * 100.0))

    top = sorted(sources, key=lambda s: -(s['energy_i'] * s['terrain_factor']))[:10]
    out_sources = [{
        'name': s['name'],
        'type': GROUP_TYPE[s['group']],
        'category': GROUP_LABEL[s['group']],
        'distance_m': round(s['dist']),
        'weight': s['weight'],
        'terrain_reduction_pct': s['reduction_pct'],
        'rise_m': s['rise'],
    } for s in top]

    return jsonify({
        'score': round(score),
        'level_db': round(level_db, 1),
        'sources': out_sources,
        'terrain_note': terrain_note,
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
