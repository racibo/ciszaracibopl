// Netlify Function: proxy do Overpass API.
// Rozwiązuje problemy z CORS (przeglądarka woła /api/overpass samoopisowo)
// i pozwala przymierzyć kilka backendów serwerowo (bez CORS).
exports.handler = async (event) => {
  let body;
  try {
    body = JSON.parse(event.body || "{}");
  } catch (e) {
    body = {};
  }
  const q = body.q;
  if (!q) {
    return { statusCode: 400, body: JSON.stringify({ error: "brak parametru q" }) };
  }

  const backends = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter"
  ];

  let lastErr = null;
  for (const url of backends) {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: "data=" + encodeURIComponent(q),
          signal: AbortSignal.timeout(12000)
        });
        if (!resp.ok) {
          lastErr = "HTTP " + resp.status + " (" + url + ")";
          continue;
        }
        const text = await resp.text();
        return {
          statusCode: 200,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
          },
          body: text
        };
      } catch (e) {
        lastErr = e.message + " (" + url + ")";
      }
    }
  }

  return {
    statusCode: 502,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ error: lastErr || "brak odpowiedzi Overpass" })
  };
};
