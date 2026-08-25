// Generator statycznych kafelków hałasu (cache JSON) – wersja z JEDNYM zapytaniem.
//
// Pobiera cały obszar BBOX (Trójmiasto + margines) POJEDYNCZYM zapytaniem Overpass,
// a potem dzieli elementy na kafelki siatki (komórka STATIC_CELL). Przeglądarka
// najpierw czyta kafelek, zanim uderzy do live Overpassa – dzięki temu Trójmiasto
// działa całkowicie offline (bez żadnego zapytania live).
//
// Uwaga: stałe STATIC_ORIGIN_* i STATIC_CELL MUSZĄ być zgodne z index.html!
import { writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const TILES_DIR = join(ROOT, 'tiles');

const STATIC_ORIGIN_LAT = 54.30;
const STATIC_ORIGIN_LON = 18.40;
const STATIC_CELL = 0.02;          // ~2.2 km
const RADIUS = 2000;               // margines (zgodny z index.html)
const OVERPASS = 'https://overpass-api.de/api/interpreter';

// Obszar: Trójmiasto + margines (Gdańsk–Gdynia–Sopot)
const BBOX = { latMin: 54.30, latMax: 54.62, lonMin: 18.38, lonMax: 18.82 };

const HW = 'motorway|trunk|primary|secondary|tertiary|residential|unclassified|living_street|service|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link';
const RW = 'rail|narrow_gauge|funicular|light_rail|tram|subway';

const bboxQ = `${BBOX.latMin},${BBOX.lonMin},${BBOX.latMax},${BBOX.lonMax}`;
function query() {
  return `[out:json][timeout:120];(` +
    `way["highway"~"${HW}"](${bboxQ});` +
    `way["railway"~"${RW}"](${bboxQ});` +
    `way["building"](${bboxQ});` +
    `node["amenity"~"^(school|university|kindergarten)$"](${bboxQ});` +
    `node["leisure"~"^(stadium|sports_centre|pitch|playground)$"](${bboxQ});` +
    `node["amenity"~"^(restaurant|cafe|bar|pub|fast_food)$"](${bboxQ});` +
    `node["shop"](${bboxQ});` +
    `node["office"](${bboxQ});` +
    `);out geom;`;
}

async function overpass(q, attempt = 0) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), 120000); // twardy timeout zapytania
  try {
    const res = await fetch(OVERPASS, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'data=' + encodeURIComponent(q),
      signal: ctrl.signal
    });
    clearTimeout(to);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return await res.json();
  } catch (e) {
    clearTimeout(to);
    if (attempt < 4) {
      await new Promise(r => setTimeout(r, 3000 * (attempt + 1)));
      return overpass(q, attempt + 1);
    }
    throw e;
  }
}

function cellOf(lat, lon) {
  return [Math.round((lon - STATIC_ORIGIN_LON) / STATIC_CELL), Math.round((lat - STATIC_ORIGIN_LAT) / STATIC_CELL)];
}
const gxMin = Math.round((BBOX.lonMin - STATIC_ORIGIN_LON) / STATIC_CELL);
const gxMax = Math.round((BBOX.lonMax - STATIC_ORIGIN_LON) / STATIC_CELL);
const gyMin = Math.round((BBOX.latMin - STATIC_ORIGIN_LAT) / STATIC_CELL);
const gyMax = Math.round((BBOX.latMax - STATIC_ORIGIN_LAT) / STATIC_CELL);
const inRange = (gx, gy) => gx >= gxMin && gx <= gxMax && gy >= gyMin && gy <= gyMax;

async function main() {
  await mkdir(TILES_DIR, { recursive: true });
  console.log('Pobieram cały obszar Trójmiasta jednym zapytaniem Overpass…');
  const json = await overpass(query());
  const els = json.elements || [];
  console.log(`Otrzymano ${els.length} elementów.`);

  // Siatka kafelków: "gx_gy" -> {ways, buildings, poi}
  const tiles = new Map();
  const get = (gx, gy) => {
    const k = gx + '_' + gy;
    let t = tiles.get(k);
    if (!t) { t = { ways: [], buildings: [], poi: [] }; tiles.set(k, t); }
    return t;
  };

  for (const el of els) {
    if (el.type === 'way') {
      const geom = el.geometry || [];
      if (geom.length < 2) continue;
      const lats = geom.map(g => g.lat), lons = geom.map(g => g.lon);
      const laMin = Math.min(...lats), laMax = Math.max(...lats);
      const loMin = Math.min(...lons), loMax = Math.max(...lons);
      const [gx0, gy0] = cellOf(laMin, loMin);
      const [gx1, gy1] = cellOf(laMax, loMax);
      for (let gx = Math.max(gx0, gxMin); gx <= Math.min(gx1, gxMax); gx++)
        for (let gy = Math.max(gy0, gyMin); gy <= Math.min(gy1, gyMax); gy++) {
          if (el.tags && el.tags.building) get(gx, gy).buildings.push(el);
          else get(gx, gy).ways.push(el);
        }
    } else if (el.type === 'node') {
      if (el.lat == null || el.lon == null) continue;
      const [gx, gy] = cellOf(el.lat, el.lon);
      if (inRange(gx, gy)) get(gx, gy).poi.push(el);
    }
  }

  let count = 0;
  for (const [k, t] of tiles) {
    if (!t.ways.length && !t.buildings.length && !t.poi.length) continue;
    await writeFile(join(TILES_DIR, k + '.json'), JSON.stringify(t));
    count++;
  }
  console.log(`Zapisano ${count} kafelków.`);

  if (count > 0) {
    const manifest = {
      generated: new Date().toISOString(),
      originLat: STATIC_ORIGIN_LAT, originLon: STATIC_ORIGIN_LON,
      cell: STATIC_CELL, radius: RADIUS, bbox: BBOX,
      tiles: count, endpoint: OVERPASS
    };
    await writeFile(join(TILES_DIR, 'manifest.json'), JSON.stringify(manifest, null, 2));
    console.log('Manifest zapisany.');
  } else {
    console.log('Brak danych z Overpass – nie publikuję manifestu.');
  }
}

main().catch(e => { console.error(e); process.exit(1); });
