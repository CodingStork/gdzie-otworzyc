# CLAUDE.md — przeczytaj najpierw (dla agentów AI)

Ten plik jest dla Ciebie, agenta AI, który przychodzi do projektu bez kontekstu (nowy komputer, nowa sesja, inny model).
Marcin, właściciel projektu, **nie czyta dokumentacji** — piszemy ją wyłącznie dla agentów. Po przeczytaniu masz wiedzieć:
co budujemy, po co, jak z Marcinem pracować, co już ustalono (i dlaczego) i gdzie leży reszta.

## 1. Co to jest i po co

**Lokalizator — gdzie otworzyć firmę** (do v3.6 „Gdzie otworzyć?”; repozytorium nadal nazywa się `gdzie-otworzyc`) — aplikacja webowa z mapą Polski,
która odpowiada na pytanie przedsiębiorcy: **„gdzie otworzyć firmę (albo gdzie się reklamować), żeby mieć najwięcej klientów i najmniej konkurencji?”**
Przykłady Marcina: salon kosmetyczny szuka miejsca z dużą liczbą kobiet i małą liczbą salonów; **brukarz** szuka okolic, gdzie powstają nowe domy.

Formalnie to projekt zaliczeniowy z przedmiotu **„Analiza danych przestrzennych”**. Warunki prowadzącego:
frontend + backend + model wnioskujący (ML opcjonalny — „modelem” jest model Huffa),
kod w otwartym repozytorium oddawany systematycznie (małe, opisowe commity), **student musi rozumieć cały kod**.

### Cel: realnie przydatne narzędzie, nie ćwiczenie do odhaczenia

Poprzeczka: **„czy osoba, która naprawdę otwiera salon albo firmę brukarską, podjęłaby na podstawie tej mapy lepszą decyzję?”**
- **Mapa mówi prawdę.** Nie upiększaj wyniku, nie ukrywaj luk w danych (kreskowanie, jedno zdanie ostrzeżenia, źródła z liczbami).
- **Odpowiadaj na pytanie użytkownika, nie pokazuj surowych danych** — liczymy, **ilu klientów zdobędzie nowa firma** (Huff).
- **Prostota.** Marcin (v3.7): „Jeżeli mamy na jednym ekranie 10 tłumaczeń, co jak działa, gdy nikt nie pytał, to jest syf.”
  Na ekranie tylko liczby, które odpowiadają na pytanie, i źródła; wyjaśnienia pod pytajnikami. Żadnych żółtych ramek, notatek „na zapas”, podpowiedzi oczywistych dla branży.
- **Sprawdzaj sam, zanim powiesz „gotowe”.** Uruchom aplikację, przeklikaj realne scenariusze (Brzeg, Wrocław, Bydgoszcz, cała Polska), zrób zrzuty.
  Do tego są testy E2E (`tests/e2e`, Playwright) — dopisuj test do każdej uwagi testera.
- **Dobre źródła danych są ważniejsze od kolejnych funkcji** (OSM ma kilka razy mniej usług niż rzeczywistość; Overture zrobione, CEIDG w planach).

## 2. Jak pracować z Marcinem

- Pisze po polsku, jest studentem i **nie zna się na GIS** — sam dobieraj źródła, metody, rozwiązuj problemy techniczne. „Ty musisz zdecydować” = zdecyduj i krótko uzasadnij.
- Pytania w formie **wyboru a/b/c + „inne”** (AskUserQuestion), z rekomendacją na pierwszym miejscu. Nie pytaj o rzeczy, które możesz sprawdzić sam (np. pomiarem).
- **Nie czyta plików md** — streszczaj w czacie prostym językiem, najlepiej ze zrzutami ekranu.
- **Nie wybiegaj do przodu.** Najpierw on testuje, potem kolejne kroki. Jedno pytanie naraz.
- Uwagi daje notatkami i zrzutami, często ostro („obrzydliwe”, „syf”) — to sygnał, że coś jest za głośne albo za skomplikowane; zrób prościej, nie tłumacz się.
  Weryfikuj jego hipotezy pomiarem (np. limit 30 km okazał się założeniem bez pomiaru — siatka rzednie i cała Polska liczy się w kilka sekund).
- Po zmianach **restartuj jego serwer na porcie 8000** (karta terminala `start.bat`), gdy zmienił się backend; zmiany frontendu wystarczy odświeżyć Ctrl+F5.
- Kod prosty, z **komentarzami po polsku** objaśniającymi pojęcia przestrzenne. Ściąga do obrony: `docs/sciaga-do-obrony.md` — aktualizuj przy każdej zmianie metody.

## 3. Proces

- Agent prowadzący (Opus) robi research, decyzje, implementację lub delegowanie, weryfikację w przeglądarce i raport. Większe zmiany kiedyś szły przez spec + plan
  i osobną sesję implementacyjną (te dokumenty i sesje usunięto w v3.7 — historia jest w gicie); drobne poprawki rób od razu.
- Agent w chmurze (bez dostępu do danych) pracował na syntetycznej bazie (`tests/factories.make_db`, `tests/e2e/synthetic.py`) — jego wyniki trzeba sprawdzić na prawdziwej bazie.
- Do weryfikacji możesz uruchomić drugi serwer na **porcie 8001** (konfiguracja `app8001` w `.claude/launch.json`).
- Zmiany wersji v3.6+ są na gałęzi PR #2 (`claude/gracious-edison-9t79mz`, lokalnie `v36-pr2`) — scalić do `main` po testach Marcina (`git merge --ff-only`, nie przyciskiem na GitHubie).

## 4. Historia decyzji — czego NIE robić z powrotem

| Wersja | Co | Dlaczego zmienione |
|---|---|---|
| v1 | Heksagony H3 dla całej Polski, „klienci na 1 konkurenta”, skala percentylowa | Kolory zlewały 4 600 i 19 000; heksagony rosły z oddaleniem |
| v2 / v2.1 | Mapa dynamiczna z poziomami szczegółowości, okrąg 2SFCA, skala log | Ciągłe przeliczanie całej Polski przy ruchu mapy męczyło; mapa „zalana kolorem” |
| v3 | Miejsce + promień → „Pokaż mapę”, **mgła** (powierzchnia ciągła, log, przezroczystość), **model Huffa** z opcją zewnętrzną | Brak danych o firmach, panele pomieszane |
| v3.1 | Firmy z **OSM + Overture** (deduplikacja), podsumowanie, trend budów, lewo = ustawienia / prawo = wnioski | — |
| v3.2 | Tryb „Cała Polska” z **gotowej mapy z ETL** (krok `national`), katalog bez rzemieślników (`HIDDEN_TYPES`) | — |
| v3.3 | **Luki w danych o firmach**: krok `gaps`, warstwy `rel__…`, szare kreskowanie | Na mapie Polski wygrywały miasteczka bez salonów w danych (luka, nie okazja) |
| v3.4 | Wybór obszaru gestem: klik → okrąg + karta, prostokąt, animacja wprowadzająca | Formularz był niezrozumiały |
| v3.5 | Audyt: werdykt wg **podobnych miejsc** + test Poissona, top-5 z lokalnych szczytów, paznokcie w salonie (`TYPE_ALIASES`) | Średnia krajowa zaniżana przez wsie; werdykt przy 1–2 firmach był szumem |
| v3.6 | **Jedna droga**: narzędzie (bez domyślnego) → obszar → „Analizuj”; okrąg = 20% ekranu z kropkami; kolory z widocznej części; testy E2E | Mapa liczyła się sama po wyborze klientów; tryb „Cała Polska” usunięty |
| v3.7 | **Prostota + Lokalizator**: każdy obszar (do całej Polski) liczony z zasięgiem użytkownika (siatka rzednie: krok = promień/90); po prawej tylko klienci i firmy + źródła; bez werdyktu, rankingu, notatek i podpowiedzi; dymek z „na 1 firmę” przy ≥ 2 firmach; odświeżenie = ustawienia fabryczne; drugi klik narzędzia je odznacza; miejscowość → okrąg 5 km; zmiana narzędzia zamienia kształt; ✕ karty poza dymkiem; wyszukiwarka bez powtórzeń; **tryb nocny** (Esri Dark Gray, paleta magma) | Uwagi Marcina z testów v3.6 (zweryfikowane w przeglądarce 2026-11-03, czeka na jego testy) |

Odrzucone świadomie: heksagony jako główna warstwa; ciągłe przeliczanie przy ruchu mapy; mapa bivariate; Leaflet.heat; tęczowe palety; zasięg < 0,3 km;
rzemieślnicy w katalogu (dopóki nie ma CEIDG); średnia zamiast maksimum w piramidzie; Overpass API na żywo; średnia krajowa jako punkt odniesienia werdyktu;
ranking najlepszych miejsc w interfejsie; osobny typ „paznokcie”; **gotowa mapa Polski dla zaznaczonych obszarów** (v3.7 — ignorowała zasięg użytkownika);
**werdykt i notatki na ekranie** (v3.7 — szum dla użytkownika); **stan analizy w adresie URL** (v3.7 — odświeżenie ma zaczynać od zera);
żółte ramki z komunikatami; domyślnie wybrane narzędzie.

## 5. Stan techniczny

Szczegóły (metoda, wzory, źródła, licencje, architektura, instalacja): **`README.md`**.

- **Stack:** Python 3.13 przez `uv` (systemowy 3.15 jest za nowy), FastAPI + uvicorn, DuckDB (`data/app.duckdb`), numpy/scipy (cKDTree), pyproj, shapely, h3 v4, pyosmium.
  Frontend: czysty JS + Leaflet 1.9.4, bez Node i bez budowania. Testy E2E: Playwright (`uv run playwright install chromium` raz).
- **Dane:** Eurostat Census GRID 2021 (1 km) rozłożony dasymetrycznie na H3 res 9; OSM (Geofabrik) → firmy, miejscowości, ulice, wagi budynków;
  Overture Places → firmy; GUNB RWDZ + ULDK → pozwolenia (dokładność do obrębu). Układy: lokalny metryczny / EPSG:2180 do odległości, 3035 spis, 4326 H3/mapa.
- **Analiza (`/api/surface`):** siatka `surface.make_grid` — krok = promień/90 (min. 50 m), zawsze ok. 180 punktów w poprzek. Pomiar: 34 km ~2 s, 150 km ~3 s,
  350 km (cała Polska) 4–7 s dla zasięgu 0,3–20 km. Okrąg 1–350 km, prostokąt 0,6–700 km. Obszar > 30 km promienia / 60 km boku dostaje `area: "big"` i puste `top`
  (`routes.TOP_RADIUS_KM`). Backend dalej liczy werdykt (`service.verdict`, klasy gęstości z kroku `gaps`), top-5 i `top_edge` — **frontend ich nie pokazuje**.
- **Frontend:** `app.js` (stan, narzędzia `chooseTool`/`dropTool`/`convertSelection`, `run`, `drawLayer`, `applyTheme`, `applyViewHash` — hash tylko ustawia widok `#z=&clat=&clng=` i jest czyszczony),
  `ui.js` (`renderSummary` = dwie liczby + `sourcesText`, `pointPopup`, `areaCard`, pytajniki `HELP`), `map.js` (`showCircle`, `showRect` z kropką w środku,
  `flyToCircle` z miejscem na kartę `CARD_ROOM_PX`, `setTheme`), `colors.js` (`YLORRD`, `MAGMA`, `setDarkPalette`, `logScale` z `MIN_RATIO = 4`), `intro.js`.
- **Tryb nocny:** zmienne CSS w `:root` / `:root[data-theme="dark"]`; `index.html` ustawia motyw przed pierwszą klatką z `prefers-color-scheme`;
  przycisk ☾/☀ w pasku przy mapie, wybór niezapamiętywany (odświeżenie = ustawienia fabryczne). Obrysy mapy z `--area` / `--rect`.
- **Nieużywane, do decyzji:** krok ETL `national` i `/api/national` (gotowa mapa Polski) — od v3.7 frontend ich nie woła; `sanity` nadal sprawdza tabele `national_*`.
- **Testy:** 288 jednostkowych + 17 E2E (`uv run pytest -q`, ok. 5 min). E2E bez Chromium pomijają się same.
- **Komendy:** `uv sync` · `uv run pytest -v` · `uv run python -m etl.run_all [--only kroki] [--force]` (kroki: …, `aggregate`, `gaps`, `national`) ·
  `uv run python -m etl.sanity` · `start.bat` (port 8000). Po zmianie danych o firmach/ludności: `--only aggregate,gaps,national --force`.

### Pułapki, które już kosztowały czas
- **Końce linii:** większość plików ma CRLF (Windows), część LF (np. ten plik), testy bywają mieszane. `sed -i` w Git Bash i Python `write_text` zamieniają CRLF na LF —
  diff pokazuje cały plik. Edytuj narzędziem Edit albo w Pythonie na bajtach z zachowaniem `\r\n`.
- **Przeglądarka trzyma stare pliki JS/CSS** — po zmianie frontendu w panelu przeglądarki zrób `fetch(plik, {cache: 'reload'})` i przeładuj; Marcinowi każ Ctrl+F5.
- **W folderze roboczym (scratchpad) leży `inspect.py`**, który przesłania bibliotekę Pythona — skrypty pomocnicze trzymaj w podfolderze i uruchamiaj z `-I`.
- **Sieć w sesjach w chmurze** blokuje źródła danych — tam tylko syntetyczna baza, wyniki nieprawdziwe.
- **`data/` nie jest w repozytorium.** Na nowym komputerze cały ETL (kilka godzin, ~3 GB, ≥ 20 GB dysku).
- **Luki liczy `gaps`, a warstwy `rel__…` w `national` pomija policzone** — po zmianie firm/ludności `--force`.
- **Serwer i ETL nie mogą działać naraz** (blokada DuckDB → 503). Nie zabijaj serwera Marcina bez pytania (restart po zmianach backendu jest ustalony).
- **ULDK (GUGiK)** po ~1 h intensywnych zapytań blokuje IP — geokodowanie jest wznawialne, odczekaj.
- Formaty GUNB/ULDK/spisu są pełne niespodzianek — przed zmianą ETL przeczytaj `docs/zrodla-danych.md`.
- Darmowe kafelki CARTO wymagają klucza → podkład Esri Canvas (Light/Dark Gray). Nominatim: 1 zapytanie/s, wymagany User-Agent, zwraca duplikaty nazw (filtrujemy).
- Animowany zoom Leaflet potrafi się zawiesić — `safeFlyTo` ma awaryjne domknięcie; `flyToCircle` w tle skacze bez animacji.

## 6. Co dalej (otwarte)

1. **Testy Marcina po v3.7**, potem scalenie PR #2 do `main`.
2. **Zasięg klienta zależny od gęstości** (wieś > miasto) — na wsi model zawyża liczbę klientów, bo nie widzi firm w mieście dalej niż 4 × zasięg.
   Wymaga kalibracji na prawdziwej bazie (suma E nowych firm w klasie gęstości vs liczba firm). `docs/audyt-przydatnosci.md`, sekcja B4.
3. **CEIDG** jako trzecie źródło firm (brukarze, ogrodnicy, kosmetyczki bez lokalu). PKD 2025: fryzjerstwo 96.21.Z, kosmetyka 96.22.Z (dawniej 96.02.Z — szukać w obu).
   Marcin musi złożyć wniosek o token API (dane.biznes.gov.pl, Profil Zaufany). **Token trafia do `.env` (gitignore), nigdy do czatu ani repo.** Adresy geokodować punktami adresowymi PRG.
4. **Zamożność i ludność dzienna:** GUS BDL (dochody gmin z PIT, dzieci 0–6, budynki oddane) i przepływy do pracy — dla kawiarni, restauracji, siłowni, przedszkoli.
5. **Sprzątanie po v3.7:** czy usunąć krok `national` / `/api/national` (oszczędność ok. 60 MB bazy i ok. 15 min ETL) albo werdykt/top-5 w backendzie — zapytać Marcina.
6. Atrakcyjność sieci w Huffie (`brand`), przedszkola z RSPO, liczba mieszkań z kubatury (GUNB), kropki wszystkich firm na wyniku.
7. **Tailscale** (dostęp z uczelni) — instrukcja w README; dopiero po testach Marcina.
8. Drobne: deduplikacja „jeden do wielu”, `/api/poi` bez `ORDER BY` przy limicie 5 000, brak pliku `.release` → „Overture Maps nieznane”.
9. Przy każdej nowej wersji: **zaktualizuj ten plik** (tabela §4, stan §5–6), README i ściągę.

## 7. Zasady stałe

- Nie wpisuj haseł ani tokenów za Marcina; logowania robi on sam.
- Commity: po polsku, prefiksy `feat:` / `fix:` / `docs:` / `perf:` / `chore:`, autor z adresem **noreply** GitHuba
  (`164074465+CodingStork@users.noreply.github.com`, ustawiony lokalnie w repo) — prywatny e-mail nie może trafić do publicznej historii.
- Repo publiczne: https://github.com/CodingStork/gdzie-otworzyc (konto CodingStork, gałąź `main`).
- Atrybucje źródeł danych (OSM ODbL, Overture CDLA, Eurostat, GUNB, GUGiK, Esri) muszą zostać w aplikacji i README.

## 8. Mapa dokumentów

- `README.md` — opis dla ludzi: jak używać, metoda, źródła, architektura, instalacja, ograniczenia.
- `docs/sciaga-do-obrony.md` — pojęcia, kod i pytania na obronę (sekcja 30 = v3.7).
- `docs/zrodla-danych.md` — zweryfikowane formaty i pułapki źródeł danych.
- `docs/raport-etl.md` — wyniki i czasy kroków ETL.
- `docs/kompletnosc-danych.md` — jak pełne są dane o firmach wg typu i wielkości miejscowości.
- `docs/audyt-przydatnosci.md` — audyt v3.5 (10 ról): słabości modelu (B4 — zasięg na wsi), nowe źródła danych, uzasadnienia; część zaleceń dot. interfejsu jest już nieaktualna (v3.7 uprościło ekran).
- `docs/screenshots/` — aktualne zrzuty (jasny i nocny wygląd).
