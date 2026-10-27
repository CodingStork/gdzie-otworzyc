# „Gdzie otworzyć?” v2 — mapa dynamiczna (LOD), zasięg-okrąg, dasymetria — specyfikacja

Data: 2026-10-27. Status: zatwierdzone przez Marcina w rozmowie. Zastępuje sekcje 4, 6 i 7 specyfikacji v1
([2026-10-26-gdzie-otworzyc-design.md](2026-10-26-gdzie-otworzyc-design.md)); reszta v1 (źródła, katalog, hosting) obowiązuje.

## 1. Uwagi użytkownika po testach v1 (powód zmian)

1. Brak trybów z jednym wyborem: sam typ działalności (np. „gdzie są fryzjerzy”) albo sam czynnik popytu („gdzie mieszka dużo seniorów”), oba sterowane suwakiem zasięgu.
2. Mały zasięg klienta daje ostrzejszą, ciekawszą mapę → minimum suwaka **0,1 km**.
3. 5 klas kolorów: w centrum miasta 150 i 800 „klientów na konkurenta” mają ten sam kolor → **płynny gradient**.
4. Heksagony rosną z promieniem obszaru → mają być **zawsze tak drobne, jak pozwalają dane**.
5. Nie wiadomo, czym się różnią Okazja / Popyt / Konkurencja → **wyjaśnienia pod „?”**.
6. Kliknięcie heksagonu czasem stawia pinezkę zamiast pokazać dymek (BŁĄD — przyczyna niżej).

Dodatkowo znalezione przy przeglądzie (Opus):
7. Dymek pokazuje sumy ważone jądrem Gaussa („Konkurenci w zasięgu: 192,3”) — nieinterpretowalne.
8. Po kliknięciu pozycji top-5 animacja `flyTo` zostaje w stanie pośrednim (rozmazane etykiety).
9. Miejsca z top-5 nie są oznaczone na mapie.
10. Liczby „klientów na konkurenta” są zawyżone (OSM ma ~1/3–1/4 firm), UI tego nie mówi.
11. Zablokowana baza (ETL w tle) → „Błąd serwera (500)” zamiast czytelnego komunikatu.

**Przyczyna błędu 6 (zweryfikowana w przeglądarce):** Leaflet z rendererem canvas tworzy osobny `<canvas>` na całą mapę dla KAŻDEGO pane. Pane `poi` (zIndex 460) leży nad `hexes` (410); gdy coś się w nim narysuje (czerwony obrys z top-5 albo punkty firm), jego canvas przechwytuje kliknięcia, nie znajduje pod kursorem obiektu i przekazuje zdarzenie do mapy → nowa pinezka.

## 2. Decyzje

| Temat | Decyzja |
|---|---|
| Obszar analizy | **Widoczny fragment mapy.** Znika suwak promienia, okrąg obszaru, pinezka, checkbox „Cała Polska” i przycisk „Analizuj”. Analiza odświeża się sama po przesunięciu/przybliżeniu mapy i po zmianie formularza. |
| Wielkość heksagonów | **Zależna od przybliżenia (LOD)**: zoom ≤ 6 → res 5, 7–8 → res 6, 9 → res 7, 10–11 → res 8, ≥ 12 → res 9. Przy zmianie poziomu nowa siatka płynnie się pojawia, stara gaśnie (efekt „dzielenia”). |
| Obliczenia | Zawsze na **najdrobniejszej rozdzielczości, na jaką pozwala koszt** (`compute_res` ≥ `display_res`, zwykle 9 albo 8), wynik agregowany do `display_res` średnią ważoną liczbą mieszkańców. |
| „W zasięgu” | **Okrąg o promieniu = zasięg klienta** (klasyczny 2SFCA z progiem odległości), zamiast jądra Gaussa. Liczby są całkowite i sprawdzalne. |
| Wynik okazji | `D / (S + 1)` = **„klientów na firmę po otwarciu Twojej”** (+1 to Ty jako nowy konkurent). |
| Tryby | typ + popyt → warstwy Okazja/Popyt/Konkurencja; tylko typ → Konkurencja; tylko popyt → Popyt. Co najmniej jedno musi być wybrane. |
| Zasięg klienta | Suwak logarytmiczny **0,1–20 km**. Dla czynników z pozwoleń efektywne minimum **1 km** (lokalizacja pozwoleń = środek obrębu). Gdy zasięg < odstęp heksagonów `compute_res`, komunikat „przybliż mapę, by zobaczyć mniejszy zasięg”. |
| Kolory | **Płynny gradient** (ColorBrewer YlGnBu, 9 punktów, interpolacja RGB) wg **percentyla** wartości w pobranym obszarze; legenda = pasek gradientu z wartościami min / 25% / mediana / 75% / 90% / max. |
| Ludność | **Metoda dasymetryczna**: ludność każdej komórki spisu 1 km rozłożona proporcjonalnie do ważonej powierzchni użytkowej budynków mieszkalnych z OSM, do H3 **res 9** (~0,1 km²). Komórki bez budynków → równomiernie (jak v1). |
| Kliknięcie mapy | W dowolnym miejscu (także na heksagonie) → dymek z **dokładnymi liczbami dla klikniętego punktu** w okręgu zasięgu + okrąg na mapie + 5 najbliższych konkurentów z odległościami. Brak osobnej obsługi kliknięć heksagonów. |
| Top-5 | W obrębie widoku; **numerowane znaczniki** na mapie; metryka zależna od trybu. |
| Wyjaśnienia | Ikona „?” przy: warstwach, zasięgu klienta, legendzie (teksty w §5). |
| API | `/api/analyze` usunięte. Nowe: `/api/view` (heatmapa widoku) i `/api/point` (dymek punktu). |

## 3. Dane (ETL)

- **Nowy krok `buildings`**: z `poland-latest.osm.pbf` (17,8 mln dróg z tagiem `building`, przejście ~1 min bez lokalizacji, kilka min z lokalizacjami) dla każdego budynku: środek, powierzchnia rzutu (m²), liczba kondygnacji → **waga = powierzchnia × kondygnacje × współczynnik typu**. Typy (rozkład z PL: `yes` 10,6 mln, `house` 1,5 mln, `outbuilding` 1,1 mln, `detached` 1,0 mln, `farm_auxiliary` 1,0 mln, `residential` 0,9 mln, `garage` 0,2 mln, `apartments` 0,2 mln, `bungalow` 0,15 mln…):
  - współczynnik 1,0: `house, detached, semidetached_house, terrace, bungalow, residential, apartments, farm, dormitory`
  - 0,5: `yes` (nieokreślony — w PL to w większości domy, ale też budynki gospodarcze)
  - 0: wszystko inne
  - kondygnacje: `building:levels` (liczba, przycięta do 1–40); domyślnie `apartments` 5, `residential` 2, pozostałe 1
  - pomijamy rzuty < 20 m² i relacje (multipolygony)
  - wynik: `building_weights(cell_e INTEGER, cell_n INTEGER, h3 VARCHAR, w DOUBLE)` — suma wag per (komórka spisu 1 km w EPSG:3035, heksagon res 9).
- **Ludność res 9**: `hex_pop_r9` = dla każdej komórki spisu wartości × `w(komórka, hex) / Σw(komórka)`; komórki bez wag → próbkowanie równomierne 10×10 punktów. Suma T zachowana (±0,1%). Kolumna pomocnicza w meta/raporcie: % ludności rozłożonej przez budynki (oczekiwane > 90%).
- **Baza agregacji = res 9**: `poi_counts_r9`, `permits_r9` (środek obrębu → res 9); `aggregate` buduje res 8, 7, 6, **5** z res 9. Wszystkie tabele `hex_pop_r*` dostają kolumny `lat, lng` (środek heksagonu) do filtrowania prostokątem.
- `hex_pop_r8` z v1 (rozkład równomierny) zostaje zastąpione agregatem z res 9.

## 4. Backend

### `/api/view`
Parametry: `type` (opcjonalny), `demand` (opcjonalny; co najmniej jeden z nich), `bbox=minLng,minLat,maxLng,maxLat`, `zoom` (int 5–18), `bandwidth_km` (0,1–20), `months` (12/24/36).
1. `display_res` z zoomu (tabela §2). `r` = zasięg (dla pozwoleń ≥ 1 km).
2. `bbox` **przyciągnięty** na zewnątrz do siatki (krok: res 5 → 2°, 6 → 1°, 7 → 0,5°, 8 → 0,25°, 9 → 0,1°) — małe przesunięcia mapy trafiają w cache i kolory nie skaczą.
3. `compute_res` = najdrobniejsza z {9, 8, 7, 6, 5}, nie grubsza niż `display_res`, dla której szacowana liczba komórek obszaru+bufora ≤ 800 tys. i par (komórka, sąsiad w okręgu) ≤ 30 mln.
4. Komórki `compute_res` w prostokącie + bufor `r`; `d_j` (popyt), `s_j` (firmy); `D_i = Σ d_j` i `S_i = Σ s_j` po komórkach o środku w odległości ≤ `r` (cKDTree w EPSG:2180, własna komórka zawsze się liczy).
5. Agregacja do `display_res`: średnia ważona `pop_total` komórek (+ε) dla `score`, `D`, `S` = „wartość dla przeciętnego mieszkańca heksagonu”.
6. Percentyle (0–100) każdej metryki wśród heksagonów z danymi; legenda = kwantyle [0; 0,25; 0,5; 0,75; 0,9; 1].
7. Wynik kroków 2–6 w cache LRU (klucz: parametry + przyciągnięty bbox). Top-5 liczone poza cache dla dokładnego bbox widoku.

### `/api/point`
Parametry: `lat, lng, type?, demand?, bandwidth_km, months`. Dokładne liczby w okręgu `r` wokół punktu: popyt z komórek res 9 (środek ≤ r), firmy z tabeli `poi` po dokładnej odległości punktów, 5 najbliższych firm (nazwa, metry), wynik `D/(S+1)`, okres pozwoleń.

### Błąd zablokowanej bazy
`duckdb.IOException` przy otwieraniu → 503 „Baza danych jest właśnie aktualizowana. Spróbuj ponownie za kilka minut.” (bez zapamiętania zepsutego połączenia).

## 5. Frontend — teksty (dokładnie te)

Pytajnik „Okazja”: **„Ilu potencjalnych klientów przypadnie na jedną firmę, jeśli otworzysz tu swoją: klienci w zasięgu ÷ (konkurenci w zasięgu + 1). Im ciemniejszy kolor, tym lepiej. Porównuj miejsca między sobą — w OpenStreetMap brakuje części firm, więc same liczby są zawyżone.”**

Pytajnik „Popyt”: **„Ilu potencjalnych klientów jest w zasięgu od danego miejsca, np. mieszkańców w promieniu 1,5 km. Liczba mieszkańców to szacunek: dane ze spisu 2021 (kwadraty 1 km) rozłożone na budynki mieszkalne z OpenStreetMap. Dla nowych domów liczymy pozwolenia na budowę z wybranego okresu.”**

Pytajnik „Konkurencja”: **„Ile firm wybranego typu jest w zasięgu od danego miejsca. Dane z OpenStreetMap — mogą być niepełne.”**

Pytajnik „Zasięg klienta”: **„Z jak daleka przychodzą klienci. Fryzjer czy sklep spożywczy: kilkaset metrów do 2 km; market budowlany czy brukarz: 10–20 km. Mały zasięg daje ostrą mapę pokazującą pojedyncze ulice, duży — ogólny obraz okolicy.”**

Pytajnik legendy: **„Kolor pokazuje pozycję miejsca w rankingu widocznego obszaru: najjaśniejszy to najniższe wartości, najciemniejszy — najwyższe. Dokładne liczby zobaczysz po kliknięciu mapy.”**

Dymek punktu (tryb pełny, przykład): „**W promieniu 1,5 km:** ok. 45 300 mieszkańców (szacunek) · 31 fryzjerów w OSM → **ok. 1 416 klientów na firmę** po otwarciu Twojej. Najbliżsi: Salon X — 120 m, …”

Etykiety warstw: „Okazja”, „Popyt”, „Konkurencja”; puste opcje list: „— nie wybieraj —”. Nagłówek top-5 zależny od trybu: „Najlepsze miejsca” / „Największy popyt” / „Najwięcej firm”.

## 6. Ograniczenia do pokazania i opisania
Ludność to szacunek modelowy (dasymetria); pozwolenia z dokładnością do obrębu (stąd min. 1 km); OSM niepełny (liczby porównawczo); kolory są względne dla widoku.
