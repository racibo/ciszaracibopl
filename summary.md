# CiszaRaciBoPL — podsumowanie projektu (przypięte)

Aplikacja: **https://racibo.github.io/ciszaracibopl/** (GitHub Pages z brancha `master`).
Lokalnie: `python app.py` → http://localhost:5000 (serwuje `index.html` + `tiles/`).

## Cel
Mapa hałasu wokół dowolnego punktu w Polsce (Trójmiasto ma statyczny cache, reszta Polski
przez live Overpass). Model: dyskretyzacja dróg/torów na odcinki 20 m, 48 promieni (co 7,5°),
rozszerzenie `1/r²` (geometryczne), osłona budynkowa (ray-casting), osłona terenu (wał/ekskarpata
z OSM `man_made=embankment`), lokalny `terrain_slope_m` ze STACJA.txt. Wynik: Lden w dB, z
rozbiciem na drogi/kolej/teren, plus tabela i mapa wkładu każdego źródła.

## Kluczowe funkcje (index.html)
- `fetchWays(lat,lng,radius,group)` — dla Trójmiasto czyta `tiles/...json` (Geofabrik, monthly
  przez GitHub Action `cache.yml`); dla reszty Polski live Overpass, z fallbackiem do cache.
- `aggregateLine(p, geom, base, polys, ...)` — zwraca `segs[]` (każdy: dist, angle, att, weight,
  baseAtt, blocked, visible, redBuild, terrainFactor, redTerrain), `energy`, `energyUnblocked`,
  `closest`, `distMin`, `redDist`, `redBud`, `redTer`, `screenFrac`, `level`, `basePct`.
- `runPipeline(p)` — pipeline 1/3…2d/3; buduje `sources`, rysuje mapę, pajęczynę, tabelę, score.
- `score`: suma `eff*energy` (eff = visible×distance≈unblocked×factor); jeśli `scoreEnergy=0`
  → tryb "brak dróg" (info, nie błąd). Rezerwa: 38 dB dla terenu, 30 dB dla tła.
- `applyTerrainSlopeCorrection` / `readLocalTerrainSlope` — korekta Lden = base + 10·log10(1+slope/100).

## Co do tej pory zrobiliśmy (historia)
1. Model `1/r²` zamiast `1/r` (zgodny z akustyką źródła liniowego); zakaz `energy=0`.
2. Sumowanie obu kierunków tej samej ulicy po `name+group` (usuwa "wybiórcze odcinki").
3. Osłona terenu (wał): `redTer` 0–1 (domyślnie ~0.4), `terrainFactor`, korekta +2.5/+5 dB
   dla nasypu, tabela + mapa uwzględniają `redTer`.
4. Lokalny `terrain_slope_m` ze STACJA.txt (np. 2.8 dla Gdańsk-Śródmieście) → korekta +0.4…1.2 dB.
5. Poprawki wizualne: gradient rysowany tylko dla odcinków w promieniu mapy; tooltipy z dB;
   tabela z dystansem, osłoną budynkową i terenem; pajęczyna kolorowana wg dB.
6. Tryb "brak dróg w promieniu" (score energia=0) pokazuje info zamiast błędu.
7. Rozbudowa tabeli: `visible`, `blocked`, `redDist`, `redBud`, `redTer`, `base_pct`, `level`,
   `energy`, sortowanie wg `eff*energy`, oznaczanie źródeł osłoniętych wałem.
8. Statyczny cache Trójmiasto z Geofabrik (`scripts/build-cache-geofabrik.py`, workflow `cache.yml`).

## Analiza (dlaczego bliski, odsłonięty odcinek nie był pokazywany)
Bliski odcinek dwupasmówki (~120 m, odsłonięty) był analizowany (jest w `sources` i wchodzi w
score), ale **nie był wizualizowany**. Przyczyny:
1. **Mapa rysuje tylko top 8 źródeł wg całkowitej energii** — długa, cichsza droga wygrywa z
   krótkim, bliskim odcinkiem (energia sumuje się z długości, nie z bliskości).
2. **Pajęczyna filtruje `level > 35`** — krótki odcinek ma niską całkowitą energię → znikał.
3. **Tabela pokazuje tylko top 6** — bliski krótki odcinek poza listą.
4. **Grupowanie unnamed way-ów po zaokrąglonych współrzędnych** (`Math.round(closest*1000)`)
   — niestabilne; mogło rozbijać jeden way na klucze.
5. (Hipotetycznie) **Starość cache** — dla Trójmiasto cache z Geofabrik, odświeżany monthly;
   clear localStorage nic nie da (cache statyczny jest władczy), ew. trzeba przebudować kafelki.

## Poprawki właśnie wprowadzone (commit 3dd2267)
- `index.html:1174` — `drawList`: rysuj **wszystkie** źródła w promieniu `ANALYSIS_R`
  (limit 25, sortowane wg energii) zamiast top 8 → bliskie/krótkie/odsłonięte nie znikają.
- `index.html:1251` — tabela: oprócz top 6 dopisujemy źródła `dist <= 300 m` (`nearSrc`)
  oraz osłonięte wałem (`bermSrc`), limit 10.
- `index.html:1283` — pajęczyna: pokazuj bliskie (`dist <= 400 m`) zawsze, dalsze gdy
  `level > 30` (próg obniżony z 35).
- `index.html:975` + `:1010` — grupowanie unnamed way-ów po stabilnym `el.id`
  (`group|#id`) zamiast zaokrąglonych współrzędnych.
- Deploy: push na `master` → GitHub Pages.

## Jak zweryfikować (punkt 54.405730, 18.570462)
Po wdrożeniu (kilka minut na GitHub Pages) kliknij w ten punkt. Bliska dwupasmówka powinna
teraz być na mapie (cieńsza linia + gradient), w pajęczynie (nitka do punktu) i w tabeli.
Jeśli wciąż jej brak → to kwestia danych (brak way-a w kafelku Geofabrik) — sprawdź w
https://www.openstreetmap.org/ czy droga istnieje; w razie potrzeby przebuduj kafelki
(ręczne uruchomienie workflow `cache.yml`).
