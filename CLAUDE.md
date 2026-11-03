# CLAUDE.md — przeczytaj najpierw (dla agentów AI)

Ten plik jest dla Ciebie, agenta AI, który przychodzi do projektu bez kontekstu (nowy komputer, nowa sesja, inny model).
Marcin, właściciel projektu, **nie czyta dokumentacji** — piszemy ją wyłącznie dla agentów. Po przeczytaniu masz wiedzieć:
co budujemy, po co, jak z Marcinem pracować, co już ustalono (i dlaczego) i gdzie leży reszta.

## 1. Co to jest i po co

**„Gdzie otworzyć?”** — aplikacja webowa z mapą Polski, która odpowiada na pytanie przedsiębiorcy:
**„gdzie otworzyć firmę (albo gdzie się reklamować), żeby mieć najwięcej klientów i najmniej konkurencji?”**
Przykłady, które Marcin sam podał: salon kosmetyczny szuka miejsca z dużą liczbą kobiet i małą liczbą salonów;
**brukarz** szuka okolic, gdzie powstają nowe domy (pozwolenia na budowę), bo tam będą zlecenia.

Formalnie to projekt zaliczeniowy z przedmiotu **„Analiza danych przestrzennych”**. Warunki prowadzącego:
frontend + backend + model wnioskujący (prowadzący zaakceptował, że ML jest opcjonalny — „modelem” jest u nas model Huffa),
kod w otwartym repozytorium oddawany systematycznie (małe, opisowe commity), **student musi rozumieć cały kod** —
prac „zrobionych przez AI bez zrozumienia” prowadzący nie zalicza.

### Cel: realnie przydatne narzędzie, nie ćwiczenie do odhaczenia

Marcin wprost powiedział, że chce projektu, który ma **prawdziwe zastosowanie**, i że „walczy o dane o biznesach”.
Poprzeczka nie brzmi „żeby działało i przeszło na zaliczeniu”, tylko **„czy osoba, która naprawdę otwiera salon albo firmę brukarską,
podjęłaby na podstawie tej mapy lepszą decyzję?”**. Jeśli odpowiedź brzmi „nie” albo „mapa mogłaby ją wprowadzić w błąd”, praca nie jest skończona.

Traktuj to jak własny produkt. Konkretnie oznacza to:
- **Mapa mówi prawdę.** Marcin: „Chcemy, żeby nasze narzędzie było dokładne… mówiło prawdę”. Nie upiększaj wyniku, nie ukrywaj luk w danych —
  pokazuj je (ostrzeżenia, „OSM 18, Overture 18”, „szacunek”). Lepsza uczciwa niepewność niż ładna bzdura.
- **Odpowiadaj na pytanie użytkownika, nie pokazuj surowych danych.** Mapa „gdzie mieszka dużo ludzi” to tylko mapa ludności (xkcd 1138);
  liczymy, **ilu klientów zdobędzie nowa firma** (Huff) i porównujemy liczbę firm z **miejscami o podobnej gęstości zaludnienia** (od v3.5; średnia krajowa zaniżała oczekiwania w miastach).
- **Ma być czytelne dla laika.** Marcin nie zna się na danych przestrzennych i jest pierwszym testerem — jeśli on czegoś nie rozumie, użytkownik też nie.
  Każde pojęcie ma pytajnik z prostym zdaniem; wnioski piszemy zdaniami („Konkurencja na poziomie średniej krajowej”).
- **Sprawdzaj sam, zanim powiesz „gotowe”.** Marcin prosił: „Sprawdź samemu… czy dane są łatwe do interpretacji”. Uruchom aplikację,
  przeklikaj realne scenariusze (Brzeg, Wrocław, Warszawa), zrób zrzuty, zadaj sobie pytanie „czy to ma sens?”.
  Kilka błędów wyszło dopiero w przeglądarce, choć testy były zielone.
- **Dobre źródła danych są ważniejsze od kolejnych funkcji.** Największa słabość to niekompletne dane o firmach (OSM ma kilka razy mniej usług niż rzeczywistość).
  Każde realne uzupełnienie (Overture zrobione, CEIDG w planach) jest warte więcej niż nowy przycisk.

## 2. Jak pracować z Marcinem

- Pisze po polsku, jest studentem i **nie zna się na GIS** — oczekuje, że agent sam dobierze źródła, metody i rozwiąże problemy techniczne.
  Gdy mówi „nie znam się, ty musisz zdecydować”, podejmij decyzję i krótko ją uzasadnij.
- Pytania zadawaj w formie **wyboru a/b/c + „inne”** (narzędzie AskUserQuestion), z rekomendacją na pierwszym miejscu. Nie pytaj o rzeczy, które możesz sprawdzić sam.
- **Nie czyta plików md** — wszystko, co ważne (decyzje, wyniki, co ma zrobić), streszczaj w czacie prostym językiem, najlepiej ze zrzutami ekranu.
- **Nie wybiegaj do przodu.** Najpierw on testuje aplikację, potem kolejne kroki (np. Tailscale dopiero po jego testach). Zadawaj jedno pytanie naraz, nie listę zadań na zapas.
- Daje uwagi w formie notatek i zrzutów; traktuj je poważnie, ale weryfikuj — np. „brak salonów” okazał się luką OSM w konkretnej okolicy, a nie błędem kodu.
- Nie wykonuje sam rzeczy technicznych, chyba że to konieczne (logowanie do GitHuba, Profil Zaufany) — wtedy daj mu dokładną instrukcję krok po kroku.
- Kod ma być prosty, z **komentarzami po polsku** objaśniającymi pojęcia przestrzenne, bo Marcin musi go obronić. Ściąga do obrony: `docs/sciaga-do-obrony.md` — aktualizuj ją przy każdej zmianie metody.

## 3. Jak dotąd pracowaliśmy (role i proces)

- **Agent prowadzący (Opus) = szef projektu:** research, decyzje, specyfikacja (`docs/superpowers/specs/`), plan wykonawczy (`docs/superpowers/plans/`),
  delegowanie implementacji, weryfikacja w przeglądarce, raport dla Marcina.
- **Implementacja:** osobna sesja (Sonnet) wykonuje plan zadanie po zadaniu (TDD, commit po każdym zadaniu), na końcu przegląd całości.
- Cykl wersji: uwagi Marcina → research → spec + plan → implementacja → weryfikacja w przeglądarce (scenariusze z planu) → zrzuty do `docs/screenshots/` →
  README + ściąga → push → streszczenie dla Marcina → jego testy → kolejne uwagi.
- Do weryfikacji uruchamiaj drugi serwer na **porcie 8001** (`uv run uvicorn backend.app.main:app --port 8001`), żeby nie ruszać serwera Marcina na 8000.
- **Testy „jak użytkownik” (od v3.6):** `tests/e2e/test_uzytkownik.py` — Playwright klika w aplikację na syntetycznej bazie. Każdą uwagę Marcina
  o zachowaniu interfejsu zamieniaj w taki scenariusz (zanim poprawisz kod), bo testy jednostkowe tego nie łapią.

## 4. Historia decyzji — czego NIE robić z powrotem

| Wersja | Co | Dlaczego zmienione |
|---|---|---|
| v1 | Heksagony H3 dla całej Polski, wskaźnik „klienci na 1 konkurenta”, skala percentylowa | Kolory zlewały 4 600 i 19 000; heksagony rosły z oddaleniem; niezrozumiałe „okazja/popyt/konkurencja” |
| v2 / v2.1 | Mapa dynamiczna z poziomami szczegółowości (LOD), dasymetria na budynki, okrąg 2SFCA, skala log | Ciągłe przeliczanie całej Polski przy ruchu mapy było męczące; mapa „zalana kolorem” po oddaleniu |
| v3 | Przepływ **miejsce + promień → „Pokaż mapę”**, **mgła** (powierzchnia ciągła YlOrRd, log, przezroczystość), **model Huffa** z opcją zewnętrzną, szczegóły po kliknięciu | Uwagi: brak danych o firmach, panele pomieszane, heksagony w szczegółach zbędne, nie da się kliknąć poza okrąg |
| v3.1 | Firmy z **OSM + Overture Maps** (deduplikacja), **podsumowanie obszaru** ze średnią krajową, ulice w top-5, **trend budów**, lewo = ustawienia / prawo = wnioski, klik poza okręgiem = nowe miejsce, zasięg min. 0,3 km, zakładki na telefonie | — (commit 5d9dbf8; tryb „Wybrane miejsce” działa dalej bez zmian) |
| v3.2 | Przełącznik **Cała Polska / Wybrane miejsce**: po oddaleniu **gotowa mapa Polski z ETL** (krok `national`: Huff dla 420 tys. punktów res 8, piramida **max** res 7–5, **stała skala** z `national_meta`, `/api/national`), po przybliżeniu (półprzekątna ≤ 20 km) **mapa na żywo** (`/api/surface` w trybie prostokąta widoku); katalog **bez rzemieślników** (brukarz, ogrody, okna, kuchnie, instalatorzy → `HIDDEN_TYPES`), podpowiedź dla nich, „Przeanalizuj to miejsce” w dymku, hash `mode=pl` | — (dalej działa; v3.3 dokłada oznaczanie luk w danych) |
| v3.3 | **„Mało danych o firmach”**: krok ETL `gaps` (luka = w promieniu 2 km oczekiwane ≥ 3 firmy wg średniej krajowej, a w danych ≤ ¼), warstwa `rel__…` (wiarygodni klienci = E − E_luka), **szare kreskowanie** na mgle „Gdzie otworzyć” (udział klientów z luk > 50%), top-5 bez luk, ostrzeżenia z liczbami w dymku i podsumowaniu (werdykt „nie da się ocenić”) | Na mapie Polski wygrywały miasteczka bez żadnego salonu w OSM/Overture (Olsztynek, Sianów) — luki w danych, nie okazje (aktualna, zweryfikowana w przeglądarce 2026-10-28; czeka na testy Marcina) |

| v3.4 | **Wybór obszaru gestem**: kliknięcie → pinezka + okrąg podglądu + **karta** (liczby punktu z `/api/point`, suwak promienia, ✓ / ✕); przycisk **„▭ Prostokąt”** (rysowanie Pointer Events, uchwyty w rogach, wymiary, limity 0,6–60 km, ✓); `/api/surface?area=rect`; hash `bbox=`; **animacja wprowadzająca** (`intro.js`, przycisk „?”); formularz (wyszukiwarka + promień) zostaje jako druga droga | Marcin: formularz „miejsce + promień + Pokaż mapę” był niezrozumiały — obszar wskazuje się na mapie. Zniknęły `preview` / `NEW_PLACE_INFO` / `highlightShow` (nowy wybór zastępuje podgląd) i dymek z przyciskiem „Przeanalizuj to miejsce” w trybie Polski (zastąpiła go karta). Zweryfikowane w przeglądarce 2026-10-28, czeka na testy Marcina |

| v3.5 | **Audyt przydatności** (`docs/audyt-przydatnosci.md`, 10 ról): werdykt porównuje z **podobnymi miejscami** (krok `gaps`: kwintyle ludności wg mieszkańców w 2 km → `density_cells`, `density_rates`) i z **testem Poissona** (`service.verdict`: „few” przy < 3 oczekiwanych, „less/more” tylko przy p < 10% i różnicy ≥ 20–25%); top-5 tylko z **lokalnych szczytów** (`surface.peaks_and_edge`, flaga `top_edge`); **brak top-5 na gotowej mapie Polski**; skala kolorów ≥ 10×; **paznokcie scalone z salonem** (`TYPE_ALIASES`); zdanie zastrzeżenia branży (`caveat`) pod jej wyborem; market budowlany domyślnie z mieszkańcami; podsumowanie od werdyktu; zwarta karta; bez notatek dublujących legendę | Średnia krajowa (zaniżana przez wsie) robiła z każdego miasta „więcej konkurencji”; werdykt przy 1–2 firmach był szumem; top-5 Polski wskazywał wsie (Rudki, Pruchnik); top-5 z krawędzi okręgu; kolory rozciągały różnicę 20% na całą paletę. Zweryfikowane testami i w przeglądarce **na danych syntetycznych** (sieć bez dostępu do danych) — czeka na `--only gaps` i testy Marcina |

| v3.6 | **Uwagi Marcina po v3.5**: bez przełącznika „Cała Polska / Wybrane miejsce” i bez automatycznej mgły — **jedna droga**: narzędzie w lewym panelu (◯ Okrąg / ▭ Prostokąt, **bez domyślnego**) → obszar → branża/klienci → **„Analizuj”** (karta nie ma tego przycisku, dopóki nie ma ustawień; pola pulsują). Okrąg po kliknięciu = **20% krótszego boku ekranu** (`map.kmForScreenFraction`), płynne centrowanie, **kropka w środku** (przesuwa) i **na krawędzi** (promień), pole km; okrąg na kuli (`map.destination`). **Duże obszary** (okrąg > 30 km do 350 km, prostokąt > 60 km do 700 km) z gotowej mapy Polski (`national.run_area`, bez top-5). Skala kolorów **z widocznych komórek** (przemalowanie po ruchu mapy bez zapytań), `MIN_RATIO` 10× → **4×**, w dymku „Kolor mapy w tym miejscu”. Animacja: krok „tools” (przyciski po lewej), potem okrąg/prostokąt na środku mapy. **Testy E2E** (Playwright, 14 scenariuszy) | Marcin: po wybraniu klientów mapa policzyła się sama dla całej Polski, choć nie kliknął „Analizuj”; okrąg 2 km niewidoczny po oddaleniu; „Analizuj” prowadził do komunikatu „wybierz branżę”; animacja klikała w Litwę; w centrum Bydgoszczy jeden kolor przy 4 700 i 7 400 mężczyzn; brak testów symulujących użytkownika. Zweryfikowane testami (w tym E2E) **na danych syntetycznych** — do sprawdzenia na prawdziwej bazie: `docs/zadania-dla-agenta-lokalnego.md` |

Odrzucone świadomie: heksagony jako główna warstwa, ciągłe przeliczanie przy ruchu mapy (v3.2 liczy na żywo dopiero PO przybliżeniu do miasta i po zakończeniu ruchu; oddalony widok jest gotowy z ETL), przełącznik „Konkurencja”, mapa bivariate, Leaflet.heat,
tęczowe palety, zasięg < 0,3 km (dane ludności mają ~300 m rozdzielczości), typy firm pracujących u klienta w katalogu (dopóki nie ma CEIDG — „konkurencja” byłaby fikcją), średnia zamiast maksimum w piramidzie (zalewa małe ośrodki), Overpass API na żywo (blokuje automaty), **średnia krajowa jako punkt odniesienia werdyktu** (v3.5 — zaniżają ją wsie), **ranking najlepszych miejsc dla całej Polski** (v3.5 — mieszał rynki o różnej zamożności i dojazdach), **osobny typ „paznokcie”** (podzbiór salonu kosmetycznego w danych), werdykt „mniej/więcej konkurencji” bez testu istotności, **mgła liczona bez kliknięcia „Analizuj”** (tryb „Cała Polska” do v3.5 — tester nie wiedział, dla jakiego obszaru patrzy na wynik), **domyślne narzędzie zaznaczania** i **okrąg o stałym promieniu w km po kliknięciu** (niewidoczny po oddaleniu), jedna skala kolorów dla całego obszaru niezależnie od przybliżenia.

## 5. Stan techniczny

Szczegóły (metoda, wzory, źródła, licencje, architektura, instalacja): **`README.md`**. Najważniejsze skróty:

- **Stack:** Python 3.13 przez `uv` (systemowy Python 3.15 jest za nowy dla bibliotek), FastAPI + uvicorn, DuckDB (`data/app.duckdb`),
  numpy/scipy (cKDTree), pyproj, shapely, h3 v4, pyosmium. Frontend: czysty JS + Leaflet 1.9.4, bez Node i bez budowania.
- **Dane:** Eurostat Census GRID 2021 (1 km) rozłożony dasymetrycznie na H3 res 9; OSM (Geofabrik) → firmy, miejscowości, ulice, wagi budynków;
  Overture Places → firmy; GUNB RWDZ + ULDK → pozwolenia na budowę (dokładność do obrębu). Układy: EPSG:2180/lokalny metryczny do odległości, 3035 spis, 4326 H3/mapa.
- **Stan v3.6:** frontend bez trybów (`app.js`: `state.tool`, `state.selection` + `state.card`, `state.area` = przeanalizowany obszar; `chooseTool`, `beginCircle`, `setCircleRadius`, `beginRect`, `updateCardReady`, `confirmSelection`, `run`, `drawLayer({ withTop })`, `visibleValues`, `valueAt`; `window.gdzieOtworzyc` = uchwyt dla testów E2E). `map.js`: `showCircle` (kropki `circle-handle center/edge`), `setCircleRadius`, `kmForScreenFraction`, `panTo`, `fitCircleIfNeeded`, `startRectDraw` / `stopRectDraw` / `onDrawCancel` (przycisk prostokąta zniknął z mapy, został „?”), `destination` (punkt na kuli), `setFog(..., center)` dla siatki w Mercatorze. `ui.js`: `initTools`, `setTool`, `toolsAttention`, `settingsAttention`, `hasSettings`, `areaCard` (zastąpiła `selectionCard` i `rectCard`), `snapRadius` (1–350 km), `parseKm`. Usunięte: `setMode`, `setReachLocked`, suwak promienia i „Pokaż mapę”, `api.national` we frontendzie. Backend: `/api/surface` przyjmuje `px`; okrąg 1–350 km (> 30 km → `national.cached_area`), prostokąt `area=rect` do 700 km boku (> 60 km → duży obszar); `area_summary(..., res=7)` dla dużych, `load_density_cells` przez `fetchnumpy`. Hash bez `mode`; stary `mode=pl&z&clat&clng` ustawia tylko widok. Testy: 288 + 14 E2E = 302 zielone (`uv run playwright install chromium` raz; bez przeglądarki E2E się pomijają). Czasy dużych obszarów na prawdziwej bazie **niezmierzone**.
- **Stan v3.5 (audyt):** krok `gaps` zapisuje też `density_cells(lat, lng, pop_total, cls)` i `density_rates(type_id, cls, firms, population, rate, min_residents, max_residents)`; `area_summary` zwraca `benchmark` (`similar_places` / `national` w starej bazie), `benchmark_firms`, `benchmark_per_firm`, `place_name` (najbliższe miasto okręgu), werdykty `less/more/similar/few/unknown`; `/api/surface` zwraca `top_edge`; `/api/national` nie ma już notatek o kreskowaniu i typowym zasięgu (dublowały legendę i podpowiedź pod suwakiem). Katalog: 10 typów, `caveat` w `BusinessType` i w `/api/catalog`, `TYPE_ALIASES` (`nails` → `beauty`) w API i w linkach. Frontend: werdykt pierwszy w podsumowaniu, `ui.setTopNote` (małe różnice < 20%, krawędź, zawyżenie na słabo zaludnionym terenie), `#type-hint` pod branżą, brak top-5 na gotowej mapie, `MIN_RATIO = 10` w `colors.js`. Testy: 284 zielone. **Po aktualizacji bazy:** `uv run python -m etl.run_all --only gaps` (bez tego werdykt porównuje ze średnią krajową, a `etl.sanity` zgłasza brak tabel `density_*`). Gotowej mapy (`national`) nie trzeba przeliczać.
- **Stan v3.4:** wybór gestem w całości po stronie frontendu (`app.js`: `beginSelection`, `beginRectSelection`, `confirmSelection`, `state.selection` / `state.area`; `map.js`: `showSelection`, `showRect`, `setRectArea`, kontrolka „▭ Prostokąt”; `ui.js`: `selectionCard`, `rectCard`; `intro.js`). Backend: tylko parametr `area` w `/api/surface` (`rect` → `divisions=90`, podsumowanie `shape: "rect"` z `width_km`/`height_km`, dolny limit boku 0,6 km w `routes.py`). Suwak promienia ma krok 0,5 km poniżej 5 km (`ui.snapRadius`). Testy backendu w `tests/test_surface_api.py` (3 nowe); frontend sprawdzony ręcznie w przeglądarce (scenariusze a–g, zrzuty `docs/screenshots/v34-*.png`). Rysowanie palcem sprawdzone tylko syntetycznymi zdarzeniami Pointer Events i emulacją telefonu 375×812 (nie na prawdziwym telefonie).
- **Stan v3.3:** 260 testów zielonych (`uv run pytest -v`, ok. 4 min), `etl.sanity` OK (sprawdza też tabele luk: udział ludności w lukach dla salonów 0,5–5%). Krok `gaps` = 128 s, `national` doliczył 27 warstw `rel__…` w 375 s (razem 92 warstwy), baza 365 → 408 MB; `/api/surface` Wrocław 0,53 → 0,67 s. Progi luki to stałe `GAP_*` w `catalog.py` (ustalone pomiarem, szczegóły `docs/raport-etl.md`, sekcja v3.3) — nie zmieniaj bez nowego pomiaru. Po zmianie danych o firmach/ludności: `uv run python -m etl.run_all --only aggregate,gaps,national --force`.
- **Stan v3.2 (dalej aktualny dla gotowej mapy):** 230 testów zielonych, `etl.sanity` OK (sprawdza też gotową mapę Polski). Krok `national` = 780 s, 65 warstw, baza 346 → 365 MB (szczegóły: `docs/raport-etl.md`, sekcja v3.2). `/api/national` ~0,25 s bez cache, kilkanaście ms z cache; widok na żywo ~0,7 s. Typów w katalogu jest 10 od v3.5 (rzemieślnicy i paznokcie w `HIDDEN_TYPES`, ETL nadal je zbiera do `poi`). Przy zmianie danych: `uv run python -m etl.run_all --only aggregate,national --force`.
- **Stan v3.1 (dalej aktualny dla danych):** Tabela `poi` ma kolumny `source` (`osm`/`overture`) i `source_id` (dawniej `osm_id`).
  Salony kosmetyczne: 7 206 z OSM + 24 133 z Overture. Zasięg 0,1–0,3 km API podnosi do 0,3 z notatką; trend pomija ostatni, niepełny miesiąc danych.
- **API:** `/api/national` (gotowa mapa Polski: stała skala, rozdzielczość wg `px`), `/api/surface` (mgła + podsumowanie + top-5 + trend; okrąg `lat,lng,radius_km` albo prostokąt widoku `west,south,east,north`), `/api/point` (dymek), `/api/catalog`, `/api/poi`, `/api/geocode`, `/api/meta`.
- **Komendy:** `uv sync` · `uv run pytest -v` · `uv run python -m etl.run_all [--only kroki] [--force]` (kroki: …, `aggregate`, `gaps`, `national`) · `uv run python -m etl.sanity` · `start.bat` (port 8000).

### Pułapki, które już kosztowały czas
- **Przeglądarka bez okna (Playwright) a przybliżanie kółkiem:** kilka szybkich `mouse.wheel` potrafi zawiesić animację przybliżania Leaflet (mgła znika, kliknięcia nie działają) — w testach przybliżaj przyciskiem „+” z odstępem ok. 0,7 s. Ten sam typ problemu co „animowany zoom przy starcie z hasha” niżej.
- **Końce linii:** większość plików ma CRLF (Marcin pracuje na Windows), część testów ma końce mieszane. Edycja skryptem (Python `read_text`/`write_text`) zamienia je na LF i diff pokazuje cały plik jako zmieniony — zachowaj oryginalne końce linii (tak przepisano commity v3.5).
- **Sieć w sesjach w chmurze** może blokować źródła danych (Geofabrik, Eurostat, Overture S3, GUS BDL, GUNB, ULDK, unpkg, kafelki Esri). Do sprawdzania interfejsu wystarcza syntetyczna baza z `tests/factories.make_db(..., gaps=True, national=True)` i Leaflet z pakietu npm podstawiony w Playwright — ale wyniki z niej nie są prawdziwe.
- **`data/` nie jest w repozytorium** (gitignore). Na nowym komputerze trzeba uruchomić cały ETL (kilka godzin, ~3 GB pobierania, ≥ 20 GB dysku).
- **Luki w danych liczy `gaps`, a warstwy `rel__…` w `national` pomija policzone** — po zmianie firm lub ludności użyj `--force`, inaczej kreskowanie będzie nieaktualne (sanity tego nie wykryje). Małe miejscowości (oczekiwane < 3 firmy) nie są oceniane; warstwa „Gdzie są firmy” nie ma kreskowania.
- **Mapa Polski jest policzona dla typowego zasięgu** — jeśli zmienisz `bandwidth_km` typu, `default_reach_km` czynnika, katalog albo dane, trzeba przeliczyć krok `national` (`--only aggregate,national --force`; sanity wykryje brakującą warstwę, ale nie nieaktualną).
- **Największe wartości na mapie Polski bywały lukami w danych o firmach** (np. Olsztynek: 3,6 tys. kobiet w kwadracie 3 × 3 km i 0 salonów w OSM + Overture) — od v3.3 takie miejsca są kreskowane i wykluczone z top-5; nie „naprawiaj” braku firm w kodzie (to zrobi CEIDG).
- **Serwer i ETL nie mogą działać naraz** (blokada pliku DuckDB → API zwraca 503). Nie zabijaj serwera Marcina bez pytania.
- **ULDK (GUGiK)** po ~1 h intensywnych zapytań blokuje IP (przekierowanie 302 na WAF) — geokodowanie jest wznawialne, odczekaj i dokończ.
- Formaty danych GUNB/ULDK/spisu są pełne niespodzianek — zanim coś zmienisz w ETL, przeczytaj `docs/zrodla-danych.md`.
- Darmowe kafelki CARTO wymagają klucza → podkład Esri Light Gray. Nominatim: limit 1 zapytanie/s, wymagany User-Agent.
- Animowany zoom Leaflet potrafi się zawiesić przy starcie z hasha — używamy dopasowania bez animacji.

## 6. Co dalej (otwarte)

Pełna lista z uzasadnieniem i kosztami: `docs/audyt-przydatnosci.md`, sekcja 7. Najważniejsze, w kolejności:

1. **Testy Marcina po v3.6** i sprawdzenie na prawdziwej bazie przez agenta lokalnego: `docs/zadania-dla-agenta-lokalnego.md` (scenariusze a–h: m.in. Bydgoszcz/mężczyźni, czas dużych obszarów, werdykt dla Brzegu po `--only gaps`).
2. **Zasięg klienta zależny od gęstości** (wieś > miasto) — na wsi model zawyża liczbę klientów, bo nie widzi firm w mieście dalej niż 4 × zasięg (to wyniosło Rudki i Pruchnik na szczyt mapy Polski w v3.3). Wymaga kalibracji na prawdziwej bazie (suma E nowych firm w klasie vs liczba firm) i przeliczenia `national --force`.
3. **CEIDG** jako trzecie źródło firm — najważniejsze dla branż, których nie ma w OSM/Overture (brukarze, ogrodnicy, kosmetyczki bez lokalu). Od 2025 r. PKD 2025: fryzjerstwo 96.21.Z, kosmetyka 96.22.Z (dawniej oba 96.02.Z, okres przejściowy do końca 2026) — szukać w obu klasyfikacjach. Marcin musi złożyć wniosek o token API (dane.biznes.gov.pl, Profil Zaufany). **Token trafia do pliku `.env` (w gitignore), nigdy do czatu ani repo.** Schemat odpowiedzi API nie jest publiczny — sprawdzić po otrzymaniu tokenu. Adresy geokodować punktami adresowymi PRG (GUGiK).
4. **Zamożność i ludność dzienna:** GUS BDL (dochody gmin z PIT na mieszkańca, wynagrodzenia, dzieci 0–6, budynki oddane do użytkowania) i przepływy ludności do pracy — najważniejsze dla kawiarni, restauracji, siłowni i przedszkoli.
5. **Atrakcyjność sieci w Huffie** (`brand` z OSM/Overture: dyskont, duży market budowlany), **przedszkola z RSPO**, **liczba mieszkań z kubatury** (GUNB), **pozwolenia sprzed 2–4 lat** dla rzemieślników, **kropki wszystkich firm** na wyniku.
6. **Tailscale** (dostęp z uczelni) + reguła zapory dla portu 8000 — instrukcja w README; dopiero po testach Marcina.
7. Z v3.2–v3.3: osobna stała skala kolorów dla każdego poziomu piramidy; luki wg stawek klas gęstości + test Poissona (wymaga nowego pomiaru, bo zmieni udział ludności w lukach sprawdzany w `etl.sanity`); powrót typów rzemieślniczych po dołączeniu CEIDG.
8. Drobne, odłożone z przeglądu v3.1: deduplikacja „jeden do wielu”, `/api/poi` bez `ORDER BY` przy limicie 5 000, sanity liczy wiersze typ×firma, brak pliku `.release` → „Overture Maps nieznane”.
9. Przy każdej nowej wersji: **zaktualizuj ten plik** (tabela w §4, stan w §5–6), README i ściągę.

## 7. Zasady stałe

- Nie wpisuj haseł ani tokenów za Marcina; logowania robi on sam.
- Commity: po polsku, prefiksy `feat:` / `fix:` / `docs:` / `perf:` / `chore:`, autor z adresem **noreply** GitHuba
  (`164074465+CodingStork@users.noreply.github.com`, ustawiony lokalnie w repo) — prywatny e-mail nie może trafić do publicznej historii.
- Repo publiczne: https://github.com/CodingStork/gdzie-otworzyc (konto CodingStork, gałąź `main`).
- Atrybucje źródeł danych (OSM ODbL, Overture CDLA, Eurostat, GUNB, GUGiK, Esri) muszą zostać w aplikacji i README.

## 8. Mapa dokumentów

- `README.md` — opis dla ludzi: jak używać, metoda, źródła, architektura, instalacja, ograniczenia.
- `docs/sciaga-do-obrony.md` — pytania i odpowiedzi, które Marcin musi umieć na obronie.
- `docs/zrodla-danych.md` — zweryfikowane formaty i pułapki źródeł danych.
- `docs/raport-etl.md` — wyniki i stan przetwarzania danych (w tym czas i rozmiar kroku `national`).
- `docs/audyt-przydatnosci.md` — audyt v3.5: werdykty dla każdej branży i warstwy, słabości modelu, szum w interfejsie, nowe źródła, lista zmian (zrobione / do zrobienia), przegląd „adwokata diabła”.
- `docs/zadania-dla-agenta-lokalnego.md` — v3.6: co zgłosił Marcin i co zrobiono, scenariusze do przeklikania na prawdziwych danych, czego nie dało się zrobić bez bazy (dla agenta sterującego komputerem Marcina).
- `docs/kompletnosc-danych.md` — jak pełne są dane o firmach wg typu i wielkości miejscowości (porównanie z GUS/D&B).
- `docs/superpowers/specs/*-design.md` — specyfikacje kolejnych wersji (v1 2026-10-26, v2 i v3 2026-10-27).
- `docs/superpowers/plans/*.md` — plany wykonawcze (najnowszy: `2026-10-28-v34-wybor-gestem.md`).
