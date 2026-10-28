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

# v3 (2026-10-27) — mgła + model Huffa

Dane i ETL bez zmian; zmienia się tylko analiza (`/api/surface`, `/api/point`) i frontend. Baza `data/app.duckdb` jak w v2.

## Czasy `GET /api/surface` (prawdziwa baza, obliczenia na tym samym komputerze, bez pamięci podręcznej)

Pomiar: `run_surface` na bazie produkcyjnej (czas serwera); w przeglądarce Wrocław 30 km / zasięg 15 km: 2,4 s łącznie z pobraniem i narysowaniem mgły.

| Scenariusz | Czas | Siatka | Źródła popytu |
|---|---|---|---|
| Pruszków, fryzjer + mieszkańcy, promień 10 km, zasięg 1,5 km (scenariusz 2) | 1,4 s | 180×180 | res 9 |
| Kraków, tylko seniorzy, promień 8 km, zasięg 2 km (scenariusz 5) | 1,7 s | 180×180 | res 9 |
| Kraków, tylko fryzjer, promień 8 km, zasięg 1,5 km (scenariusz 5b) | 0,4 s | 180×180 | — |
| Wrocław, brukarstwo + nowe domy jednorodzinne, promień 30 km, zasięg 15 km (scenariusz 6) | 2,3 s | 200×200 | res 7 |
| Warszawa, fryzjer + mieszkańcy, promień 30 km, zasięg 2 km | 2,6 s | 200×200 | res 9 |
| Warszawa, fryzjer + mieszkańcy, promień 30 km, zasięg 5 km | 3,2 s | 200×200 | res 8 |

Wszystkie poniżej celu (< 3 s dla 10 km / 2 km, < 5 s dla scenariusza 6). Ruch i przybliżanie mapy nie wysyłają żadnych zapytań (sprawdzone w historii zasobów przeglądarki: po przeciągnięciu i przybliżeniu mapy liczba wywołań `/api/*` bez zmian).

## Odchylenia od planu v3

- **Siatka: krok = promień / 90 (a nie / 150).** Plan podawał `/150` (≈ 70 tys. punktów w okręgu), ale spec §3 mówi o ≤ ~23 tys. punktów; pierwszy pomiar przy `/150` dał 5–11 s. Przy `/90` (≈ 25 tys. punktów, krok 50–300 m) mgła wygląda tak samo płynnie, bo i tak jest interpolowana ×4.
- **Jeden przebieg po parach (punkt siatki, źródło popytu) dla „Gdzie otworzyć” i „Gdzie są klienci”** (`huff_and_potential`): znajdowanie par w `cKDTree` jest najdroższe, więc obie warstwy liczymy razem — połowa czasu.
- **Zaokrąglenie wartości do 3 cyfr znaczących (spec: 2).** Przy 2 cyfrach gładka powierzchnia miała widoczne „schodki” (pierścienie jednego koloru) po zamianie na mgłę.
- **Mgła rysowana inaczej niż w planie:** zamiast powiększać gotowy obraz RGBA z `filter: blur`, interpolujemy *wartości* (smoothstep, ×4) i dopiero potem kolorujemy każdy piksel (tablica 256 kolorów); piksele poza okręgiem są przezroczyste. Interpolacja wartości nie daje ciemnych obwódek ani widocznych kwadratów siatki, a nie wymaga filtra.
- **Rozdzielczość źródeł popytu:** `reach ≤ 2 km → r9`, `≤ 8 km → r8`, inaczej `r7` (jak w planie); konkurenci z `poi` w promieniu `promień + 8·zasięg` (żeby dostępność konkurencji `C_i` była poprawna także dla źródeł z bufora).
- **Usunięty zbędny kod v2:** `resolution.py`, `scoring.py`, `catchment_sums`, `/api/view`, testy LOD; checkbox „Punkty firm” zastąpiony rysowaniem konkurentów w szczegółach punktu (ruch mapy nie może wysyłać zapytań).
- Suwak zasięgu jest logarytmiczny o 100 krokach, więc np. 15 km zaokrągla się do 15,5 km (jak w v2.1).
- Kliknięcie mapy w dymku: komórki res 9 pokazujemy tylko dla zasięgu ≤ 3 km (powyżej `cells = []`), konkurenci rysowani z `/api/poi`.

## Weryfikacja w przeglądarce (v3)

Wbudowana przeglądarka, panel podglądu (800×600) i emulacja telefonu 375×812; zrzuty `docs/screenshots/v3-*.png`: start (karta instrukcji), Pruszków fryzjer + mieszkańcy („Gdzie otworzyć” i „Gdzie są klienci”), szczegóły po kliknięciu (okrąg zasięgu, drobne heksagony, konkurenci, dymek), Kraków seniorzy (jedna mapa, bez przełącznika), Wrocław brukarstwo 30 km, telefon. Sprawdzone: przełączanie warstw bez nowego zapytania, komunikat „Wybierz branżę lub klientów.” przy „Pokaż mapę” bez wyboru, klik w pustą mapę ustawia miejsce (pinezka + okrąg podglądu), odtworzenie widoku z linku po przeładowaniu.

## Poprawki po przeglądzie (v3)

- **Siatka w lokalnym układzie metrycznym** (`LocalFrame`, odwzorowanie poprzeczne Merkatora wokół wybranego miejsca) zamiast EPSG:2180: w 2180 siatka jest obrócona względem południków (do ok. 4° na zachodzie/wschodzie kraju), więc obraz mgły rozciągany prostokątem w stopniach był przesunięty nawet o ok. 2 km przy promieniu 30 km. Spec §3 mówił „EPSG:2180” — to odchylenie.
- **Zasięg > 12 km → źródła popytu res 6** (wcześniej res 7): syntetyczny pomiar najgorszego przypadku (spis, zasięg 20 km, promień 30 km) dawał ok. 7 s.
- Siatka ma 25–31 tys. punktów w okręgu (krok jest obcinany do 300 m od promienia ok. 27 km).
- Znane drobiazgi bez zmian: format dymku („Mieszkańcy: ok. X (szacunek)”, „Fryzjer w OSM: N”) różni się od przykładu w spec §4; tekst legendy „krok koloru ≈ podwojenie wartości” jest dosłowny ze spec §5, a ściśle zależy od rozpiętości skali; kilka nieużywanych metod w `map.js`/`ui.js`.
- Czasy po poprawkach (prawdziwa baza): Wrocław 30 km / zasięg 15 km (pozwolenia) 0,9 s; **najgorszy przypadek — Warszawa, market budowlany + mieszkańcy, promień 30 km, zasięg 20 km: 1,4 s**; pozostałe scenariusze bez zmian (0,4–3,2 s).

## v3.1 — Overture Maps i ulice (2026-10-27)

Nowe kroki ETL: `overture` (po `osm`) i `streets`. Polecenia: `uv run python -m etl.run_all --only overture --force`, `--only streets --force`, potem `--only aggregate` i `uv run python -m etl.sanity` (**OK**).

| Krok | Czas | Wynik |
|---|---|---|
| overture | 25 s (pobranie ~15 s + deduplikacja) | wydanie `2026-10-21.0`; 173 987 wierszy typ×obiekt przed deduplikacją → **104 087** po (`meta.overture`) |
| streets | 87 s | **1 992 424** punktów wzdłuż nazwanych dróg |
| aggregate | 11 s | `poi_counts_r9` 162 528 wierszy |

Punkty `poi` po scaleniu (OSM + Overture po deduplikacji = razem; w nawiasie liczba z Overture przed deduplikacją):

| Typ | OSM | Overture (przed → po) | Razem |
|---|---|---|---|
| sklep spożywczy | 50 879 | 36 930 → 12 599 | 63 478 |
| restauracja/fast food | 35 415 | 40 259 → 14 911 | 50 326 |
| salon kosmetyczny | 7 206 | 28 240 → 24 133 | 31 339 |
| fryzjer | 10 814 | 13 423 → 9 725 | 20 539 |
| przedszkole/żłobek | 11 282 | 9 348 → 4 795 | 16 077 |
| market budowlany | 4 433 | 11 080 → 9 858 | 14 291 |
| kawiarnia | 5 865 | 7 438 → 4 086 | 9 951 |
| barber | 2 314 | 7 527 → 6 865 | 9 179 |
| siłownia | 2 210 | 7 630 → 6 256 | 8 466 |
| ogrody | 1 622 | 3 545 → 3 074 | 4 696 |
| tatuaż | 564 | 3 446 → 2 993 | 3 557 |
| paznokcie | 1 304 | 1 786 → 1 606 | 2 910 |
| kuchnie/stolarz | 772 | 1 101 → 1 066 | 1 838 |
| instalatorzy | 590 | 1 087 → 1 056 | 1 646 |
| okna/drzwi | 763 | 845 → 778 | 1 541 |
| brukarstwo | 551 | 302 → 286 | 837 |

Odchylenia od planu:
- **Kolumna `poi.osm_id` przemianowana na `source_id`** (przechowuje też UUID Overture) i dodana `source ∈ {'osm','overture'}`. Krok `overture` sam migruje starą bazę (nie trzeba powtarzać kroku `osm`, 3 min).
- Dla grup usług, w których OSM jest słaby (salony, barberzy, siłownie, tatuaż, budowlanka), Overture daje 2–10× więcej firm niż OSM, dla sklepów i restauracji deduplikacja usuwa 60–70% (Overture zawiera sporo punktów, które są też w OSM).
- Próg sanity: Overture ≥ 100 000 w `poi` (jest 104 087) — blisko progu, bo deduplikacja jest agresywna; `beauty` razem ≥ 25 000 (jest 31 339).
- Plik wstępny `overture_places_pl.parquet` z sesji nadrzędnej zawierał też sąsiednie kraje i firmy zamknięte; krok `overture --force` zastąpił go wyciągiem już przefiltrowanym (tylko PL, otwarte, `confidence ≥ 0,5`).

## v3.1 — odchylenia od planu w backendzie/frontendzie i poprawki po przeglądzie (2026-10-27)

- **Task 1 i 2 w jednym commicie** (wspólne zmiany `run_all.py`, `catalog.py`, jedno uruchomienie ETL na prawdziwych danych).
- **Minimalny zasięg:** API przyjmuje 0,1–20 km (poniżej: 422), wartości 0,1–0,3 km podnosi do 0,3 km z notatką „Dane o mieszkańcach mają rozdzielczość ok. 300 m…” — dzięki temu stare linki działają. Suwak w interfejsie ma zakres 0,3–20 km; stary link z mniejszym zasięgiem dostaje 0,3 i tę samą notatkę.
- **Podsumowanie obszaru** liczy popyt zawsze z komórek res 9 (niezależnie od zasięgu), żeby liczba mieszkańców w okręgu nie zależała od suwaka zasięgu. Wiersz „Obszar: {miejsce}, promień r km” zastępuje zdanie „W promieniu r km od {miejsce}” (nazw miejscowości nie odmieniamy). Liczby (klienci, klienci na firmę) są zaokrąglane do setek/dziesiątek.
- **`/api/poi` zwraca też `source`** (tooltip firmy: OpenStreetMap / Overture Maps); `/api/meta` zawiera wiersz `overture` (wydanie w URL).
- **Teksty pytajników i ostrzeżeń** uzupełnione o Overture (zmiana względem spec v3 §5: „z OpenStreetMap i Overture Maps”); `POOR_WARNING` i ostrzeżenie o braku konkurencji też.
- **Promień obszaru** nadal ma krok 1 km (suwak 1–30), więc 1,5 km z linku zaokrągla się do 2 km (zrzut v31-b).
- **Warstwa trendu:** 12 pełnych miesięcy kończy się na miesiącu poprzedzającym najnowszy w danych (najnowszy jest niepełny — w danych z 2026-10 ma 4,5 tys. pozwoleń na domy jednorodzinne wobec ok. 8,5 tys. w pełnym miesiącu; bez tej korekty cały kraj wychodził lekko „na minus”). Zwykły popyt z pozwoleń nadal liczy okno do najnowszego miesiąca (jak w v3).
- Poprawki po przeglądzie świeżym recenzentem: `etl/streets.py` pomija węzły (node) z tagiem `highway`; `verdict` zwraca `None`, gdy brak średniej krajowej; `street_label` zna więcej nazw bez „ul.” (Rynek, Droga, Most, Park, Wybrzeże, „ul.”/„ulica”) i porównuje nazwę miejsca jako całe słowo; podgląd nowego miejsca + zmiana ustawień dopasowuje widok; nazwa warstwy z linku nie trafia do selektora CSS; usunięty martwy kod.
- Odłożone (drobne): deduplikacja „jeden do wielu” (jeden punkt OSM usuwa wszystkie punkty Overture tego typu w 50 m — dla sklepów spożywczych i restauracji odpada ok. 2/3), `/api/poi` bez `ORDER BY` przy limicie 5 000, próg `overture_min` liczy wiersze typ×firma, brak pliku `.release` daje „Overture Maps nieznane” w stopce, końce linii CRLF→LF w `download.py`/`osm_poi.py`.


---

# v3.2 (2026-10-28) — gotowa mapa Polski (krok `national`)

Polecenie: `uv run python -m etl.run_all --only national` (na prawdziwej bazie `data/app.duckdb`; serwer musiał być zatrzymany).

## Czas i rozmiar

| Co | Wynik |
|---|---|
| Czas całego kroku `national` | **780 s (13 min)**, cel < 30 min (druga, niezależna próba na kopii bazy: 750 s) |
| Punkty docelowe (`national_r8`) | 420 330 komórek H3 res 8 (komórki z ludnością + pierścień sąsiadów) |
| Piramida `national_r7 / r6 / r5` | 65 055 / 9 707 / 1 455 komórek (maksimum z dzieci) |
| Warstwy (kolumny FLOAT) | 65, wpisy w `national_meta` (p5, p99, zasięg, okno pozwoleń) |
| Rozmiar bazy | 346 304 512 → 365 178 880 B (**+19 MB** razem ze wszystkimi tabelami `national_*`; limit z planu to 300 MB samej tabeli res 8) |
| `etl.sanity` | **OK** (nowe sprawdzenia: każda warstwa z katalogu istnieje i ma wartości dodatnie, centrum Warszawy w górnych 5% popytu) |

Czasy zadań (kopia bazy, jedno przejście po 420 tys. punktów): Huff dla typu z zasięgiem ≤ 2 km (źródła popytu res 9, ~940 tys. komórek) 16–34 s, tatuaż (5 km) 43 s, markety i przedszkola 9–19 s, sam popyt 11–16 s, trend 7–11 s, zagęszczenie firm < 1 s (market budowlany 8 s). Reszta czasu to zapis kolumn (`ALTER TABLE … ADD COLUMN` + `UPDATE`) i piramida. Dostępność konkurencji `C_i` liczona jest raz na typ i rodzinę czynników (spis / pozwolenia), a wszystkie czynniki typu liczone są jednym przebiegiem po parach (punkt, źródło) (`surface.py: huff_multi`).

## Czasy odpowiedzi API (prawdziwa baza)

| Zapytanie | Pierwsze (bez cache) | Z cache |
|---|---|---|
| `/api/national` — cała Polska, 1000 px (rozdzielczość res 6, ~190 kB JSON) | 0,21–0,26 s | 6–24 ms |
| `/api/national` — kadr 4° × 3° (res 7) | ok. 0,26 s | ok. 10 ms |
| `/api/surface` w trybie widoku, ~30 × 22 km, siatka promień/60 | 0,7 s (z siatką promień/90 było 1,9–2,7 s) | 17 ms |

## Odchylenia od planu i decyzje podjęte samodzielnie

- **`HIDDEN_TYPES` zostały w kodzie** (ETL `poi` nadal je zbiera, `match_types`/`match_overture` sięgają po `ALL_TYPES`); nie psuje to API: dla usuniętego typu `/api/surface` zwraca 422 jak dla nieznanego.
- **Grupa „Budowlanka / dom” zniknęła**, a market budowlany (`diy`) przeniesiono do „Handel / gastro / sport” zamiast tworzyć grupę z jednym typem. Typów w katalogu jest 11.
- **Oceny `osm_quality`** wg `docs/kompletnosc-danych.md`; dla `medium` jest łagodne ostrzeżenie („Dane o tych firmach są niepełne — część firm może nie być widoczna.”), dla `poor` nie ma już żadnego typu.
- **`/api/surface` w trybie widoku:** wybrano wariant „okrąg opisany na widoku + maska przycięta do prostokąta” (plan dopuszczał oba). Siatka widoku jest rzadsza (promień/60 zamiast /90), bo bez tego widok 30 km liczył się ok. 2 s.
- **Wspólny kod:** `huff_and_potential` jest teraz cienką nakładką na `huff_multi` (wiele czynników naraz), a `round_significant` przeniesiono do `surface.py` — te same funkcje liczą API na żywo i ETL (test sprawdza zgodność wartości w punkcie res 8 z `huff_expected`).
- **Siatka odpowiedzi `/api/national`** jest równa w rzucie Mercatora (nie w stopniach), żeby obraz mgły przylegał do kafelków; pola wypełniane są wartością najbliższej komórki H3, gdy komórka H3 jest większa od komórki siatki.
- **Nazwa miejsca w dużym widoku:** `service.nearest_place_name` faworyzuje osiedla i wsie nad miastami (dobre dla okręgu, złe dla kraju: rynek Olsztynka nazywał się „Mierki”), więc w trybie Polski nazwę wybiera `national.place_name` (odległość dzielona przez wagę rodzaju miejsca).
- **Notatka o lukach w danych** w odpowiedzi `/api/national` dla warstw zależnych od firm: największe wartości w skali kraju to często miejsca bez wpisów o firmach (np. Olsztynek: 3,6 tys. kobiet w kwadracie 3 × 3 km i 0 salonów w OSM + Overture). Tego nie „naprawia” żaden model — pokazujemy to uczciwie.

## Poprawki z przeglądu (Opus)

Przegląd całości zrobił subagent Opus; poprawione: (1) pinezki top-5 w oddalonym widoku stoją na najlepszej komórce res 8 w komórce-rodzicu (a nie na jej środku); (2) odpowiedź `/api/national` zwraca `layer_reach_km` — legenda trendu podaje jego prawdziwy zasięg (10 km), nie zasięg branży; (3) `state.loading` nie zostaje `true` po przełączeniu trybu w trakcie liczenia; (4) `px` poza zakresem jest przycinany zamiast zwracać 422; (5) ETL liczy od nowa warstwę policzoną dla innego zasięgu niż obecny w katalogu, a API ignoruje warstwy bez kolumny w całej piramidzie (przerwany ETL); (6) przy gotowej mapie zablokowany jest też okres pozwoleń (24 mies.), a dymek liczy z tym samym oknem; (7) siatka Mercatora ma dolną krawędź zgodną z liczbą wierszy, a przy bardzo dużych ekranach komórki rosną tylko tyle, ile trzeba; (8) przenikanie mgły nie jest już przerywane przez `dimFog`, brak warstwy „Gdzie otworzyć” nie przełącza na stałe wyboru w panelu, a top-5 „w widoku” zawiera tylko miejsca widoczne na ekranie. Odłożone drobiazgi: powrót do gotowej mapy, gdy środek widoku na żywo wypada poza Polską; dymek po zmianie formularza przed nową odpowiedzią.

## Obserwacja dotycząca czytelności (scenariusz a)

Na mapie całej Polski dla salonów kosmetycznych prawie cały zaludniony kraj jest pomarańczowo-czerwony: stała skala (p5–p99 z res 8) i maksimum z dzieci na res 6 podnoszą typowy kolor (mediana res 6 to 458 przy skali 116–993). Duże miasta nie wygrywają tylko dlatego, że są duże (Huff uwzględnia konkurencję; centrum Wrocławia jest jasne, jasne są też lasy), ale kontrast na poziomie kraju jest umiarkowany — przy przybliżeniu rośnie. Rozważana, odłożona zmiana: osobna stała skala dla każdego poziomu piramidy.

## Weryfikacja w przeglądarce (v3.2)

Wbudowana przeglądarka (okno ok. 800 × 600 oraz emulacja telefonu 375 × 812), serwer na porcie 8001 z prawdziwą bazą. Zrzuty w `docs/screenshots/v32-*.png`. Sprawdzone scenariusze z planu: a) start „Cała Polska” z salonem i kobietami; b) przybliżanie Polska → Dolny Śląsk → Wrocław (przejście gotowa → na żywo; legenda zmienia podpis na „Kolory dopasowane do widoku”, w prawym panelu pojawia się „Podsumowanie obszaru — widoczny obszar”); c) ok. 10 szybkich obrotów kółkiem w obie strony — bez odpowiedzi 4xx/5xx w logu sieci (stare zapytania są anulowane; jedyny wpis 422 w konsoli pochodzi z pierwszego, już poprawionego błędu startowego: mapa miała wymiar 0 px i wysłała pusty prostokąt widoku); d) klik → dymek → „Przeanalizuj to miejsce” → „Wybrane miejsce” z okręgiem; e) bez branży, klienci = nowe domy jednorodzinne (mapa popytu i trendu dla Polski, podpowiedź dla rzemieślników widoczna); f) stary link z `type=paving` (bez błędu, zostaje czynnik popytu); g) telefon. **Nie sprawdzono:** Safari/Firefox, dostępu z drugiego urządzenia (Tailscale).
