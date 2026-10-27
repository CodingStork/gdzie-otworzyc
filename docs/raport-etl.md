# Raport ETL — pełny przebieg na prawdziwych danych (2026-10-26)

Komputer: Windows 11, Python 3.13 (uv), dane pobrane i przetworzone lokalnie. Polecenie: `uv run python -m etl.run_all`.

## Czasy kroków

| Krok | Czas | Wynik |
|---|---|---|
| download | 140 s (pierwsze pobranie ~2,7 GB; kolejne uruchomienia pomijają istniejące pliki) | census.zip 566 MB → parquet 76 MB, `poland-latest.osm.pbf` 2,1 GB, 18 plików GUNB (16 woj. + 2 zgłoszeń) |
| population | 11 s | 374 423 heksagony res 8, ludność 37 092 675 |
| osm | 187 s | `poi` 136 584, `places` 118 157 |
| permits | 32 s | `permits_raw` 1 042 375 wierszy |
| geocode | ok. 79 min (56 545 obrębów, 5 wątków) + dokończenie | patrz niżej |
| permits_hex | < 1 s | `permits_r8` 689 664 wierszy |
| aggregate | 3 s | `hex_pop_r7/r6`, `poi_counts_r8/r7/r6`, `permits_r7/r6` |

Rozmiar `data/app.duckdb`: ok. 93 MB.

## Liczby wierszy

| Tabela | Wiersze |
|---|---|
| hex_pop_r8 / r7 / r6 | 374 423 / 63 700 / 9 669 |
| poi / places | 136 584 / 118 157 |
| poi_counts_r8 / r7 / r6 | 63 554 / 40 535 / 22 791 |
| permits_raw | 1 042 375 (pozwolenia 994 311, zgłoszenia 48 064; od 2016-01-01 do 2026-10-23) |
| permits_r8 / r7 / r6 | 689 664 / 658 829 / 440 120 |
| obreb_geom | 54 361 (patrz niżej) |

Punkty OSM wg typu: sklep spożywczy 50 879, restauracja/fast food 35 415, przedszkole/żłobek 11 282, fryzjer 10 814, salon kosmetyczny 7 206, kawiarnia 5 865, market budowlany 4 433, barber 2 314, siłownia 2 210, ogrody 1 622, paznokcie 1 304, kuchnie/stolarz 772, okna/drzwi 763, instalatorzy 590, tatuaż 564, brukarstwo 551.

## Kontrola jakości (`uv run python -m etl.sanity`)

Wynik: **OK — dane przeszły kontrolę jakości** (po zastrzeżeniu poniżej o niedokończonym geokodowaniu). Najważniejsze wartości: suma ludności 37 092 675 (próg 36,9–37,2 mln), fryzjerzy 10 814 (≥ 8 000), `places` 118 157 (≥ 40 000), nowe domy jednorodzinne w ostatnich 12 miesiącach danych 86 056 (≥ 50 000), wszystkie tabele `*_r6` niepuste.

## Geokodowanie obrębów (ULDK) — stan i **do dokończenia**

Z 56 545 obrębów występujących w pozwoleniach:

| Status | Liczba | Udział |
|---|---|---|
| region (kształt obrębu z ULDK) | 44 106 | 78,0% |
| commune (fallback: środek gminy) | 8 743 | 15,5% |
| missing (ULDK nie zna obrębu ani gminy) | 1 512 | 2,7% |
| **jeszcze niegeokodowane** | **2 184** | **3,9%** |

Po ok. godzinie intensywnych zapytań serwer ULDK zaczął przekierowywać połączenia z tego komputera (HTTP 302 na `integracja01.gugik.gov.pl/resp/uldk.php`, strona-pułapka z odpowiedzią o rozmiarze 4 GB) — wygląda to na blokadę ochrony przed nadmiernym ruchem. Blokada trwała jeszcze po kilku godzinach, więc ostatnie 2 184 obrębów (w kolejności alfabetycznej identyfikatorów — głównie województwo zachodniopomorskie, kody `32…`) **czeka na dokończenie**. W tych obrębach nie ma jeszcze danych o nowych budowach (pozostałe czynniki — ludność, konkurencja — działają normalnie).

**Co zrobić (po odczekaniu na odblokowanie, zatrzymawszy serwer):**

```powershell
uv run python -m etl.run_all --only geocode,permits_hex,aggregate --force
uv run python -m etl.sanity
```

`--force` przy kroku `geocode` ponawia także 1 512 obrębów ze statusem `missing` (część z nich mogła zostać błędnie oznaczona przed zmianą kodu). Krok jest wznawialny i teraz przerwie się z wyraźnym komunikatem, jeśli ULDK znów zacznie blokować (dane nie są wtedy zapisywane jako „brak wyniku”).

## Odchylenia od planu i zaobserwowane anomalie

- **Podkład mapy: Esri zamiast CARTO.** Kafelki CARTO Positron zwracają obecnie znak wodny „API KEY REQUIRED”. Użyto Esri World Light Gray (osobne warstwy podkładu i etykiet, maks. zoom 16); atrybucja zmieniona na „© Esri”. Etykiety Esri przy małym zoomie są po angielsku (Warsaw), po przybliżeniu — lokalne.
- **Duplikaty w rejestrze GUNB:** 308 994 z 1 351 868 wierszy (23%) to powtórzone numery wniosków/zgłoszeń (usunięte po `source_id`); 499 wierszy bez obrębu odrzucono. Nowe domy jednorodzinne: 1 013 684 (ok. 100 tys. rocznie — zgodnie ze statystyką GUNB), wielorodzinne: 28 691.
- **ULDK:** `GetCommuneById` bywa, że zwraca inną jednostkę niż zapytana (opisane w `zrodla-danych.md`) — używany tylko jako fallback; klient nie śledzi przekierowań i traktuje nieznane odpowiedzi jako błąd (nie „brak wyniku”); domyślnie 3 wątki zamiast 5.
- **Kod analizy:** pierścienie `grid_disk` z mnożnikiem 1,16 (pierścień k leży w odległości 0,87–1,0 × k × odstęp), jądro liczone macierzą rzadką (`cKDTree.sparse_distance_matrix`) zamiast pętli `query_ball_point` — ten sam wynik, szybciej; kandydatami do wyświetlenia są tylko heksagony z jakimikolwiek danymi (morze nie dostaje heksagonów).
- **ETL:** kroki `permits_hex` i `aggregate` zawsze się przebudowują (tanie, tabele pochodne); pozostałe pomijają się, jeśli wynik istnieje. Daty pozwoleń spoza 2016–dziś są odrzucane (literówki przesuwałyby okno czasowe). Wypakowywanie plików jest atomowe.
- **Fixture'y GUNB** w testach są syntetyczne (zanonimizowane), ale odtwarzają prawdziwe pułapki formatu (zduplikowana kolumna `cecha`, nowa linia w polu w cudzysłowie, „zmiana pozwolenia”, kategoria XXVI, brak obrębu, duplikat numeru).

## Czasy odpowiedzi API (scenariusze z planu)

| Scenariusz | Czas | Heksagony |
|---|---|---|
| Salon kosmetyczny / Kobiety / Opole 10 km | ~0,4 s | 393 |
| Brukarstwo / Nowe domy jednorodzinne (24 mies.) / Wrocław 30 km | ~0,15 s | 580 |
| Sklep spożywczy / cała Polska | ~0,2 s | 9 678 |

Wszystkie poniżej 3 s. Weryfikację w przeglądarce wykonano w wbudowanej przeglądarce (okno ok. 800×520 i emulacja telefonu 375×812). **Nie sprawdzono:** dostępu z drugiego urządzenia przez Tailscale ani reguły zapory Windows (wymagają działań właściciela — instrukcja w README).

---

# v2 (2026-10-27) — budynki, ludność dasymetryczna w res 9, agregaty 9 → 5

Polecenie: `uv run python -m etl.run_all --only buildings,population,permits_hex,aggregate --force` (log: `data/etl_v2.log`).

## Czasy kroków

| Krok | Czas | Wynik |
|---|---|---|
| buildings | 951 s | 13 979 149 budynków z wagą > 0 (z 17,8 mln obiektów `building`), suma wag 1 909 377 590, `building_weights` 1 226 407 wierszy |
| population | 8 s | `hex_pop_r9` 938 150 heksagonów, ludność 37 092 675 (suma zachowana) |
| permits_hex | < 1 s | `permits_r9` 714 645 wierszy |
| aggregate | 15 s | `hex_pop_r8..r5`, `poi_counts_r9..r5`, `permits_r9..r5` (wszystkie z kolumnami `lat, lng`) |

Rozmiar `data/app.duckdb`: ok. 277 MB (v1: 93 MB).

## Jakość

- **Udział ludności rozłożonej przez budynki: 100,0%** (próg ≥ 85%): w każdej komórce spisu z ludnością jest co najmniej jeden budynek z wagą > 0, więc rozkład równomierny (zapas) nie był potrzebny.
- `uv run python -m etl.sanity` → **OK**. Suma `hex_pop_r9.pop_total` 37 092 675 (próg 36,9–37,2 mln), `building_weights` 1,23 mln wierszy (próg ≥ 1 mln).
- Mediana ludności heksagonu res 9: ok. 10 osób, maksimum 5 448 (zabudowa wielorodzinna) — ludność jest skupiona w budynkach, nie rozmyta po kwadracie.

## Liczby wierszy

| Tabela | Wiersze |
|---|---|
| hex_pop_r9 / r8 / r7 / r6 / r5 | 938 150 / 275 775 / 60 029 / 9 607 / 1 445 |
| poi_counts_r9 / r8 / r7 / r6 / r5 | 93 747 / 63 764 / 40 576 / 22 814 / 9 475 |
| permits_r9 / r8 / r7 / r6 / r5 | 714 645 / 712 717 / 681 076 / 457 012 / 166 522 |
| building_weights | 1 226 407 |

## Odchylenia od planu (v2)

- **Kolumny `lat, lng` także w `poi_counts_r*` i `permits_r*`** (plan: tylko w `hex_pop_r*`). Dzięki temu zapytania o komórki w prostokącie widoku są jednakowe dla wszystkich tabel i nie trzeba liczyć środków heksagonów w Pythonie.
- **Stare funkcje v1 (`kernel_sums`, `quantile_breaks`, `choose_resolution`, `effective_bandwidth_km`)** zostały usunięte dopiero w Task 5 (razem z przepisaniem `service.py`), a nie w Task 4 — do tego czasu korzystał z nich stary serwis i stare testy.
- **Brak notatki o „najmniejszym liczonym zasięgu” przy `compute_res = 9`**: drobniejszej siatki nie ma, więc prośba „przybliż mapę” wprowadzałaby w błąd. Notatka pojawia się tylko przy grubszym `compute_res`.
- **Obsługa zablokowanej bazy** jest globalnym handlerem wyjątku `DatabaseBusy` w `main.py` (obejmuje wszystkie endpointy), a nie obsługą w każdym endpoincie osobno.
- **`poi.h3` zostaje w res 8** (kolumna z v1, niewykorzystywana przez v2); `poi_counts_r9` liczone jest z `poi.lat/lng`.

## Czasy odpowiedzi API v2 (prawdziwa baza, `GET /api/view`)

Pomiar `curl`-em z Pythona na tym samym komputerze (pierwsze zapytanie po starcie serwera obejmuje otwarcie bazy) oraz `performance.now()` w przeglądarce dla widoku całej Polski.

| Scenariusz | Czas | Heksagony (rysowane) | display/compute res |
|---|---|---|---|
| Warszawa, zoom 13, fryzjer + mieszkańcy, zasięg 0,5 km (pierwsze zapytanie) | 2,2 s | 2 489 | 9 / 9 |
| to samo, z pamięci podręcznej | 0,04 s | 2 489 | 9 / 9 |
| Warszawa, zoom 11, zasięg 1,5 km | 0,20 s | 4 707 | 8 / 9 |
| Mazowsze, zoom 9, zasięg 1,5 km | 0,37 s | 15 222 | 7 / 8 |
| **Cała Polska, zoom 6, zasięg 0,1 km** | **0,22 s** (w przeglądarce 0,22–0,24 s) | 1 445 | 5 / 7 |
| Cała Polska, zoom 6, zasięg 20 km (market + nowe budynki) | 0,12–0,14 s | 1 445 | 5 / 6 |
| Kraków, zoom 13, tylko seniorzy, 1 km | 0,07 s | 3 820 | 9 / 9 |
| Wrocław, zoom 10, brukarz + nowe domy, 0,3 km (→ 1 km) | 0,16 s | 3 179 | 8 / 9 |

Wszystkie wyraźnie poniżej 5 s. Przy zoomie 6 `compute_res` to 7 (a nie 8): bbox przyciągnięty do siatki 2° jest większy od samej Polski, więc estymata liczby komórek res 8 przekracza limit 800 tys.

## Weryfikacja w przeglądarce (v2)

Wbudowana przeglądarka, okno 1280×800 i emulacja telefonu 375×812; zrzuty w `docs/screenshots/v2-*.png`. Sprawdzone: tryby (sam typ → tylko „Konkurencja”, sam popyt → tylko „Popyt”, oba → trzy warstwy), automatyczne odświeżanie po przesunięciu/zoomie, płynne przejście między rozdzielczościami (próbkowanie `opacity` paneli: stara siatka gaśnie 0,70 → 0, nowa rośnie 0 → 0,70 w ok. 250 ms), pytajniki, link z hashem po przeładowaniu, notatka o min. 1 km dla pozwoleń, notatka o przybliżeniu przy małym zoomie, **kliknięcie heksagonu zawsze daje dymek z liczbami i okrąg, nigdy pinezkę** (także z włączonymi punktami firm i po kliknięciu pozycji top-5). **Nie sprawdzono:** dostępu z drugiego urządzenia (Tailscale) ani Safari/Firefox.

## Dodatkowe odchylenia i uwagi z implementacji frontendu

- Statyczne pliki frontendu są serwowane z `Cache-Control: no-cache` (przeglądarka potrafiła uruchomić stary `index.html` z nowym `app.js`).
- Na telefonie na czas otwarcia dymku chowają się kontrolki warstw/legenda; legenda jest tam niższa (bez podpisu 90%).
- Zasięg < 1 km dla pozwoleń: suwak pokazuje wybraną wartość, a faktyczny zasięg (1 km) podaje notatka i dymek.
- Eurostat przypisuje komórki graniczne (np. „DE-PL”) do Polski w całości — pojedyncze heksagony tuż za granicą (np. po niemieckiej stronie Nysy) mają więc ludność i mogą trafić do top-5; to ograniczenie danych z v1.
- Top-5 jest liczone dla widocznego obszaru, więc po „przelocie” do wskazanego miejsca lista się zmienia.

## v2.1 — skala kolorów i promień od miejscowości

- Kolor heksagonu liczy teraz przeglądarka z **wartości w skali logarytmicznej** (zakres = 2.–98. percentyl dodatnich wartości rysowanych heksagonów), a nie z percentyla z API. Powód: dla dzieci w Warszawie (zasięg 2,5 km, zoom 10) punkt pod Pruszkowem (ok. 4 600) i centrum (ok. 19 000) miały percentyle 93 i 100, czyli prawie ten sam kolor. Pole `legend` i percentyle w odpowiedzi `/api/view` zostały (nic ich już nie koloruje; testy API bez zmian).
- `/api/view` przyjmuje opcjonalne `area=lat,lng,promień_km` (promień 1–50 km, punkt w Polsce); działa wyłącznie przy wyborze top-5 (poza cache rdzenia), więc nie zmienia czasu odpowiedzi.
- Weryfikacja w przeglądarce (okno 1024×768 — tyle ma panel podglądu): zrzuty `docs/screenshots/v21-*.png`. Rozkład wartości na kwartyle skali (dzieci, Warszawa, zasięg 2,5 km): z12 14/15/16/55%, z10 49/29/14/8%, z9 45/39/9/6%, z7 16/51/24/10% — na każdym poziomie widać zróżnicowanie.
