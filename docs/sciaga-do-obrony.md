# Ściąga do obrony — „Gdzie otworzyć?” (wersja 3)

Prostym językiem: co robi aplikacja, jakie pojęcia z analizy danych przestrzennych w niej występują i **gdzie dokładnie w kodzie** je znaleźć. Każde pojęcie ma 3–6 zdań i wskazanie `plik:funkcja`.

## Jak to działa w jednym akapicie

Wybierasz typ działalności (np. fryzjer) i/lub klientów (np. mieszkańcy), **miejsce** (miejscowość albo klik na mapie), **promień obszaru** (1–30 km) i **zasięg klienta** (z jak daleka przychodzą klienci, 0,1–20 km), po czym klikasz „Pokaż mapę”. Dla okręgu wokół miejsca serwer liczy **powierzchnię ciągłą** na regularnej siatce (w metrach, EPSG:2180). Główna mapa **„Gdzie otworzyć”** pokazuje **szacowaną liczbę klientów nowej firmy** wg **modelu Huffa**; druga, **„Gdzie są klienci”**, pokazuje dostępny popyt. Kolor to żółto-czerwona „mgła” w skali logarytmicznej (małe wartości przezroczyste). Ruch mapy niczego nie przelicza; **kliknięcie** pokazuje szczegóły: okrąg zasięgu, drobne heksagony z ludnością, konkurentów i liczby. Dane (ludność ze spisu rozłożona na budynki OSM, firmy z OSM, pozwolenia z GUNB) przetwarzamy **raz** do bazy DuckDB (ETL).

Wzór: `E(g) = Σ_i d_i · f(d_ig) / (f(d_ig) + C_i + A0)`, `f(d) = exp(−d / zasięg)`, `C_i = Σ_k f(d_ik)`, `A0 = exp(−1)`.

---

## 1. Układy współrzędnych (EPSG 4326 / 3035 / 2180)

Układ współrzędnych mówi, jak liczby opisują miejsce na Ziemi. **EPSG:4326 (WGS84)** to stopnie szerokości i długości geograficznej — tak mówią OSM, ULDK i H3. **EPSG:3035 (ETRS89-LAEA)** to europejski układ w metrach, w którym Eurostat publikuje siatkę spisu (kwadraty 1 km × 1 km). **EPSG:2180 (PUWG 1992)** to polski układ metryczny. Odległości liczymy w metrach (2180), bo stopień długości geograficznej ma inną długość w Polsce niż na równiku — odległość „na stopniach” byłaby zniekształcona.
- Spis 3035 → 4326: `etl/population.py:cells_to_hex` (`Transformer.from_crs(3035, 4326)`).
- Budynki 4326 → 3035 (przypisanie do komórki spisu): `etl/buildings.py:build_building_weights`.
- 4326 → metry do odległości: `backend/app/analysis/kernel.py:LocalFrame` (lokalny układ wokół wybranego miejsca, osie na północ/wschód — siatka mgły musi być wyrównana do południków, bo w EPSG:2180 byłaby obrócona nawet o ok. 4°) oraz `to_metric` (EPSG:2180).

## 2. Siatka H3 jako magazyn danych (a nie sposób rysowania)

H3 (Uber) dzieli Ziemię na heksagony w wielu rozdzielczościach; każdy ma 6 równo oddalonych sąsiadów, a rozdzielczości są **hierarchiczne** (heksagon ma „rodzica” poziom wyżej). W bazie trzymamy ludność, firmy i pozwolenia w res 9 (~0,3 km między środkami) do res 5. W v3 heksagony **nie są już główną mapą** — służą jako źródła popytu w obliczeniach (res 9 dla zasięgu ≤ 2 km, res 8 do 8 km, res 7 powyżej, żeby było szybko) i jako drobne komórki pokazywane po kliknięciu. Mapę rysujemy jako powierzchnię ciągłą (punkt 6).
- Dobór rozdzielczości źródeł: `backend/app/analysis/service.py:demand_res`; agregacja w bazie: `etl/aggregate.py:build_aggregates` (funkcja SQL `h3_parent`).

## 3. MAUP (problem modyfikowalnej jednostki przestrzennej)

Wynik analizy zależy od tego, jak potniemy mapę na jednostki: te same dane w granicach gmin, powiatów czy heksagonów dadzą różne obrazy. Dlatego nie liczymy „na gminę”. Wartość w każdym punkcie siatki to suma po **wszystkich** źródłach w okolicy z wagą malejącą z odległością, więc nie zależy od tego, gdzie leży granica komórki. Siatka obliczeniowa (krok ok. promień/90, 50–300 m, do ok. 31 tys. punktów) jest tylko próbkowaniem gładkiej powierzchni, a obraz jest dodatkowo interpolowany.
- `backend/app/analysis/surface.py:make_grid`, `huff_and_potential`.

## 4. Interpolacja powierzchniowa i **metoda dasymetryczna**

Spis podaje ludność w kwadratach 1 km, a my potrzebujemy jej w heksagonach res 9 (~0,1 km²). **Interpolacja powierzchniowa** dzieli kwadrat na siatkę punktów i rozkłada ludność równomiernie. To uproszczenie: w rzeczywistości ludzie mieszkają w domach, nie w lesie.

**Metoda dasymetryczna** (dasymetric mapping) poprawia to: ludność kwadratu rozkładamy **proporcjonalnie do wagi budynków mieszkalnych** z OpenStreetMap w każdym heksagonie. Waga budynku = powierzchnia rzutu × liczba kondygnacji × współczynnik typu (dom/blok = 1, `building=yes` = 0,5, garaż/stodoła = 0). Powierzchnia × kondygnacje przybliża powierzchnię użytkową, czyli „ile ludzi się tu zmieści”. Dzięki temu heksagon z blokami dostaje dużo mieszkańców, a pole obok — nic. Suma ludności w kwadracie jest zachowana (kontrola ±0,1%).

Ograniczenia: to wciąż szacunek (nie znamy liczby mieszkań w budynku); OSM może nie mieć budynków w części wsi — wtedy kwadrat rozkładamy równomiernie (jak w v1). Udział ludności rozłożonej przez budynki zapisujemy w `meta` i sprawdzamy w kontroli jakości (≥ 85%).
- `etl/buildings.py` (`building_factor`, `levels`, `polygon_area_m2`, `build_building_weights`), `etl/population.py:dasymetric_to_hex`, `build_hex_pop`.

## 5. Model Huffa (Huff 1963) — „Gdzie otworzyć”

Pytanie: ilu klientów zdobyłaby **nowa** firma postawiona w danym miejscu? Każdy mieszkaniec (komórka spisu *i* z `d_i` osobami) wybiera między wszystkimi firmami; im bliżej firma, tym większa szansa. „Siła” firmy w odległości *d* to `f(d) = exp(−d/zasięg)`. Dla mieszkańca *i* siła istniejących konkurentów to `C_i = Σ_k f(d_ik)`. Szansa, że wybierze nową firmę w punkcie *g*: `f(d_ig) / (f(d_ig) + C_i + A0)`. Szacowana liczba klientów: `E(g) = Σ_i d_i · (ta szansa)`.

**Opcja zewnętrzna `A0 = exp(−1)`** to „inne możliwości”: firmy, których nie ma w OSM (OSM jest niekompletny), zakupy gdzie indziej, rezygnacja z usługi. Odpowiada jednemu konkurentowi w odległości równej zasięgowi klienta. Bez niej w miejscu bez konkurencji nowa firma dostawałaby 100% mieszkańców w zasięgu, a dzielenie przez zero byłoby możliwe, gdyby `f` było równe 0 — z `A0` mianownik jest zawsze > 0 (konkurent dokładnie w punkcie *g* też nie psuje obliczeń). Intuicja: dużo ludzi i mało konkurentów w ich pobliżu = dużo klientów. Model jest klasykiem analiz lokalizacji (np. ArcGIS Business Analyst).
- `backend/app/analysis/surface.py:huff_and_potential`, stała `A0`; testy `tests/test_surface_core.py` (`test_huff_no_competitors`, `test_huff_competitor_reduces`).

## 6. Powierzchnia ciągła (izopleta) zamiast heksagonów/choropletu — i dlaczego nie Leaflet.heat

Wartości, które zmieniają się płynnie (dostępność klientów), lepiej pokazać jako **powierzchnię ciągłą** (kolor zmienia się płynnie, jak na mapie izoplet/warstwic) niż jako **choropleta** (mapa kolorowanych jednostek — gmin, heksagonów, wprowadzająca sztuczne granice i efekt MAUP). Serwer liczy wartości na regularnej siatce, przeglądarka **interpoluje wartości** (smoothstep, ×4) i dopiero potem koloruje piksele — dzięki temu nie ma widocznych kwadratów siatki ani ciemnych obwódek. Drobne komórki (heksagony) pokazujemy dopiero po kliknięciu, jako szczegóły.

**Dlaczego nie gotowa wtyczka Leaflet.heat?** Sumuje punkty w pikselach ekranu, więc obraz zależy od przybliżenia i nie odpowiada liczbom — nasza mgła jest policzona w metrach i ma legendę z prawdziwymi wartościami.
- `frontend/js/map.js:renderFog`; siatka: `backend/app/analysis/surface.py:make_grid`.

## 7. Shneiderman (1996): przegląd → zawężenie → szczegóły na żądanie

Zasada projektowania wizualizacji „overview first, zoom and filter, then details-on-demand”. W aplikacji: **zawężenie** to wybór branży, klientów, miejsca i promienia (serwer liczy tylko okolicę, ruch mapy niczego nie przelicza), **przegląd** to mgła w okręgu z top-5, a **szczegóły na żądanie** to klik w mapę: okrąg zasięgu, drobne heksagony z ludnością, konkurenci i dymek z liczbami. Wcześniejsza wersja (v2) liczyła cały widok przy każdym ruchu mapy i miała kilka warstw naraz — trudną do odczytania.
- `frontend/js/app.js` (przepływ `run`, `showPointAt`).

## 8. Kolor: dlaczego nie tęcza, dlaczego log, dlaczego przezroczystość

- **Nie tęcza:** do wartości rosnących w jedną stronę używa się skali **sekwencyjnej jednobarwnej** (ColorBrewer **YlOrRd**: żółty → pomarańczowy → czerwony — Brewer; Borland & Taylor 2007: tęcza wprowadza fałszywe granice i nie ma naturalnej kolejności). Czerwony = „więcej / lepiej”.
- **Skala logarytmiczna:** ludność i liczba firm mają rozkład prawostronnie skośny, więc skala liniowa zrobiłaby z miasta jedną czerwoną plamę. `t = (log10(v) − log10(lo)) / (log10(hi) − log10(lo))`, `lo` = 5. percentyl, `hi` = 99. percentyl wartości dodatnich w okręgu. Każdy krok koloru to mniej więcej podwojenie wartości. Percentyl rankingowy odrzuciliśmy już w v2.1: ściska ogon rozkładu.
- **Przezroczystość:** α = 0 dla `t < 0,05`, rośnie do 0,85 przy `t = 0,5`; małe wartości znikają, zostaje efekt „mgły” i widać podkład (etykiety miast leżą nad mgłą).
- Kolory są względne dla okręgu — dokładne liczby pokazują legenda (okrągłe wartości) i dymek. Przykład problemu normalizacji w mapach: xkcd 1138 („to tylko mapa ludności”) — dlatego główna mapa pokazuje odpowiedź na pytanie użytkownika (ilu klientów), a nie surowy popyt.
- `frontend/js/colors.js` (`fogColor`, `logScale`, `niceLogTicks`).

## 9. Zasięg klienta i rozpad wykładniczy

W v2 używaliśmy twardego okręgu (2SFCA), w v3 **gładkiego rozpadu**: `f(d) = exp(−d/zasięg)`. Przy odległości równej zasięgowi chęć dotarcia spada do ok. 37% (o ok. 2/3), przy dwukrotnie większej do ok. 14% (o ok. 85%). Wpływ obcinamy dla `d > 4·zasięg` (poniżej 2%), żeby obliczenia były szybkie. Zasięg to jedyny parametr, który użytkownik rozumie („jak daleko klient dojdzie”); typowe wartości są w katalogu (`bandwidth_km`). Dla pozwoleń zasięg to co najmniej 1 km (lokalizacja pozwoleń to środek obrębu).
- `backend/app/analysis/surface.py:decay`; `backend/app/catalog.py` (pole `bandwidth_km`).

## 10. Efekt krawędzi i bufor

Źródła spoza okręgu też wpływają na punkty przy brzegu. Dlatego wczytujemy popyt z buforem `4·zasięg` wokół okręgu, a konkurentów z buforem `8·zasięg` (żeby dostępność konkurencji `C_i` była poprawna także dla źródeł z bufora). Morze i teren za granicą nie mają danych: mgła tam jest przezroczysta, a top-5 wybiera tylko miejsca z wartościami > 0 (test `test_surface_sea_edge`).
- `backend/app/analysis/service.py:run_surface` (zmienne `_box(..., radius + 4·zasięg)`).

## 11. Geokodowanie: działka → obręb → punkt

Pozwolenie na budowę ma numer działki, ale działek są miliony, a serwis GUGiK (ULDK) odpowiada ~0,35 s na zapytanie. Dlatego sumujemy pozwolenia do **obrębów ewidencyjnych** (jednostek ~kilkudziesięciu tysięcy w Polsce, np. `160602_4.0038`), pobieramy kształt obrębu z ULDK i jako jego położenie bierzemy `representative_point()` — punkt zawsze leżący *wewnątrz* kształtu (zwykły środek ciężkości bywa poza figurą wklęsłą). Dokładność to obręb: w mieście osiedle, na wsi cała wieś — stąd minimalny zasięg 1 km dla popytu z pozwoleń. Gdy obrębu nie ma w ULDK, używamy środka gminy. Wyniki zapisujemy w tabeli-cache `obreb_geom`, więc przerwany ETL można wznowić.
- `etl/permits.py:normalize_obreb_id`, `etl/geocode_obreby.py:UldkClient`, `wkt_to_latlng`, `geocode_missing`, `build_permits_hex`.

## 12. Kompletność danych VGI (OpenStreetMap)

OSM jest tworzony przez wolontariuszy (VGI — volunteered geographic information), więc jest **niekompletny**, zwłaszcza dla małych usług: w całej Polsce jest ok. 10 tys. fryzjerów w OSM, a realnie ok. 3–4 razy więcej. Wynik „mało konkurencji” może więc znaczyć „mało wpisanych do OSM”, a same liczby „klientów na firmę” są zawyżone — dlatego mapę czytamy porównawczo (które miejsce jest lepsze), nie absolutnie. Każdy typ ma ocenę `osm_quality` (good/medium/poor), a dla `poor` aplikacja ostrzega, że to głównie mapa popytu. Docelowo drugim źródłem konkurencji byłby rejestr CEIDG.
- `backend/app/catalog.py` (`osm_quality`, `POOR_WARNING`), `etl/osm_poi.py:extract`.

## 13. Dlaczego pozwolenie na budowę ≠ dom

Pozwolenie to zamiar: budowa trwa 1–3 lata, a część pozwoleń nigdy nie jest zrealizowana. Wiemy też tylko, że dom ma powstać w danym obrębie — nie wiemy dokładnie gdzie. Dlatego „nowe domy” traktujemy jako **wskaźnik kierunku rozwoju** okolicy (przydatny np. dla brukarza), nie jako dokładną liczbę domów. W aplikacji pod legendą jest o tym przypomnienie, a okno czasowe (12/24/36 miesięcy) liczymy od najnowszych danych w rejestrze. Z rejestru wykluczamy „zmiany pozwoleń”, żeby nie liczyć tego samego domu dwa razy.
- `etl/permits.py:parse_permits`, `backend/app/analysis/service.py:_permit_window`.

## 14. Jak działa top-5 (non-maximum suppression)

Biorąc po prostu 5 punktów siatki o najwyższej wartości, dostalibyśmy 5 sąsiadów z tego samego skupiska. Dlatego wybieramy zachłannie od najlepszego i **odrzucamy punkty bliższe niż** `max(zasięg, promień/5)` od już wybranych (non-maximum suppression). Top-5 dotyczy tylko okręgu i aktywnej mapy; nazwa miejsca to najbliższe osiedle/wieś w promieniu 3 km (osiedle ma pierwszeństwo przed miastem).
- `backend/app/analysis/surface.py:top_points`, `service.py:nearest_place_name`.

## 15. Szczegóły punktu: dokładne liczby

Powierzchnia jest policzona na siatce i zaokrąglona, więc po kliknięciu backend liczy **dokładnie** dla klikniętego punktu: popyt z komórek res 9, których środek leży w okręgu zasięgu, firmy z tabeli `poi` po rzeczywistej odległości (haversine), 5 najbliższych firm oraz **ten sam wzór Huffa** dla jednego punktu („Otwierając tu, zdobyłbyś ok. X klientów”). Na mapie rysuje się okrąg zasięgu, drobne heksagony z ludnością (do zasięgu 3 km) i konkurenci; zamknięcie dymku to wszystko usuwa.
- `backend/app/analysis/service.py:point_details`, `_expected_at`.

---

## Pytania, które może zadać prowadzący

**1. Dlaczego heksagony, a nie kwadraty albo gminy — i czemu w v3 już ich nie widać na mapie?**
Heksagon ma sześciu równo oddalonych sąsiadów i jest hierarchiczny, więc dobrze nadaje się do **przechowywania** danych (ludność, firmy). Ale wartości zmieniające się płynnie lepiej pokazać jako powierzchnię ciągłą (izopleta): sztuczne granice komórek sugerują skoki, których nie ma, i wprowadzają MAUP. Heksagony pokazuję dopiero po kliknięciu, jako szczegóły.

**2. Co to jest model Huffa i skąd wiesz, że wynik ma sens?**
To klasyczny model wyboru firmy (Huff 1963): szansa wyboru zależy od odległości do firmy i do konkurentów. Wynik `E` to szacowana liczba klientów nowej firmy w danym miejscu. Nie twierdzę, że to prognoza zysku — to ranking miejsc, który trzeba zestawić z lokalną wiedzą. Walidacją są testy z ręcznie policzonymi wartościami (brak konkurencji, konkurent w tym samym punkcie) oraz zgodność liczby z mapy z liczbą w dymku.

**3. Co to jest opcja zewnętrzna `A0` i po co jest?**
To „inne możliwości”: firmy spoza OSM, zakupy gdzie indziej, rezygnacja. `A0 = exp(−1)` odpowiada jednemu konkurentowi w odległości równej zasięgowi. Bez niej w miejscu bez konkurencji nowa firma brałaby wszystkich w zasięgu, a OSM jest niekompletny — `A0` częściowo to koryguje i zapewnia, że mianownik nie jest zerem.

**4. Dlaczego odległości liczysz w EPSG:2180, a nie w stopniach?**
Bo stopnie nie są jednostką długości: 1° długości geograficznej to ok. 68 km na 52°N, a 1° szerokości ok. 111 km. EPSG:2180 jest metryczny i dopasowany do Polski; w nim leży cała siatka obliczeniowa.

**5. Co to jest zasięg klienta i dlaczego rozpad wykładniczy?**
To odległość, z której typowy klient jest gotów dotrzeć (fryzjer: 1,5 km, market budowlany: 15 km). `f(d) = exp(−d/zasięg)`: przy odległości równej zasięgowi chęć dotarcia spada o ok. 2/3, przy podwójnej o ok. 85%. Jest gładki (bez skoku na granicy okręgu jak w v2) i ma jeden zrozumiały parametr.

**6. Jak z kwadratów 1 km zrobiłeś heksagony i skąd wiesz, gdzie mieszkają ludzie?**
Metodą dasymetryczną: ludność każdego kwadratu rozkładam na heksagony res 9 proporcjonalnie do wagi budynków mieszkalnych z OSM (powierzchnia × kondygnacje × współczynnik typu). Gdzie OSM nie ma budynków, rozkładam równomiernie. Suma jest zachowana (kontrola ±0,1%). To szacunek — i tak to opisuję w interfejsie.

**7. Czy dane z OpenStreetMap są wystarczające?**
Nie dla wszystkich branż — OSM jest niekompletny dla małych usług, więc mapę trzeba czytać porównawczo. Typy mają ocenę jakości, a dla „poor” ostrzegam, że to głównie mapa popytu. `A0` częściowo to kompensuje. Rozwiązaniem byłby rejestr CEIDG (kody PKD są już w katalogu), ale wymaga tokenu.

**8. Jak geokodujesz pozwolenia na budowę?**
Nie działki (to miliony zapytań), tylko obręby ewidencyjne przez ULDK GUGiK: pobieram kształt obrębu i biorę punkt reprezentatywny leżący wewnątrz. Wyniki są w cache (`obreb_geom`), a gdy obrębu brak, używam środka gminy. Dokładność = obręb, dlatego dla nowych domów zasięg wynosi co najmniej 1 km.

**9. Dlaczego skala logarytmiczna, żółto-czerwona paleta i przezroczystość — a nie tęcza?**
Rozkłady są skośne, więc skala liniowa zalałaby mapę jednym kolorem; logarytm zachowuje proporcje (krok koloru ≈ podwojenie wartości). Paleta jednobarwna (YlOrRd) czyta się jako „więcej”, a tęcza (Borland & Taylor 2007) wprowadza fałszywe granice. Przezroczystość pozwala małym wartościom „zniknąć”, a etykiety miast zostają czytelne.

**10. Jak zapewniłeś, że wyniki są szybkie?**
Dane są przetwarzane raz (ETL → DuckDB). Zapytanie dotyczy tylko okręgu (≤ 30 km), siatka ma 25–31 tys. punktów w okręgu, pary (punkt, źródło) znajduje drzewo cKDTree porcjami po 2 000 punktów, a obie warstwy („Gdzie otworzyć” i „Gdzie są klienci”) liczone są w jednym przebiegu. Przy dużym zasięgu źródła popytu są grubsze (res 8/7). Czasy: 0,4–3,2 s (patrz `docs/raport-etl.md`, sekcja v3), a ostatnie wyniki są w pamięci podręcznej (LRU 32). Ruch mapy w ogóle nie wysyła zapytań.

**11. Dlaczego przepływ „miejsce + promień → mapa → klik”?**
Zasada Shneidermana (1996): przegląd → zawężenie → szczegóły na żądanie. Wcześniejszy dynamiczny widok całej mapy był męczący i trudny do odczytania; teraz użytkownik zawęża zadanie, widzi okolicę, a liczby poznaje dopiero po kliknięciu.

*Bonus — jak odtworzyć bazę?* `uv sync`, potem `uv run python -m etl.run_all` (kilka godzin: najdłużej pobieranie OSM, budynki i geokodowanie obrębów), a na końcu `start.bat`.
