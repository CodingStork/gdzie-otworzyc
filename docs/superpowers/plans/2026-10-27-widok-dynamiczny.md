# „Gdzie otworzyć?” v2 — mapa dynamiczna Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przebudować aplikację tak, by heatmapa liczyła się dla widocznego fragmentu mapy z heksagonami zależnymi od przybliżenia, zasięgiem-okręgiem, ludnością rozłożoną na budynki, płynnym gradientem, trybami jednego wyboru i dymkiem z dokładnymi liczbami dla klikniętego punktu.

**Architecture:** ETL dostaje krok `buildings` (wagi budynków mieszkalnych z OSM) i liczy ludność dasymetrycznie do H3 res 9; wszystkie tabele mają bazę res 9 i agregaty 8–5 z kolumnami `lat,lng`. Backend: `/api/view` (bbox + zoom → heksagony `display_res`, liczone na `compute_res` i agregowane) i `/api/point` (dokładne liczby w okręgu). Frontend: auto-odświeżanie na `moveend`, dwa naprzemienne pane'y do płynnego przejścia między rozdzielczościami, gradient wg percentyla, jedno kliknięcie mapy = dymek punktu.

**Tech Stack:** bez zmian względem v1 (Python 3.13/uv, FastAPI, DuckDB, numpy, scipy cKDTree, pyproj, h3 v4, pyosmium; Leaflet 1.9.4, h3-js 4.1.0, Esri Light Gray).

**Spec:** [docs/superpowers/specs/2026-10-27-widok-dynamiczny-design.md](../specs/2026-10-27-widok-dynamiczny-design.md) (czytaj w całości — zawiera dokładne teksty UI). Kontekst v1: [spec v1](../specs/2026-10-26-gdzie-otworzyc-design.md), [plan v1](2026-10-26-gdzie-otworzyc.md), [źródła danych](../../zrodla-danych.md), [raport ETL](../../raport-etl.md).

## Global Constraints

- Wszystkie Global Constraints planu v1 obowiązują (uv + Python 3.13 — `uv` jest w PATH użytkownika; w razie braku pełna ścieżka: `C:\Users\Marcin\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`; komentarze/docstringi po polsku objaśniające pojęcia; UI po polsku; brak Node; commit po każdym tasku z `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`).
- Teksty UI z spec §5 — **dosłownie**.
- Mapowanie zoom → `display_res`: `{≤6: 5, 7: 6, 8: 6, 9: 7, 10: 8, 11: 8, ≥12: 9}`.
- `HEX_SPACING_KM = {9: 0.30, 8: 0.80, 7: 2.11, 6: 5.6, 5: 14.8}`.
- Krok przyciągania bbox: `SNAP_DEG = {5: 2.0, 6: 1.0, 7: 0.5, 8: 0.25, 9: 0.1}`.
- Limity `compute_res`: komórek ≤ 800 000, par ≤ 30 000 000. Średnie pole komórki [km²]: `{9: 0.105, 8: 0.737, 7: 5.16, 6: 36.1, 5: 252.9}`.
- Zasięg klienta: 0,1–20 km; dla `demand.source == "permits"` efektywnie `max(r, 1.0)`.
- Paleta gradientu (YlGnBu 9): `['#ffffd9','#edf8b1','#c7e9b4','#7fcdbb','#41b6c4','#1d91c0','#225ea8','#253494','#081d58']`.
- Serwer i ETL nie mogą działać jednocześnie (blokada DuckDB). Przed krokami ETL zatrzymaj serwer.
- NIE pushuj, NIE dodawaj remote.

## Review Focus

1. **Widok bez danych** (morze, zagranica, sam las) → 200 z pustą listą heksagonów, bez wyjątku; legenda ukryta. Test: `test_view_empty_area` (Task 5).
2. **Tylko typ / tylko popyt / żaden** → odpowiednio warstwa S / D; brak obu → 422 „Wybierz typ działalności albo czynnik popytu”. Testy: `test_view_modes`, `test_view_requires_one` (Task 5).
3. **Mały zasięg (0,1 km) przy widoku całej Polski** → `compute_res` grubsze niż 9, w odpowiedzi notatka o przybliżeniu; brak eksplozji pamięci. Test: `test_view_country_small_radius_note` (Task 5).
4. **Kliknięcie punktu bez firm i bez mieszkańców w okręgu** → dymek z zerami, `score` = 0, pusta lista najbliższych. Test: `test_point_empty` (Task 6).
5. **Baza zablokowana przez ETL** → 503 z komunikatem z spec §4. Test: `test_locked_db_returns_503` (Task 7).

---

### Task 1: Wagi budynków mieszkalnych z OSM (`buildings`)

**Files:**
- Create: `etl/buildings.py`, `tests/test_buildings.py`
- Modify: `tests/fixtures/tiny.osm` (dopisz budynki), `etl/run_all.py` (nowy krok `buildings` po `osm`)

**Interfaces:**
- Produces:
  - `RESIDENTIAL = {"house","detached","semidetached_house","terrace","bungalow","residential","apartments","farm","dormitory"}`; `UNKNOWN_FACTOR = 0.5` (dla `yes`); `DEFAULT_LEVELS = {"apartments": 5, "residential": 2}` (reszta 1); `MIN_AREA_M2 = 20`.
  - `building_factor(tag: str) -> float` (1.0 / 0.5 / 0.0).
  - `levels(tags: Mapping[str,str], building: str) -> int` — `building:levels` jako liczba (np. `"3"`, `"2.5"` → 2), przycięta do 1–40; brak/śmieci → domyślne.
  - `polygon_area_m2(coords: list[tuple[float, float]]) -> float` — wzór Gaussa (shoelace) w lokalnym rzucie równoodległościowym wokół środka (`x = lng·cos(lat0)·111 320`, `y = lat·110 540`); `coords` = (lat, lng).
  - `extract_buildings(pbf_path) -> pd.DataFrame` — kolumny `lat, lng, w` (tylko `w > 0`), pyosmium `FileProcessor(...).with_locations().with_filter(KeyFilter("building"))`, tylko drogi (ways) z ≥ 3 poprawnymi węzłami; środek = średnia węzłów (bez zdublowanego ostatniego).
  - `build_building_weights(pbf_path, con) -> int` — tabela `building_weights(cell_e INTEGER, cell_n INTEGER, h3 VARCHAR, w DOUBLE)`: środek → EPSG:3035 (pyproj, wektorowo) → `cell_e = floor(x/1000)*1000`, `cell_n = floor(y/1000)*1000`; `h3` = res 9; suma `w` per (cell_e, cell_n, h3). Zwraca liczbę wierszy; loguje liczbę budynków i sumę wag.
- `run_all.STEPS` = `("download", "population", "osm", "buildings", "permits", "geocode", "permits_hex", "aggregate")` — UWAGA: `population` musi teraz iść PO `buildings`; ustaw kolejność: `("download", "osm", "buildings", "population", "permits", "geocode", "permits_hex", "aggregate")`.

- [ ] **Step 1: Fixture** — dopisz do `tiny.osm`: kwadrat 10×10 m `building=house` (100 m²), kwadrat 20×20 m `building=apartments building:levels=4`, kwadrat 20×20 m `building=garage`, kwadrat 3×3 m `building=yes` (za mały), kwadrat 10×10 m `building=yes`.
- [ ] **Step 2: Failing testy**

```python
def test_building_factor():
    assert building_factor("house") == 1.0 and building_factor("yes") == 0.5 and building_factor("garage") == 0.0

def test_levels():
    assert levels({"building:levels": "3"}, "house") == 3
    assert levels({"building:levels": "2.5"}, "house") == 2
    assert levels({"building:levels": "abc"}, "apartments") == 5
    assert levels({}, "residential") == 2 and levels({"building:levels": "99"}, "yes") == 40

def test_polygon_area_square_10m():
    lat0, lng0 = 52.0, 21.0
    dlat, dlng = 10 / 110540, 10 / (111320 * math.cos(math.radians(lat0)))
    sq = [(lat0, lng0), (lat0, lng0 + dlng), (lat0 + dlat, lng0 + dlng), (lat0 + dlat, lng0), (lat0, lng0)]
    assert polygon_area_m2(sq) == pytest.approx(100, rel=0.01)

def test_extract_buildings_weights(tiny_osm):
    df = extract_buildings(tiny_osm)
    assert sorted(df["w"].round()) == [50, 100, 1600]   # yes 100·0.5, house 100, apartments 400·4; garage i mały pominięte

def test_build_building_weights_table(tiny_osm):
    con = duckdb.connect()
    assert build_building_weights(tiny_osm, con) >= 1
    row = con.execute("SELECT SUM(w), MIN(length(h3)) FROM building_weights").fetchone()
    assert row[0] == pytest.approx(1750, rel=0.01)
```

- [ ] **Step 3: Run** `uv run pytest tests/test_buildings.py -v` — FAIL.
- [ ] **Step 4: Implementuj** (chunkami po ~1 mln budynków do list numpy; komentarz po polsku: czym jest metoda dasymetryczna i dlaczego waga = powierzchnia użytkowa).
- [ ] **Step 5: Run** — PASS; `uv run pytest -q` — wszystkie PASS.
- [ ] **Step 6: Commit** — `feat: wagi budynków mieszkalnych z OSM (dasymetria)`

### Task 2: Ludność dasymetryczna res 9 + baza agregacji res 9 + res 5 + `lat,lng`

**Files:**
- Modify: `etl/population.py`, `etl/aggregate.py`, `etl/geocode_obreby.py` (`build_permits_hex`), `etl/run_all.py`, `etl/sanity.py`, `tests/factories.py`, istniejące testy ETL
- Test: `tests/test_population.py`, `tests/test_aggregate.py`, `tests/test_sanity.py`

**Interfaces:**
- Consumes: `building_weights` (Task 1); `load_polish_cells`, `impute_subcategories`, `cells_to_hex` (v1).
- Produces:
  - `population.dasymetric_to_hex(cells: pd.DataFrame, weights: pd.DataFrame, res: int = 9, n_uniform: int = 10) -> tuple[pd.DataFrame, float]` — `cells`: kolumny `E, N, T, F, M, Y_LT15, Y_1564, Y_GE65`; `weights`: `cell_e, cell_n, h3, w`. Komórki z Σw > 0 → udział `w/Σw`; pozostałe → `cells_to_hex(..., res, n=n_uniform)`. Zwraca (ramka `h3` + `POP_COLUMNS`, udział ludności rozłożonej przez budynki 0–1).
  - `population.build_hex_pop(parquet_path, con) -> int` — teraz tworzy **`hex_pop_r9`** (jeśli brak `building_weights` → równomiernie z ostrzeżeniem w logu), zapisuje udział do `meta` jako wiersz `source="dasymetria"`, `rows` = udział w promilach. Usuń tworzenie `hex_pop_r8` stąd.
  - `aggregate.BASE_RES = 9`, `aggregate.COARSE_RESOLUTIONS = (8, 7, 6, 5)`; `build_aggregates(con)` tworzy `hex_pop_r8..r5` z `hex_pop_r9`, `poi_counts_r9..r5` (res 9 liczone z `poi.lat/lng` przez UDF `h3_cell(lat, lng, res)`), `permits_r8..r5` z `permits_r9`; **każda** tabela `hex_pop_r*` (łącznie z r9) ma kolumny `lat, lng` (środek heksagonu, UDF `h3_lat`, `h3_lng`).
  - `geocode_obreby.build_permits_hex(con, res: int = 9) -> int` — tworzy `permits_r{res}`.
  - `sanity`: `REQUIRED_TABLES` z `hex_pop_r9`, `permits_r9`, `poi_counts_r9`, `building_weights`, `*_r5`; nowe progi: suma `hex_pop_r9.pop_total` ∈ [36,9; 37,2] mln, udział dasymetrii ≥ 0,85, `building_weights` ≥ 1 mln wierszy.
  - `tests/factories.make_db(...)` — `pop` przyjmuje heksagony **res 9**; buduje bazę przez nowe `build_aggregates`.

- [ ] **Step 1: Failing testy**

```python
def test_dasymetric_follows_buildings():
    cells = pd.DataFrame({"E": [5000000], "N": [3200000], "T": [1000], "F": [500], "M": [500],
                          "Y_LT15": [100], "Y_1564": [700], "Y_GE65": [200]})
    a, b = <dwa różne heksagony res 9 leżące w tej komórce>   # wylicz z h3.latlng_to_cell punktów komórki
    w = pd.DataFrame({"cell_e": [5000000, 5000000], "cell_n": [3200000, 3200000], "h3": [a, b], "w": [300.0, 100.0]})
    out, share = dasymetric_to_hex(cells, w)
    got = out.set_index("h3")["pop_total"]
    assert got[a] == pytest.approx(750) and got[b] == pytest.approx(250) and share == 1.0

def test_dasymetric_fallback_uniform_keeps_sum():
    # komórka bez budynków → rozkład równomierny, suma zachowana, udział 0
    out, share = dasymetric_to_hex(cells_bez_wag, pusta_ramka_wag)
    assert out["pop_total"].sum() == pytest.approx(1000) and share == 0.0

def test_aggregates_from_res9_with_latlng():
    # 7 dzieci res 9 jednego rodzica res 8 → hex_pop_r8 jeden wiersz z sumą i poprawnym lat/lng środka; istnieje hex_pop_r5
```

- [ ] **Step 2: Run** `uv run pytest tests/test_population.py tests/test_aggregate.py -v` — FAIL.
- [ ] **Step 3: Implementuj**, popraw `factories.py` i wszystkie testy ETL zależne od res 8 (stare `test_analyze*` zostaną usunięte w Task 5 — tu je tymczasowo oznacz `pytest.mark.skip(reason="zastąpione przez /api/view w Task 5")`).
- [ ] **Step 4: Run** `uv run pytest -q` — PASS (poza skipniętymi).
- [ ] **Step 5: Commit** — `feat: ludność dasymetryczna w H3 res 9 i agregaty 9→5`

### Task 3: Przeliczenie prawdziwych danych

**Files:** Modify: `docs/raport-etl.md`

- [ ] **Step 1:** Zatrzymaj serwer (jeśli działa). Run (w tle, log do `data/etl_v2.log`): `uv run python -m etl.run_all --only buildings,population,permits_hex,aggregate --force` — Expected: koniec bez wyjątku.
- [ ] **Step 2:** `uv run python -m etl.sanity` — Expected: OK. Jeśli udział dasymetrii < 0,85 albo suma ludności poza progiem — znajdź przyczynę (nie zmieniaj progów).
- [ ] **Step 3:** Dopisz sekcję „v2 (2026-10-27)” do `docs/raport-etl.md`: czasy kroków, liczba budynków, Σ wag, udział dasymetrii, liczby wierszy `hex_pop_r9..r5`, `poi_counts_r9`, `permits_r9`, rozmiar bazy.
- [ ] **Step 4: Commit** — `chore: przeliczenie danych v2 (budynki, res 9)`

### Task 4: Rdzeń analizy v2 (okrąg, rozdzielczości, agregacja, percentyle)

**Files:**
- Modify: `backend/app/analysis/resolution.py`, `backend/app/analysis/kernel.py`, `backend/app/analysis/scoring.py`
- Test: `tests/test_analysis_core.py` (przepisz)

**Interfaces:**
- Produces:
  - `resolution.py`: `HEX_SPACING_KM`, `CELL_AREA_KM2`, `SNAP_DEG` (wartości z Global Constraints); `display_res_for_zoom(zoom: int) -> int`; `snap_bbox(bbox: tuple[float,float,float,float], res: int) -> tuple[...]` (na zewnątrz do wielokrotności `SNAP_DEG[res]`); `choose_compute_res(bbox, radius_km: float, display_res: int) -> int` — od 9 w górę do `display_res`: pierwsza rozdzielczość, dla której `n = pole(bbox+bufor r)/CELL_AREA_KM2[res] ≤ 800_000` i `n · max(1, π r² / CELL_AREA_KM2[res]) ≤ 30_000_000`; pole prostokąta w km² liczone z `111,32 · cos(lat_środka)` × `110,54`.
  - `kernel.py`: zostaw `to_metric`; usuń `kernel_sums`; dodaj `catchment_sums(target_xy, source_xy, values, radius_m: float) -> np.ndarray` — suma `values` źródeł w odległości ≤ `radius_m` (cKDTree `sparse_distance_matrix` lub `query_ball_point`), `values` (M,) lub (M,k).
  - `scoring.py`: zostaw `score`, `percentile_rank`, `pick_top`; usuń `quantile_breaks`; dodaj `legend_values(x: np.ndarray) -> list[float]` (kwantyle 0; 0,25; 0,5; 0,75; 0,9; 1; puste → `[]`); `weighted_parent_mean(child_h3: np.ndarray, values: np.ndarray, weights: np.ndarray, parent_res: int) -> tuple[np.ndarray, np.ndarray]` → (`parent_h3`, średnie ważone; kolumny `values` (N,k) zachowane; wagi + 1e-6).

- [ ] **Step 1: Failing testy**

```python
def test_display_res_for_zoom():
    assert [display_res_for_zoom(z) for z in (5, 6, 7, 8, 9, 10, 11, 12, 16)] == [5, 5, 6, 6, 7, 8, 8, 9, 9]

def test_snap_bbox_outward():
    assert snap_bbox((21.03, 52.21, 21.07, 52.26), 8) == (21.0, 52.0, 21.25, 52.5)

def test_compute_res_city_vs_country():
    assert choose_compute_res((20.9, 52.1, 21.2, 52.35), 1.5, 9) == 9          # miasto
    assert choose_compute_res((14.1, 49.0, 24.2, 54.9), 1.5, 5) == 8           # cała Polska, mały zasięg
    assert choose_compute_res((14.1, 49.0, 24.2, 54.9), 20, 5) in (6, 7)       # cała Polska, duży zasięg

def test_catchment_disk_counts():
    t = np.array([[0.0, 0.0]]); src = np.array([[0, 0], [900, 0], [1100, 0]], float)
    assert catchment_sums(t, src, np.array([1.0, 2.0, 4.0]), 1000)[0] == 3.0   # 1100 m poza okręgiem

def test_weighted_parent_mean():
    kids = np.array(list(h3.cell_to_children(<rodzic res 8>, 9)))[:2]
    p, v = weighted_parent_mean(kids, np.array([10.0, 20.0]), np.array([3.0, 1.0]), 8)
    assert len(p) == 1 and v[0] == pytest.approx(12.5, rel=1e-4)

def test_legend_values():
    assert legend_values(np.arange(101.0)) == [0, 25, 50, 75, 90, 100]
```

- [ ] **Step 2: Run** `uv run pytest tests/test_analysis_core.py -v` — FAIL.
- [ ] **Step 3: Implementuj** (docstringi: 2SFCA z progiem odległości, dlaczego średnia ważona ludnością, dlaczego przyciąganie bbox).
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat: rdzeń analizy v2 - okrąg zasięgu, poziomy szczegółowości`

### Task 5: `/api/view` (zastępuje `/api/analyze`)

**Files:**
- Modify: `backend/app/analysis/service.py` (przepisz), `backend/app/api/routes.py`, `backend/app/catalog.py` (nic albo drobne)
- Delete: `tests/test_analyze.py`, `tests/test_analyze_permits.py`, `tests/test_analyze_poland.py`
- Create: `tests/test_view.py`

**Interfaces:**
- Consumes: Task 4, `nearest_place_name` (zostaje), `_permit_window` (zostaje, z `res` = compute_res).
- Produces:
  ```python
  @dataclass(frozen=True)
  class ViewParams:
      type_id: str | None; demand_id: str | None
      bbox: tuple[float, float, float, float]; zoom: int
      bandwidth_km: float; months: int = 24
  def run_view(con, p: ViewParams) -> dict
  def cached_view(p: ViewParams) -> dict      # LRU 64 na rdzeniu (przyciągnięty bbox), top-5 poza cache
  ```
  Odpowiedź: `{"mode": "full"|"demand"|"competition", "display_res", "compute_res", "radius_km" (efektywny), "hexes": [[h3, score|None, D|None, S|None, pct_score|None, pct_D|None, pct_S|None], …], "legend": {"score": [...], "D": [...], "S": [...]}` (klucze tylko dla dostępnych metryk), `"top": [{"h3","lat","lng","name","value"}]`, `"top_metric": "score"|"D"|"S"`, `"notes": [str]`, `"warnings": [str]`, `"permits_period"?`.
  Algorytm = spec §4 kroki 1–7. Komórki bufora: `SELECT h3, lat, lng, pop_total[, kolumna popytu] FROM hex_pop_r{c} WHERE lat BETWEEN … AND lng BETWEEN …` (bufor = r w stopniach), plus komórki z firmami/pozwoleniami w tym prostokącie (join `poi_counts_r{c}`/`permits_r{c}` z `h3_lat/h3_lng` liczonym w Pythonie dla brakujących). Heksagony wynikowe: tylko z `D > 0` lub `S > 0` (zależnie od trybu). Top-5: wśród heksagonów `display_res` w dokładnym bbox; metryka trybu; `pick_top(..., min_sep_m=max(2·r, przekątna_widoku/6)·1000)` (dla trybu competition — bez progu popytu: podaj `D = S`). Notatki: `r < HEX_SPACING_KM[compute_res]` → „Przy tym przybliżeniu najmniejszy liczony zasięg to ok. {spacing} km — przybliż mapę, aby zobaczyć dokładniej.”; popyt z pozwoleń i r < 1 → „Lokalizację pozwoleń znamy z dokładnością do obrębu, dlatego zasięg dla nowych domów wynosi co najmniej 1 km.”. Ostrzeżenia jak v1 (`POOR_WARNING` gdy typ `poor`, brak pozwoleń, brak konkurencji tylko w trybie full).
  - `GET /api/view?type&demand&bbox&zoom&bandwidth_km&months` — puste stringi = brak; walidacja 422 po polsku („Wybierz typ działalności albo czynnik popytu”, „Nieprawidłowy bbox”, `bandwidth_km` 0,1–20, `zoom` 3–19, `months ∈ {12,24,36}`); usuń `/api/analyze`.

- [ ] **Step 1: Failing testy** (`make_db` z siatką res 9 wokół Warszawy, kilka POI `hairdresser`, kilka pozwoleń):
  - `test_view_full_mode` — `zoom=13` → `display_res == 9`, `mode == "full"`, heksagony z 7 kolumnami, `pct_score` w 0–100, `legend.score` ma 6 wartości, top niepuste z nazwą.
  - `test_view_lod_parent_cells` — ten sam obszar, `zoom=10` → `display_res == 8` i każdy h3 ma rozdzielczość 8.
  - `test_view_modes` — tylko `type` → `mode == "competition"`, kolumny score/D są `None`, `legend` ma tylko `S`; tylko `demand` → `mode == "demand"`.
  - `test_view_requires_one` — brak obu → 422 z komunikatem.
  - `test_view_disk_counts_exact` — 1 heksagon res 9 z `pop_total=100` + POI w odległości 500 m; `bandwidth_km=1` → D w heksagonie = 100 + populacja sąsiadów ≤ 1 km (policz w teście), S = 1.
  - `test_view_empty_area` — bbox nad Bałtykiem → 200, `hexes == []`.
  - `test_view_country_small_radius_note` — bbox całej Polski, `zoom=6`, `bandwidth_km=0.1` → `compute_res < 9` i notatka o przybliżeniu.
  - `test_view_permits_min_radius` — `demand=new_sf`, `bandwidth_km=0.3` → `radius_km == 1.0` + notatka o obrębie.
  - `test_view_cache_hit_on_small_pan` — dwa bboxy różniące się o 0,01° → rdzeń liczony raz (licznik wywołań).
- [ ] **Step 2: Run** `uv run pytest tests/test_view.py -v` — FAIL.
- [ ] **Step 3: Implementuj**; usuń stare testy analyze i `skip`-y z Task 2.
- [ ] **Step 4: Run** `uv run pytest -q` — PASS.
- [ ] **Step 5: Commit** — `feat: /api/view - analiza widocznego obszaru z poziomami szczegółowości`

### Task 6: `/api/point` (dymek klikniętego punktu)

**Files:** Modify: `backend/app/analysis/service.py`, `backend/app/api/routes.py`; Create: `tests/test_point.py`

**Interfaces:**
- Produces: `point_details(con, lat: float, lng: float, type_id: str | None, demand_id: str | None, bandwidth_km: float, months: int) -> dict` → `{"radius_km", "demand": float|None, "demand_name": str|None, "competitors": int|None, "type_name": str|None, "score": float|None, "nearest": [{"name","distance_m"}] (≤5), "permits_period"?, "notes": [...]}`. Popyt: komórki `hex_pop_r9` (albo `permits_r9` w oknie) z prostokąta wokół punktu, środek ≤ r (haversine). Firmy: `poi` z prostokąta, dokładna odległość ≤ r; `nearest` = 5 najbliższych w okręgu (bez nazwy → „bez nazwy”). `score = demand/(competitors+1)` gdy oba.
- `GET /api/point?lat&lng&type&demand&bandwidth_km&months` (walidacja jak `/api/view`, punkt w Polsce).

- [ ] **Step 1: Failing testy:** `test_point_counts` (znane POI w 300 m i 2 km przy r=1 → competitors 1, nearest[0].distance_m ≈ 300 ±5); `test_point_score`; `test_point_empty` (punkt bez danych → zera, `nearest == []`, score 0); `test_point_validation` (punkt poza Polską → 422).
- [ ] **Step 2: Run** `uv run pytest tests/test_point.py -v` — FAIL.
- [ ] **Step 3: Implementuj.**
- [ ] **Step 4: Run** `uv run pytest -q` — PASS.
- [ ] **Step 5: Commit** — `feat: /api/point - dokładne liczby w zasięgu klikniętego punktu`

### Task 7: Czytelny błąd przy zablokowanej bazie

**Files:** Modify: `backend/app/db.py`, `backend/app/api/routes.py`; Test: `tests/test_app.py`

**Interfaces:** `db.DatabaseBusy(Exception)`; `cursor()` łapie `duckdb.IOException` przy `connect` → `DatabaseBusy` (połączenie NIE jest zapamiętywane). Wszystkie endpointy korzystające z bazy → 503 z `DB_BUSY_MESSAGE = "Baza danych jest właśnie aktualizowana. Spróbuj ponownie za kilka minut."`.

- [ ] **Step 1: Failing test** `test_locked_db_returns_503` — otwórz bazę testową w trybie zapisu w osobnym procesie (`subprocess` z `python -c "import duckdb,time; c=duckdb.connect(path); time.sleep(5)"`) i wywołaj `/api/view` → 503 z komunikatem; po zakończeniu procesu kolejne wywołanie → 200.
- [ ] **Step 2–4:** Run FAIL → implementuj → PASS.
- [ ] **Step 5: Commit** — `fix: czytelny komunikat, gdy baza jest zajęta przez ETL`

### Task 8: Frontend — formularz, tryby, pytajniki, auto-odświeżanie

**Files:** Modify: `frontend/index.html`, `frontend/js/app.js`, `frontend/js/ui.js`, `frontend/js/api.js`, `frontend/css/style.css`

**Interfaces:**
- Consumes: `/api/view`, `/api/point`, `/api/catalog`.
- Produces: `api.js`: `view(params, signal)`, `point(params)` (usuń `analyze`); `ui.js`: `selectedParams() -> {type, demand, bandwidth_km, months?}` (puste = brak), `renderHelp()` (pytajniki), `renderTop(list, metric, onClick)`, `setLayerAvailability(mode)` (wyłącza radio warstw niedostępnych w trybie i przełącza na dostępną), `renderNotes(list)`.
- Zmiany: usuń fieldset „Obszar” poza wyszukiwarką (zostaje pole adresu — wybór przenosi mapę `setView(..., 14)`), usuń promień, „Cała Polska”, przycisk „Analizuj”, pinezkę. Obie listy mają pierwszą opcję „— nie wybieraj —” (`value=""`). Zmiana typu nadal ustawia domyślny popyt i zasięg branży. Suwak zasięgu: logarytmiczny `input type=range min=0 max=100`, `km = 0.1 · 200^(x/100)`, wyświetlanie: < 2 km co 0,1, ≥ 2 km co 0,5; pozycja domyślna z zasięgu branży (odwrotność wzoru). Zasięg klienta przeniesiony z „Zaawansowane” na wierzch (pod listy). Pytajniki: przycisk `?` (okrągły, 18 px) obok etykiet warstw, zasięgu i legendy; klik/hover pokazuje dymek z tekstem z spec §5 (dosłownie), zamykany klikiem poza nim/Escape.
- Auto-odświeżanie: `map.on('moveend')` + zmiany formularza (suwak: `change`, nie `input`; listy: `change`) → debounce 250 ms → `view()` z `AbortController` (poprzednie zapytanie przerywane); wskaźnik ładowania = cienki pasek na górze mapy. Brak typu i popytu → komunikat „Wybierz typ działalności albo czynnik popytu” i czyszczenie mapy.
- Hash: `type, demand, bw, m, layer, lat, lng, z` (środek i zoom mapy); stare parametry `r`, `pl` ignorowane.

- [ ] **Step 1: Implementuj.**
- [ ] **Step 2: Weryfikacja ręczna** (serwer na prawdziwej bazie): wybór samego „Fryzjer” → mapa konkurencji, „Popyt”/„Okazja” wyłączone; sam „Seniorzy” → mapa popytu; oba → trzy warstwy; przesunięcie mapy odświeża wynik bez klikania; suwak 0,1 km ↔ 20 km; pytajniki pokazują teksty; link z hashem odtwarza widok po przeładowaniu.
- [ ] **Step 3: Commit** — `feat: frontend v2 - tryby, pytajniki, auto-odświeżanie widoku`

### Task 9: Frontend — mapa: LOD z płynnym przejściem, gradient, dymek punktu, top-5, naprawa kliknięć

**Files:** Modify: `frontend/js/map.js`, `frontend/js/colors.js`, `frontend/js/app.js`, `frontend/css/style.css`

**Interfaces:**
- `colors.js`: `GRADIENT` (paleta z Global Constraints), `gradientColor(pct: number) -> string` (interpolacja RGB po 9 punktach, pct 0–100), `gradientCss() -> string` (`linear-gradient(to right, …)`).
- `MapView`: `setHexes(rows, pctIndex, {fade: boolean})`, `showPoint(lat, lng, radiusKm, htmlElement)` (okrąg zasięgu + popup; zamknięcie popupu usuwa okrąg), `setTopMarkers(list, onClick)`, `setPoi(points)`, `safeFlyTo(lat, lng, zoom)`, `onMapClick(cb)`, `getView() -> {bbox, zoom, center}`.
- **Naprawa kliknięć (spec §1 pkt 6):** heksagony rysowane canvasem z `interactive: false`; punkty firm, obrys i znaczniki top-5 — renderer **SVG** (`L.svg({pane})`) albo `L.marker`/`divIcon`, nie canvas. Jedyne kliknięcie, które coś robi na mapie, to `map.on('click')` → `/api/point` → `showPoint`. Klik w punkt firmy → jego tooltip/popup z nazwą (`bubblingMouseEvents: false`).
- **LOD z płynnym przejściem:** dwa pane'y `hexesA`, `hexesB` (zIndex 410/411) z własnymi rendererami canvas, CSS `transition: opacity 400ms`. Nowy wynik rysuj w nieaktywnym pane (opacity 0), w następnej klatce ustaw mu opacity = suwak przezroczystości, staremu 0; po `transitionend` (albo `setTimeout` 450 ms — zabezpieczenie) wyczyść stary. Przy zmianie `display_res` czas 400 ms, przy samym przesunięciu 150 ms.
- **Gradient:** kolor heksagonu = `gradientColor(row[pctIndex])` (indeksy: score 4, D 5, S 6); legenda = pasek `gradientCss()` z podpisami `legend[m]` (min, 25%, mediana, 75%, 90%, max) + pytajnik legendy + notatki (`notes`) i okres pozwoleń.
- **Dymek punktu:** treść wg spec §5 (tryb full/demand/competition), liczby `toLocaleString('pl-PL')`, populacja zaokrąglona do 100 z „ok.”, lista najbliższych firm z odległością (m / km).
- **Top-5:** numerowane kółka (`divIcon`, 22 px, kolor `#d62728`, biała cyfra) w pane nad heksagonami; klik w znacznik lub pozycję listy → `safeFlyTo(…, max(zoom, 14))` + `showPoint` dla tego miejsca.
- **`safeFlyTo`:** gdy `document.hidden` → `setView(..., {animate:false})`; w przeciwnym razie `flyTo`, a po 2 s, jeśli `map._animatingZoom` nadal true → `map.setView(map.getCenter(), map.getZoom(), {animate:false})`. Tak samo zabezpiecz `setView` z wyszukiwarki.

- [ ] **Step 1: Implementuj.**
- [ ] **Step 2: Weryfikacja ręczna w przeglądarce** (desktop ~1280×800 i 375×812), zrzuty ekranu do `docs/screenshots/v2-*.png`:
  1. Warszawa, Fryzjer + Mieszkańcy, zasięg 0,5 km, zoom 13 → drobne heksagony (res 9), wyraźnie różne odcienie w centrum (brak „jednego koloru” dla różnych wartości).
  2. Oddalanie 13 → 6 → heksagony płynnie przechodzą w większe; przybliżanie odwrotnie; brak rozmazanych etykiet po zakończeniu animacji.
  3. Klik w dowolny heksagon (także po kliknięciu pozycji top-5 i z włączonymi punktami firm) → ZAWSZE dymek z liczbami i okrąg, nigdy pinezka.
  4. Tylko „Seniorzy (65+)”, zasięg 1 km, Kraków → mapa popytu; tylko „Fryzjer” → mapa konkurencji.
  5. Brukarstwo + nowe domy jednorodzinne, zasięg 0,3 → notatka o min. 1 km.
  6. Widok całej Polski (zoom 6) z zasięgiem 0,1 km → działa, notatka o przybliżeniu, czas odpowiedzi < 5 s (zmierz `performance.now()` i zapisz w raporcie).
- [ ] **Step 3: Commit** — `feat: frontend v2 - płynne poziomy szczegółowości, gradient, dymek punktu, naprawa kliknięć`

### Task 10: Dokumentacja i przegląd

**Files:** Modify: `README.md`, `docs/sciaga-do-obrony.md`, `docs/zrodla-danych.md`, `docs/raport-etl.md`

- [ ] **Step 1:** README: nowy sposób użycia (bez promienia), zrzuty v2, metoda: 2SFCA z progiem odległości, dasymetria, LOD; ograniczenia.
- [ ] **Step 2:** Ściąga do obrony: dopisz pojęcia **metoda dasymetryczna** (co to, dlaczego budynki, wagi, ograniczenia), **poziomy szczegółowości / hierarchia H3**, **2SFCA z okręgiem vs jądro Gaussa** (dlaczego zmiana: interpretowalność), **skala kolorów wg percentyla vs klasy kwantylowe**, **agregacja średnią ważoną ludnością**; zaktualizuj odpowiedzi na pytania prowadzącego, które dotyczyły starego algorytmu.
- [ ] **Step 3:** `uv run pytest -q` i `uv run python -m etl.sanity` — PASS/OK.
- [ ] **Step 4:** Jeden przegląd całości zmian v2 (`git diff <commit przed Task 1>..HEAD`) przez świeżego subagenta na modelu `opus` (`superpowers:requesting-code-review`); popraw istotne uwagi.
- [ ] **Step 5: Commit** — `docs: dokumentacja v2`; zakończ raportem po polsku (co działa, odchylenia od planu, czasy odpowiedzi, co sprawdzić ręcznie).
