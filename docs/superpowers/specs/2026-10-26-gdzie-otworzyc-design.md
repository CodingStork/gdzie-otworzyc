# „Gdzie otworzyć?” — mapa okazji biznesowych — specyfikacja (design)

Data: 2026-10-26. Status: zatwierdzone w rozmowie z właścicielem projektu (Marcin).
Dokument wewnętrzny dla zespołu (czaty Claude). Źródła danych i ich zweryfikowane szczegóły: [docs/zrodla-danych.md](../../zrodla-danych.md).

---

## 1. Kontekst i cel

Projekt zaliczeniowy z przedmiotu **„Analiza danych przestrzennych”**. Wymagania prowadzącego:
- aplikacja (frontend + backend + model wnioskujący); oceniane przede wszystkim **wiedza z analizy danych przestrzennych**, potem jakość wykonania,
- kod w otwartym repozytorium (GitHub), oddawany **systematycznie** (regularne commity),
- „prace zrobione z AI bez głębokiego zrozumienia tematyki nie będą zaliczane” → **Marcin musi rozumieć każdy element**. Kod prosty, czytelny, z komentarzami objaśniającymi pojęcia przestrzenne; na końcu ściąga do obrony.

Ustalenia z właścicielem:
- **Model wnioskujący (ML) NIE jest obowiązkowy** — prowadzący zaakceptował temat. Priorytet: mapa i wykorzystanie danych. ML/Gi* — opcjonalne etapy na sam koniec, jeśli starczy czasu.
- Biznesy: **na start tylko OpenStreetMap**. Marcin złoży wniosek o token CEIDG — integracja później (architektura ma to przewidzieć: katalog typów zawiera kody PKD).
- Zasięg: **cała Polska** (dane przetwarzane raz lokalnie).
- Grupy biznesów: **usługi osobiste, budowlanka/dom, handel/gastro/sport** (bez grupy „zdrowie”).
- Hosting: komputer domowy Marcina (≥16 GB RAM, ≥20 GB dysku, Windows 11), dostęp z laptopa przez **Tailscale**.
- Heatmapa **na prawdziwej mapie** (podkład kafelkowy), estetycznie i czytelnie.

### Problem użytkownika
Osoba chce otworzyć działalność (np. salon kosmetyczny) albo znaleźć rejon do reklamy (np. brukarz). Chce wiedzieć, **gdzie jest dużo potencjalnych klientów i mało konkurencji**.

### Kryteria sukcesu v1
1. Użytkownik wybiera typ działalności, czynnik popytu, obszar (adres/klik + promień albo „cała Polska”) i w < 3 s dostaje heatmapę „klienci na 1 konkurenta” na mapie.
2. Widzi top 5 lokalizacji z nazwą osiedla/miejscowości, klik → przybliżenie.
3. Po kliknięciu heksagonu widzi liczby: popyt w zasięgu, konkurenci w zasięgu, wynik, percentyl.
4. Działa dla 16 typów działalności i 9 czynników popytu (sekcja 5).
5. Działa na laptopie na uczelni (Tailscale) i na telefonie (układ responsywny).
6. Jasno komunikuje ograniczenia danych (niekompletność OSM, pozwolenie ≠ wybudowany dom, spis z 2021).

### Poza zakresem v1
Konta użytkowników, płatne API, scrapowanie Google Maps (łamie ToS), dane o dochodach, ruch pieszy, ceny najmu.

---

## 2. Architektura

```
            (raz + odświeżanie co tydzień)                      (na żądanie)
 ┌────────────── ETL (Python) ───────────────┐      ┌──────── Backend FastAPI ────────┐     ┌──── Frontend ────┐
 │ Eurostat Census GRID 2021 → hex_pop        │      │ /api/catalog                    │     │ index.html       │
 │ Geofabrik poland.osm.pbf  → poi, places    │ ───▶ │ /api/analyze  (jądro Gaussa,    │ ──▶ │ Leaflet + h3-js  │
 │ GUNB RWDZ CSV + ULDK      → permits        │ DuckDB│   ranking, top-5)               │ JSON│ (bez buildowania)│
 │ agregacja do H3 res 8 → 7 → 6              │ plik │ /api/poi /api/geocode /api/meta │     │                  │
 └────────────────────────────────────────────┘      └─────────────────────────────────┘     └──────────────────┘
```

### Kluczowa decyzja: ETL zamiast scrapowania na żywo
Publiczne Overpass API blokuje automatyczne zapytania już po kilku żądaniach, ULDK odpowiada ~0,35 s na działkę. Dlatego wszystkie dane pobieramy hurtowo z otwartych plików, przetwarzamy raz do jednego pliku **DuckDB** (`data/app.duckdb`), a backend tylko liczy na gotowych tabelach. Dzięki temu „cała Polska” jest możliwa, a odpowiedź jest natychmiastowa.

### Wspólna siatka analityczna: H3
Wszystkie dane sprowadzamy do heksagonów **H3** (Uber). Powody (do obrony): równe odległości do sąsiadów (w odróżnieniu od kwadratów), hierarchia rozdzielczości (agregacja dziecko→rodzic), standard w analizie mobilności/usług.

| Rozdzielczość | Śr. pole | Odstęp środków | Użycie |
|---|---|---|---|
| 8 | 0,74 km² | ~0,8 km | analiza lokalna (promień ≤ 15 km), poziom bazowy ETL |
| 7 | 5,2 km² | ~2,1 km | promień 15–50 km |
| 6 | 36 km² | ~5,6 km | cała Polska (~9 tys. heksagonów) |

Identyfikatory H3 przechowujemy jako **stringi** (zgodne z h3-js w przeglądarce).

### Stack
- **Python 3.13** zarządzany przez **uv** (systemowy Python 3.15 jest za nowy dla części bibliotek geo — nie używać go).
- Backend: FastAPI + uvicorn. Biblioteki: `duckdb`, `numpy`, `pandas`, `pyarrow`, `scipy` (cKDTree), `pyproj`, `shapely`, `h3` (v4), `osmium` (pyosmium), `httpx`, `pytest`. Opcjonalnie później: `scikit-learn`, `esda`/`libpysal`.
- Frontend: czysty HTML + CSS + JS (moduły ES, bez Node, bez buildowania). CDN z przypiętymi wersjami: `leaflet@1.9.4`, `h3-js@4.1.0` (unpkg/jsdelivr). Backend serwuje frontend jako pliki statyczne.
- Układ współrzędnych do obliczeń odległości: **EPSG:2180 (PUWG 1992)** — metryczny, polski. Dane wejściowe: EPSG:3035 (siatka spisu), EPSG:4326 (OSM, ULDK, H3).

### Struktura repozytorium
```
backend/app/
  main.py            # FastAPI, montuje /api i statyczny frontend
  config.py          # ścieżki, stałe
  db.py              # połączenie DuckDB (read-only w runtime)
  catalog.py         # typy działalności + czynniki popytu (sekcja 5)
  analysis/
    kernel.py        # sumy ważone jądrem Gaussa (cKDTree, EPSG:2180)
    scoring.py       # wynik, percentyle, top-N z separacją
    resolution.py    # wybór rozdzielczości H3 i bufora
  api/routes.py      # endpointy
  services/geocode.py# proxy Nominatim z cache
etl/
  download.py        # pobieranie surowych plików do data/raw/
  population.py      # Census GRID → hex_pop (res 8)
  osm_poi.py         # pbf → poi, places, (opcjonalnie context)
  permits.py         # GUNB CSV → permits_raw
  geocode_obreby.py  # ULDK, cache, wznawialne
  aggregate.py       # res 8 → 7 → 6, tabele *_r7, *_r6
  run_all.py         # orkiestracja, idempotentne kroki, --force
frontend/
  index.html  css/style.css  js/{app,api,map,ui,colors}.js
tests/              # pytest, fixtures z małymi danymi
data/               # (gitignore) raw/, app.duckdb
docs/
start.bat           # uruchomienie serwera na Windows
```

Konwencje: identyfikatory w kodzie po angielsku, **komentarze i docstringi po polsku** (Marcin musi rozumieć), UI po polsku.

---

## 3. Dane i ETL

Szczegóły formatów, URL-e i pułapki: [docs/zrodla-danych.md](../../zrodla-danych.md). Każdy krok ETL jest idempotentny (pomija, jeśli wynik istnieje; `--force` wymusza) i loguje liczby rekordów.

### 3.1 Ludność → `hex_pop`
- Źródło: `ESTAT_Census_2021_V3.parquet` z ZIP-a Eurostat (566 MB ZIP; parquet w środku 76 MB).
- Filtr: `'PL' in CNTR_ID.split('-')`, `T > 0`.
- Wartości `-9999/-8888` w podkategoriach → imputacja: `T × udział krajowy` (M 0,483; F 0,515; Y_LT15 0,153; Y_1564 0,651; Y_GE65 0,187 — przeliczyć z danych w ETL, nie wpisywać na sztywno).
- **Interpolacja powierzchniowa** kwadrat 1 km → heksagony: każdą komórkę dzielimy na siatkę 5×5 punktów (co 200 m, środki podkomórek) w EPSG:3035, każdy punkt niesie 1/25 wartości, transformacja do WGS84, `h3.latlng_to_cell(res=8)`, sumowanie. (Założenie równomiernego rozkładu w komórce — ograniczenie do opisania; ulepszenie dasymetryczne budynkami OSM = opcja.)
- Kontrola: suma T w `hex_pop` = suma T wejścia (±0,1%).
- Schemat: `hex_pop(h3 VARCHAR PK, pop_total, pop_f, pop_m, pop_lt15, pop_1564, pop_ge65 DOUBLE)`.

### 3.2 Biznesy i nazwy miejsc → `poi`, `places`
- Źródło: `https://download.geofabrik.de/europe/poland-latest.osm.pbf` (~2 GB).
- pyosmium (`osmium.FileProcessor(...).with_locations()` + filtr kluczy `shop, amenity, craft, leisure, place`); dla dróg/obszarów (way) punkt = średnia współrzędnych węzłów (wystarczające dla budynków usługowych). Relacje pomijamy.
- Każdy obiekt dopasowujemy do typów z katalogu (sekcja 5) regułami tagów; obiekt może pasować do >1 typu (np. fryzjer i barber).
- `poi(osm_id VARCHAR, type_id VARCHAR, name VARCHAR, lat, lng DOUBLE, h3 VARCHAR)` — res 8.
- `places(name, kind, lat, lng, h3)` — `place ∈ {city, town, village, suburb, neighbourhood, quarter, hamlet}` — do nazywania top-5.
- Opcjonalnie (pod ML): `context(h3, n_shops_all, n_bus_stops, ...)`.

### 3.3 Nowe budowy → `permits_raw`, `permits`
- Źródła: 16 plików wojewódzkich (pozwolenia) + 2 pliki ogólnopolskie (zgłoszenia) z `wyszukiwarka.gunb.gov.pl/pliki_pobranie/`. **Różne schematy kolumn** — dwa osobne parsery.
- Filtr: `kategoria ∈ {I, XIII}` i rodzaj = „budowa nowego…”; wykluczyć zmiany pozwoleń (opis zawiera „zmian”); deduplikacja po `numer_gunb` / `numer_ewidencyjny_system`.
- Pola wyjściowe: `kind` (`sf` = jednorodzinny kat. I, `mf` = wielorodzinny kat. XIII), `date` (pozwolenia: `data_wydania_decyzji`; zgłoszenia: `data_wplywu_wniosku_do_urzedu`), `obreb_id` = `{jednostka}.{obreb zero-padded do 4}`, `terc`, `source` (`pozwolenie`/`zgloszenie`).
- Geokodowanie: `geocode_obreby.py` → ULDK `GetRegionById` (sprawdzone), centroid obrębu (shapely `representative_point()` żeby zawsze był wewnątrz) → H3 res 8. Cache w tabeli `obreb_geom(obreb_id PK, name, lat, lng, status)`; wznawialne; max 5 równoległych zapytań; retry z backoffem. Fallback dla nieznalezionych: gmina (`GetCommuneById` po `jednostka`), na końcu pominięcie z licznikiem w logu.
- Wynik: `permits(h3 VARCHAR, month DATE, kind VARCHAR, n INTEGER)`.
- Ograniczenie do opisania w UI: pozwolenie ≠ wybudowany dom (budowa trwa 1–3 lata, część nigdy nie startuje); lokalizacja z dokładnością do obrębu (miasto: dzielnica/osiedle, wieś: cała wieś).

### 3.4 Agregacja wielorozdzielcza
`aggregate.py`: z tabel res 8 tworzy `hex_pop_r7/r6`, `poi_counts_r8/r7/r6(h3, type_id, n)`, `permits_r7/r6` przez `h3.cell_to_parent`. Backend czyta wyłącznie gotowe tabele.

### 3.5 Metadane i odświeżanie
`meta(source, url, downloaded_at, version, rows)`. Endpoint `/api/meta` pokazuje świeżość danych w stopce UI. Odświeżanie OSM + GUNB co tydzień (ręcznie `run_all.py` albo Harmonogram zadań Windows — opcja). Census statyczny.

---

## 4. Analiza: wskaźnik „klienci na 1 konkurenta”

Model dostępności oparty na **estymacji jądrowej (KDE) / uproszczonym 2SFCA**:

Dla heksagonu analizowanego *i* i wszystkich heksagonów *j* w zasięgu:

- popyt w zasięgu: `D_i = Σ_j d_j · K(dist_ij)`
- konkurencja w zasięgu: `S_i = Σ_j s_j · K(dist_ij)`
- jądro Gaussa: `K(d) = exp(−d² / (2h²))`, obcięte dla `d > 3h`
- **wynik: `score_i = D_i / (S_i + 1)`** („ilu potencjalnych klientów przypada na jednego konkurenta w zasięgu”; +1 to wygładzenie, żeby brak konkurencji nie dawał nieskończoności)

gdzie `d_j` = wartość czynnika popytu w heksagonie (np. liczba kobiet albo nowych domów z ostatnich *m* miesięcy), `s_j` = liczba firm danego typu, `h` = szerokość pasma (zasięg klienta) — domyślna z katalogu, zmienialna suwakiem.

Algorytm `/api/analyze`:
1. Wybór rozdzielczości: promień ≤ 15 km → res 8; ≤ 50 km → res 7; „cała Polska” → res 6. Efektywne `h = max(h_typu, 0,6 × odstęp heksagonów)`.
2. Pobranie heksagonów w obszarze **plus bufor 3h** (unikamy **efektu krawędzi** — konkurent tuż za granicą obszaru też się liczy).
3. Środki heksagonów → EPSG:2180, `scipy.spatial.cKDTree`, `query_ball_point(r=3h)`, sumy ważone (wektorowo w numpy).
4. Wynik i percentyl liczone tylko dla heksagonów w obszarze (bez bufora).
5. **Top-5**: najwyższy wynik pośród heksagonów z `D_i ≥ 25. percentyl D` w obszarze (żeby nie polecać lasów, gdzie nie ma ani klientów, ani konkurencji), z separacją ≥ 2h między wybranymi (non-maximum suppression). Nazwa = najbliższe `places` ≤ 3 km (preferencja: suburb/neighbourhood/village > town > city).
6. Ostrzeżenia: `osm_quality` typu = `poor` → komunikat; obszar bez danych → komunikat.
7. Cache wyników w pamięci (LRU, klucz = parametry zaokrąglone).

Warstwy w UI z jednej odpowiedzi: **Okazja** (`score`), **Popyt** (`D`), **Konkurencja** (`S`).

### Pojęcia do obrony (wpisać w komentarze i ściągę)
KDE i wybór szerokości pasma, efekt krawędzi i bufor, MAUP (problem modyfikowalnej jednostki przestrzennej — dlatego H3 + kernel zamiast granic gmin), interpolacja powierzchniowa, układy współrzędnych (3035 / 2180 / 4326) i dlaczego odległości liczymy w metrycznym, model 2SFCA, geokodowanie, kompletność danych VGI (OSM).

---

## 5. Katalog: typy działalności i czynniki popytu

Plik `backend/app/catalog.py` — jedno źródło prawdy, używane przez ETL (reguły tagów) i API. Kody PKD = PKD 2007 (pod przyszłe CEIDG; od 2025 obowiązuje PKD 2025 — mapowanie zweryfikować przy integracji CEIDG).

### Czynniki popytu
| id | nazwa w UI | źródło | uwagi |
|---|---|---|---|
| `pop_total` | Mieszkańcy | Census T | |
| `pop_f` | Kobiety | Census F | |
| `pop_m` | Mężczyźni | Census M | |
| `pop_lt15` | Dzieci (<15 lat) | Census Y_LT15 | |
| `pop_1564` | Osoby 15–64 lata | Census Y_1564 | |
| `pop_ge65` | Seniorzy (65+) | Census Y_GE65 | |
| `new_sf` | Nowe domy jednorodzinne | GUNB kat. I | okres: 12 / 24 / 36 mies. (domyślnie 24) |
| `new_mf` | Nowe bloki (wielorodzinne) | GUNB kat. XIII | liczba inwestycji, nie mieszkań (brak liczby lokali w danych) |
| `new_all` | Wszystkie nowe budynki mieszkalne | GUNB I + XIII | |

### Typy działalności
| grupa | id | nazwa | reguła tagów OSM | PKD 2007 | domyślny popyt | h [km] | jakość OSM |
|---|---|---|---|---|---|---|---|
| Usługi osobiste | `hairdresser` | Fryzjer | `shop=hairdresser` | 96.02.Z | pop_total | 1,5 | medium |
| | `barber` | Barber | `shop=hairdresser` + `hairdresser=barber` lub `male=yes`; `shop=barber` | 96.02.Z | pop_m | 2 | poor |
| | `beauty` | Salon kosmetyczny | `shop=beauty` | 96.02.Z | pop_f | 1,5 | medium |
| | `nails` | Stylizacja paznokci | `shop=beauty` + `beauty=nails`; `shop=nails` | 96.02.Z | pop_f | 1,5 | poor |
| | `tattoo` | Studio tatuażu | `shop=tattoo` | 96.09.Z | pop_1564 | 5 | medium |
| Budowlanka / dom | `paving` | Brukarstwo | `craft=paver`; `craft=stonemason` | 43.99.Z | new_sf | 15 | poor |
| | `garden` | Ogrody i zieleń | `craft=gardener`; `shop=garden_centre` | 81.30.Z | new_sf | 15 | poor |
| | `windows` | Okna i drzwi | `shop=windows`; `shop=doors`; `craft=window_construction` | 43.32.Z | new_all | 15 | poor |
| | `diy` | Market / hurtownia budowlana | `shop=doityourself`; `shop=hardware`; `shop=trade` + `trade=building_supplies` | 47.52.Z | new_all | 15 | good |
| | `kitchen` | Meble kuchenne / stolarz | `shop=kitchen`; `craft=carpenter`; `craft=joiner` | 31.02.Z | new_all | 10 | poor |
| | `installer` | Instalatorzy (hydraulik, elektryk) | `craft=plumber`; `craft=electrician`; `craft=hvac` | 43.22.Z | new_all | 10 | poor |
| Handel / gastro / sport | `grocery` | Sklep spożywczy | `shop=convenience`; `shop=supermarket` | 47.11.Z | pop_total | 1 | good |
| | `cafe` | Kawiarnia | `amenity=cafe` | 56.30.Z | pop_1564 | 1,5 | good |
| | `restaurant` | Restauracja / fast food | `amenity=restaurant`; `amenity=fast_food` | 56.10.A | pop_total | 2 | good |
| | `fitness` | Siłownia / fitness | `leisure=fitness_centre`; `leisure=sports_centre` + `sport=fitness` | 93.13.Z | pop_1564 | 3 | medium |
| | `kindergarten` | Przedszkole / żłobek | `amenity=kindergarten`; `amenity=childcare` | 85.10.Z | pop_lt15 | 2 | good |

Każdy typ ma też listę „sugerowanych” czynników popytu (pierwszy = domyślny), np. `kindergarten`: pop_lt15, new_sf, new_all. Użytkownik może wybrać dowolny czynnik.

Komunikat dla `osm_quality = poor`: „Dane o firmach tego typu w OpenStreetMap są bardzo niepełne. Traktuj mapę głównie jako mapę popytu.”

---

## 6. API

| Metoda | Ścieżka | Parametry | Zwraca |
|---|---|---|---|
| GET | `/api/health` | — | `{status:"ok"}` |
| GET | `/api/catalog` | — | grupy → typy (`id,name,default_demand,suggested_demands,bandwidth_km,osm_quality,warning`), czynniki popytu (`id,name,source,needs_months`) |
| GET | `/api/analyze` | `type, demand, lat, lng, radius_km (1–50)` **lub** `scope=poland`; opcjonalnie `bandwidth_km, months (12/24/36)` | `{res, bandwidth_km, hexes:[[h3, score, D, S, d, s, pct], …], top:[{h3,lat,lng,name,score,D,S}], stats:{n_hex, n_competitors, total_demand, score_quantiles}, warnings:[…]}` |
| GET | `/api/poi` | `type, bbox=minLng,minLat,maxLng,maxLat` | `[{lat,lng,name}]` (limit 5000; więcej → `truncated:true`) |
| GET | `/api/geocode` | `q` | `[{name, lat, lng}]` — proxy do Nominatim (`countrycodes=pl`, nagłówek User-Agent, max 1 zapytanie/s, cache) |
| GET | `/api/meta` | — | świeżość źródeł + atrybucje |

Błędy: 422 przy złych parametrach (komunikat po polsku), 503 gdy brak bazy (`app.duckdb` nie zbudowana) z instrukcją uruchomienia ETL.

Hexy wysyłamy jako kompaktowe tablice (bez geometrii) — przeglądarka liczy kształty przez `h3.cellToBoundary`.

---

## 7. Frontend / UI

Makieta zatwierdzona w rozmowie: **panel boczny po lewej (~300 px) + mapa na resztę ekranu**.

Panel boczny (od góry):
1. Tytuł „Gdzie otworzyć?”
2. **Typ działalności** — `<select>` z `<optgroup>` per grupa.
3. **Porównaj z** — `<select>` czynników popytu; po zmianie typu ustawia domyślny i oznacza sugerowane; dla `new_*` pojawia się wybór okresu 12/24/36 mies.
4. **Obszar** — pole wyszukiwania adresu (z podpowiedziami z `/api/geocode`) lub klik na mapie stawia pinezkę; suwak promienia 1–50 km (okrąg na mapie); checkbox „Cała Polska”.
5. Zaawansowane (zwinięte): suwak „zasięg klienta” (h).
6. Przycisk **Analizuj** (jedyny akcentowany).
7. **Najlepsze miejsca** — top-5: nazwa, wynik („2 140 klientów / konkurenta”); klik = przelot mapy + podświetlenie.
8. Ostrzeżenia (żółty box) i stopka: świeżość danych + atrybucje (OSM, Eurostat, GUNB, GUGiK).

Mapa (Leaflet, `preferCanvas: true`):
- Podkład **CARTO Positron bez etykiet** (`light_nolabels`) → pane z heksagonami (półprzezroczyste, suwak przezroczystości) → pane z **etykietami CARTO** (`light_only_labels`, `pointer-events:none`) nad heksagonami → punkty konkurencji (małe koła, kolor kontrastowy).
- Przełącznik warstw (prawy górny róg): Okazja / Popyt / Konkurencja + checkbox „Punkty firm” (`/api/poi` dla bieżącego widoku, dopiero od zoomu ≥ 11).
- Skala kolorów: sekwencyjna (jedna barwa, jasna → ciemna), **klasy kwantylowe (5)** liczone w obszarze; legenda z wartościami granic.
- Klik w heksagon → popup: popyt w zasięgu, konkurenci w zasięgu, wynik, percentyl.
- Stan w URL hash (`#type=beauty&demand=pop_f&lat=…&lng=…&r=10`) → link można wysłać innym.
- < 768 px: panel staje się wysuwanym arkuszem na dole.
- Stany: ładowanie (spinner na przycisku), brak wyników, błąd API (komunikat po polsku), brak bazy (instrukcja).

Atrybucja na mapie: „© OpenStreetMap contributors © CARTO | Ludność: © EU, Eurostat GISCO (Census 2021, zmodyfikowane) | Pozwolenia: GUNB RWDZ | Geokodowanie: GUGiK ULDK”.

---

## 8. Uruchamianie i hosting

- `uv sync` → `uv run python -m etl.run_all` (jednorazowo kilka godzin; najdłużej: OSM pbf i geokodowanie obrębów) → `start.bat` (`uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`).
- Zapora Windows: zezwolić na port 8000 dla sieci prywatnej / interfejsu Tailscale.
- Tailscale na PC i laptopie → `http://<nazwa-pc>:8000` (MagicDNS). Opcjonalnie `tailscale funnel 8000` → publiczny link dla prowadzącego.
- `data/` w `.gitignore`; w README instrukcja odtworzenia bazy.

---

## 9. Testy

- `pytest`, małe fixture'y w `tests/fixtures/` (wycinki prawdziwych CSV GUNB z pułapkami: zduplikowane nagłówki, nowe linie w cudzysłowach, wiersze „zmiana pozwolenia”; kilka komórek spisu z -9999; przykładowe odpowiedzi ULDK).
- Jednostkowe: parsowanie `GRD_ID`, imputacja, interpolacja (zachowanie sumy), parsery GUNB, normalizacja `obreb_id`, parser odpowiedzi ULDK, dopasowanie tagów OSM do typów, jądro (wartości na syntetycznej siatce z ręcznie policzonym wynikiem), efekt krawędzi (bufor), top-N z separacją, wybór rozdzielczości.
- Integracyjne: API na małej bazie testowej budowanej w fixture (`TestClient`).
- Frontend: ręczna weryfikacja w przeglądarce (desktop + widok mobilny) po każdym etapie UI.

---

## 10. Etapy (każdy kończy się działającą aplikacją i commitami)

| # | Etap | Rezultat |
|---|---|---|
| M0 | Szkielet: repo, uv, FastAPI, pusta mapa Leaflet z podkładem Positron, start.bat | strona działa lokalnie i przez Tailscale |
| M1 | ETL ludności → `hex_pop`; `/api/analyze` z samym popytem; heatmapa popytu w UI | pierwsza prawdziwa heatmapa |
| M2 | ETL OSM (`poi`, `places`) + katalog + wynik + popup + top-5 + warstwy + punkty firm | **MVP** dla usług osobistych i handlu/gastro |
| M3 | ETL GUNB + geokodowanie obrębów + czynniki `new_*` z wyborem okresu | budowlanka działa |
| M4 | Tryb „cała Polska” (res 6/7), wyszukiwarka adresów, URL hash, mobile, ostrzeżenia, `/api/meta`, cache | wersja do oddania |
| M5 | README po polsku (dla prowadzącego) + `docs/sciaga-do-obrony.md` (wyjaśnienie metod prostym językiem) | gotowe do zaliczenia |
| M6* | Warstwa „Trend” dla budowlanki (ostatnie 12 mies. vs poprzednie 12) | opcja |
| M7* | Hot-spoty Getis-Ord Gi* (esda, wagi z sąsiedztwa H3) — obrys istotnych skupisk okazji | opcja |
| M8* | Model ML „luki rynkowej” (HistGradientBoosting z loss=poisson, przestrzenna walidacja krzyżowa po województwach, warstwa oczekiwane − rzeczywiste) | opcja (model wnioskujący) |
| M9* | Integracja CEIDG (gdy przyjdzie token) jako drugie źródło konkurencji + geokodowanie adresów | opcja |
| M10* | Dokładne geokodowanie działek dla ostatnich 24 mies. | opcja |

(* = opcjonalne, decyzja Marcina po M5)

---

## 11. Ryzyka

| Ryzyko | Skutek | Mitygacja |
|---|---|---|
| Niekompletność OSM (np. Opole: 30 salonów fryzjersko-kosmetycznych) | zawyżony wynik okazji | `osm_quality` + ostrzeżenia; CEIDG w M9 |
| ULDK niedostępne / limity | ETL budowlanki staje | cache, wznawianie, throttling, fallback do gminy |
| Zmiana formatu CSV GUNB | parser się sypie | walidacja nagłówków z czytelnym błędem; testy na fixture'ach |
| Spis z 2021 | dane starzeją się | komunikat w UI; nowe domy z GUNB częściowo to kompensują |
| Pozwolenie ≠ wybudowany dom | nadmierny optymizm | opis w UI i ściądze do obrony |
| Wydajność widoku całej Polski | wolne rysowanie | res 6, canvas renderer, kompaktowy JSON |
| Polityka Nominatim | blokada wyszukiwarki | proxy z cache, 1 zapytanie/s, User-Agent z nazwą projektu |
| Python 3.15 na komputerze | brak kół bibliotek | uv z przypiętym Pythonem 3.13 |
