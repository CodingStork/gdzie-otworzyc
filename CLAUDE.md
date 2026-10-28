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
  liczymy, **ilu klientów zdobędzie nowa firma** (Huff) i porównujemy z **średnią krajową** (per capita).
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

## 4. Historia decyzji — czego NIE robić z powrotem

| Wersja | Co | Dlaczego zmienione |
|---|---|---|
| v1 | Heksagony H3 dla całej Polski, wskaźnik „klienci na 1 konkurenta”, skala percentylowa | Kolory zlewały 4 600 i 19 000; heksagony rosły z oddaleniem; niezrozumiałe „okazja/popyt/konkurencja” |
| v2 / v2.1 | Mapa dynamiczna z poziomami szczegółowości (LOD), dasymetria na budynki, okrąg 2SFCA, skala log | Ciągłe przeliczanie całej Polski przy ruchu mapy było męczące; mapa „zalana kolorem” po oddaleniu |
| v3 | Przepływ **miejsce + promień → „Pokaż mapę”**, **mgła** (powierzchnia ciągła YlOrRd, log, przezroczystość), **model Huffa** z opcją zewnętrzną, szczegóły po kliknięciu | Uwagi: brak danych o firmach, panele pomieszane, heksagony w szczegółach zbędne, nie da się kliknąć poza okrąg |
| v3.1 | Firmy z **OSM + Overture Maps** (deduplikacja), **podsumowanie obszaru** ze średnią krajową, ulice w top-5, **trend budów**, lewo = ustawienia / prawo = wnioski, klik poza okręgiem = nowe miejsce, zasięg min. 0,3 km, zakładki na telefonie | — (commit 5d9dbf8; tryb „Wybrane miejsce” działa dalej bez zmian) |
| v3.2 | Przełącznik **Cała Polska / Wybrane miejsce**: po oddaleniu **gotowa mapa Polski z ETL** (krok `national`: Huff dla 420 tys. punktów res 8, piramida **max** res 7–5, **stała skala** z `national_meta`, `/api/national`), po przybliżeniu (półprzekątna ≤ 20 km) **mapa na żywo** (`/api/surface` w trybie prostokąta widoku); katalog **bez rzemieślników** (brukarz, ogrody, okna, kuchnie, instalatorzy → `HIDDEN_TYPES`), podpowiedź dla nich, „Przeanalizuj to miejsce” w dymku, hash `mode=pl` | — (aktualna, zweryfikowana w przeglądarce 2026-10-28; czeka na testy Marcina) |

Odrzucone świadomie: heksagony jako główna warstwa, ciągłe przeliczanie przy ruchu mapy (v3.2 liczy na żywo dopiero PO przybliżeniu do miasta i po zakończeniu ruchu; oddalony widok jest gotowy z ETL), przełącznik „Konkurencja”, mapa bivariate, Leaflet.heat,
tęczowe palety, zasięg < 0,3 km (dane ludności mają ~300 m rozdzielczości), typy firm pracujących u klienta w katalogu (dopóki nie ma CEIDG — „konkurencja” byłaby fikcją), średnia zamiast maksimum w piramidzie (zalewa małe ośrodki), Overpass API na żywo (blokuje automaty).

## 5. Stan techniczny

Szczegóły (metoda, wzory, źródła, licencje, architektura, instalacja): **`README.md`**. Najważniejsze skróty:

- **Stack:** Python 3.13 przez `uv` (systemowy Python 3.15 jest za nowy dla bibliotek), FastAPI + uvicorn, DuckDB (`data/app.duckdb`),
  numpy/scipy (cKDTree), pyproj, shapely, h3 v4, pyosmium. Frontend: czysty JS + Leaflet 1.9.4, bez Node i bez budowania.
- **Dane:** Eurostat Census GRID 2021 (1 km) rozłożony dasymetrycznie na H3 res 9; OSM (Geofabrik) → firmy, miejscowości, ulice, wagi budynków;
  Overture Places → firmy; GUNB RWDZ + ULDK → pozwolenia na budowę (dokładność do obrębu). Układy: EPSG:2180/lokalny metryczny do odległości, 3035 spis, 4326 H3/mapa.
- **Stan v3.2:** 230 testów zielonych, `etl.sanity` OK (sprawdza też gotową mapę Polski). Krok `national` = 780 s, 65 warstw, baza 346 → 365 MB (szczegóły: `docs/raport-etl.md`, sekcja v3.2). `/api/national` ~0,25 s bez cache, kilkanaście ms z cache; widok na żywo ~0,7 s. Typów w katalogu jest 11 (rzemieślnicy w `HIDDEN_TYPES`, ETL nadal je zbiera do `poi`). Przy zmianie danych: `uv run python -m etl.run_all --only aggregate,national --force`.
- **Stan v3.1 (dalej aktualny dla danych):** Tabela `poi` ma kolumny `source` (`osm`/`overture`) i `source_id` (dawniej `osm_id`).
  Salony kosmetyczne: 7 206 z OSM + 24 133 z Overture. Zasięg 0,1–0,3 km API podnosi do 0,3 z notatką; trend pomija ostatni, niepełny miesiąc danych.
- **API:** `/api/national` (gotowa mapa Polski: stała skala, rozdzielczość wg `px`), `/api/surface` (mgła + podsumowanie + top-5 + trend; okrąg `lat,lng,radius_km` albo prostokąt widoku `west,south,east,north`), `/api/point` (dymek), `/api/catalog`, `/api/poi`, `/api/geocode`, `/api/meta`.
- **Komendy:** `uv sync` · `uv run pytest -v` · `uv run python -m etl.run_all [--only kroki] [--force]` (kroki: …, `aggregate`, `national`) · `uv run python -m etl.sanity` · `start.bat` (port 8000).

### Pułapki, które już kosztowały czas
- **`data/` nie jest w repozytorium** (gitignore). Na nowym komputerze trzeba uruchomić cały ETL (kilka godzin, ~3 GB pobierania, ≥ 20 GB dysku).
- **Mapa Polski jest policzona dla typowego zasięgu** — jeśli zmienisz `bandwidth_km` typu, `default_reach_km` czynnika, katalog albo dane, trzeba przeliczyć krok `national` (`--only aggregate,national --force`; sanity wykryje brakującą warstwę, ale nie nieaktualną).
- **Największe wartości na mapie Polski to często luki w danych o firmach** (np. Olsztynek: 3,6 tys. kobiet w kwadracie 3 × 3 km i 0 salonów w OSM + Overture) — API dopisuje o tym notatkę; nie „naprawiaj” tego w kodzie.
- **Serwer i ETL nie mogą działać naraz** (blokada pliku DuckDB → API zwraca 503). Nie zabijaj serwera Marcina bez pytania.
- **ULDK (GUGiK)** po ~1 h intensywnych zapytań blokuje IP (przekierowanie 302 na WAF) — geokodowanie jest wznawialne, odczekaj i dokończ.
- Formaty danych GUNB/ULDK/spisu są pełne niespodzianek — zanim coś zmienisz w ETL, przeczytaj `docs/zrodla-danych.md`.
- Darmowe kafelki CARTO wymagają klucza → podkład Esri Light Gray. Nominatim: limit 1 zapytanie/s, wymagany User-Agent.
- Animowany zoom Leaflet potrafi się zawiesić przy starcie z hasha — używamy dopasowania bez animacji.

## 6. Co dalej (otwarte)

1. **CEIDG** jako trzecie źródło firm (kody PKD już są w katalogu) — najważniejsze dla branż, których nie ma w OSM/Overture (brukarze, ogrodnicy).
   Marcin musi złożyć wniosek o token API (dane.biznes.gov.pl, Profil Zaufany). **Token trafia do pliku `.env` (w gitignore), nigdy do czatu ani repo.**
2. **Tailscale** (dostęp z uczelni) + reguła zapory dla portu 8000 — instrukcja w README; robimy dopiero, gdy Marcin przetestuje wersję lokalnie.
3. Z v3.2: osobna stała skala kolorów dla każdego poziomu piramidy (na mapie całej Polski kontrast jest umiarkowany — mediana res 6 leży wyżej niż mediana res 8, od której liczy się skala); powrót typów rzemieślniczych po dołączeniu CEIDG (są w `HIDDEN_TYPES`).
4. Drobne, odłożone z przeglądu v3.1: deduplikacja „jeden do wielu” (dla sklepów i restauracji odpada ok. 2/3 punktów Overture — sprawdzić, czy nie za agresywnie),
   `/api/poi` bez `ORDER BY` przy limicie 5 000, sanity liczy wiersze typ×firma, brak pliku `.release` → „Overture Maps nieznane”,
   promień obszaru ma krok 1 km, w podsumowaniu „Obszar: punkt na mapie”, gdy miejsce wybrano kliknięciem (można dociągnąć nazwę najbliższej miejscowości).
5. Opcjonalnie: hot-spoty Getis-Ord Gi\*, model ML „luki rynkowej” z walidacją przestrzenną, dokładne geokodowanie działek.
6. Przy każdej nowej wersji: **zaktualizuj ten plik** (tabela w §4, stan w §5–6), README i ściągę.

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
- `docs/kompletnosc-danych.md` — jak pełne są dane o firmach wg typu i wielkości miejscowości (porównanie z GUS/D&B).
- `docs/superpowers/specs/*-design.md` — specyfikacje kolejnych wersji (v1 2026-10-26, v2 i v3 2026-10-27).
- `docs/superpowers/plans/*.md` — plany wykonawcze (najnowszy: `2026-10-28-v32-cala-polska.md`).
