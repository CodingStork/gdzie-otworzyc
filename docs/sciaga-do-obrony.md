# Ściąga do obrony — „Gdzie otworzyć?”

Prostym językiem: co robi aplikacja, jakie pojęcia z analizy danych przestrzennych w niej występują i **gdzie dokładnie w kodzie** je znaleźć. Każde pojęcie ma 3–6 zdań i wskazanie `plik:funkcja`.

## Jak to działa w jednym akapicie

Wybierasz typ działalności (np. salon kosmetyczny), czynnik popytu (np. liczba kobiet) i miejsce na mapie. Aplikacja liczy dla każdego heksagonu siatki H3 wynik **„klienci na 1 konkurenta”**: sumę potencjalnych klientów w pobliżu (z wagą malejącą z odległością) podzieloną przez liczbę konkurentów w pobliżu (liczoną tak samo) powiększoną o 1. Dane (ludność ze spisu, firmy z OpenStreetMap, pozwolenia na budowę z GUNB) przetwarzamy **raz** do jednej bazy DuckDB (ETL), więc odpowiedź na kliknięcie to ułamek sekundy.

Wzór: `score = D / (S + 1)`, gdzie `D = Σ d_j · K(odległość_ij)`, `S = Σ s_j · K(odległość_ij)`, `K(d) = exp(−d² / 2h²)`.

---

## 1. Układy współrzędnych (EPSG 4326 / 3035 / 2180)

Układ współrzędnych mówi, jak liczby opisują miejsce na Ziemi. **EPSG:4326 (WGS84)** to stopnie szerokości i długości geograficznej — tak mówią OSM, ULDK i H3. **EPSG:3035 (ETRS89-LAEA)** to europejski układ w metrach, w którym Eurostat publikuje siatkę spisu (kwadraty 1 km × 1 km). **EPSG:2180 (PUWG 1992)** to polski układ metryczny. Odległości liczymy w metrach (2180), bo stopień długości geograficznej ma inną długość w Polsce niż na równiku — odległość „na stopniach” byłaby zniekształcona.
- Spis 3035 → 4326: `etl/population.py:cells_to_hex` (`Transformer.from_crs(3035, 4326)`).
- 4326 → 2180 do odległości: `backend/app/analysis/kernel.py:to_metric`.

## 2. Siatka H3 i dlaczego heksagony

H3 (Uber) dzieli Ziemię na heksagony w wielu rozdzielczościach. Każdy heksagon ma 6 sąsiadów w **tej samej odległości** (w kwadratach sąsiedzi po przekątnej są dalej), więc „zasięg” wygląda naturalnie. Rozdzielczości są hierarchiczne: heksagon ma jednego „rodzica” poziom wyżej, więc zbiorcze tabele (res 7, res 6) to zwykłe sumowanie. Używamy: res 8 (~0,8 km między środkami) dla obszarów do 15 km, res 7 (~2,1 km) do 50 km i res 6 (~5,6 km) dla całej Polski. Identyfikator H3 trzymamy jako tekst (zgodny z biblioteką w przeglądarce).
- Wybór rozdzielczości: `backend/app/analysis/resolution.py:choose_resolution`.
- Agregacja do rodziców: `etl/aggregate.py:build_aggregates` (funkcja SQL `h3_parent`).

## 3. MAUP (problem modyfikowalnej jednostki przestrzennej)

Wynik analizy zależy od tego, jak potniemy mapę na jednostki: te same dane w granicach gmin, powiatów czy heksagonów dadzą różne obrazy. Dlatego nie liczymy wskaźnika „na gminę”, tylko na jednolitej siatce H3 z **gładkim jądrem** (każdy heksagon „patrzy” na okolicę, a nie tylko na siebie). Dodatkowo szerokość jądra nie może być mniejsza niż ok. 0,6 odstępu heksagonów, żeby wynik nie zależał od przypadkowego położenia siatki.
- `backend/app/analysis/resolution.py:effective_bandwidth_km`.

## 4. Interpolacja powierzchniowa (areal interpolation)

Spis podaje ludność w kwadratach 1 km, a my potrzebujemy jej w heksagonach, które z kwadratami się nie pokrywają. Każdy kwadrat dzielimy na siatkę 5 × 5 punktów (co 200 m), każdy punkt dostaje 1/25 ludności kwadratu i trafia do heksagonu, w którym leży. Zakładamy więc, że ludność jest w kwadracie rozłożona równomiernie — to uproszczenie (w rzeczywistości ludzie mieszkają w zabudowie, nie w lesie). Suma ludności jest zachowana — sprawdzamy to w kodzie (kontrola ±0,1%). W ETL wartości ukryte przez Eurostat (−9999, ochrona prywatności) w podkategoriach (kobiety, mężczyźni, wiek) uzupełniamy proporcjonalnie do łącznej liczby ludności.
- `etl/population.py:cells_to_hex`, `impute_subcategories`, `build_hex_pop`.

## 5. KDE (estymacja jądrowa) i szerokość pasma

Zamiast liczyć klientów tylko „w moim heksagonie”, sumujemy wszystkich w okolicy, ale **z wagą malejącą z odległością**: blisko waga ≈ 1, daleko ≈ 0 (jądro Gaussa `exp(−d²/2h²)`). `h` to **szerokość pasma** = „zasięg klienta”: jak daleko ludzie jadą po daną usługę (salon: ~1,5 km, markety budowlane: ~15 km). Za wąskie `h` daje „kropkowaną” mapę, za szerokie rozmywa różnice; dlatego `h` jest domyślnie dobrane do branży i można je zmienić suwakiem. Źródła dalsze niż 3h pomijamy (ich waga < 1,2%).
- `backend/app/analysis/kernel.py:kernel_sums` (drzewo cKDTree wybiera tylko sąsiadów).
- Domyślne `h` dla typów: `backend/app/catalog.py` (pole `bandwidth_km`).

## 6. Efekt krawędzi i bufor

Gdyby liczyć tylko heksagony w wybranym kole, te przy brzegu „nie widziałyby” konkurenta stojącego tuż za granicą i wynik byłby zawyżony. Dlatego pobieramy dane z **buforem 3h** wokół obszaru, a wynik (i percentyle) liczymy tylko dla heksagonów wewnątrz koła. Morze i teren za granicą nie mają danych, więc nie dostają heksagonów (testy: `test_analyze_half_empty_area`).
- `backend/app/analysis/service.py:run_analysis` (zmienna `reach_m = radius_m + 3h`).

## 7. Model 2SFCA a nasz wskaźnik

2SFCA (two-step floating catchment area) to metoda z geografii zdrowia: w kroku 1 dla każdego dostawcy liczy się stosunek „dostawca / ludność w jego zasięgu”, w kroku 2 sumuje się te stosunki dla każdego mieszkańca. Nasz wskaźnik jest **uproszczoną, odwróconą** wersją: dla każdego miejsca liczymy `popyt w zasięgu / (konkurencja w zasięgu + 1)` z gładkim jądrem zamiast twardego okręgu. Jest prostszy do wytłumaczenia („ilu klientów na jednego konkurenta”), ale nie rozdziela popytu między konkurentów tak dokładnie jak pełne 2SFCA. „+1” zapobiega dzieleniu przez zero i działa jak „wirtualny konkurent”.
- `backend/app/analysis/scoring.py:score`.

## 8. Geokodowanie: działka → obręb → punkt

Pozwolenie na budowę ma numer działki, ale działek są miliony, a serwis GUGiK (ULDK) odpowiada ~0,35 s na zapytanie. Dlatego sumujemy pozwolenia do **obrębów ewidencyjnych** (jednostek ~kilkudziesięciu tysięcy w Polsce, np. `160602_4.0038`), pobieramy kształt obrębu z ULDK i jako jego położenie bierzemy `representative_point()` — punkt zawsze leżący *wewnątrz* kształtu (zwykły środek ciężkości bywa poza figurą wklęsłą). Dokładność to obręb: w mieście osiedle, na wsi cała wieś. Gdy obrębu nie ma w ULDK, używamy środka gminy. Wyniki zapisujemy w tabeli-cache `obreb_geom`, więc przerwany ETL można wznowić.
- `etl/permits.py:normalize_obreb_id` (budowa identyfikatora), `etl/geocode_obreby.py:UldkClient`, `wkt_to_latlng`, `geocode_missing`, `build_permits_hex`.

## 9. Kompletność danych VGI (OpenStreetMap)

OSM jest tworzony przez wolontariuszy (VGI — volunteered geographic information), więc jest **niekompletny**, zwłaszcza dla małych usług: np. w całej Polsce jest ok. 10 tys. fryzjerów w OSM, a realnie wielokrotnie więcej. Wynik „mało konkurencji” może więc znaczyć „mało wpisanych do OSM”. Dlatego każdy typ ma ocenę `osm_quality` (good/medium/poor), a dla `poor` aplikacja ostrzega, żeby traktować mapę głównie jako mapę popytu. Docelowo drugim źródłem konkurencji byłby rejestr CEIDG.
- `backend/app/catalog.py` (`osm_quality`, `POOR_WARNING`), `etl/osm_poi.py:extract`.

## 10. Dlaczego pozwolenie na budowę ≠ dom

Pozwolenie to zamiar: budowa trwa 1–3 lata, a część pozwoleń nigdy nie jest zrealizowana. Wiemy też tylko, że dom ma powstać w danym obrębie — nie wiemy dokładnie gdzie. Dlatego „nowe domy” traktujemy jako **wskaźnik kierunku rozwoju** okolicy (przydatny np. dla brukarza), nie jako dokładną liczbę domów. W aplikacji pod legendą jest o tym przypomnienie, a okno czasowe (12/24/36 miesięcy) liczymy od najnowszych danych w rejestrze. Z rejestru wykluczamy „zmiany pozwoleń”, żeby nie liczyć tego samego domu dwa razy.
- `etl/permits.py:parse_permits`, `backend/app/analysis/service.py:_permit_window`.

## 11. Jak działa top-5 (non-maximum suppression)

Biorąc po prostu 5 heksagonów o najwyższym wyniku, dostalibyśmy 5 sąsiadów z tego samego skupiska. Dlatego wybieramy zachłannie od najlepszego i **odrzucamy miejsca bliższe niż 2h** od już wybranych (non-maximum suppression). Dodatkowo kandydatem jest tylko heksagon z popytem co najmniej na poziomie 25. percentyla — inaczej wygrywałyby puste tereny (lasy), gdzie jest 0 klientów i 0 konkurentów, a wynik bywa wysoki tylko z powodu małego mianownika. Nazwa miejsca to najbliższe osiedle/wieś w promieniu 3 km (osiedle ma pierwszeństwo przed miastem).
- `backend/app/analysis/scoring.py:pick_top`, `service.py:nearest_place_name`.

---

## 10 pytań, które może zadać prowadzący

**1. Dlaczego heksagony, a nie kwadraty albo gminy?**
Heksagon ma sześciu równo oddalonych sąsiadów, więc zasięg jest bardziej naturalny niż w kwadratach (gdzie przekątna jest 1,41× dalej). Gminy mają bardzo różną wielkość, więc wynik zależałby od granic (MAUP). H3 jest przy tym hierarchiczne — łatwo przechodzić między rozdzielczościami.

**2. Skąd wiesz, że wynik „klienci na 1 konkurenta” ma sens?**
To prosty, wyjaśnialny model dostępności (uproszczone 2SFCA/KDE): popyt w zasięgu podzielony przez konkurencję w zasięgu. Nie twierdzę, że to prognoza zysku — to ranking miejsc „dużo klientów, mało konkurencji”, który trzeba zestawić z lokalną wiedzą. Walidacją są testy na syntetycznych danych z ręcznie policzonym wynikiem i przegląd map dla znanych miast.

**3. Co to jest szerokość pasma h i jak ją dobrano?**
To „zasięg klienta” — odległość, przy której waga spada do ~60% (σ jądra Gaussa). Dobrałem ją orientacyjnie dla branży (salon 1,5 km, siłownia 3 km, market budowlany 15 km) i dałem suwak. Zmiana h zmienia gładkość mapy, ale nie ranking dramatycznie — można to pokazać na żywo.

**4. Dlaczego odległości liczysz w EPSG:2180, a nie w stopniach?**
Bo stopnie nie są jednostką długości: 1° długości geograficznej to ok. 68 km na 52°N, a 1° szerokości ok. 111 km. Liczenie odległości w stopniach zniekształciłoby kształt jądra. EPSG:2180 jest metryczny i dopasowany do Polski.

**5. Co to jest efekt krawędzi i jak sobie z nim radzisz?**
Przy brzegu analizowanego obszaru brakuje sąsiadów po drugiej stronie granicy, więc wskaźnik byłby zaniżony/zawyżony. Pobieram dane z buforem 3h wokół obszaru, a wynik pokazuję tylko wewnątrz. Konkurent tuż za granicą koła wciąż się liczy.

**6. Jak z kwadratów 1 km zrobiłeś heksagony?**
Interpolacją powierzchniową: każdy kwadrat dzielę na 25 punktów, każdy niesie 1/25 ludności, przypisuję go do heksagonu, w którym leży, i sumuję. Zakładam równomierny rozkład ludności w kwadracie — to ograniczenie. Można je poprawić metodą dasymetryczną (np. wagami z budynków OSM).

**7. Czy dane z OpenStreetMap są wystarczające?**
Nie dla wszystkich branż — OSM jest niekompletny dla małych usług, więc oznaczyłem typy oceną jakości i dla „poor” ostrzegam, że mapa to głównie mapa popytu. Rozwiązaniem byłby rejestr CEIDG (kody PKD są już w katalogu), ale wymaga tokenu.

**8. Jak geokodujesz pozwolenia na budowę?**
Nie działki (to miliony zapytań), tylko obręby ewidencyjne przez ULDK GUGiK: pobieram kształt obrębu i biorę punkt reprezentatywny leżący wewnątrz. Wyniki są w cache (`obreb_geom`), a gdy obrębu brak, używam środka gminy. Dokładność = obręb, co opisuję jako ograniczenie.

**9. Dlaczego „nowe domy” to dobry czynnik popytu dla brukarza, skoro pozwolenie nie znaczy domu?**
Bo pozwolenia to wiodący wskaźnik kierunku rozwoju zabudowy: tam, gdzie wydano dużo pozwoleń, w ciągu 1–3 lat powstanie popyt na utwardzenie podjazdów i zagospodarowanie ogrodu. Nie traktuję tego jako liczby domów, tylko jako intensywność inwestycji, i mówię o tym w interfejsie.

**10. Jak zapewniłeś, że wyniki są szybkie dla całej Polski?**
Dane są przetwarzane raz (ETL → DuckDB), a przy zapytaniu liczę sumy ważone tylko na heksagonach w obszarze, z drzewem cKDTree wybierającym sąsiadów w promieniu 3h. Dla całej Polski używam res 6 (~9,7 tys. heksagonów), a wyniki są w pamięci podręcznej (LRU). Typowa odpowiedź to ułamek sekundy.

*Bonus — jak odtworzyć bazę?* `uv sync`, potem `uv run python -m etl.run_all` (kilka godzin: najdłużej pobieranie OSM i geokodowanie obrębów), a na końcu `start.bat`.
