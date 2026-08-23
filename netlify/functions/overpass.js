// Netlify Function: proxy do Overpass API.
// Rozwiązuje problemy z CORS (przeglądarka woła /api/overpass samoopisowo)
// i pozwala przymierzyć kilka backendów serwerowo (bez CORS).
exports.handler = async (event) => {
  let q;
  if (event.body) {
    let raw = event.body;
    if (event.isBase64Encoded) {
      raw = Buffer.from(raw, "base64").toString("utf8");
    }
    if (typeof raw === "object") {
      q = raw.q; // ciało już sparsowane
    } else {
      try {
        q = JSON.parse(raw).q;
      } catch (e) {
        q = raw; // ciało to surowe zapytanie Overpass
      }
    }
  }
  if (!q) {
    return { statusCode: 400, body: JSON.stringify({ error: "brak parametru q" }) };
  }

  if (q === "__debug") {
    return {
      statusCode: 200,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        eventBody: event.body,
        isBase64: event.isBase64Encoded,
        outgoing: "data=" + enc(q),
        qSample: q.slice(0, 120)
      })
    };
  }

  // encodeURIComponent nie koduje (),*!~' – Overpass tego nie toleruje w form-urlencoded.
  const enc = (s) =>
    encodeURIComponent(s).replace(/[()*!~']/g, (c) =>
      "%" + c.charCodeAt(0).toString(16).toUpperCase());

  const backends = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter"
  ];

  // Wyścig: pierwszy działający backend wygrywa (mieści się w limicie 10s Netlify).
  const controllers = [];
  const requests = backends.map((url) => {
    const c = new AbortController();
    controllers.push(c);
    return (async () => {
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "User-Agent": "cisza-proxy/1.0",
          "Accept": "*/*"
        },
        body: "data=" + enc(q),
        signal: AbortSignal.timeout(8000)
      });
      if (!resp.ok) throw new Error("HTTP " + resp.status + " (" + url + ")");
      return await resp.text();
    })().catch((e) => { c.abort(); throw e; });
  });

  try {
    const text = await Promise.any(requests);
    controllers.forEach((c) => c.abort());
    return {
      statusCode: 200,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*"
      },
      body: text
    };
  } catch (e) {
    const all = Array.isArray(e.errors) ? e.errors.map(String).join("; ") : (e.message || String(e));
    return {
      statusCode: 502,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ error: all || "brak odpowiedzi Overpass" })
    };
  }
};
