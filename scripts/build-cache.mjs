// Generator statycznych kafelków hałasu (cache JSON) dla aplikacji "W poszukiwaniu ciszy".
// Uruchamiany przez GitHub Actions (raz w miesiącu) oraz ręcznie (workflow_dispatch).
//
// Dla każdego węzła siatki (komórka STATIC_CELL stopni) pobiera z Overpassa:
//   - drogi i tory (way["highway"] / way["railway"])  -> tile.ways
//   - budynki (way["building"])                        -> tile.buildings
//   - punktowe źródła (szkoły, boiska, gastronomia)    -> tile.poi
// i zapisuje je do tiles/<gx>_<gy>.json. Przeglądarka (index.html) najpierw próbuje
// wczytać taki kafelek, zanim uderzy do live Overpassa.
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
const RADIUS = 2000;               // margines wokół komórki (pokrywa zasięg analizy do 2000 m)
const OVERPASS = 'https://overpass-api.de/api/interpreter';

// Obszar: Trójmiasto + margines (Gdańsk–Gdynia–Sopot)
const BBOX = { latMin: 54.30, latMax: 54.62, lonMin: 18.38, lonMax: 18.82 };

const HW = 'motorway|trunk|primary|secondary|tertiary|residential|unclassified|living_street|service|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link';
const RW = 'rail|narrow_gauge|funicular|light_rail|tram|subway';

function cellQuery(lat, lon) {
  const a = `around:${RADIUS},${lat.toFixed(6)},${lon.toFixed(6)}`;
  return `[out:json][timeout:60];(` +
    `way["highway"~"${HW}"](${a});` +
    `way["railway"~"${RW}"](${a});` +
    `way["building"](${a});` +
    `node["amenity"~"^(school|university|kindergarten)$"](${a});` +
    `node["leisure"~"^(stadium|sports_centre|pitch|playground)$"](${a});` +
    `node["amenity"~"^(restaurant|cafe|bar|pub|fast_food)$"](${a});` +
    `node["shop"](${a});` +
    `node["office"](${a});` +
    `);out geom;`;
}

async function overpass(q, attempt = 0) {
  try {
    const res = await fetch(OVERPASS, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'data=' + encodeURIComponent(q)
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return await res.json();
  } catch (e) {
    if (attempt < 4) {
      await new Promise(r => setTimeout(r, 3000 * (attempt + 1)));
      return overpass(q, attempt + 1);
    }
    throw e;
  }
}

function splitElements(elements) {
  const ways = [], buildings = [], poi = [];
  for (const el of elements || []) {
    if (el.type === 'way') {
      if (el.tags && el.tags.building) buildings.push(el);
      else if ((el.tags && el.tags.highway) || (el.tags && el.tags.railway)) ways.push(el);
    } else if (el.type === 'node') {
      poi.push(el);
    }
  }
  return { ways, buildings, poi };
}

async function main() {
  await mkdir(TILES_DIR, { recursive: true });
  const latCells = [];
  for (let lat = BBOX.latMin; lat <= BBOX.latMax + 1e-9; lat += STATIC_CELL) latCells.push(lat);
  const lonCells = [];
  for (let lon = BBOX.lonMin; lon <= BBOX.lonMax + 1e-9; lon += STATIC_CELL) lonCells.push(lon);

  let count = 0;
  for (const lat of latCells) {
    for (const lon of lonCells) {
      const gx = Math.round((lon - STATIC_ORIGIN_LON) / STATIC_CELL);
      const gy = Math.round((lat - STATIC_ORIGIN_LAT) / STATIC_CELL);
      const file = join(TILES_DIR, `${gx}_${gy}.json`);
      try {
        const json = await overpass(cellQuery(lat, lon));
        const tile = splitElements(json.elements);
        await writeFile(file, JSON.stringify(tile));
        count++;
        console.log(`OK ${gx}_${gy} (ways=${tile.ways.length} buildings=${tile.buildings.length} poi=${tile.poi.length})`);
      } catch (e) {
        console.error(`FAIL ${gx}_${gy}: ${e.message}`);
      }
      await new Promise(r => setTimeout(r, 1500)); // grzeczność wobec Overpassa
    }
  }
  const manifest = {
    generated: new Date().toISOString(),
    originLat: STATIC_ORIGIN_LAT, originLon: STATIC_ORIGIN_LON,
    cell: STATIC_CELL, radius: RADIUS, bbox: BBOX,
    tiles: count, endpoint: OVERPASS
  };
  await writeFile(join(TILES_DIR, 'manifest.json'), JSON.stringify(manifest, null, 2));
  console.log(`Wygenerowano ${count} kafelków.`);
}

main().catch(e => { console.error(e); process.exit(1); });
