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
   Nadal NIEZWERYFIKOWANE (poprawki dotyczyły UI/progów, nie danych) — zob. Droga krajowa.

## Poprawki (commit 3dd2267) — UI/progi
- `drawList`: rysuj wszystkie źródła w `ANALYSIS_R` (limit 25) zamiast top 8.
- Tabela: + źródła `dist<=300 m` i osłonięte wałem (limit 10).
- Pajęczyna: bliskie (`<=400 m`) zawsze, dalsze gdy `level>30`.
- Próba grupowania unnamed po `el.id` (`group|#id`) — **MARTWY KOD** (zob. bug #1 niżej).

## Poprawki (commit e9920a7) — właściwe bugi
**Bug #1 (główny): fallback nazwy zabijał grupowanie po id.** `cands.push` nadpisywał
`name` etykietą (`GROUP_LABEL[group]`), więc `c.name` było zawsze prawdziwe i gałąź
`group|#id` nigdy się nie wykonywała → nienazwane tory tramwajowe (OSM nie ma `name` na
way-u, nazwa jest na relacji) zlewały się w jedno "megaźródło" na promień CUTOFF (tramwaj
1000 m). Jego `closest` to dowolny wygrany fragment, nie realnie najbliższy.
Poprawka: `name: tags.name || null` + osobna `label: tags.name || GROUP_LABEL[group]`;
akumulator i `raw` trzymają obie; klucz grupowania teraz działa (`null`→`group|#id`).

**Bug #2: kolizja klucza `group|name` przy rysowaniu i w tabeli.** `coneByKey[key]=grp`
nadpisywał się → przy wielu źródłach z tą samą nazwą wygrywał ostatni (najsłabszy, zwykle
najdalszy) → kliknięcie w tabeli (`focusCone`) pokazywało najdalszy punkt linii.
Poprawka: każde źródło dostaje unikalne `uid: 'src'+n` (w pętli `raw`), używane wszędzie
zamiast `group|name` — rysowanie, tabela (`key`), `focusCone`, tooltipy/pajęczyna używają `label`.
Dodano `console.table(sources.map(...))` do diagnostyki bez zgadywania.

Efekt: tramwaj rozdziela się na fizyczne odcinki; dominujące źródło to realnie najbliższe/
najgłośniejsze; kliknięcie w tabeli przybliża właściwy stożek.

## Droga krajowa (hipoteza #5 — WERYFIKOWANA: brak błędu)
Offline-parsing `tiles/8_5.json` (cache Geofabrik) dla domu (54.405150, 18.567941):
Aleja Grunwaldzka (`highway=primary`) przebiega na **NE (azymut 28-46°), 195-237 m** od
domu (way 277203727: 195 m/45°, 277203730: 215 m/46°, 61804798: 237 m/28°, 978107667: 218 m/34°).
**NIE MA jej w azymucie 75°/170 m.** Skan źródeł z domu (55-95°/250 m) pokazał tylko
`Droga lokalna` (45-114 m: src38, src28, src30, src11, src50, src41, src27) + boisko 103 m.
→ Tabela `185 m · NE (40°)` jest **POPRAWNA**; użytkownik pomylił kierunek (E zamiast NE)
i drogę (lokalna zamiast krajowa). Żaden błąd kodu/da­nych. `przesłonięte: 94%` to średnia
źródła, nie punktu `closest`. Jeśli droga na E to wg użytkownika Grunwaldzka — do sprawdzenia
tag `highway=` na openstreetmap.org (jeśli `residential`→`lokalna` jest OK).

## BŁĄD KRYTYCZNE: obcięcie danych na granicy kafelka (commit 2fce91f)
**Objaw:** Grunwaldzka w azymucie 90°/167 m (droga wojewódzka, 4 pasy) nie pojawiała się;
tabela pokazywała ją tylko na NE/194 m. Użytkownik słusznie podejrzewał, że "linia zatrzymuje
się na lokalnej drodze i nie idzie dalej".
**Przyczyna:** `fetchWays`/`fetchBuildings`/`fetchPOI` ładowały **tylko jeden kafelek**
(`loadStaticTile(lat,lon)` → `tiles/<gx>_<gy>.json` punktu). Dom w komórce 8_5, ale
wschodnia część Grunwaldzkiej (way 430542807, az 62-82°/167-205 m) leży w komórce **9_5**
(punkt 18.5706 → gx=9). Kafelek 9_5 zawiera ten way (sprawdzone offline), ale 8_5 nie →
droga w sąsiedniej komórce (mimo 167 m od domu!) znikała z analizy.
**Naprawa:** `loadStaticTileBlock(lat,lon,radius)` ładuje blok komórek pokrywający `radius`
(±2 lon / ±1 lat dla 2000 m), scala z **deduplikacją po id** (way może być w kilku
komórkach → bez dedupe podwójna energia). `fetchWays`/`fetchBuildings`/`fetchPOI` używają
bloku. Dla poza Trójmiastem (center=null) → fallback do live Overpass (bez zmian).
**Weryfikacja:** kliknij dom → w konsoli `window.__lastSources` powinno zawierać Grunwaldzką
z `closest` w azymucie ~75-82°/~170 m (droga wojewódzka, głośniejsza od lokalnej 60 m).


- `window.__lastSources` / `window.__lastPoint` — inspekcja w konsoli po kliknięciu.
- Skrypt skanujący źródła w paśmie azymutu/odległości od domu (wykrywa brakujące fragmenty).
- Cache offline: `tiles/<gx>_<gy>.json`, `gx=round((lon-18.40)/0.02)`, `gy=round((lat-54.30)/0.02)`.


## Jak zweryfikować (punkt 54.405730, 18.570462)
Po wdrożeniu (kilka minut na GitHub Pages) kliknij w ten punkt. Bliska dwupasmówka powinna
teraz być na mapie (cieńsza linia + gradient), w pajęczynie (nitka do punktu) i w tabeli.
Jeśli wciąż jej brak → to kwestia danych (brak way-a w kafelku Geofabrik) — sprawdź w
https://www.openstreetmap.org/ czy droga istnieje; w razie potrzeby przebuduj kafelki
(ręczne uruchomienie workflow `cache.yml`).

## Usprawnienia UX (commit po 2fce91f)
1. **Panel ustawień zwinięty** (`<details>` bez `open`) — przestał zajmować miejsce w
   wynikach; suwaki (zasięg/wał/threads) nadal działają (readSettings czyta po id).
   **Sidebar poszerzony do 480px**, tabela `table-layout:fixed` + mniejszy font → brak
   przewijania poziomego. Dodany przełącznik `showHistory` (mapa hałasu).
2. **Opisowa skala hałasu + porównania**: `scale-legend` wzbogacone o analogie dB
   (szept 30 / rozmowa 60 / ulica 70 / autostrada 80). `dbAnalogy(level)` zwraca frazę
   (np. "jak główna droga w szczycie"); użyta w `buildAssessment` i w nowym `#noiseScale`
   ("Twój wynik to X dB – [analogia].").
 3. **Nitki pajęczyny kolorowane na skali zielona→czerwona** (`levelColor` wg poziomu dB) —
    wszystkie nitki mają kolor z gradientu; najgłośniejsze (`loud = energy >= 0.4*maxE`)
    dodatkowo pogrubione (waga 4, pełna opakość), reszta cienkie przerywane.
4. **Mapa hałasu / przebadane miejsca**: `saveHistory(lat,lng,score,level)` →
   `localStorage[cisza_history_v1]` (do 300 pkt). `historyLayer` (L.layerGroup) rysuje
   kolorowe `circleMarker` (kolor wg `scoreColor`, promień rośnie z wynikiem) z popupem.
   Przełącznik `showHistory` (domyślnie włączony) + link "wyczyść" (`clearHistory`).
 5. **Źródła punktowe (POI) + hałas okresowy**: szkoły/boiska/stadiony uwzględniane (już
    były), teraz **zawsze pokazywane w tabeli** (periodicSrc dopisane do topSrc, limit 12).
    W `buildAssessment` notatka okresowa: jeśli przyrost z powodu źródeł okresowych
    (`10*log10(tE/(tE-pE))`) ≥ 1 dB → "hałas rośnie o ok. X dB"; w przeciwnym razie (gdy
    źródła okresowe pomijalne vs suma, np. daleki szkolny obiekt) pokazuje ich własny
    poziom (`10*log10(pE)`) lub milczy — **nigdy nie pokazuje "0 dB"** (poprzedni błąd).

## Poprawki (bieżąca sesja)
- **Usunięto mylące "rośnie o ok. 0 dB"** — notatka okresowa warunkowa (przyrost ≥1 dB
  albo poziom własny ≥30 dB), w przeciwnym razie pusta.
- **Nitki pajęczyny**: wszystkie na gradient `levelColor` (zielona→czerwona); najgłośniejsze
  tylko pogrubione, nie wymuszają czystego czerwonego.
- **Panel edukacyjny "Decybele i zdrowie słuchu"** (zwijany `<details class="edu">` w
  sidebarze): logarytmiczna natura dB, tabela przykładów 30–130 dB, normy PL (40/30 dB dom,
  85 dB praca), wpływ na zdrowie (NIOSH/CDC), porady ochronne. Treść edukacyjna, nie
  zastępuje pomiaru akustycznego.

## Przebudowa wyników (bieżąca sesja – commit po 717ee4b)
- **Usunięto różę kierunkową (pajęczynę w wynikach)** — `drawRose` i `#roseWrap` usunięte;
  nitki na mapie (threadLayer) pozostają (kolor `levelColor`, najgłośniejsze pogrubione).
- **Wynik końcowy w decybelach, nie 0–100**: `scoreCircle` pokazuje `level_db` dB; pod nim
  **pasek zdrowotny** (`#dbGauge`) z gradientem zielona→czerwona i zaznaczonymi strefami
  (30 / 55 / 70·norma / 85⚠ / 120) oraz markerem na aktualnym poziomie (`#dbMarker`).
- **Tabela zwarta i wyraźna**: 4 kolumny (Źródło / Poziom dB / Tłumienia / Wkład),
  pogrubione czcionki (`#srcTable` CSS), tłumienia w jednej komórce.
- **Panel edukacyjny interpretuje wynik**: `eduInterpretation(level)` generuje dynamiczny
  opis (co oznacza X dB + wpływ na zdrowie wg progów 40/55/70/85/100), statyczna wiedza w
  zwiniętym `<details class="edu-sub">`.
- **Mapa hałasu (historia) opcjonalna i lokalna**: `showHistory` domyślnie **wyłączone**;
  markery w **ciągłym gradientzie HSL** (niski wynik=zieleń → wysoki=czerwień), `scoreColor`
  przerobione na `hsl((1-score/100)*120,65%,45%)`. Usunięto martwy `roseLayer`.

## Poprawki (commit po 7ce1c91)
- **BŁĄD: kolumna „Poziom" pokazywała `undefined dB`** — obiekty tabeli (`d.sources`/`top`)
  nie kopiowały pola `level` z surowych źródeł. Dodano `level: isFinite(s.level)?Math.round(s.level):null`
  do mapowania `top`; w tabeli `s.level != null ? s.level+' dB' : '—'`. `s.level` = poziom po
  redukcji odległości (czyli to, czego dotyczą nitki pajęczyny).
- **Panel „Co oznacza Twój wynik"**: `eduInterpretation(level)` podaje czy szkodzi zdrowiu,
  oraz **bezpieczny czas przebywania** (`safeExposureHours` wg NIOSH: 85 dB→8 h, –3 dB = 2× czasu).
- **Rozbicie osłon w opisie**: `buildAssessment` wylicza z tłumień energetycznych, który czynnik
  najbardziej redukuje dominantę (odległość / budynek i zieleń / ukształtowanie terenu) i podaje
  to w dB (np. „Najskuteczniej redukuje ten hałas odległość – o ok. 3 dB…").

## Poprawki (commit po 885f219)
- **Wyjaśnienie dlaczego źródła w tabeli mają niższy poziom niż wynik końcowy**: dodano
  stopkę pod tabelą – „Poziom" to własny hałas źródła po redukcjach; wynik końcowy sumuje
  WSZYSTKIE źródła + tło (30 dB) logarytmicznie, więc jest zawsze wyższy (poprawna akustyka).
- **Kolumna „Poziom" = efektywny poziom** `eff_level = s.level + 10·log10(terrainFactor)`
  (po odległości + budynkach + terenie), zgodny z tym, jak liczony jest wynik końcowy.
- **Nitki pajęczyny kolorowane wg efektywnego poziomu** (`levelColor(s.level+10·log10(terrainFactor))`),
  nie surowego `s.level` – najgroźniejsze źródło (po redukcjach) jest najbardziej czerwone;
  tooltip też pokazuje efektywny dB.
- **Opis dopasowany do poziomu**: `buildAssessment` nie pisze „hałas może przeszkadzać" dla
  cichego źródła (<45 dB); tekst zależy od efektywnego dB (nieodczuwalny / lekko słychać /
  przeszkadza). Usunięto mylące „poza osłoną budynkową".


