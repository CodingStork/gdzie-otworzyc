# Ściąga do obrony — „Gdzie otworzyć?” (wersja 2)

Prostym językiem: co robi aplikacja, jakie pojęcia z analizy danych przestrzennych w niej występują i **gdzie dokładnie w kodzie** je znaleźć. Każde pojęcie ma 3–6 zdań i wskazanie `plik:funkcja`.

## Jak to działa w jednym akapicie

Wybierasz typ działalności (np. salon kosmetyczny) i/lub czynnik popytu (np. liczba kobiet), ustawiasz **zasięg klienta** (z jak daleka przychodzą klienci, 0,1–20 km) i oglądasz mapę. Analiza dotyczy **widocznego fragmentu mapy** i odświeża się sama po przesunięciu lub przybliżeniu. Dla każdego heksagonu siatki H3 liczymy, ilu potencjalnych klientów (D) i ilu konkurentów (S) jest **w okręgu o promieniu równym zasięgowi klienta**, a wynik to **„klienci na firmę po otwarciu Twojej”**: `D / (S + 1)`. Kolor to płynny gradient wg pozycji miejsca w rankingu widocznego obszaru (percentyl). Kliknięcie mapy pokazuje dymek z dokładnymi liczbami dla klikniętego punktu. Dane (ludność ze spisu rozłożona na budynki OSM, firmy z OSM, pozwolenia z GUNB) przetwarzamy **raz** do bazy DuckDB (ETL), więc odpowiedź to ułamek sekundy do kilku sekund.

Wzór: `score = D / (S + 1)`, gdzie `D = Σ d_j` i `S = Σ s_j` po komórkach `j`, których środek leży w odległości ≤ `r` od heksagonu `i`.

---

## 1. Układy współrzędnych (EPSG 4326 / 3035 / 2180)

Układ współrzędnych mówi, jak liczby opisują miejsce na Ziemi. **EPSG:4326 (WGS84)** to stopnie szerokości i długości geograficznej — tak mówią OSM, ULDK i H3. **EPSG:3035 (ETRS89-LAEA)** to europejski układ w metrach, w którym Eurostat publikuje siatkę spisu (kwadraty 1 km × 1 km). **EPSG:2180 (PUWG 1992)** to polski układ metryczny. Odległości liczymy w metrach (2180), bo stopień długości geograficznej ma inną długość w Polsce niż na równiku — odległość „na stopniach” byłaby zniekształcona.
- Spis 3035 → 4326: `etl/population.py:cells_to_hex` (`Transformer.from_crs(3035, 4326)`).
- Budynki 4326 → 3035 (przypisanie do komórki spisu): `etl/buildings.py:build_building_weights`.
- 4326 → 2180 do odległości: `backend/app/analysis/kernel.py:to_metric`.

## 2. Siatka H3, hierarchia i poziomy szczegółowości (LOD)

H3 (Uber) dzieli Ziemię na heksagony w wielu rozdzielczościach. Każdy heksagon ma 6 sąsiadów w **tej samej odległości** (w kwadratach sąsiedzi po przekątnej są dalej), więc „zasięg” wygląda naturalnie. Rozdzielczości są **hierarchiczne**: heksagon ma jednego „rodzica” poziom wyżej, więc przejście do grubszej siatki to zwykłe grupowanie po rodzicu. W bazie mamy res 9 (~0,3 km między środkami) do res 5 (~15 km).

**Poziomy szczegółowości (LOD, level of detail)**: im bardziej przybliżysz mapę, tym drobniejsze heksagony (zoom ≤ 6 → res 5, 7–8 → res 6, 9 → res 7, 10–11 → res 8, ≥ 12 → res 9). Dzięki temu na ekranie heksagony mają podobną wielkość i nie ma ich tysięcy ani kilku wielkich plam. Przy zmianie poziomu nowa siatka płynnie się pojawia, a stara gaśnie (efekt „dzielenia”).

Rozróżniamy `display_res` (siatka *rysowana*) i `compute_res` (siatka, na której *liczymy*, nie grubsza niż rysowana): liczymy możliwie drobno (res 9 albo 8), żeby okrąg zasięgu był dokładny, a potem agregujemy do rysowanej siatki.
- `backend/app/analysis/resolution.py:display_res_for_zoom`, `choose_compute_res` (limity: ≤ 800 tys. komórek i ≤ 30 mln par komórka–sąsiad).
- Agregacja do rodziców w bazie: `etl/aggregate.py:build_aggregates` (funkcja SQL `h3_parent`).

## 3. MAUP (problem modyfikowalnej jednostki przestrzennej)

Wynik analizy zależy od tego, jak potniemy mapę na jednostki: te same dane w granicach gmin, powiatów czy heksagonów dadzą różne obrazy. Dlatego nie liczymy wskaźnika „na gminę”, tylko na jednolitej siatce H3, a każdy heksagon „patrzy” na okolicę w okręgu, a nie tylko na siebie. Liczymy zawsze na najdrobniejszej siatce, na jaką pozwala koszt, i dopiero potem agregujemy — wyniki na różnych poziomach przybliżenia są więc spójne. Dodatkowo bbox widoku przyciągamy do siatki, więc drobne przesunięcie mapy nie zmienia wyniku ani kolorów.
- `backend/app/analysis/resolution.py:snap_bbox`, `service.py:_compute_core`.

## 4. Interpolacja powierzchniowa i **metoda dasymetryczna**

Spis podaje ludność w kwadratach 1 km, a my potrzebujemy jej w heksagonach res 9 (~0,1 km²). **Interpolacja powierzchniowa** dzieli kwadrat na siatkę punktów i rozkłada ludność równomiernie. To uproszczenie: w rzeczywistości ludzie mieszkają w domach, nie w lesie.

**Metoda dasymetryczna** (dasymetric mapping) poprawia to: ludność kwadratu rozkładamy **proporcjonalnie do wagi budynków mieszkalnych** z OpenStreetMap w każdym heksagonie. Waga budynku = powierzchnia rzutu × liczba kondygnacji × współczynnik typu (dom/blok = 1, `building=yes` = 0,5, garaż/stodoła = 0). Powierzchnia × kondygnacje przybliża powierzchnię użytkową, czyli „ile ludzi się tu zmieści”. Dzięki temu heksagon z blokami dostaje dużo mieszkańców, a pole obok — nic. Suma ludności w kwadracie jest zachowana (kontrola ±0,1%).

Ograniczenia: to wciąż szacunek (nie znamy liczby mieszkań w budynku); OSM może nie mieć budynków w części wsi — wtedy kwadrat rozkładamy równomiernie (jak w v1). Udział ludności rozłożonej przez budynki zapisujemy w `meta` i sprawdzamy w kontroli jakości (≥ 85%).
- `etl/buildings.py` (`building_factor`, `levels`, `polygon_area_m2`, `build_building_weights`), `etl/population.py:dasymetric_to_hex`, `build_hex_pop`.

## 5. Zasięg klienta: okrąg (2SFCA) zamiast jądra Gaussa

W v1 źródła ważyło jądro Gaussa `exp(−d²/2h²)` — gładkie, ale **nieinterpretowalne**: dymek pokazywał „konkurentów w zasięgu: 192,3”. W v2 używamy **twardego okręgu**: do `D` wliczamy wszystkich mieszkańców, a do `S` wszystkie firmy, których środek leży w odległości ≤ `r` (zasięg klienta). Liczby są całkowite i da się je sprawdzić na mapie (okrąg rysuje się po kliknięciu). To klasyczna metoda **2SFCA** (two-step floating catchment area) z progiem odległości — okrąg „pływa” po mapie, a w każdym położeniu zliczamy popyt i podaż.

Wada okręgu: skokowa zmiana przy przesunięciu o próg. Zaletą jest przejrzystość („w promieniu 1,5 km jest 31 fryzjerów”) i brak parametru, którego nie da się wytłumaczyć. Dla popytu z pozwoleń zasięg jest co najmniej 1 km (lokalizacja pozwoleń to środek obrębu).
- `backend/app/analysis/kernel.py:catchment_sums` (drzewo cKDTree, przetwarzanie porcjami).
- Domyślny zasięg dla typów: `backend/app/catalog.py` (pole `bandwidth_km`).

## 6. Efekt krawędzi i bufor

Gdyby liczyć tylko heksagony w widoku, te przy brzegu „nie widziałyby” konkurenta stojącego tuż za krawędzią ekranu i wynik byłby zaniżony/zawyżony. Dlatego wczytujemy dane z **buforem r** (promień zasięgu) wokół widoku, a wynik pokazujemy tylko dla heksagonów w widoku. Morze i teren za granicą nie mają danych, więc nie dostają heksagonów (test: `test_view_empty_area`).
- `backend/app/analysis/service.py:_compute_core` (zmienna `box` = bbox + bufor).

## 7. Model 2SFCA a nasz wskaźnik

Pełne 2SFCA (z geografii zdrowia): krok 1 — dla każdego dostawcy stosunek „dostawca / ludność w jego zasięgu”, krok 2 — suma tych stosunków w zasięgu mieszkańca. Nasz wskaźnik jest **uproszczoną, odwróconą** wersją: dla każdego miejsca `popyt w okręgu / (konkurencja w okręgu + 1)`. Jest prostszy do wytłumaczenia („ilu klientów na jedną firmę po otwarciu mojej”), ale nie rozdziela popytu między konkurentów tak dokładnie jak pełne 2SFCA. „+1” to **Ty jako nowy konkurent** — zapobiega też dzieleniu przez zero.
- `backend/app/analysis/scoring.py:score`.

## 8. Agregacja średnią ważoną ludnością

Gdy liczymy na res 9, a rysujemy res 7, każdy większy heksagon składa się z wielu małych. Wynik dla dużego heksagonu to **średnia ważona liczbą mieszkańców** małych komórek („wartość dla przeciętnego mieszkańca heksagonu”). Zwykła średnia zrównałaby gęsto zamieszkaną ulicę z pustym polem obok, a suma zależałaby od liczby dzieci. Waga to `pop_total + 1e-6` (żeby heksagon bez mieszkańców miał zwykłą średnią zamiast dzielenia przez zero).
- `backend/app/analysis/scoring.py:weighted_parent_mean`.

## 9. Skala kolorów: gradient wg percentyla a klasy kwantylowe

W v1 mapa miała 5 klas kolorów (kwantyle): w centrum miasta 150 i 800 „klientów na konkurenta” trafiały do tej samej klasy i miały ten sam kolor. W v2 kolor to **płynny gradient** (paleta YlGnBu, interpolacja RGB po 9 punktach) zależny od **percentyla**: pozycji wartości w rankingu wszystkich heksagonów widocznego obszaru (0 = najniższa, 100 = najwyższa). Percentyl, a nie sama wartość, bo rozkład wyników jest bardzo skośny (kilka miejsc ma ogromne wartości) i kolor wg wartości malowałby prawie wszystko na jasno. Legenda to pionowy pasek gradientu z wartościami dla percentyli 0, 25, 50, 75, 90 i 100. Kolory są **względne dla widoku** — dokładne liczby pokazuje dymek po kliknięciu.
- `backend/app/analysis/scoring.py:percentile_rank`, `legend_values`; `frontend/js/colors.js:gradientColor`.

## 10. Geokodowanie: działka → obręb → punkt

Pozwolenie na budowę ma numer działki, ale działek są miliony, a serwis GUGiK (ULDK) odpowiada ~0,35 s na zapytanie. Dlatego sumujemy pozwolenia do **obrębów ewidencyjnych** (jednostek ~kilkudziesięciu tysięcy w Polsce, np. `160602_4.0038`), pobieramy kształt obrębu z ULDK i jako jego położenie bierzemy `representative_point()` — punkt zawsze leżący *wewnątrz* kształtu (zwykły środek ciężkości bywa poza figurą wklęsłą). Dokładność to obręb: w mieście osiedle, na wsi cała wieś — stąd minimalny zasięg 1 km dla popytu z pozwoleń. Gdy obrębu nie ma w ULDK, używamy środka gminy. Wyniki zapisujemy w tabeli-cache `obreb_geom`, więc przerwany ETL można wznowić.
- `etl/permits.py:normalize_obreb_id`, `etl/geocode_obreby.py:UldkClient`, `wkt_to_latlng`, `geocode_missing`, `build_permits_hex`.

## 11. Kompletność danych VGI (OpenStreetMap)

OSM jest tworzony przez wolontariuszy (VGI — volunteered geographic information), więc jest **niekompletny**, zwłaszcza dla małych usług: w całej Polsce jest ok. 10 tys. fryzjerów w OSM, a realnie ok. 3–4 razy więcej. Wynik „mało konkurencji” może więc znaczyć „mało wpisanych do OSM”, a same liczby „klientów na firmę” są zawyżone — dlatego mapę czytamy porównawczo (które miejsce jest lepsze), nie absolutnie. Każdy typ ma ocenę `osm_quality` (good/medium/poor), a dla `poor` aplikacja ostrzega, że to głównie mapa popytu. Docelowo drugim źródłem konkurencji byłby rejestr CEIDG.
- `backend/app/catalog.py` (`osm_quality`, `POOR_WARNING`), `etl/osm_poi.py:extract`.

## 12. Dlaczego pozwolenie na budowę ≠ dom

Pozwolenie to zamiar: budowa trwa 1–3 lata, a część pozwoleń nigdy nie jest zrealizowana. Wiemy też tylko, że dom ma powstać w danym obrębie — nie wiemy dokładnie gdzie. Dlatego „nowe domy” traktujemy jako **wskaźnik kierunku rozwoju** okolicy (przydatny np. dla brukarza), nie jako dokładną liczbę domów. W aplikacji pod legendą jest o tym przypomnienie, a okno czasowe (12/24/36 miesięcy) liczymy od najnowszych danych w rejestrze. Z rejestru wykluczamy „zmiany pozwoleń”, żeby nie liczyć tego samego domu dwa razy.
- `etl/permits.py:parse_permits`, `backend/app/analysis/service.py:_permit_window`.

## 13. Jak działa top-5 (non-maximum suppression)

Biorąc po prostu 5 heksagonów o najwyższym wyniku, dostalibyśmy 5 sąsiadów z tego samego skupiska. Dlatego wybieramy zachłannie od najlepszego i **odrzucamy miejsca bliższe niż** `max(2r, 1/6 przekątnej widoku)` od już wybranych (non-maximum suppression). Dodatkowo kandydatem jest tylko heksagon z popytem co najmniej na poziomie 25. percentyla — inaczej wygrywałyby puste tereny (lasy), gdzie jest 0 klientów i 0 konkurentów, a wynik bywa wysoki tylko z powodu małego mianownika. Top-5 dotyczy widocznego fragmentu mapy, a miejsca są numerowane na mapie. Metryka zależy od trybu (Okazja / Popyt / Konkurencja). Nazwa miejsca to najbliższe osiedle/wieś w promieniu 3 km (osiedle ma pierwszeństwo przed miastem).
- `backend/app/analysis/scoring.py:pick_top`, `service.py:_pick_top`, `nearest_place_name`.

## 14. Dymek punktu: dokładne liczby

Heatmapa jest liczona na komórkach i agregowana, więc jej wartości są przybliżone. Po kliknięciu mapy backend liczy **dokładnie** dla klikniętego punktu: popyt z komórek res 9, których środek leży w okręgu zasięgu, firmy z tabeli `poi` po rzeczywistej odległości punktów (wzór haversine), 5 najbliższych firm z odległościami. Na mapie rysuje się okrąg zasięgu, który znika po zamknięciu dymku.
- `backend/app/analysis/service.py:point_details`.

---

## 10 pytań, które może zadać prowadzący

**1. Dlaczego heksagony, a nie kwadraty albo gminy?**
Heksagon ma sześciu równo oddalonych sąsiadów, więc zasięg jest bardziej naturalny niż w kwadratach (gdzie przekątna jest 1,41× dalej). Gminy mają bardzo różną wielkość, więc wynik zależałby od granic (MAUP). H3 jest przy tym hierarchiczne — łatwo przechodzić między rozdzielczościami, co wykorzystuję w poziomach szczegółowości.

**2. Skąd wiesz, że wynik „klienci na firmę” ma sens?**
To prosty, wyjaśnialny model dostępności (uproszczone 2SFCA): popyt w okręgu zasięgu podzielony przez (konkurencję w tym okręgu + 1). Nie twierdzę, że to prognoza zysku — to ranking miejsc „dużo klientów, mało konkurencji”, który trzeba zestawić z lokalną wiedzą. Liczby są sprawdzalne: dymek po kliknięciu pokazuje dokładne zliczenia w okręgu. Walidacją są testy na syntetycznych danych z ręcznie policzonym wynikiem i przegląd map dla znanych miast.

**3. Co to jest zasięg klienta i dlaczego okrąg, a nie jądro Gaussa?**
To promień okręgu, z którego przychodzą klienci (salon: 1,5 km, market budowlany: 15 km; suwak 0,1–20 km). W v1 użyłem jądra Gaussa, ale wynik trudno było zinterpretować („192,3 konkurenta”). Okrąg daje liczby całkowite, które można policzyć na mapie, więc łatwiej je obronić. Kosztem jest mniej gładkie przejście na granicy okręgu.

**4. Dlaczego odległości liczysz w EPSG:2180, a nie w stopniach?**
Bo stopnie nie są jednostką długości: 1° długości geograficznej to ok. 68 km na 52°N, a 1° szerokości ok. 111 km. Liczenie odległości w stopniach zniekształciłoby kształt okręgu. EPSG:2180 jest metryczny i dopasowany do Polski.

**5. Co to jest efekt krawędzi i jak sobie z nim radzisz?**
Przy brzegu widocznego obszaru brakuje sąsiadów po drugiej stronie krawędzi, więc wskaźnik byłby zaniżony/zawyżony. Wczytuję dane z buforem równym zasięgowi wokół widoku, a wynik pokazuję tylko wewnątrz. Konkurent tuż za krawędzią ekranu wciąż się liczy.

**6. Jak z kwadratów 1 km zrobiłeś heksagony i skąd wiesz, gdzie mieszkają ludzie?**
Metodą dasymetryczną: ludność każdego kwadratu rozkładam na heksagony res 9 proporcjonalnie do wagi budynków mieszkalnych z OSM (powierzchnia × kondygnacje × współczynnik typu). Gdzie OSM nie ma budynków, rozkładam równomiernie. Suma ludności jest zachowana (kontrola ±0,1%), a udział ludności rozłożonej przez budynki sprawdzam w kontroli jakości (powyżej 85%). To szacunek, nie spis na poziomie budynków — i tak to opisuję w interfejsie.

**7. Czy dane z OpenStreetMap są wystarczające?**
Nie dla wszystkich branż — OSM jest niekompletny dla małych usług, więc same liczby „klientów na firmę” są zawyżone, a mapę trzeba czytać porównawczo. Oznaczyłem typy oceną jakości i dla „poor” ostrzegam, że mapa to głównie mapa popytu. Rozwiązaniem byłby rejestr CEIDG (kody PKD są już w katalogu), ale wymaga tokenu.

**8. Jak geokodujesz pozwolenia na budowę?**
Nie działki (to miliony zapytań), tylko obręby ewidencyjne przez ULDK GUGiK: pobieram kształt obrębu i biorę punkt reprezentatywny leżący wewnątrz. Wyniki są w cache (`obreb_geom`), a gdy obrębu brak, używam środka gminy. Dokładność = obręb, dlatego dla nowych domów zasięg wynosi co najmniej 1 km.

**9. Dlaczego kolor zależy od percentyla, a nie od wartości?**
Rozkład wyniku jest bardzo skośny — kilka miejsc ma wartości dziesiątki razy większe niż reszta. Gdyby kolor zależał od wartości, prawie cały obszar byłby jasny. Percentyl (pozycja w rankingu widocznego obszaru) wykorzystuje całą paletę i różnicuje nawet wartości z centrum miasta. Wadą jest to, że kolory są względne dla widoku — dlatego legenda podaje wartości dla percentyli, a dymek dokładne liczby.

**10. Jak zapewniłeś, że wyniki są szybkie, także dla całej Polski?**
Dane są przetwarzane raz (ETL → DuckDB) do tabel w res 9–5. Przy zapytaniu wybieram najdrobniejszą rozdzielczość, na której mieści się limit kosztu (≤ 800 tys. komórek i ≤ 30 mln par), liczę sumy w okręgach drzewem cKDTree, agreguję do rysowanej siatki, a wyniki trafiają do pamięci podręcznej (bbox przyciągnięty do siatki, więc małe przesunięcia nie liczą od nowa). Dla całej Polski przy małym zasięgu liczę na res 8 i rysuję res 5; aplikacja mówi wtedy, że najmniejszy liczony zasięg jest większy, i prosi o przybliżenie.

*Bonus — jak odtworzyć bazę?* `uv sync`, potem `uv run python -m etl.run_all` (kilka godzin: najdłużej pobieranie OSM, budynki i geokodowanie obrębów), a na końcu `start.bat`.
