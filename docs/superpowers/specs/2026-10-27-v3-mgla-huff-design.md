# „Gdzie otworzyć?” v3 — miejsce + promień, mgła (powierzchnia ciągła), model Huffa — specyfikacja

Data: 2026-10-27. Status: zatwierdzone przez Marcina. Zastępuje sposób prezentacji i analizy z v2/v2.1
([v2](2026-10-27-widok-dynamiczny-design.md)); dane i ETL v2 (ludność dasymetryczna res 9, POI, pozwolenia) zostają bez zmian.

## 1. Dlaczego (uwagi Marcina po v2.1 + research)

Marcin: ciągłe przeliczanie całej Polski przy ruchu mapy jest niewygodne; woli: wpisuję miejsce, podaję promień, dostaję dokładną mapę.
Heksagony mu się nie podobają → „prawdziwa heatmapa” do czerwonego, w formie mgły; szczegóły (heksagony/okręgi, skala) dopiero po kliknięciu.
Przełącznik „Konkurencja” nikogo nie interesuje. Nazwy „Popyt”/„Okazja” bez pytajników są niezrozumiałe.

Zasady z literatury, które stosujemy (do README i ściągi):
- **Shneiderman (1996) „The Eyes Have It”: overview first, zoom and filter, then details-on-demand** → przepływ: wybór miejsca i promienia (zawężenie) → mapa okolicy → klik = szczegóły.
- **Mapy „to tylko mapa ludności” (xkcd 1138)** → główna mapa nie pokazuje surowego popytu, tylko odpowiedź na pytanie użytkownika (ilu klientów zdobędzie).
- **Model Huffa (Huff 1963; ArcGIS Business Analyst)** — prawdopodobieństwo wyboru firmy zależy od odległości do niej i do konkurentów → „szacowana liczba Twoich klientów”.
- **Mapa izoplet / powierzchnia ciągła** (kształty z danych, nie z siatki) zamiast choropletu/hexbinu do wartości zmieniających się płynnie; precyzyjne komórki tylko na żądanie.
- **Kolor: sekwencyjna skala jednokierunkowa (ColorBrewer YlOrRd), nie tęcza** (Borland & Taylor 2007); skala **logarytmiczna** dla rozkładów skośnych; niskie wartości przezroczyste (efekt mgły).
- Odrzucone: mapa dwuwymiarowa (bivariate) — trudna w odczycie; gotowe wtyczki heatmap (Leaflet.heat) — sumują punkty w pikselach ekranu, obraz zależy od przybliżenia i nie odpowiada liczbom.

## 2. Przepływ i interfejs

1. **Start:** pusta mapa Polski (bez kolorów) + karta instrukcji: „1. Wybierz branżę (i/lub klientów). 2. Wpisz miejscowość albo kliknij mapę. 3. Ustaw promień i kliknij »Pokaż mapę«.”
2. Panel: **Typ działalności**, **Twoi klienci to** (czynnik popytu; opcja „— nie wybieraj —” w obu), **Zasięg klienta** (suwak log 0,1–20 km, jak v2.1), **Miejsce** (wyszukiwarka + „albo kliknij mapę”), **Promień obszaru** (suwak 1–30 km, domyślnie 10), przycisk **„Pokaż mapę”**.
3. Po „Pokaż mapę”: mapa dopasowuje się do okręgu; poza okręgiem przygaszenie (ciemny półprzezroczysty welon z „dziurą” w okręgu); w okręgu **mgła** żółty → pomarańczowy → czerwony. Ruch mapy NICZEGO nie przelicza. Zmiana list/suwaków przy ustawionym miejscu → automatyczne przeliczenie (debounce 300 ms). Klik w mapę przed „Pokaż mapę” ustawia miejsce.
4. **Warstwy** (zamiast Okazja/Popyt/Konkurencja):
   - typ + klienci → przełącznik dwóch opcji: **„Gdzie otworzyć”** (domyślna) i **„Gdzie są klienci”**;
   - tylko typ → jedna mapa **„Gdzie są {firmy}”** (np. „Gdzie są fryzjerzy”), bez przełącznika;
   - tylko klienci → jedna mapa **„Gdzie są klienci”**, bez przełącznika.
5. **Legenda:** tytuł („Szacowana liczba Twoich klientów” / „Dostępni klienci: {czynnik}” / „Zagęszczenie: {typ}”), pasek gradientu z przezroczystością, podpisy w okrągłych wartościach log (jak v2.1), pytajnik.
6. **Klik w mapę (po wyliczeniu) = szczegóły na żądanie:** okrąg zasięgu klienta wokół punktu, w nim drobne heksagony res 9 pokolorowane liczbą mieszkańców (szara skala, cienkie) i znaczniki konkurentów; dymek z liczbami (§4). Zamknięcie dymku usuwa szczegóły.
7. **Top-5** (tylko w okręgu, numerowane znaczniki, lista w panelu z wartością) dla aktywnej mapy.
8. Hash: `type, demand, reach, m, layer, lat, lng, r`.

## 3. Analiza (`/api/surface`)

Parametry: `type?`, `demand?` (co najmniej jeden), `lat, lng` (w Polsce), `radius_km` 1–30, `reach_km` 0,1–20 (dla pozwoleń efektywnie ≥ 1), `months`.

- **Siatka obliczeniowa:** regularna w EPSG:2180 pokrywająca okrąg; krok `cell_m = clamp(radius_m / 150, 50, 300)` (≤ ~23 tys. punktów w okręgu); punkty poza okręgiem = brak wartości.
- **Funkcja odległości (rozpad):** `f(d) = exp(−d / reach)`, obcięta dla `d > 4·reach`.
- **Źródła:** popyt `d_i` z `hex_pop_r9` (środki komórek; dla `reach > 2 km` z `hex_pop_r8`, dla `> 8 km` z `r7`) albo `permits_r9..` w oknie; konkurenci = punkty `poi` danego typu (dokładne położenia). Zakres: okrąg + bufor `4·reach`.
- **Gdzie otworzyć (model Huffa z opcją zewnętrzną):** dla każdego źródła popytu `C_i = Σ_k f(d_ik)` (dostępność konkurencji), `A0 = exp(−1)` — „inne możliwości” (firmy spoza OSM, zakupy gdzie indziej; odpowiada konkurentowi w odległości równej zasięgowi). Dla punktu siatki `g` (hipotetyczna nowa firma): **`E(g) = Σ_i d_i · f(d_ig) / (f(d_ig) + C_i + A0)`** = szacowana liczba klientów.
- **Gdzie są klienci:** `P(g) = Σ_i d_i · f(d_ig)`.
- **Gdzie są {firmy}:** `K(g) = Σ_k f(d_kg)`.
- **Top-5:** maksima siatki z separacją `max(reach, radius/5)` (non-maximum suppression), nazwy jak v1 (`nearest_place_name`).
- **Odpowiedź:** `{"layers": ["open","demand"] | ["demand"] | ["competition"], "grid": {"west","south","east","north","nx","ny","cell_m"}, "values": {"open": [...], "demand": [...], "competition": [...]}` (tablice nx·ny, wiersze od północy, `null` poza okręgiem, wartości zaokrąglone do 2 cyfr znaczących), `"top": {"open": [...], ...}` (`{lat,lng,name,value}`), `"notes"`, `"warnings"`, `"permits_period"?`}. Siatkę zwracamy w EPSG:4326 jako prostokąt (bounds) — przy 30 km zniekształcenie rzutu jest pomijalne dla wizualizacji.
- Wydajność: obliczenia blokami po ~2 000 punktów siatki (cKDTree `query_ball_point`); cel: promień 10 km / zasięg 2 km < 3 s; LRU cache (klucz = parametry zaokrąglone: lat/lng 4 miejsca, promień 0,5 km, zasięg 0,1 km).

## 4. Szczegóły punktu (`/api/point`, przebudowa)

Dla klikniętego punktu i zasięgu `reach`: liczby w **okręgu o promieniu = zasięg** (proste, sprawdzalne): mieszkańcy/klienci (szacunek), liczba firm, 5 najbliższych firm z odległością; do tego `E` (Huff) dla tego punktu i komórki res 9 w okręgu (`[h3, pop_total]`) do narysowania. Dymek (tryb pełny): „**W promieniu 2 km:** ok. 8 000 mieszkańców (szacunek) · 3 fryzjerów w OSM. **Otwierając tu, zdobyłbyś ok. 1 900 klientów** (model Huffa). Najbliżsi: …”.

## 5. Teksty pytajników (dosłownie)

- **Gdzie otworzyć:** „Ilu klientów mogłaby przyciągnąć nowa firma w danym miejscu. Liczymy to modelem Huffa: każdy mieszkaniec wybiera między firmami, a bliższa firma przyciąga go mocniej. Uwzględniamy wszystkich konkurentów z OpenStreetMap i »inne możliwości« (firmy, których nie ma w OSM, zakupy gdzie indziej). Najbardziej czerwone miejsca to najlepsze lokalizacje.”
- **Gdzie są klienci:** „Ilu potencjalnych klientów jest w pobliżu danego miejsca — bliżsi liczą się bardziej. Mieszkańcy to szacunek: spis 2021 rozłożony na budynki mieszkalne z OpenStreetMap. Dla nowych domów liczymy pozwolenia na budowę z wybranego okresu.”
- **Gdzie są {firmy}:** „Gdzie jest najwięcej firm wybranego typu. Dane z OpenStreetMap — mogą być niepełne.”
- **Zasięg klienta:** „Jak daleko typowy klient jest gotów dojść lub dojechać. Fryzjer, sklep spożywczy: kilkaset metrów do 2 km; market budowlany, brukarz: 10–20 km. W tej odległości chęć dotarcia spada o ok. 2/3, a dwa razy dalej — o ok. 85%.”
- **Promień obszaru:** „Jak duży obszar wokół wybranego miejsca przeanalizować. Mniejszy obszar = szybciej i dokładniej.”
- **Legenda:** „Kolor w skali logarytmicznej: każdy krok koloru to mniej więcej podwojenie wartości. Przezroczyste miejsca mają bardzo małe wartości. Dokładne liczby zobaczysz po kliknięciu mapy.”

## 6. Rysowanie mgły
Wartości siatki → kolor: log, `lo` = percentyl 5 wartości > 0 w okręgu, `hi` = percentyl 99; paleta **YlOrRd** 9 (`#ffffcc,#ffeda0,#fed976,#feb24c,#fd8d3c,#fc4e2a,#e31a1c,#bd0026,#800026`); **przezroczystość** α = 0 dla t < 0,05, potem liniowo do 0,85 przy t = 0,5 i 0,85 powyżej; × suwak przezroczystości. Rysowane na `<canvas>` w rozdzielczości siatki, powiększone ×4 z wygładzaniem (bilinear) i lekkim rozmyciem (`filter: blur(…)` ~1 komórka), podane jako `L.imageOverlay` w pane nad podkładem i pod etykietami. Okrąg obszaru i welon — SVG, nieinteraktywne.

## 7. Usuwane
`/api/view`, poziomy szczegółowości (LOD), heksagony jako główna warstwa, przełącznik „Konkurencja”, auto-przeliczanie przy ruchu mapy. Tabele i ETL bez zmian.
