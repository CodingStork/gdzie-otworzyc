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
