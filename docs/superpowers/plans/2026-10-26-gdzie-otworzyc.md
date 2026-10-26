# „Gdzie otworzyć?” Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplikacja webowa pokazująca na mapie Polski heatmapę „potencjalni klienci na 1 konkurenta” dla wybranego typu działalności i czynnika popytu.

**Architecture:** Jednorazowy (odświeżany) ETL w Pythonie pobiera otwarte dane (Eurostat Census GRID 2021, OSM z Geofabrik, GUNB RWDZ + geokodowanie ULDK), sprowadza je do siatki H3 (res 8 → 7 → 6) i zapisuje w jednym pliku DuckDB. Backend FastAPI liczy na żądanie sumy ważone jądrem Gaussa (cKDTree w EPSG:2180) i ranking top-5. Frontend to czysty HTML/JS z Leaflet + h3-js, serwowany przez backend.

**Tech Stack:** Python 3.13 (uv), FastAPI, uvicorn, DuckDB, numpy, pandas, pyarrow, scipy, pyproj, shapely, h3 v4, osmium (pyosmium ≥4), httpx, pytest; Leaflet 1.9.4, h3-js 4.1.0, CARTO Positron.

**Spec:** [docs/superpowers/specs/2026-10-26-gdzie-otworzyc-design.md](../specs/2026-10-26-gdzie-otworzyc-design.md) — czytaj razem z [docs/zrodla-danych.md](../../zrodla-danych.md) (zweryfikowane formaty plików i URL-e).

## Global Constraints

- Python **3.13** przez `uv` (`.python-version` = `3.13`). Systemowego Pythona 3.15 NIE używać.
- Uruchamianie wszystkiego przez `uv run ...` z katalogu głównego repo (`C:\Projekty\Przestrzenne`). Środowisko: Windows 11, powłoka PowerShell / Git Bash.
- Identyfikatory w kodzie po angielsku; **komentarze i docstringi po polsku**, objaśniające pojęcia przestrzenne (właściciel projektu musi rozumieć kod na obronie). UI wyłącznie po polsku.
- Frontend bez Node i bez kroku budowania; biblioteki tylko z CDN z przypiętą wersją: `https://unpkg.com/leaflet@1.9.4/dist/leaflet.js` (+ `leaflet.css`), `https://unpkg.com/h3-js@4.1.0/dist/h3-js.umd.js`.
- Identyfikatory H3 zawsze jako `str`. Odległości liczone w **EPSG:2180**. Siatka spisu w **EPSG:3035**. H3/OSM/ULDK w **EPSG:4326**.
- Nazwy tabel DuckDB (doprecyzowanie względem spec — jednolite sufiksy): `hex_pop_r8|r7|r6`, `poi`, `places`, `poi_counts_r8|r7|r6`, `permits_raw`, `obreb_geom`, `permits_r8|r7|r6`, `meta`.
- Doprecyzowanie API względem spec §6: `/api/poi` zwraca obiekt `{"items": [...], "truncated": bool}` (nie gołą listę); `/api/analyze` dodatkowo zwraca `stats.D_breaks`, `stats.S_breaks` i (dla `new_*`) `permits_period`.
- Ścieżki: `data/raw/` (surowe pliki), `data/app.duckdb` (baza). Katalog `data/` jest w `.gitignore`. Zmienna środowiskowa `GO_DATA_DIR` nadpisuje `data/` (używane w testach).
- Wszystkie zapytania HTTP z nagłówkiem `User-Agent: GdzieOtworzyc/0.1 (projekt studencki)`.
- Serwer: `uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`. ETL i serwer nie działają jednocześnie (blokada pliku DuckDB) — serwer otwiera bazę **read-only**.
- Commit po każdym tasku, wiadomości w stylu `feat: …` / `test: …` / `docs: …`, zakończone linią `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (lub odpowiednim modelem wykonawcy).
- Atrybucja (dokładny tekst, używany w UI i `/api/meta`): `© OpenStreetMap contributors © CARTO | Ludność: © EU, Eurostat GISCO (Census 2021, zmodyfikowane) | Pozwolenia: GUNB RWDZ | Geokodowanie: GUGiK ULDK`

## Review Focus

1. **Obszar przy granicy / morzu** (np. Świnoujście, Hel): część koła bez danych → brak błędu, brak heksagonów na morzu, top-5 tylko z lądu. Test: `test_analyze_half_empty_area` (Task 8).
2. **Typ bez żadnej konkurencji w OSM** (np. brukarstwo w małym mieście): wynik = popyt, ostrzeżenie o braku konkurencji, brak dzielenia przez zero. Test: `test_analyze_no_competitors_warns` (Task 8).
3. **Czynnik `new_*`, gdy tabela pozwoleń nie istnieje lub jest pusta**: ostrzeżenie zamiast błędu 500. Test: `test_analyze_permits_missing_warns` (Task 15).
4. **Mały promień (1 km) z dużym zasięgiem klienta (15 km)**: separacja top-N większa niż obszar → zwraca 1 lokalizację, bez wyjątku. Test: `test_pick_top_separation_larger_than_area` (Task 7).
5. **Wyszukiwarka adresów**: puste/krótkie zapytanie, polskie znaki, Nominatim niedostępny → `[]` albo czytelny 502, nigdy 500. Testy: `test_geocode_short_query`, `test_geocode_upstream_error` (Task 18).

---

## Milestone M0 — szkielet

### Task 1: Szkielet backendu (uv, FastAPI, health, serwowanie frontendu)

**Files:**
- Create: `pyproject.toml`, `.python-version`, `start.bat`, `backend/__init__.py`, `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/main.py`, `backend/app/api/__init__.py`, `backend/app/api/routes.py`, `frontend/index.html` (placeholder `<h1>Gdzie otworzyć?</h1>`), `etl/__init__.py`, `tests/__init__.py`, `tests/test_app.py`

**Interfaces:**
- Produces: `backend.app.config`: `ROOT: Path`, `DATA_DIR: Path` (z `GO_DATA_DIR` lub `ROOT/"data"`), `RAW_DIR = DATA_DIR/"raw"`, `DB_PATH = DATA_DIR/"app.duckdb"`, `FRONTEND_DIR = ROOT/"frontend"`, `USER_AGENT: str`, `ATTRIBUTION: str` (tekst z Global Constraints). `backend.app.main.app: FastAPI`; `backend.app.api.routes.router: APIRouter` z prefiksem `/api`.

- [ ] **Step 1: Zainstaluj uv i zainicjuj projekt**

Run: `winget install --id=astral-sh.uv -e` (jeśli `uv --version` nie działa; po instalacji otwórz nową powłokę).
`pyproject.toml`: `name = "gdzie-otworzyc"`, `requires-python = ">=3.13,<3.14"`, dependencies: `fastapi`, `uvicorn[standard]`, `duckdb`, `numpy`, `pandas`, `pyarrow`, `scipy`, `pyproj`, `shapely`, `h3>=4`, `osmium>=4`, `httpx`; `[dependency-groups] dev = ["pytest"]`; `[tool.pytest.ini_options] pythonpath = ["."]`, `testpaths = ["tests"]`.
Run: `uv python install 3.13; uv sync`
Expected: `.venv` utworzony, brak błędów kompilacji kół.

- [ ] **Step 2: Napisz failing test**

```python
from fastapi.testclient import TestClient
from backend.app.main import app

def test_health():
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}

def test_index_served():
    r = TestClient(app).get("/")
    assert r.status_code == 200 and "Gdzie otworzyć?" in r.text
```

- [ ] **Step 3: Run** `uv run pytest tests/test_app.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 4: Implementuj** `config.py`, `routes.py` (`GET /api/health`), `main.py` (dołącza router, potem `app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True))` — mount na końcu, żeby nie przykrył `/api`). `start.bat`: `uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`.

- [ ] **Step 5: Run** `uv run pytest tests/test_app.py -v` — Expected: 2 PASS.

- [ ] **Step 6: Commit** — `git add -A; git commit -m "feat: szkielet backendu FastAPI z serwowaniem frontendu"`

### Task 2: Powłoka frontendu (mapa Positron, panel boczny, układ responsywny)

**Files:**
- Create/replace: `frontend/index.html`, `frontend/css/style.css`, `frontend/js/app.js`, `frontend/js/map.js`

**Interfaces:**
- Produces (`frontend/js/map.js`, moduł ES): `export function initMap(elementId) -> MapView`, gdzie `MapView` = obiekt z metodami: `onClick(cb(lat,lng))`, `setPin(lat,lng)`, `setAreaCircle(lat,lng,radiusKm|null)`, `setHexes(rows, valueIndex, breaks, colors)`, `setHexOpacity(0..1)`, `onHexClick(cb(row))`, `setPoi(points)`, `flyTo(lat,lng,zoom)`, `highlightHex(h3)`, `getBbox() -> [minLng,minLat,maxLng,maxLat]`, `getZoom()`. W tym tasku implementuj `initMap`, `onClick`, `setPin`, `setAreaCircle`, `flyTo`, `getBbox`, `getZoom`; pozostałe dochodzą w Task 9/12.
- DOM id-ki (używane w kolejnych taskach): `#type-select`, `#demand-select`, `#months-row`, `#months-select`, `#search-input`, `#search-results`, `#radius-input`, `#radius-value`, `#poland-checkbox`, `#bandwidth-input`, `#bandwidth-value`, `#analyze-btn`, `#top-list`, `#warnings`, `#legend`, `#layer-switch` (radio `name="layer"` wartości `score|D|S`), `#poi-checkbox`, `#opacity-input`, `#meta-footer`, `#sidebar`, `#map`.

- [ ] **Step 1: Zbuduj układ** wg spec sekcja 7: `#sidebar` (szer. 300 px) + `#map` (reszta). Kolejność kontrolek w panelu dokładnie jak w spec §7 (tytuł, typ, porównaj z, obszar, zaawansowane w `<details>`, przycisk Analizuj, najlepsze miejsca, ostrzeżenia, stopka). Na < 768 px panel = arkusz na dole (max 45vh, przewijany), mapa nad nim.

- [ ] **Step 2: Mapa w `map.js`:** `L.map(id, {preferCanvas: true})`, start `[52.07, 19.48]`, zoom 6. Warstwy:
  - podkład: `https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png`
  - pane `hexes` (zIndex 410) — na heksagony,
  - pane `labels` (zIndex 450, `pointerEvents = 'none'`) z `https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png`,
  - pane `poi` (zIndex 460).
  Atrybucja = `ATTRIBUTION` (wpisz tekst w JS).

- [ ] **Step 3: Weryfikacja ręczna** — `start.bat`, otwórz `http://localhost:8000`: mapa Polski z etykietami, klik stawia pinezkę i okrąg o promieniu z suwaka (aktualizuje się przy przesuwaniu), w DevTools tryb 375×812 → panel na dole, brak poziomego scrolla.

- [ ] **Step 4: Commit** — `feat: powłoka frontendu z mapą Leaflet i panelem bocznym`

---

## Milestone M1 — ludność i pierwsza heatmapa

### Task 3: Pobieranie surowych danych

**Files:**
- Create: `etl/download.py`, `tests/test_download.py`

**Interfaces:**
- Produces: `CENSUS_URL = "https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip"`, `OSM_URL = "https://download.geofabrik.de/europe/poland-latest.osm.pbf"`, `GUNB_BASE = "https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/"`, `GUNB_VOIVODESHIPS: tuple[str, ...]` (16 nazw z docs/zrodla-danych.md §1), `GUNB_NOTIFICATION_FILES = ("wynik_zgloszenia_2016_2021.zip", "wynik_zgloszenia_2022_up.zip")`;
  `download(url: str, dest: Path, force: bool = False, client: httpx.Client | None = None) -> Path` — strumieniowo do `dest.with_suffix(dest.suffix + ".part")`, potem rename; pomija, jeśli `dest` istnieje i `not force`;
  `extract_member(zip_path: Path, member_suffix: str, dest: Path) -> Path` — wypakowuje pierwszy element kończący się `member_suffix`;
  `download_all(raw_dir: Path, force: bool = False) -> dict[str, Path]` — klucze: `"census_parquet"` (po wypakowaniu `ESTAT_Census_2021_V3.parquet`), `"osm_pbf"`, `"gunb_permits"` → lista CSV (wypakowane), `"gunb_notifications"` → lista CSV.

- [ ] **Step 1: Failing testy** (z `httpx.MockTransport`, bez sieci):

```python
def test_download_writes_and_skips(tmp_path):
    calls = []
    def handler(req): calls.append(req.url); return httpx.Response(200, content=b"abc")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = download("https://x/f.bin", tmp_path / "f.bin", client=client)
    assert p.read_bytes() == b"abc"
    download("https://x/f.bin", tmp_path / "f.bin", client=client)
    assert len(calls) == 1                      # drugi raz pominięty
    assert not (tmp_path / "f.bin.part").exists()

def test_download_sends_user_agent(tmp_path): ...  # handler sprawdza req.headers["user-agent"] == USER_AGENT

def test_extract_member(tmp_path):
    # zbuduj zip z "a/x.txt" i "a/ESTAT_Census_2021_V3.parquet"
    out = extract_member(zip_path, "V3.parquet", tmp_path / "out.parquet")
    assert out.read_bytes() == b"PQ"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_download.py -v` — FAIL.
- [ ] **Step 3: Implementuj** funkcje (timeout 60 s na odczyt, `follow_redirects=True`).
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat: pobieranie surowych danych ETL`

### Task 4: Ludność → `hex_pop_r8` (interpolacja powierzchniowa)

**Files:**
- Create: `etl/population.py`, `tests/test_population.py`

**Interfaces:**
- Produces:
  `POP_COLUMNS = {"T": "pop_total", "F": "pop_f", "M": "pop_m", "Y_LT15": "pop_lt15", "Y_1564": "pop_1564", "Y_GE65": "pop_ge65"}`
  `parse_grd_id(grd_id: str) -> tuple[int, int]` → `(easting, northing)` lewego dolnego rogu,
  `load_polish_cells(parquet_path: Path) -> pd.DataFrame` — kolumny `E, N, T, F, M, Y_LT15, Y_1564, Y_GE65`; filtr `'PL' in CNTR_ID.split('-')` i `T > 0`; czyta tylko potrzebne kolumny (pyarrow),
  `impute_subcategories(df: pd.DataFrame) -> pd.DataFrame` — wartości < 0 w podkategoriach → `T × udział`, gdzie udział = `sum(col[col>=0]) / sum(T[col>=0])` liczony z danych,
  `cells_to_hex(df: pd.DataFrame, res: int = 8, n: int = 5) -> pd.DataFrame` — kolumny wyjściowe: `h3` + wartości `POP_COLUMNS`,
  `build_hex_pop(parquet_path: Path, con: duckdb.DuckDBPyConnection) -> int` — tworzy/zastępuje `hex_pop_r8(h3 VARCHAR PRIMARY KEY, pop_total, pop_f, pop_m, pop_lt15, pop_1564, pop_ge65 DOUBLE)`, zwraca liczbę wierszy.

- [ ] **Step 1: Failing testy**

```python
def test_parse_grd_id():
    assert parse_grd_id("CRS3035RES1000mN2684000E4285000") == (4285000, 2684000)

def test_impute_uses_observed_share():
    df = pd.DataFrame({"T": [100, 10], "F": [60, -9999], "M": [40, -9999],
                       "Y_LT15": [10, -9999], "Y_1564": [70, 5], "Y_GE65": [20, -9999]})
    out = impute_subcategories(df)
    assert out.loc[1, "F"] == pytest.approx(6.0)     # 10 × 60/100
    assert out.loc[1, "Y_1564"] == 5                 # znane wartości bez zmian
    assert (out[["F", "M", "Y_LT15", "Y_GE65"]] >= 0).all().all()

def test_cells_to_hex_preserves_sum():
    df = pd.DataFrame({"E": [4285000, 5000000], "N": [3300000, 3200000], "T": [1000, 250],
                       "F": [500, 125], "M": [500, 125], "Y_LT15": [150, 40],
                       "Y_1564": [650, 160], "Y_GE65": [200, 50]})
    out = cells_to_hex(df, res=8, n=5)
    assert out["pop_total"].sum() == pytest.approx(1250)
    assert out["h3"].map(h3.get_resolution).eq(8).all()
    assert len(out) >= 2                     # komórka 1 km² rozkłada się na kilka heksagonów
```

- [ ] **Step 2: Run** `uv run pytest tests/test_population.py -v` — FAIL.
- [ ] **Step 3: Implementuj.** `cells_to_hex`: offsety środków podkomórek `(i + 0.5) * 1000 / n` dla `i in range(n)` w obu osiach, każdy punkt niesie `wartość / n²`; transformacja `pyproj.Transformer.from_crs(3035, 4326, always_xy=True)` wektorowo; `h3.latlng_to_cell` w pętli/list comprehension; `groupby("h3").sum()`. Docstring po polsku wyjaśnia interpolację powierzchniową i założenie równomiernego rozkładu.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat: ETL ludności z siatki spisu 2021 do heksagonów H3`

### Task 5: Agregacja wielorozdzielcza

**Files:**
- Create: `etl/aggregate.py`, `tests/test_aggregate.py`

**Interfaces:**
- Consumes: `hex_pop_r8` (Task 4); opcjonalnie `poi` (Task 10), `permits_r8` (Task 14).
- Produces: `build_aggregates(con: duckdb.DuckDBPyConnection) -> dict[str, int]` (nazwa tabeli → liczba wierszy). Tworzy:
  - `hex_pop_r7`, `hex_pop_r6` (te same kolumny, sumy),
  - jeśli istnieje `poi`: `poi_counts_r8|r7|r6(h3 VARCHAR, type_id VARCHAR, n INTEGER)`,
  - jeśli istnieje `permits_r8`: `permits_r7|r6(h3, month DATE, kind VARCHAR, n INTEGER)`.
  Brakujące tabele źródłowe pomija bez błędu. Rodzic przez UDF DuckDB `h3_parent(h3 VARCHAR, res INTEGER) -> VARCHAR` zarejestrowany `con.create_function` (opakowuje `h3.cell_to_parent`).
  `table_exists(con, name: str) -> bool` — tu zdefiniowane, używane też przez backend.

- [ ] **Step 1: Failing testy**: (a) 7 heksagonów-dzieci jednego rodzica res 7 z `pop_total` 1..7 → `hex_pop_r7` ma 1 wiersz z sumą 28 i `hex_pop_r6` 1 wiersz z 28; (b) bez tabeli `poi` funkcja nie rzuca wyjątku i nie tworzy `poi_counts_r8`; (c) z tabelą `poi` (3 wiersze, 2 typy) → `poi_counts_r8` ma poprawne `n` per (h3, type_id).
- [ ] **Step 2: Run** `uv run pytest tests/test_aggregate.py -v` — FAIL.
- [ ] **Step 3: Implementuj** (SQL `CREATE OR REPLACE TABLE … AS SELECT h3_parent(h3, 7) AS h3, SUM(...) … GROUP BY 1`).
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat: agregacja H3 res 8→7→6`

### Task 6: Katalog typów i czynników popytu + `/api/catalog`

**Files:**
- Create: `backend/app/catalog.py`, `tests/test_catalog.py`
- Modify: `backend/app/api/routes.py`

**Interfaces:**
- Produces (`backend.app.catalog`):
  ```python
  @dataclass(frozen=True)
  class TagRule:            # wszystkie pary muszą pasować; wartość "*" = dowolna
      tags: dict[str, str]
  @dataclass(frozen=True)
  class Demand:
      id: str; name: str; source: Literal["census", "permits"]
      column: str | None            # kolumna hex_pop_* dla census
      kinds: tuple[str, ...]        # ("sf",) / ("mf",) / ("sf","mf") dla permits
      needs_months: bool
  @dataclass(frozen=True)
  class BusinessType:
      id: str; group: str; name: str; rules: tuple[TagRule, ...]; pkd: str
      suggested_demands: tuple[str, ...]   # pierwszy = domyślny
      bandwidth_km: float; osm_quality: Literal["good", "medium", "poor"]
  GROUPS: tuple[tuple[str, str], ...]      # ("personal","Usługi osobiste"), ("construction","Budowlanka / dom"), ("retail","Handel / gastro / sport")
  DEMANDS: dict[str, Demand]; TYPES: dict[str, BusinessType]
  POOR_WARNING = "Dane o firmach tego typu w OpenStreetMap są bardzo niepełne. Traktuj mapę głównie jako mapę popytu."
  MONTHS_OPTIONS = (12, 24, 36); DEFAULT_MONTHS = 24
  def match_types(tags: Mapping[str, str]) -> list[str]
  def catalog_json() -> dict   # {"groups":[{"id","name","types":[{"id","name","default_demand","suggested_demands","bandwidth_km","osm_quality","warning"}]}],
                               #  "demands":[{"id","name","source","needs_months"}], "months_options":[12,24,36], "default_months":24}
  ```
  Dane: **dokładnie** tabele z spec §5 (9 czynników, 16 typów, reguły tagów, PKD, h, jakość). Kolumny census: `pop_total, pop_f, pop_m, pop_lt15, pop_1564, pop_ge65`. Sugerowane czynniki: pierwszy = „domyślny popyt” z tabeli, dalej 1–2 sensowne (np. `kindergarten`: `pop_lt15, new_sf, new_all`; budowlanka: `new_sf|new_all, new_all|new_sf, pop_total`).
- `GET /api/catalog` → `catalog_json()`.

- [ ] **Step 1: Failing testy**

```python
def test_catalog_counts():
    assert len(TYPES) == 16 and len(DEMANDS) == 9
    assert all(t.suggested_demands[0] in DEMANDS for t in TYPES.values())

def test_match_barber_is_also_hairdresser():
    assert set(match_types({"shop": "hairdresser", "hairdresser": "barber"})) == {"hairdresser", "barber"}

def test_match_requires_all_tags():
    assert match_types({"shop": "trade"}) == []
    assert match_types({"shop": "trade", "trade": "building_supplies"}) == ["diy"]

def test_match_fitness_sports_centre():
    assert match_types({"leisure": "sports_centre", "sport": "fitness"}) == ["fitness"]
    assert match_types({"leisure": "sports_centre", "sport": "soccer"}) == []

def test_api_catalog():
    j = TestClient(app).get("/api/catalog").json()
    beauty = next(t for g in j["groups"] for t in g["types"] if t["id"] == "beauty")
    assert beauty["default_demand"] == "pop_f" and beauty["bandwidth_km"] == 1.5
    paving = next(t for g in j["groups"] for t in g["types"] if t["id"] == "paving")
    assert paving["warning"] == POOR_WARNING
```

- [ ] **Step 2: Run** `uv run pytest tests/test_catalog.py -v` — FAIL.
- [ ] **Step 3: Implementuj.** `match_types` zwraca id w kolejności `TYPES`, bez duplikatów.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat: katalog typów działalności i czynników popytu`

### Task 7: Rdzeń analizy (rozdzielczość, jądro, wynik, top-N)

**Files:**
- Create: `backend/app/analysis/__init__.py`, `backend/app/analysis/resolution.py`, `backend/app/analysis/kernel.py`, `backend/app/analysis/scoring.py`, `tests/test_analysis_core.py`

**Interfaces:**
- Produces:
  - `resolution.py`: `HEX_SPACING_KM = {8: 0.80, 7: 2.11, 6: 5.6}`; `choose_resolution(radius_km: float | None) -> int` (None → 6; ≤ 15 → 8; ≤ 50 → 7); `effective_bandwidth_km(bandwidth_km: float, res: int) -> float` = `max(bandwidth_km, 0.6 * HEX_SPACING_KM[res])`.
  - `kernel.py`: `to_metric(lat: np.ndarray, lng: np.ndarray) -> np.ndarray` (N×2, metry EPSG:2180); `kernel_sums(target_xy: np.ndarray, source_xy: np.ndarray, values: np.ndarray, bandwidth_m: float) -> np.ndarray` — `values` kształtu (M,) lub (M,k), wynik (N,) lub (N,k); `K(d) = exp(-d²/(2h²))`, źródła dalej niż `3h` ignorowane (`cKDTree(source_xy).query_ball_point(target_xy, 3h)`).
  - `scoring.py`: `score(D: np.ndarray, S: np.ndarray) -> np.ndarray` = `D / (S + 1)`; `percentile_rank(x: np.ndarray) -> np.ndarray` (int 0–100, rangi średnie przy remisach); `quantile_breaks(x: np.ndarray, k: int = 5) -> list[float]` (k−1 granic, unikalne, rosnące); `pick_top(scores: np.ndarray, D: np.ndarray, xy: np.ndarray, min_sep_m: float, n: int = 5, d_quantile: float = 0.25) -> list[int]`.

- [ ] **Step 1: Failing testy**

```python
def test_choose_resolution():
    assert [choose_resolution(r) for r in (1, 15, 15.1, 50, None)] == [8, 8, 7, 7, 6]

def test_kernel_single_source():
    t = np.array([[0.0, 0.0], [1000.0, 0.0], [5000.0, 0.0]])
    out = kernel_sums(t, np.array([[0.0, 0.0]]), np.array([10.0]), bandwidth_m=1000)
    assert out[0] == pytest.approx(10.0)
    assert out[1] == pytest.approx(10 * math.exp(-0.5))
    assert out[2] == 0.0                         # > 3h → obcięte

def test_kernel_multi_column():
    out = kernel_sums(np.zeros((1, 2)), np.zeros((2, 2)), np.array([[1.0, 2.0], [3.0, 4.0]]), 500)
    assert out.shape == (1, 2) and out[0].tolist() == [4.0, 6.0]

def test_to_metric_distance():
    xy = to_metric(np.array([52.0, 52.0]), np.array([19.0, 19.01]))
    assert np.linalg.norm(xy[0] - xy[1]) == pytest.approx(686, rel=0.02)  # 0,01° dł. na 52°N

def test_score_no_competition():
    assert score(np.array([100.0]), np.array([0.0]))[0] == 100.0

def test_pick_top_respects_separation_and_demand_floor():
    xy = np.array([[0, 0], [100, 0], [5000, 0], [9000, 0]], float)
    scores = np.array([10, 9, 8, 50.0]); D = np.array([100, 100, 100, 1.0])
    assert pick_top(scores, D, xy, min_sep_m=1000, n=5) == [0, 2]   # 3 odpada (D poniżej kwartyla), 1 za blisko 0

def test_pick_top_separation_larger_than_area():
    xy = np.array([[0, 0], [300, 0]], float)
    assert len(pick_top(np.array([2.0, 1.0]), np.array([5.0, 5.0]), xy, min_sep_m=30000)) == 1
```

- [ ] **Step 2: Run** `uv run pytest tests/test_analysis_core.py -v` — FAIL.
- [ ] **Step 3: Implementuj.** `pick_top`: kandydaci = `D >= np.quantile(D, d_quantile)` i `scores > 0`; zachłannie malejąco po `scores`, odrzucaj w odległości `< min_sep_m` od już wybranych. Docstringi po polsku: KDE, szerokość pasma, dlaczego EPSG:2180.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat: rdzeń analizy - jądro Gaussa, wynik, ranking`

### Task 8: Serwis analizy + `/api/analyze` (popyt census, konkurencja z `poi_counts`)

**Files:**
- Create: `backend/app/db.py`, `backend/app/analysis/service.py`, `tests/factories.py`, `tests/conftest.py`, `tests/test_analyze.py`
- Modify: `backend/app/api/routes.py`

**Interfaces:**
- Consumes: Task 5 (`build_aggregates`, `table_exists`), Task 6 (`TYPES`, `DEMANDS`, `POOR_WARNING`), Task 7 (wszystko).
- Produces:
  - `db.py`: `class DatabaseMissing(Exception)`; `cursor() -> duckdb.DuckDBPyConnection` — globalne połączenie `duckdb.connect(DB_PATH, read_only=True)` tworzone leniwie, zwraca `conn.cursor()` (osobny na żądanie); rzuca `DatabaseMissing`, gdy plik nie istnieje. `reset_connection()` (dla testów).
  - `service.py`:
    ```python
    @dataclass(frozen=True)
    class AnalysisParams:
        type_id: str; demand_id: str
        lat: float | None = None; lng: float | None = None; radius_km: float | None = None
        scope: Literal["local", "poland"] = "local"
        bandwidth_km: float | None = None; months: int = 24
    def run_analysis(con, p: AnalysisParams) -> dict
    ```
    Zwraca: `{"res", "bandwidth_km", "hexes": [[h3, score, D, S, d, s, pct], ...], "top": [{"h3","lat","lng","name","score","D","S"}], "stats": {"n_hex","n_competitors","total_demand","score_breaks","D_breaks","S_breaks"}, "warnings": [str]}`. Liczby zaokrąglone do 1 miejsca; `hexes` tylko te z `D > 0 or S > 0` w obszarze; `*_breaks` = `quantile_breaks` z kolumny. W tym tasku `name` w top = `f"okolice {lat:.3f}, {lng:.3f}"` (nazwy miejsc w Task 11), `scope="poland"` → `NotImplementedError` (Task 17), czynniki `permits` → ostrzeżenie „Dane o pozwoleniach nie zostały jeszcze zaimportowane.” i pusty wynik (Task 15).
  - `tests/factories.py`: `make_db(path: Path, pop: dict[str, float] | None = None, pois: list[tuple[str, float, float]] = (), permits: list[tuple[float, float, str, str, int]] = (), places: list[tuple[str, str, float, float]] = ()) -> Path` — `pop` = h3 res 8 → pop_total (pozostałe kolumny = proporcje krajowe), `pois` = (type_id, lat, lng), `permits` = (lat, lng, "YYYY-MM-01", kind, n), `places` = (name, kind, lat, lng); tworzy tabele źródłowe i woła `build_aggregates`. `tests/conftest.py`: fixture `api_client(tmp_path, monkeypatch)` ustawia `backend.app.config.DB_PATH` na bazę z `make_db` i woła `reset_connection()`.
  - `GET /api/analyze?type&demand&lat&lng&radius_km&bandwidth_km&months&scope` → `run_analysis`. Walidacja (422, komunikaty po polsku): nieznany typ → „Nieznany typ działalności”, nieznany popyt → „Nieznany czynnik popytu”, `radius_km` poza 1–50, `months ∉ {12,24,36}`, przy `scope=local` brak lat/lng albo punkt poza `lat 49.0–55.0, lng 14.0–24.2` → „Punkt poza Polską”. `DatabaseMissing` → 503 „Baza danych nie istnieje. Uruchom: uv run python -m etl.run_all”.

Algorytm `run_analysis` (lokalny): `res = choose_resolution(radius)`; `h = effective_bandwidth_km(bandwidth_km or TYPES[type].bandwidth_km, res)`; komórki bufora = `h3.grid_disk(h3.latlng_to_cell(lat, lng, res), ceil((radius + 3h) / HEX_SPACING_KM[res]) + 1)` przefiltrowane odległością środka (haversine) ≤ `radius + 3h`; obszar = ≤ `radius`. Wczytaj `d_j` z `hex_pop_r{res}.{column}` i `s_j` z `poi_counts_r{res}` (rejestracja DataFrame z listą h3 przez `con.register`, JOIN), `kernel_sums` z `values` (M,2) → D, S; wynik/percentyl tylko dla obszaru; `pick_top(..., min_sep_m = 2 * h * 1000)`. Ostrzeżenia: `osm_quality == "poor"` → `POOR_WARNING`; suma D w obszarze = 0 → „Brak danych o popycie w tym obszarze.”; brak konkurentów w buforze → „Nie znaleziono konkurencji w OpenStreetMap w tym obszarze — wynik pokazuje sam popyt.”

- [ ] **Step 1: Failing testy** (`tests/test_analyze.py`, baza z `make_db`): siatka ~200 heksagonów res 8 wokół (52.23, 21.01) z `pop_total=1000`, kilka POI `beauty`.

```python
def test_analyze_returns_hexes_and_top(api_client):
    j = api_client.get("/api/analyze", params=dict(type="beauty", demand="pop_f", lat=52.23, lng=21.01, radius_km=3)).json()
    assert j["res"] == 8 and len(j["hexes"]) > 10 and 1 <= len(j["top"]) <= 5
    best = max(j["hexes"], key=lambda r: r[1])
    assert best[1] == j["top"][0]["score"]

def test_competitor_lowers_score_nearby(api_client): ...   # heksagon z POI ma niższy score niż odległy heksagon o tym samym popycie

def test_analyze_no_competitors_warns(api_client):
    j = api_client.get("/api/analyze", params=dict(type="paving", demand="pop_total", lat=52.23, lng=21.01, radius_km=3)).json()
    assert any("konkurencji" in w for w in j["warnings"]) and POOR_WARNING in j["warnings"]
    assert all(r[3] == 0 and r[1] == r[2] for r in j["hexes"])          # S=0 → score = D

def test_analyze_half_empty_area(api_client):
    # dane tylko na wschód od środka (symuluje morze/zagranicę na zachodzie)
    j = ...; assert j["top"] and all(t["lng"] >= center_lng - 0.01 for t in j["top"])

def test_analyze_validation(api_client):
    assert api_client.get("/api/analyze", params=dict(type="xxx", demand="pop_f", lat=52, lng=21, radius_km=3)).status_code == 422
    r = api_client.get("/api/analyze", params=dict(type="beauty", demand="pop_f", lat=40, lng=21, radius_km=3))
    assert r.status_code == 422 and "poza Polską" in r.text

def test_analyze_db_missing(tmp_path, monkeypatch):  # DB_PATH na nieistniejący plik → 503 z "etl.run_all"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_analyze.py -v` — FAIL.
- [ ] **Step 3: Implementuj** `db.py`, `service.py`, endpoint, `factories.py`, `conftest.py`.
- [ ] **Step 4: Run** `uv run pytest -v` — wszystkie PASS.
- [ ] **Step 5: Commit** — `feat: endpoint analizy z jądrem Gaussa`

### Task 9: Frontend — katalog, analiza, heksagony, legenda, warstwy, popup

**Files:**
- Create: `frontend/js/api.js`, `frontend/js/colors.js`, `frontend/js/ui.js`
- Modify: `frontend/js/app.js`, `frontend/js/map.js`, `frontend/css/style.css`

**Interfaces:**
- Consumes: `/api/catalog`, `/api/analyze` (Task 6, 8); `MapView` (Task 2).
- Produces:
  - `api.js`: `getCatalog()`, `analyze(params)`, `getPoi(type, bbox)`, `geocode(q)`, `getMeta()` — `fetch` + rzucanie `Error(detail)` z polskim komunikatem z odpowiedzi.
  - `colors.js`: `PALETTE = ['#ffffcc', '#a1dab4', '#41b6c4', '#2c7fb8', '#253494']` (ColorBrewer YlGnBu, przyjazna daltonistom); `colorFor(value, breaks) -> string`.
  - `ui.js`: `renderCatalog(catalog)`, `selectedParams() -> object`, `renderLegend(title, breaks)`, `renderWarnings(list)`, `renderTop(list, onClick)`, `setLoading(bool)`, `showError(msg)`.
  - `MapView.setHexes(rows, valueIndex, breaks, colors)` (wielokąty z `h3.cellToBoundary(h3)` w pane `hexes`, `fillOpacity` z suwaka, cienka biała obwódka), `setHexOpacity`, `onHexClick`, `highlightHex`.

- [ ] **Step 1: Implementuj:** po załadowaniu `getCatalog()` → selecty (`<optgroup>` per grupa); zmiana typu ustawia domyślny popyt, sugerowane czynniki oznaczone „(sugerowane)”, suwak zasięgu klienta ustawia `bandwidth_km` typu; `#months-row` widoczny tylko dla `needs_months`. „Analizuj” → `analyze()` → `setHexes` dla warstwy z `#layer-switch` (`score` → indeks 1, `D` → 2, `S` → 3; legenda z `stats.score_breaks|D_breaks|S_breaks`, tytuły: „Klienci na 1 konkurenta”, „Popyt w zasięgu”, „Konkurencja w zasięgu”). Przełączenie warstwy przerysowuje bez nowego zapytania. Popup heksagonu: „Popyt w zasięgu”, „Konkurenci w zasięgu”, „Na 1 konkurenta”, „Percentyl” (wartości z `toLocaleString('pl-PL')`). Bez kliknięcia mapy przycisk pokazuje komunikat „Wybierz punkt na mapie albo wyszukaj adres”.
- [ ] **Step 2: Weryfikacja ręczna** na bazie testowej: `uv run python -c "from tests.factories import make_db; ..."` zbuduj `data/app.duckdb` z syntetycznymi danymi wokół Warszawy (albo prawdziwą po Task 4–5 + `run_all --only population,aggregate` gdy gotowe), `start.bat`, klik → Analizuj: heksagony w kolorach, legenda z liczbami, etykiety miast widoczne NAD heksagonami, przełączanie warstw działa, popup pokazuje liczby, suwak przezroczystości działa.
- [ ] **Step 3: Commit** — `feat: frontend rysuje heatmapę analizy`

---

## Milestone M2 — biznesy z OSM (MVP)

### Task 10: ETL OSM → `poi`, `places`

**Files:**
- Create: `etl/osm_poi.py`, `tests/fixtures/tiny.osm`, `tests/test_osm_poi.py`

**Interfaces:**
- Consumes: `match_types` (Task 6).
- Produces: `PLACE_KINDS = ("city", "town", "village", "suburb", "neighbourhood", "quarter", "hamlet")`; `extract(pbf_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]` — `poi`: `osm_id` (`"n123"`/`"w456"`), `type_id`, `name`, `lat`, `lng` (jeden wiersz na dopasowany typ); `places`: `name`, `kind`, `lat`, `lng`; `build_poi_tables(pbf_path: Path, con) -> dict[str, int]` — zapisuje `poi(osm_id, type_id, name, lat, lng, h3)` i `places(name, kind, lat, lng, h3)` (h3 res 8).

- [ ] **Step 1: Fixture `tiny.osm`** (OSM XML, pyosmium go czyta): węzeł `shop=beauty name=Salon A`; węzeł `shop=hairdresser hairdresser=barber`; way `shop=doityourself` z 4 węzłami BEZ tagów (kwadrat); węzeł `place=suburb name=Zaodrze`; węzeł `amenity=bench` (nie pasuje); węzeł `place=county` (nie pasuje).
- [ ] **Step 2: Failing testy**: `poi` ma 4 wiersze (beauty, hairdresser, barber, diy); punkt `diy` = średnia 4 węzłów (±1e-6); `places` = 1 wiersz `("Zaodrze", "suburb", …)`; `build_poi_tables` na DuckDB w pamięci zapisuje tabele z kolumną `h3` o rozdzielczości 8.
- [ ] **Step 3: Run** `uv run pytest tests/test_osm_poi.py -v` — FAIL.
- [ ] **Step 4: Implementuj** przez `osmium.FileProcessor(str(path)).with_locations().with_filter(osmium.filter.KeyFilter("shop", "amenity", "craft", "leisure", "place"))`. Test z way bez tagowanych węzłów sprawdza, że cache lokalizacji jest wypełniany przed filtrem — jeśli nie, użyj `osmium.SimpleHandler` z `apply_file(path, locations=True, idx="flex_mem")`. Węzły way z `not n.location.valid()` pomijaj. Relacje pomijaj.
- [ ] **Step 5: Run** — PASS.
- [ ] **Step 6: Commit** — `feat: ETL punktów biznesowych i nazw miejsc z OSM`

### Task 11: Nazwy top-5, `/api/poi`

**Files:**
- Modify: `backend/app/analysis/service.py`, `backend/app/api/routes.py`
- Create: `tests/test_places_poi.py`

**Interfaces:**
- Produces: `nearest_place_name(con, lat: float, lng: float, max_km: float = 3.0) -> str | None` w `service.py` — kandydaci z `places` w bbox ±0,05°, priorytet rodzaju `suburb, neighbourhood, quarter, village, hamlet` (0) > `town` (1) > `city` (2), w obrębie priorytetu najbliższy; `run_analysis` używa go dla `top[].name` (fallback `f"okolice {lat:.3f}, {lng:.3f}"`; brak tabeli `places` → fallback). `GET /api/poi?type&bbox=minLng,minLat,maxLng,maxLat` → `{"items": [{"lat","lng","name"}], "truncated": bool}`, limit 5000; zły bbox → 422 „Nieprawidłowy bbox”.

- [ ] **Step 1: Failing testy**: suburb 2 km od punktu wygrywa z city 0,5 km; nic w 3 km → `None`; top analizy ma nazwę z `places`; `/api/poi` zwraca tylko punkty danego typu w bbox; 5001 punktów → 5000 i `truncated: true`.
- [ ] **Step 2: Run** `uv run pytest tests/test_places_poi.py -v` — FAIL.
- [ ] **Step 3: Implementuj.**
- [ ] **Step 4: Run** `uv run pytest -v` — PASS.
- [ ] **Step 5: Commit** — `feat: nazwy najlepszych lokalizacji i endpoint punktów konkurencji`

### Task 12: Frontend — top-5, punkty firm, ostrzeżenia

**Files:**
- Modify: `frontend/js/app.js`, `frontend/js/ui.js`, `frontend/js/map.js`, `frontend/css/style.css`

**Interfaces:**
- Consumes: `/api/poi`, pola `top`, `warnings` z `/api/analyze`.
- Produces: `MapView.setPoi(points)` (kółka r=4, kolor `#D85A30`, biała obwódka, tooltip z nazwą lub „bez nazwy”).

- [ ] **Step 1: Implementuj:** lista top-5 („1. Zaodrze — 2 140 klientów / konkurenta”), klik → `flyTo` (zoom 14) + `highlightHex`; ostrzeżenia w żółtym boxie `#warnings`; `#poi-checkbox` włączony → `getPoi` dla bieżącego bbox przy zoomie ≥ 11 (debounce 300 ms na `moveend`), przy mniejszym zoomie komunikat „Przybliż mapę, aby zobaczyć firmy”; `truncated` → dopisek „pokazano 5000 pierwszych”.
- [ ] **Step 2: Weryfikacja ręczna** (po prawdziwym `run_all --only osm,aggregate` albo na bazie syntetycznej): top-5 klikalne, punkty firm pokrywają się z niskim wynikiem okazji, ostrzeżenie dla „Brukarstwo”.
- [ ] **Step 3: Commit** — `feat: lista najlepszych miejsc i punkty konkurencji na mapie`

---

## Milestone M3 — budowlanka (pozwolenia GUNB)

### Task 13: Parsery CSV GUNB → `permits_raw`

**Files:**
- Create: `etl/permits.py`, `tests/fixtures/gunb_permits_sample.csv`, `tests/fixtures/gunb_notifications_sample.csv`, `tests/test_permits.py`

**Interfaces:**
- Produces: `PERMIT_COLUMNS: list[str]`, `NOTIF_COLUMNS: list[str]` (nagłówki z docs/zrodla-danych.md §1, duplikaty przemianowane: `cecha_1, cecha_2`); `class UnexpectedHeader(ValueError)`;
  `normalize_obreb_id(jednostka: str, obreb: str) -> str | None` — `"160602_4", "38"` → `"160602_4.0038"`; puste/brak cyfr → `None`; bierze cyfry wiodące obrębu;
  `parse_permits(path: Path) -> pd.DataFrame` i `parse_notifications(path: Path) -> pd.DataFrame` — wspólne kolumny wyjściowe: `source_id, source ("pozwolenie"|"zgloszenie"), kind ("sf"|"mf"), date (datetime64), obreb_id, terc`;
  `build_permits_raw(permit_paths: list[Path], notif_paths: list[Path], con) -> int` — tabela `permits_raw`, deduplikacja po `source_id`, log liczby wierszy odrzuconych (bez obrębu).
  Reguły: `kategoria == "I"` → `sf`, `"XIII"` → `mf`, inne odrzucić; pozwolenia: `nazwa_zamierzenia_bud` zaczyna się od `"budowa nowego"` i `nazwa_zam_budowlanego` nie zawiera `"zmian"` (case-insensitive), data = `data_wydania_decyzji` (pusta → `data_wplywu_wniosku`), `source_id = numer_gunb`; zgłoszenia: `rodzaj_zam_budowlanego` zaczyna się od `"budowa nowego"`, data = `data_wplywu_wniosku_do_urzedu`, `source_id = numer_ewidencyjny_system`, parcela z `jednostki_numer`.
  Czytanie: `pd.read_csv(sep=";", dtype=str, keep_default_na=False, encoding="utf-8-sig", quotechar='"')`; nagłówek porównany z oczekiwanym → `UnexpectedHeader` z listą różnic.

- [ ] **Step 1: Fixtures** — po ~8 wierszy wyciętych z prawdziwych plików (pobierz `wynik_opolskie.zip` i `wynik_zgloszenia_2022_up.zip`) + dopisane ręcznie przypadki: wiersz z nową linią w polu w cudzysłowie, wiersz „zmiana pozwolenia…”, kat. XXVI, kat. XIII, pusty obręb, zduplikowany `numer_gunb`.
- [ ] **Step 2: Failing testy**: `normalize_obreb_id` (przypadki wyżej + `"", "0038"` → None); `parse_permits` zwraca tylko kat. I/XIII „budowa nowego” bez „zmian”, poprawne `kind`, `date`, `obreb_id`; wiersz z nową linią parsuje się w całości; `parse_notifications` analogicznie; zmieniony nagłówek → `UnexpectedHeader`; `build_permits_raw` deduplikuje.
- [ ] **Step 3: Run** `uv run pytest tests/test_permits.py -v` — FAIL.
- [ ] **Step 4: Implementuj.**
- [ ] **Step 5: Run** — PASS.
- [ ] **Step 6: Commit** — `feat: parsery rejestru pozwoleń i zgłoszeń GUNB`

### Task 14: Geokodowanie obrębów (ULDK) → `obreb_geom`, `permits_r8`

**Files:**
- Create: `etl/geocode_obreby.py`, `tests/test_geocode_obreby.py`

**Interfaces:**
- Consumes: `permits_raw` (Task 13); po zakończeniu Task 5 `build_aggregates` tworzy `permits_r7|r6`.
- Produces:
  `ULDK_URL = "https://uldk.gugik.gov.pl/"`;
  `parse_uldk_response(text: str) -> tuple[str, str, str] | None` — `(id, nazwa, wkt_bez_SRID)`; pierwsza linia ≠ `"0"` albo brak drugiej → `None`; obsługuje odpowiedź 2-polową `id|wkt` i 3-polową `id|nazwa|wkt`;
  `wkt_to_latlng(wkt: str) -> tuple[float, float]` — `shapely.wkt.loads(...).representative_point()`;
  `class UldkClient`: `__init__(self, client: httpx.Client, base_url: str = ULDK_URL)`, `region(self, obreb_id: str) -> tuple[str, float, float] | None` (`request=GetRegionById&id=…&result=teryt,region,geom_wkt&srid=4326`), `commune(self, jednostka_id: str) -> tuple[str, float, float] | None` (`GetCommuneById`, `result=teryt,commune,geom_wkt`); retry 3× z przerwą 1/2/4 s przy błędach sieci i 5xx;
  `geocode_missing(con, uldk: UldkClient, workers: int = 5, batch: int = 200) -> dict[str, int]` — dla `DISTINCT obreb_id` z `permits_raw` nieobecnych w `obreb_geom(obreb_id PK, name, lat, lng, status)`; `status ∈ {"region","commune","missing"}`; fallback gmina = część `obreb_id` przed kropką; zapis co `batch` (wznawialne); ThreadPoolExecutor do zapytań, zapis do DuckDB tylko w wątku głównym; zwraca liczniki statusów;
  `build_permits_hex(con) -> int` — `permits_r8(h3, month DATE, kind, n)`: JOIN `permits_raw` z `obreb_geom` (status ≠ missing), h3 res 8 z lat/lng, `month = date_trunc('month', date)`.

- [ ] **Step 1: Failing testy** (`httpx.MockTransport`): prawdziwe odpowiedzi z docs (`"0\n160602_4.0038|Namysłów|SRID=4326;MULTIPOLYGON(((...)))"`, `"0\n160602_4.0038.178/11|SRID=4326;POLYGON((...))"`, `"-1 brak wyników"`) → poprawny parse/None; punkt wewnątrz poligonu; mock zwracający 500 dwa razy i potem 200 → sukces (z `time.sleep` zamockowanym); `geocode_missing` z obrębem nieznanym (region → None, commune → OK) zapisuje `status="commune"`; drugie wywołanie nie wysyła żadnych zapytań (cache); `build_permits_hex` agreguje 3 pozwolenia z 2 miesięcy do 2 wierszy.
- [ ] **Step 2: Run** `uv run pytest tests/test_geocode_obreby.py -v` — FAIL.
- [ ] **Step 3: Implementuj.**
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat: geokodowanie obrębów przez ULDK i agregacja pozwoleń do H3`

### Task 15: Czynniki `new_*` w analizie + wybór okresu w UI

**Files:**
- Modify: `backend/app/analysis/service.py`, `frontend/js/app.js`, `frontend/js/ui.js`
- Create: `tests/test_analyze_permits.py`

**Interfaces:**
- Consumes: `permits_r8|r7|r6` (Task 14 + 5), `Demand.kinds`, `Demand.needs_months`.
- Produces: w `run_analysis` dla `source == "permits"`: `d_j = SUM(n)` z `permits_r{res}` gdzie `kind IN kinds` i `month >= cutoff`, `cutoff = pierwszy dzień miesiąca (max(month) w tabeli − months + 1)` (okno liczone od najnowszych danych, nie od dzisiaj); dodatkowe pole odpowiedzi `"permits_period": {"from": "YYYY-MM", "to": "YYYY-MM"}`.

- [ ] **Step 1: Failing testy**

```python
# fixture `api_client_with_permits` zdefiniuj w tym pliku: jak `api_client`, ale make_db(..., permits=[...]) z danymi poniżej
def test_new_sf_counts_only_window(api_client_with_permits):
    # pozwolenia sf: 5 szt. 2026-09, 7 szt. 2024-01 (poza 24 mies.), mf: 3 szt. 2026-09
    j = client.get("/api/analyze", params=dict(type="paving", demand="new_sf", months=24, lat=..., lng=..., radius_km=5)).json()
    assert sum(r[4] for r in j["hexes"]) == pytest.approx(5)
    assert j["permits_period"] == {"from": "2024-10", "to": "2026-09"}

def test_new_all_sums_kinds(...):  # = 8

def test_analyze_permits_missing_warns(api_client):   # baza bez permits_r* → 200, hexes [], ostrzeżenie "pozwoleniach"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_analyze_permits.py -v` — FAIL.
- [ ] **Step 3: Implementuj** backend; we froncie `#months-select` (12/24/36, domyślnie 24) wysyłany jako `months`, pod legendą tekst „Pozwolenia: {from} – {to}. Pozwolenie nie oznacza wybudowanego domu.”
- [ ] **Step 4: Run** `uv run pytest -v` — PASS. Weryfikacja ręczna: „Brukarstwo” + „Nowe domy jednorodzinne” na przedmieściach dużego miasta pokazuje skupiska.
- [ ] **Step 5: Commit** — `feat: popyt z nowych budów z wyborem okresu`

---

## Milestone M4 — wersja do oddania

### Task 16: Orkiestracja ETL + `meta` + `/api/meta`

**Files:**
- Create: `etl/run_all.py`, `tests/test_run_all.py`
- Modify: `backend/app/api/routes.py`

**Interfaces:**
- Consumes: wszystkie moduły ETL (Task 3, 4, 5, 10, 13, 14).
- Produces: `STEPS = ("download", "population", "osm", "permits", "geocode", "permits_hex", "aggregate")`; `run(steps: list[str] | None = None, force: bool = False, data_dir: Path = DATA_DIR) -> None`; CLI `uv run python -m etl.run_all [--only population,aggregate] [--force]`; każdy krok loguje czas i liczby, a po sukcesie wpisuje do `meta(source VARCHAR PK, url VARCHAR, downloaded_at TIMESTAMP, rows BIGINT)` (`source ∈ {"census","osm","gunb","uldk"}`). Kroki pomijają się, jeśli wynik istnieje (`table_exists`) i brak `--force`; `download` i `geocode` zawsze wznawialne. `GET /api/meta` → `{"sources": [{"source","url","downloaded_at","rows"}], "attribution": ATTRIBUTION}`.

- [ ] **Step 1: Failing testy**: `run(["aggregate"])` na bazie z samym `hex_pop_r8` tworzy `hex_pop_r6`; nieznany krok → `ValueError`; `/api/meta` zwraca wpisy z tabeli `meta` i `attribution`.
- [ ] **Step 2: Run** `uv run pytest tests/test_run_all.py -v` — FAIL.
- [ ] **Step 3: Implementuj.**
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat: orkiestracja ETL i metadane źródeł`

### Task 17: Tryb „cała Polska” + cache

**Files:**
- Modify: `backend/app/analysis/service.py`, `backend/app/api/routes.py`
- Create: `tests/test_analyze_poland.py`

**Interfaces:**
- Produces: `scope="poland"` w `run_analysis`: `res = 6`, obszar = bufor = wszystkie komórki z `hex_pop_r6` ∪ `poi_counts_r6` (∪ `permits_r6` dla `new_*`); top-5 z separacją `max(2h, 20 km)`. `cached_analysis(p: AnalysisParams) -> dict` w `service.py` — `functools.lru_cache(maxsize=128)` na parametrach z lat/lng zaokrąglonymi do 3 miejsc, `radius_km` do 0,5, `bandwidth_km` do 0,1; endpoint używa `cached_analysis`; `reset_connection()` czyści cache.

- [ ] **Step 1: Failing testy**: `scope=poland` (bez lat/lng) → `res == 6`, heksagony z kilku odległych miejsc bazy testowej; drugie identyczne wywołanie nie odpytuje bazy (zamockuj/zlicz wywołania funkcji ładującej); `scope=poland` + lat/lng spoza Polski → 200 (lat/lng ignorowane).
- [ ] **Step 2: Run** `uv run pytest tests/test_analyze_poland.py -v` — FAIL.
- [ ] **Step 3: Implementuj.**
- [ ] **Step 4: Run** `uv run pytest -v` — PASS.
- [ ] **Step 5: Commit** — `feat: analiza dla całej Polski i cache wyników`

### Task 18: Wyszukiwarka adresów (proxy Nominatim)

**Files:**
- Create: `backend/app/services/__init__.py`, `backend/app/services/geocode.py`, `tests/test_geocode.py`
- Modify: `backend/app/api/routes.py`

**Interfaces:**
- Produces: `class Geocoder`: `__init__(self, client: httpx.Client, min_interval_s: float = 1.0, base_url: str = "https://nominatim.openstreetmap.org/search")`, `search(self, q: str) -> list[dict]` → `[{"name","lat","lng"}]` (max 5); parametry `q, format=jsonv2, countrycodes=pl, limit=5, accept-language=pl`; zapytania < 3 znaków (po `strip`) → `[]` bez wywołania sieci; cache słownikowy po `q.strip().lower()`; `threading.Lock` + odstęp ≥ `min_interval_s` między zapytaniami; `class GeocoderUnavailable(Exception)` przy błędzie sieci/5xx. `GET /api/geocode?q=` → lista; `GeocoderUnavailable` → 502 „Wyszukiwarka adresów chwilowo niedostępna”.

- [ ] **Step 1: Failing testy** (`MockTransport`): `test_geocode_short_query` (`"  a "` → `[]`, 0 wywołań); `test_geocode_maps_fields` (`display_name`→`name`, `lat/lon` jako float); `test_geocode_cache` (2× „Opole” → 1 wywołanie); `test_geocode_polish_chars` („Łódź Piotrkowska” trafia do parametru `q` bez zmian); `test_geocode_upstream_error` (500 → endpoint 502 z polskim komunikatem).
- [ ] **Step 2: Run** `uv run pytest tests/test_geocode.py -v` — FAIL.
- [ ] **Step 3: Implementuj.**
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat: wyszukiwarka adresów przez Nominatim`

### Task 19: Frontend — dopracowanie (wyszukiwarka, cała Polska, URL, mobile, stany, stopka)

**Files:**
- Modify: `frontend/index.html`, `frontend/js/app.js`, `frontend/js/ui.js`, `frontend/js/map.js`, `frontend/css/style.css`

**Interfaces:**
- Consumes: `/api/geocode`, `/api/meta`, `scope=poland`.

- [ ] **Step 1: Implementuj:**
  - `#search-input`: debounce 400 ms, ≥ 3 znaki, lista `#search-results`, wybór → pinezka + `flyTo` (zoom 12); klawiatura: strzałki + Enter + Escape.
  - `#poland-checkbox`: wyłącza promień i pinezkę, wysyła `scope=poland`, po wyniku `fitBounds` Polski.
  - Stan w URL hash: `#type=beauty&demand=pop_f&lat=50.668&lng=17.923&r=10&bw=1.5&m=24&pl=0&layer=score`; odczyt przy starcie → automatyczna analiza; aktualizacja po każdej analizie (`history.replaceState`).
  - Stany: spinner i blokada podwójnego kliknięcia na „Analizuj”; błąd API → czerwony komunikat pod przyciskiem; 503 → komunikat z instrukcją ETL; pusty wynik → „Brak danych w tym obszarze”.
  - `#meta-footer`: „Dane: OSM {data}, GUNB {data}, Spis 2021” z `/api/meta`.
  - Mobile < 768 px: arkusz na dole z uchwytem do zwinięcia/rozwinięcia; po „Analizuj” arkusz się zwija, żeby było widać mapę.
- [ ] **Step 2: Weryfikacja ręczna** w przeglądarce (desktop 1440×900 i mobile 375×812): wyszukanie „Opole Krakowska” → analiza → skopiowanie URL do nowej karty odtwarza ten sam widok; „Cała Polska” rysuje się < 3 s; brak poziomego scrolla na mobile; zatrzymany serwer → czytelny błąd.
- [ ] **Step 3: Commit** — `feat: wyszukiwarka, tryb całej Polski, link do widoku, widok mobilny`

### Task 20: Pełny ETL na prawdziwych danych + kontrola jakości + dostęp przez Tailscale

**Files:**
- Create: `etl/sanity.py`, `docs/raport-etl.md`

**Interfaces:**
- Consumes: wszystko powyżej.
- Produces: `check(con) -> list[str]` w `etl/sanity.py` (lista problemów; pusta = OK) + CLI `uv run python -m etl.sanity`. Progi: suma `hex_pop_r8.pop_total` ∈ [36,9 mln; 37,2 mln]; liczba `poi` z `type_id='hairdresser'` ≥ 8000; `places` ≥ 40 000; `obreb_geom` z `status='missing'` ≤ 5% wierszy; `permits_r8` z `kind='sf'` w ostatnich 12 miesiącach ≥ 50 000; każda tabela `*_r6` niepusta.

- [ ] **Step 1: Uruchom** (w tle, przy zatrzymanym serwerze): `uv run python -m etl.run_all` — Expected: kończy się bez wyjątku (kilka godzin; najdłużej OSM i geokodowanie).
- [ ] **Step 2: Run** `uv run python -m etl.sanity` — Expected: brak problemów. Jeśli są — popraw przyczynę (nie progi), zanotuj w raporcie.
- [ ] **Step 3: Zapisz `docs/raport-etl.md`**: czasy kroków, liczby wierszy, % niezgeokodowanych obrębów, rozmiar `app.duckdb`, zaobserwowane anomalie.
- [ ] **Step 4: Weryfikacja ręczna**: `start.bat`; scenariusze: (a) „Salon kosmetyczny / Kobiety / Opole, 10 km”, (b) „Brukarstwo / Nowe domy jednorodzinne / okolice Wrocławia 30 km”, (c) „Sklep spożywczy / cała Polska”. Każdy < 3 s, sensowny wynik. Otwarcie z drugiego urządzenia przez Tailscale `http://<nazwa-pc>:8000` (zapora Windows: reguła przychodząca TCP 8000 dla profilu prywatnego). Instrukcję dla właściciela (instalacja Tailscale na PC i laptopie) zapisz w README w Task 21.
- [ ] **Step 5: Commit** — `chore: pełny ETL, kontrola jakości danych`

---

## Milestone M5 — oddanie

### Task 21: README (dla prowadzącego) + ściąga do obrony

**Files:**
- Create: `README.md`, `docs/sciaga-do-obrony.md`, `docs/screenshots/*.png`

- [ ] **Step 1: `README.md` po polsku**: cel aplikacji i przykład użycia (salon kosmetyczny, brukarz), zrzuty ekranu, źródła danych z licencjami, opis metody (KDE/2SFCA, H3, interpolacja powierzchniowa, geokodowanie obrębów) z wzorem `score = D / (S + 1)`, architektura (schemat z spec §2), instalacja (`winget install astral-sh.uv`, `uv sync`, `uv run python -m etl.run_all`, `start.bat`), dostęp przez Tailscale, ograniczenia danych, plany rozwoju (M6–M10).
- [ ] **Step 2: `docs/sciaga-do-obrony.md`** — prostym językiem, każde pojęcie 3–6 zdań + „gdzie to jest w kodzie” (plik:funkcja): układy współrzędnych (3035/2180/4326) i dlaczego odległości w metrycznym; siatka H3 i dlaczego heksagony; MAUP; interpolacja powierzchniowa; KDE i szerokość pasma; efekt krawędzi i bufor; model 2SFCA vs nasz wskaźnik; geokodowanie (działka → obręb → punkt); kompletność danych VGI/OSM; dlaczego pozwolenie ≠ dom; jak działa top-5 (non-maximum suppression). Na końcu 10 przykładowych pytań prowadzącego z odpowiedziami.
- [ ] **Step 3: Commit** — `docs: README i ściąga do obrony`

---

## Etapy opcjonalne (osobny plan po decyzji właściciela po M5)

- **M6 Trend budowlanki** — warstwa „ostatnie 12 mies. vs poprzednie 12” z `permits_r*`.
- **M7 Hot-spoty Getis-Ord Gi\*** — `esda.G_Local` na `score` z wagami z sąsiedztwa H3 (`grid_disk` k=1), obrys heksagonów z p < 0,05 i z > 0.
- **M8 Model ML luki rynkowej** — `HistGradientBoostingRegressor(loss="poisson")`, cel = liczba firm typu w heksagonie res 8, cechy = ludność wg grup w pierścieniach, nowe budowy, gęstość wszystkich POI (proxy kompletności OSM), przystanki; walidacja `GroupKFold` po województwach; warstwa „oczekiwane − rzeczywiste”.
- **M9 CEIDG** — po otrzymaniu tokenu: firmy wg PKD (status aktywny), geokodowanie adresów (GUGiK), drugie źródło `poi` z polem `source`.
- **M10 Dokładne działki** — `GetParcelById` dla pozwoleń z ostatnich 24 mies.
