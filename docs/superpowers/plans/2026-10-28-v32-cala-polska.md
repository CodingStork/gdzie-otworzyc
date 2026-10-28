# Plan v3.2 — tryb „Cała Polska” (gotowa mapa + na żywo po przybliżeniu) i uczciwy katalog branż

Data: 2026-10-28. Autor: agent prowadzący (Opus). Wykonawca: sesja implementacyjna (Sonnet), zadanie po zadaniu, TDD, commit po każdym zadaniu.
Najpierw przeczytaj `CLAUDE.md` (cel projektu, zasady), `README.md` (metoda) i `docs/kompletnosc-danych.md` (dlaczego zmieniamy katalog).

## Decyzje Marcina (2026-10-28)
1. Chce mapy całej Polski, w której mgła Huffa zmienia się przy przybliżaniu i oddalaniu. Wybrał wariant **„gotowa mapa + na żywo”**:
   po oddaleniu widać mapę Polski policzoną raz w ETL (typowy zasięg branży, stała skala kolorów dla całego kraju),
   a po przybliżeniu do poziomu miasta mgła liczy się na żywo z jego ustawieniami.
   Pamiętaj: w v2 ciągłe przeliczanie całej Polski przy ruchu mapy go męczyło — dlatego na żywo liczymy **tylko po przybliżeniu**, a oddalony widok jest natychmiastowy.
2. „Usunąć opcje dla rzemieślników, których danych po prostu nie mamy — mało danych realnie wprowadza użytkownika w błąd.”
   Decyzja prowadzącego: z listy „Typ działalności” znikają typy firm pracujących u klienta (pokrycie bardzo niskie, patrz `docs/kompletnosc-danych.md`),
   ale **czynniki popytu „nowe domy” zostają** — brukarz nadal może wybrać „Twoi klienci to: nowe domy” bez branży i zobaczyć, gdzie budują (i trend).

## Task 1 — katalog: uczciwe branże
- Usuń z `TYPES` (backend/app/catalog.py): `paving`, `garden`, `windows`, `kitchen`, `installer`. Zostaw w kodzie komentarz, że wrócą z CEIDG (M9),
  i zostaw definicje w osobnym słowniku `HIDDEN_TYPES` (nieeksportowanym w `/api/catalog`, nieużywanym przez API), żeby ETL `poi` dalej je zbierał — dane się przydadzą przy CEIDG.
  Jeśli trzymanie ich w ETL komplikuje kod, wolno je usunąć całkiem; odnotuj w raporcie.
- Zaktualizuj `osm_quality` wg `docs/kompletnosc-danych.md`: `good` — hairdresser, beauty, grocery, restaurant, kindergarten, cafe, diy; `medium` — barber, nails, tattoo, fitness.
  Sprawdź, czy dla `medium` jest sensowne ostrzeżenie (łagodniejsze niż POOR_WARNING), np. „Dane o tych firmach są niepełne — część firm może nie być widoczna.”
- Grupa „Budowlanka / dom” zostaje z jednym typem `diy` — przemianuj grupę na „Dom i budowa” albo przenieś `diy` do handlu; wybierz czytelniejsze i uzasadnij w commicie.
- Frontend: pod listą „Typ działalności” krótka podpowiedź (dosłownie):
  „Pracujesz u klienta (brukarz, instalator, ogrodnik)? Nie wybieraj branży — w »Twoi klienci to« wybierz nowe domy i zobacz, gdzie się buduje. Firm tego typu prawie nie ma w otwartych danych, więc nie pokazujemy konkurencji.”
- Stare linki z usuniętym `type` → frontend ignoruje nieznany typ (bez błędu) i zostawia czynnik popytu; API dla nieznanego typu zwraca 422 jak dotąd.
- Testy: katalog nie zawiera usuniętych typów, każdy typ ma ≥ 1 czynnik popytu istniejący w `DEMANDS`, hash z `type=paving` nie psuje frontu (test ręczny w Task 5).

## Task 2 — ETL `national`: gotowa mapa Polski
Nowy krok `national` w `etl/run_all.py` (po `aggregate`), moduł `etl/national.py`.

- **Punkty docelowe:** środki komórek H3 **res 8** (~0,74 km², ~900 m odstępu): rodzice komórek res 9 z ludnością > 0 + ich pierścień `grid_disk(·,1)`
  (firmę można otworzyć tuż obok osiedla). Pomiar prowadzącego: dolnośląskie = 38 tys. punktów res 8, Huff 1,5 km dla salonów 0,9 s → cała Polska ~15 s na warstwę.
- **Warstwy** (te same wzory i funkcje co `/api/surface`: `huff_and_potential`, `demand_potential`, `competition_density` z `backend/app/analysis/surface.py`;
  odległości w EPSG:2180; źródła popytu wg `demand_res(reach)` jak w `run_surface`):
  - `open__{type}__{demand}` — Huff dla każdego typu × każdy jego `suggested_demands`, zasięg = `bandwidth_km` typu (dla pozwoleń ≥ 1 km jak `effective_reach_km`, okno pozwoleń = `DEFAULT_MONTHS`);
  - `comp__{type}` — zagęszczenie firm, zasięg typu;
  - `demand__{demand}__{reach}` — potencjał popytu dla par (czynnik, zasięg) występujących w katalogu + dla każdego czynnika jego **zasięg domyślny bez branży**
    (dodaj do `Demand` pole `default_reach_km`: spis 1,5 km, pozwolenia 10 km);
  - `trend__{demand}` — dla czynników z pozwoleń, zasięg domyślny (jak `load_trend`).
  Dostępność konkurencji `C_i` licz raz na typ i używaj dla wszystkich jego czynników.
- **Zapis:** tabela szeroka `national_r8(h3, lat, lng, <kolumna na warstwę> FLOAT)` + piramida `national_r7`, `national_r6`, `national_r5`
  z agregacją **max** dzieci (znaczenie dla użytkownika: „najlepsze miejsce w tym rejonie”) — dla `trend` też max wartości bezwzględnej ze znakiem.
  Tabela `national_meta(layer, p5, p99, reach_km, months, computed_at)` — percentyle wartości > 0 na res 8 do **stałej skali kolorów** w całym kraju
  (dla trendu: p99 z |wartości|).
- Wartości zaokrąglij do 3 cyfr znaczących (`_round_significant`). Sprawdź rozmiar bazy; jeśli tabela res 8 > 300 MB, zgłoś w raporcie i rozważ float16/odcięcie wartości < p1.
- Czas całego kroku zmierz i wpisz do `docs/raport-etl.md` (cel < 30 min). Krok ma być wznawialny na poziomie warstwy (pomija policzone, `--force` liczy od nowa).
- Testy na małym fixture: wartość `open` w punkcie res 8 zgadza się z `huff_expected` liczonym wprost; max w piramidzie; percentyle w meta; wznawialność.
- `etl/sanity.py`: każda warstwa z katalogu istnieje, ma > 0 wartości dodatnich, a Warszawa-centrum ma `demand__pop_total__1.5` w górnych 5%.

## Task 3 — API `/api/national`
`GET /api/national?type&demand&layer&west&south&east&north&px` (px = szerokość mapy w pikselach, domyślnie 1000).
- Rozdzielczość: najgrubsza z `national_r5..r8`, której komórka jest ≤ ~4 px ekranu (żeby było gładko, ale bez setek tysięcy punktów); limit ~60 tys. komórek w odpowiedzi.
- Odpowiedź w tym samym kształcie co `/api/surface`, żeby frontend użył tego samego rysowania mgły:
  regularna siatka lat/lng nad bbox (~ px/4 × proporcjonalnie komórek), wartość komórki = max komórek H3, których środek w nią wpada, `null` gdzie brak;
  `layers`, `values`, `scale: {lo, hi}` z `national_meta` (stała skala!), `reach_km`, `top` (5 maksimów w widoku z odstępem ≥ 1/6 szerokości widoku,
  nazwa = `nearest_place_name` — bez ulic, bo widok jest duży), `notes` (np. „Mapa Polski policzona dla typowego zasięgu: 1,5 km. Przybliż, by zobaczyć Twoje ustawienia.”),
  `warnings` jak w surface.
- Gdy dla wybranego (typ, czynnik) nie ma warstwy (czynnik spoza `suggested_demands`) → `layers` = dostępne zamiast brakującej + notatka:
  „Dla tego wyboru nie ma gotowej mapy Polski — przybliż mapę, a policzymy ją na żywo.”
- `/api/surface` dostaje opcjonalny tryb prostokąta dla widoku: `west,south,east,north` zamiast `lat,lng,radius_km` (siatka pokrywa prostokąt, bez maski okręgu,
  bok ≤ 60 km), podsumowanie liczone dla prostokąta z podpisem „Widoczny obszar”. Jeśli prościej — okrąg opisany na widoku z maską przyciętą do prostokąta; opisz wybór.
- Cache LRU dla `/api/national` (klucz: parametry z bbox zaokrąglonym do siatki kafla), cel < 300 ms na odpowiedź.
- Testy API: kształt odpowiedzi, stała skala niezależna od bbox, wybór rozdzielczości wg px, 422 dla złych parametrów.

## Task 4 — frontend: przełącznik trybu i płynne przejście
- Na górze lewego panelu: **„Obszar analizy”**: ◉ **Cała Polska** / ○ **Wybrane miejsce** (domyślnie Cała Polska — „najpierw przegląd”, Shneiderman).
  Pytajnik (dosłownie): „Cała Polska: od razu widzisz całą mapę i możesz ją swobodnie przybliżać. Po oddaleniu pokazujemy gotową mapę dla typowego zasięgu branży,
  a po przybliżeniu do miasta liczymy ją na żywo z Twoimi ustawieniami. Wybrane miejsce: analiza okręgu wokół jednego miejsca z podsumowaniem i porównaniem ze średnią krajową.”
- **Cała Polska:** pola „Miejsce” i „Promień obszaru” oraz przycisk „Pokaż mapę” ukryte; mgła pojawia się od razu po wybraniu branży/klientów.
  - Widok szerszy niż ~40 km (pół przekątnej > 20 km): `/api/national` po `moveend` (debounce 250 ms), stała skala kolorów z `scale` (legenda z tymi wartościami,
    podpis „dla typowego zasięgu X km”). Suwak zasięgu nieaktywny z podpowiedzią „przybliż mapę, aby użyć własnego zasięgu”.
  - Węższy widok: `/api/surface` w trybie prostokąta z ustawieniami użytkownika (debounce 400 ms); do czasu odpowiedzi zostaje poprzednia mgła, potem płynne przenikanie (~250 ms).
    Skala kolorów lokalna jak dotąd (2 rzędy wielkości) — legenda mówi wtedy „kolory dopasowane do widoku”.
  - Anulowanie starych zapytań (AbortController / numer zapytania), żadnych wyścigów przy szybkim przewijaniu.
  - Prawy panel: legenda, top-5 „Najlepsze miejsca w widoku”, notatki/ostrzeżenia; „Podsumowanie obszaru” tylko w widoku na żywo (z podpisem „Widoczny obszar”).
  - Klik w mapę = szczegóły punktu (`/api/point`) jak teraz + w dymku przycisk **„Przeanalizuj to miejsce”** → przełącza na „Wybrane miejsce” z tym punktem.
- **Wybrane miejsce:** bez zmian względem v3.1.
- Hash: dodaj `mode=pl|place`; link z `mode=pl` odtwarza widok mapy (zoom/centrum) — dodaj `z`, `clat`, `clng` dla tego trybu.
- Telefon: przełącznik w zakładce „Ustawienia”; mgła przy przesuwaniu nie może zacinać mapy.

## Task 5 — weryfikacja w przeglądarce (port 8001, nie ruszaj serwera Marcina na 8000; jeśli 8000 blokuje bazę przy ETL — zapytaj Marcina)
Scenariusze, zrzuty do `docs/screenshots/v32-*.png`:
a) Start: Cała Polska, salon kosmetyczny + kobiety → mgła na całą Polskę od razu; czy da się odczytać (czy nie jest „zalana” ani pusta)? Czy duże miasta nie wygrywają wszystkiego tylko dlatego, że są duże?
b) Przybliżanie Polska → Dolny Śląsk → Wrocław → Psie Pole: przejście gotowa → na żywo bez mrugania, legenda zmienia podpis, top-5 sensowne.
c) Szybkie przewijanie/zoom kółkiem 10× — brak wyścigów, brak zawieszeń, konsola bez błędów.
d) Klik → dymek → „Przeanalizuj to miejsce” → tryb Wybrane miejsce z okręgiem.
e) Brak branży, klienci = nowe domy jednorodzinne → mapa Polski „gdzie budują” + trend; podpowiedź dla rzemieślników widoczna.
f) Link ze starym `type=paving` → brak błędu, zostaje czynnik popytu.
g) Telefon 375×812.
Przy każdym zrzucie zadaj pytanie z `CLAUDE.md`: czy osoba otwierająca salon podjęłaby dzięki temu lepszą decyzję? Jeśli coś wprowadza w błąd — popraw albo opisz.

## Task 6 — dokumentacja i przegląd
README (tryb Cała Polska, zmiana katalogu, piramida max, stała skala), `docs/sciaga-do-obrony.md` (dlaczego max przy agregacji, dlaczego gotowa mapa + na żywo,
dlaczego usunięto rzemieślników), `docs/raport-etl.md` (czas i rozmiar kroku `national`), **`CLAUDE.md`** (tabela §4 — wiersz v3.2, stan §5, otwarte §6).
Na koniec przegląd całości subagentem (Opus) i poprawki. Push na `main`.
