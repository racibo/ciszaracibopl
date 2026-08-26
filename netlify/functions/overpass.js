import { createHash } from 'crypto';
import { getStore } from '@netlify/blobs';

// Serwerowa warstwa cache dla Overpassa (Netlify Blobs, TTL 30 dni).
// Przeglądarka w index.html woła POST /api/overpass z ciałem {"q": "<zapytanie Overpass>"}.
// Pierwszy użytkownik w danej okolicy "płaci" za zapytanie do Overpassa; kolejni
// dostają wynik natychmiast z Blobs -> mniej żywych zapytań = mniej trafień w rate-limit.
// Gdy Blobs/Overpass zawiedzie, zwracamy 502 z pustymi elementami (frontend falluje
// do bezpośrednich mirror-ów CORS).

const ENDPOINTS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.osm.ch/api/interpreter',
  'https://private.coffee/api/overpass/',
];

const TTL_MS = 30 * 24 * 60 * 60 * 1000;

// getStore bez jawnego siteID/token działa na Netlify (kontekst wstrzykiwany automatycznie).
const store = getStore('overpass-cache');

function keyFor(q) {
  return createHash('sha256').update(q).digest('hex');
}

async function fetchOverpass(q) {
  const body = 'data=' + encodeURIComponent(q);
  for (const ep of ENDPOINTS) {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 25000);
      const r = await fetch(ep, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      if (!r.ok) continue;
      const j = await r.json();
      if (!j || !Array.isArray(j.elements)) continue;
      return j;
    } catch (e) {
      // spróbuj kolejnego endpointu
    }
  }
  return null;
}

export default async (request) => {
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  let q;
  try {
    const ct = request.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      const data = await request.json();
      q = data && data.q;
    } else {
      const text = await request.text();
      const m = text.match(/data=(.*)$/s);
      q = m ? decodeURIComponent(m[1]) : null;
    }
  } catch (e) {
    return new Response('Bad Request', { status: 400 });
  }
  if (!q) return new Response('Missing query', { status: 400 });

  const key = keyFor(q);

  // 1) HIT z Blobs (jeśli świeże ≤ 30 dni)
  try {
    const cached = await store.get(key, { type: 'json' });
    if (cached && cached._storedAt && (Date.now() - cached._storedAt) < TTL_MS) {
      return new Response(JSON.stringify(cached.data), {
        headers: { 'Content-Type': 'application/json', 'X-Cache': 'HIT' },
      });
    }
  } catch (e) {
    // cache miss / błąd odczytu -> idziemy do Overpassa
  }

  // 2) MISS -> zapytanie do Overpassa
  const data = await fetchOverpass(q);
  if (!data) {
    return new Response(JSON.stringify({ remark: 'Overpass niedostępny', elements: [] }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // 3) zapisz do Blobs (ignorujemy błędy zapisu)
  try {
    await store.set(key, JSON.stringify({ _storedAt: Date.now(), data }));
  } catch (e) { /* non-fatal */ }

  return new Response(JSON.stringify(data), {
    headers: { 'Content-Type': 'application/json', 'X-Cache': 'MISS' },
  });
};
