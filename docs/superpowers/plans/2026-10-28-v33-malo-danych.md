# v3.3 — oznaczanie „mało danych o firmach” (plan wykonawczy)

> Dla sesji implementującej (Sonnet). Przeczytaj najpierw `CLAUDE.md`. TDD, commit po każdym zadaniu (po polsku, prefiksy jak w CLAUDE.md §7).
> Nie zatrzymuj serwera Marcina na porcie 8000. ETL uruchamiasz na KOPII bazy (Task 0), weryfikujesz na porcie 8001.

## Problem (zmierzony 2026-10-28)

Na gotowej mapie Polski (salon kosmetyczny × kobiety) „najlepsze miejsca” to Olsztynek, Nowe, Sianów, Krośniewice, Nowogrodziec.
To miasteczka, w których **w danych nie ma ani jednego salonu** w promieniu 2 km, choć przy ich ludności średnio byłoby ok. 4–6.
Huff wierzy danym, więc „nowa firma zgarnia wszystkie klientki” — mapa pokazuje dziury w OSM/Overture, a nie okazje.
Marcin zgodził się: takie miejsca oznaczamy jako „mało danych o firmach” i wykluczamy z najlepszych miejsc.

## Metoda (ustalona, z pomiarów w scratchpadzie — nie zmieniaj progów bez nowego pomiaru)

1. **Źródło popytu w luce** (liczone na komórkach H3 res 9 z ludnością, osobno dla każdego typu z `TYPES`):
   - `oczekiwane_i = (ludność pop_total w promieniu 2 km od środka komórki) × (liczba firm typu w Polsce / ludność Polski)`
   - `w_danych_i = liczba firm typu (tabela poi) w promieniu 2 km`
   - luka, gdy `oczekiwane_i ≥ 3` **i** `w_danych_i ≤ 0,25 · oczekiwane_i`.
   - Dlaczego: 2 km ≈ promień małego miasta; poniżej 3 oczekiwanych firm brak firm bywa prawdziwy (wieś), więc nie oceniamy;
     „≤ ¼ średniej krajowej” to różnica, której nie tłumaczy specyfika miasteczka (miasteczka mają średnio *więcej* salonów
     na mieszkańca niż średnia krajowa — `docs/kompletnosc-danych.md`).
   - Pomiar: salony — 1,7% ludności w luce, fryzjerzy 0,9%, sklepy 0,4%. Brzeg, Oława, Wrocław — bez luki.
2. **Udział klientów z luki** w punkcie g: drugi przebieg Huffa z wagami `d_i · luka_i` (ta sama dostępność konkurencji C_i):
   `E_luka(g)`; `udział = E_luka / E`. **Wiarygodni klienci** `E_wiar = E − E_luka`.
   - Dla źródeł popytu w res < 9 (zasięg > 2 km) `luka_i` = udział ludności komórek-dzieci res 9 w luce (liczba 0–1).
3. **Użycie:**
   - kolor mgły — bez zmian (pełne E, model mówi, co mówi);
   - **szare kreskowanie** na komórkach z `udział > 0,5` (tylko warstwa „Gdzie otworzyć”);
   - **top-5** — tylko komórki z `udział ≤ 0,5`, sortowane po `E_wiar` (bez tego wygrywały sąsiednie komórki tej samej dziury z udziałem 46–49%);
     pokazywana liczba = E (jak w dymku), kolejność = po `E_wiar`;
   - dymek po kliknięciu: ostrzeżenie z liczbami (Task 4);
   - podsumowanie obszaru (okrąg / widoczny obszar): ostrzeżenie, gdy cały obszar spełnia warunek luki (Task 4).
   - Pomiar po zmianie (salon × kobiety, Polska): top-10 = Rudki, Pruchnik, Piekło, Bierówki, Zdzieszowice, Bartoszyce, Chełmża…
     (udział ≤ 9%). Sklepy spożywcze — bez zmian (luka nie dotyka czołówki). To jest oczekiwany wynik scenariusza (a).
4. **Ograniczenie (napisz uczciwie w README/ściądze):** miejscowość, w której oczekujemy < 3 firm (np. 3-tysięczne miasteczko i salony),
   nie jest oceniana — przy tak małych liczbach brak firm może być prawdziwy. Warstwa „Konkurencja” (sam typ, bez popytu) na razie bez kreskowania.

Stałe w `backend/app/catalog.py` (obok `DEFAULT_MONTHS`), z komentarzem po polsku:
`GAP_RADIUS_KM = 2`, `GAP_MIN_EXPECTED = 3`, `GAP_MAX_RATIO = 0.25`, `GAP_SHARE = 0.5`.

## Task 0 — kopia bazy do pracy

`mkdir data/v33 && cp data/app.duckdb data/v33/app.duckdb` (365 MB; `data/` jest w gitignore).
ETL na kopii: `GO_DATA_DIR=data/v33` — sprawdź, czy `etl/run_all.py` (linia ~53 łączy się z `data_dir / "app.duckdb"`) bierze katalog z
`config.DATA_DIR`; jeśli nie, popraw tak, by brał (`GO_DATA_DIR` już obsługuje `backend/app/config.py`). Serwer testowy:
`GO_DATA_DIR=data/v33 uv run uvicorn backend.app.main:app --port 8001`.

## Task 1 — krok ETL `gaps`

Nowy plik `etl/gaps.py`, krok `gaps` w `etl/run_all.py` między `aggregate` a `national` (STEPS + dispatch + sanity).
- `gap_rates(type_id, firms, population, rate)` — średnia krajowa firm na mieszkańca dla każdego typu z `TYPES`.
- `gap_share(type_id, res, h3, share)` — tylko wiersze z `share > 0`; res 9: share ∈ {1}; res 8, 7, 6: udział ludności (pop_total) dzieci res 9 w luce.
- Funkcja czysta do testów: `gap_flags(pop_xy, pop_w, firm_xy, rate) -> np.ndarray[bool]` (cKDTree, `query_ball_point(..., return_length=True)`
  dla firm; dla ludności suma wag — wzór jak w scratchpadzie: `[pw[i].sum() for i in tree.query_ball_point(xy, R)]`, ok. 12 s na typ).
- Testy (`tests/test_gaps.py`, fabryki z `tests/factories.py`): miasteczko bez firm → luka; to samo z ¼+ firm → brak; wieś (oczekiwane < 3) → brak;
  agregacja do res 8 daje udział ludności.
- `etl/sanity.py`: tabela istnieje, udział ludności w luce dla `beauty` w przedziale 0,5–5%.

## Task 2 — Huff z udziałem luki (wspólna funkcja) + gotowa mapa Polski

- `backend/app/analysis/service.py`: funkcja `load_gap_share(con, type_id, res, h3_list) -> np.ndarray` (0 dla brakujących).
  `load_demand` musi umieć zwrócić także `h3` źródeł (dodaj parametr/zwracaj czwartą kolumnę — nie dopasowuj po lat/lng).
- `etl/national.py` → `compute_job` dla `kind == "huff"`: do `huff_multi` dokładamy kolumny `w · luka` (dla każdego czynnika)
  i zapisujemy nową warstwę `rel__{type}__{demand}` = E − E_luka (nazwa przez funkcję `rel_layer` w `layers.py`, dodana do `Job.outputs`
  i `expected_layers`). Piramida: `MAX` jak dla `open`. Uruchomienie bez `--force` policzy tylko brakujące kolumny `rel__…`.
- `backend/app/analysis/national.py` (`run_national`): przy warstwie `open` czytaj też kolumnę `rel`; dla każdej komórki siatki
  `gap = rel < (1 − GAP_SHARE) · open` (dla res < 8 to porównanie maksimów: „najlepsze miejsce w rejonie opiera się głównie na luce”).
  Odpowiedź: `"gap": {"open": [0/1/None …]}` (ta sama siatka co `values.open`). Top-5: wartości `rel` z wykluczeniem komórek z gap,
  `value` = `open`. `_best_cell_position` szuka maksimum `rel`, nie `open`.
- Notatka `GAPS_NOTE` zamień na zdanie o kreskowaniu: „Szare kreskowanie: większość klientów tego miejsca mieszka tam, gdzie w danych jest
  podejrzanie mało firm (≤ ¼ średniej krajowej) — wynik może być skutkiem luki w danych, a nie braku konkurencji. Takich miejsc nie ma
  w najlepszych miejscach.”
- Testy: `test_national.py` / `test_national_api.py` — warstwa rel istnieje, piramida, gap w odpowiedzi, top-5 omija gap.

## Task 3 — tryb na żywo i okrąg (`/api/surface`)

- `run_surface`: gdy jest warstwa `open`, zamiast `huff_and_potential` użyj `huff_multi` z kolumnami `[w, w·luka]`
  (C_i jak teraz, `competition_availability`). Odpowiedź: `"gap": {"open": [...]}` jak w Task 2 (`None` poza okręgiem),
  top-5 jak w Task 2 (`E_wiar`, z wykluczeniem gap).
- Wydajność: zmierz `/api/surface` dla Wrocławia w trybie widocznego obszaru przed i po (dopuszczalne +30%).
- Testy w `test_surface_core.py` / `test_surface_api.py` na danych syntetycznych.

## Task 4 — dymek i podsumowanie obszaru

- `point_details`: przy typie + popycie dodaj `data_gap = {"share": udział klientów z luki, "observed": firmy w 2 km, "expected": oczekiwane w 2 km}`
  (observed/expected liczone wprost wokół klikniętego punktu: ludność res 9 w 2 km × `gap_rates.rate`). Zwracaj zawsze (frontend decyduje),
  frontend pokazuje ostrzeżenie, gdy `share > GAP_SHARE` **albo** punkt sam spełnia warunek luki.
  Tekst: „⚠ Mało danych o firmach: w promieniu 2 km mamy w danych 0 salonów, a przy tej liczbie mieszkańców średnio w Polsce byłoby ok. 6.
  Prawdopodobnie część firm nie jest jeszcze na mapach — sprawdź na miejscu.”
- `area_summary`: `expected_firms` = ludność pop_total obszaru × rate; gdy `expected_firms ≥ 3` i `competitors ≤ 0,25 · expected_firms` →
  ostrzeżenie w podsumowaniu w tym samym duchu (z liczbami). Werdykt „mniej konkurencji niż średnio” w takim obszarze zastąp
  „nie da się ocenić — za mało danych o firmach”.

## Task 5 — frontend

- `map.js` `renderFog`: opcjonalna tablica `gap` (ta sama siatka); na pikselach, których najbliższa komórka siatki ma gap = 1,
  rysuj ukośne szare paski (np. `(px + py) % 10 < 3` → kolor `#6b6b6b`, alfa ok. 0,55; pozostałe piksele bez zmian — kolor mgły zostaje).
  Działa w trybie okręgu, na żywo i Cała Polska (siatka Mercatora — ten sam kod).
- Legenda: pod paskiem kolorów próbka kreskowania + „mało danych o firmach” z pytajnikiem (tekst jak w notatce z Task 2, krócej).
- Top-5 i dymek: teksty z Task 4. Nie dodawaj przełączników — kreskowanie jest zawsze włączone.

## Task 6 — ETL na kopii, scenariusze, dokumentacja

1. `GO_DATA_DIR=data/v33 uv run python -m etl.run_all --only gaps,national` (bez `--force`; zanotuj czas), potem `etl.sanity`.
2. Serwer 8001 na kopii; scenariusze w przeglądarce (zrzuty `docs/screenshots/v33-*.png`):
   - (a) Cała Polska, salon kosmetyczny × kobiety: w top-5 **nie ma** Olsztynka, Nowego, Sianowa, Krośniewic, Nowogrodźca; Olsztynek widać z kreskowaniem.
   - (b) przybliżenie na Olsztynek (tryb na żywo): kreskowanie, dymek z ostrzeżeniem i liczbami.
   - (c) okrąg Brzeg 3 km, salon × kobiety: **brak** kreskowania i ostrzeżenia (36 salonów, wynik jak w v3.1).
   - (d) okrąg Olsztynek 3 km: ostrzeżenie w podsumowaniu, werdykt „nie da się ocenić”.
   - (e) sklep spożywczy × ludność, Cała Polska: top-5 jak przed zmianą (porównaj z v3.2).
   - (f) widok telefonu: legenda z kreskowaniem mieści się.
3. `uv run pytest -v` zielone. README (metoda + ograniczenie), `docs/sciaga-do-obrony.md` (pytanie „Skąd wiecie, że to luka w danych,
   a nie okazja?” — odpowiedź z liczbami i progami), `CLAUDE.md` (tabela §4: v3.3, §5 stan, kroki ETL), `docs/raport-etl.md` (czas kroku).
4. **Nie podmieniaj** `data/app.duckdb` i nie ruszaj serwera 8000 — zrobi to agent prowadzący po rozmowie z Marcinem
   (podmiana = zatrzymać serwer, `cp data/v33/app.duckdb data/app.duckdb`, uruchomić `start.bat`).
5. Przegląd całości (code review), poprawki, push na `main`.
