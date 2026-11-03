# Gdzie otworzyć? — mapa okazji biznesowych

Aplikacja webowa, która na mapie Polski pokazuje, **gdzie jest dużo potencjalnych klientów i mało konkurencji**. Projekt zaliczeniowy z przedmiotu „Analiza danych przestrzennych”.

Zaznaczasz obszar na mapie — **okrąg** albo **prostokąt** — wybierasz typ działalności (10 typów) i/lub klientów (ludność ze spisu 2021 albo nowe domy z pozwoleń na budowę) i klikasz **„Analizuj obszar”**. W obszarze pojawia się **mgła** — płynna żółto-czerwona mapa szacowanej liczby klientów nowej firmy (model Huffa) — a po prawej **wnioski**: jedno zdanie z odpowiedzią („Mniej konkurencji niż zwykle w podobnych miejscach…”), liczby, z których wynika, i najlepsze miejsca z nazwami ulic. Okrąg do 30 km promienia (prostokąt do 60 km boku) liczy się na żywo z Twoimi ustawieniami (**zasięg klienta** 0,3–20 km); większy obszar — aż do całej Polski — z **gotowej mapy Polski** policzonej wcześniej (ETL). Wersja 3.5 to wynik [audytu przydatności](docs/audyt-przydatnosci.md), wersja 3.6 — uwag pierwszego testera ([zadania dla agenta lokalnego](docs/zadania-dla-agenta-lokalnego.md)).

![Okrąg zaznaczony przy widoku całej Polski: ok. 1/5 ekranu, kropki do przesuwania i zmiany promienia, karta z polem km (dane syntetyczne)](docs/screenshots/v36-c-okrag-przy-widoku-polski-syntetyczne.png)

## Jak używać

1. **Krok 1 w lewym panelu — narzędzie:** kliknij **„◯ Okrąg”** albo **„▭ Prostokąt”** (nie ma domyślnego; bez narzędzia kliknięcie w mapę tylko podpowiada, co zrobić, a przyciski pulsują). Przy pierwszej wizycie animacja pokazuje te przyciski, a po wyborze narzędzia — jak nim zaznaczyć (przycisk „?” przy mapie odtwarza ją ponownie). Możesz też wpisać miejscowość w wyszukiwarce — mapa tam przeleci i zaznaczy okrąg.
2. **Zaznacz obszar:**
   - **okrąg** — kliknij mapę: pojawia się okrąg o promieniu ok. **20% krótszego boku ekranu** (przy widoku całej Polski to ok. 200 km, w mieście kilka km), a mapa płynnie przesuwa się tak, żeby był na środku. **Kropką na krawędzi** zmieniasz promień, **kropką w środku** przesuwasz okrąg; promień możesz też wpisać w polu „Promień: [ ] km” na karcie;
   - **prostokąt** — przeciągnij po mapie; **za rogi** zmienisz jego rozmiar (bok 0,6–700 km). Żeby narysować nowy, kliknij „▭ Prostokąt” jeszcze raz albo mapę poza nim.
3. **Krok 2 w lewym panelu — co otwierasz:** **branża** („Typ działalności”) i/lub **klienci** („Twoi klienci to”), przy nowych domach okres pozwoleń, **zasięg klienta**. Pod branżą jest jedno zdanie o tym, czego mapa dla niej nie widzi. Dopóki nic tu nie wybierzesz, karta przy obszarze **nie ma przycisku „Analizuj”** — mówi, co wybrać, a pola pulsują. **Nic nie liczy się samo**, zanim klikniesz „Analizuj obszar”.
4. **„✓ Analizuj obszar”:** poza obszarem mapa jest przygaszona, w obszarze widać mgłę. Kolory są **dopasowane do tego, co widać na ekranie** — po przybliżeniu do miasta skala liczy się tylko z widocznej części, więc widać różnice między ulicami (przemalowanie nie wysyła zapytań). Zmiana ustawień po analizie przelicza ten sam obszar.
5. **„Co pokazać na mapie”:** typ + klienci → **„Gdzie otworzyć”** (szacowana liczba Twoich klientów, model Huffa) i **„Gdzie są klienci”**; tylko typ → **„Gdzie są {firmy}”**; tylko klienci → **„Gdzie są klienci”**; klienci z pozwoleń → dodatkowo **„Gdzie budowy przybywa”** (trend). Pytajniki wyjaśniają każdą warstwę.
6. **Prawy panel (wnioski):** legenda, **podsumowanie obszaru** — najpierw werdykt jednym zdaniem („Konkurencja typowa dla podobnych miejsc.”, „Mniej konkurencji niż zwykle w podobnych miejscach — sprawdź na miejscu…”, „Za mało firm, żeby ocenić konkurencję…”), potem „Obszar: Brzeg, promień 3 km · Kobiety: ok. 18 700 (spis 2021) · Salony kosmetyczne: 36 (OpenStreetMap 18, Overture 18) · 1 firma na ok. 520 kobiet — w podobnych miejscach 1 na ok. …” — i **najlepsze miejsca** z nazwami ulic (klik = przelot i szczegóły). Dla dużego obszaru (z gotowej mapy) zamiast listy jest wyjaśnienie, że ranking pokazujemy do 30 km promienia.
7. **Kliknięcie w zbadany obszar** — szczegóły punktu: okrąg zasięgu, konkurenci, dymek z liczbami w zasięgu klienta, szacunkiem modelu i **„Kolor mapy w tym miejscu: …”** (mapa liczy klientów ważonych odległością, także spoza okręgu — dlatego to inna liczba niż „w promieniu 0,6 km”).
8. Adres strony (hash) zapisuje analizowany obszar (`lat`, `lng`, `r`, `n` dla okręgu albo `bbox=zachód,południe,wschód,północ`) i ustawienia — link można wysłać. Stare linki z trybem „Cała Polska” (`mode=pl`) ustawiają tylko widok mapy. Na telefonie panele to zakładki „Ustawienia” / „Wnioski” arkusza na dole (po wyborze narzędzia arkusz się zwija, po „Analizuj” otwierają się „Wnioski”).

| Karta bez wybranej branży i klientów: bez „Analizuj”, pola pulsują | Wynik dla okręgu wokół Brzegu |
|---|---|
| ![Karta](docs/screenshots/v36-a-okrag-bez-ustawien-syntetyczne.png) | ![Wynik](docs/screenshots/v36-b-wynik-brzeg-syntetyczne.png) |

Zrzuty v3.6 i v3.5 (`*-syntetyczne.png`) są zrobione na **syntetycznej** bazie testowej, bez podkładu mapy — pokazują interfejs, nie prawdziwe wyniki. Zrzuty z prawdziwymi danymi poniżej pochodzą z wcześniejszych wersji (inny interfejs, ta sama metoda).

## Przykłady użycia

| Przybliżanie: gotowa mapa Dolnego Śląska (stała skala) | Wrocław: gotowa mapa |
|---|---|
| ![Dolny Śląsk](docs/screenshots/v32-b1-dolny-slask-gotowa-mapa.png) | ![Wrocław, gotowa](docs/screenshots/v32-b2-wroclaw-gotowa-mapa.png) |

| Dalsze przybliżenie: mapa na żywo + podsumowanie widocznego obszaru | Klik w mapę: szczegóły i „Przeanalizuj to miejsce” |
|---|---|
| ![Wrocław, na żywo](docs/screenshots/v32-b3-wroclaw-na-zywo.png) | ![Dymek](docs/screenshots/v32-d1-klik-dymek-przeanalizuj.png) |

| Tryb „Wybrane miejsce” po „Przeanalizuj to miejsce” | Brukarz: bez branży, klienci = nowe domy (mapa Polski) |
|---|---|
| ![Wybrane miejsce](docs/screenshots/v32-d2-wybrane-miejsce-po-przeanalizuj.png) | ![Nowe domy](docs/screenshots/v32-e-nowe-domy-cala-polska.png) |

| Stary link z usuniętym typem (brukarstwo): działa, zostaje czynnik popytu | Telefon (375×812) |
|---|---|
| ![Stary link](docs/screenshots/v32-f-stary-link-brukarz.png) | ![Telefon](docs/screenshots/v32-g-telefon-nowe-domy.png) |

Zrzuty z wersji 3.5 (`docs/screenshots/audyt-*-syntetyczne.png`) pokazują nowe teksty interfejsu na **syntetycznej** bazie testowej, bez podkładu mapy (środowisko audytu nie miało dostępu do danych) — nie są prawdziwymi wynikami:

| Werdykt jednym zdaniem i porównanie z podobnymi miejscami | Mapa Polski bez rankingu miejscowości |
|---|---|
| ![Werdykt](docs/screenshots/audyt-c-werdykt-zdaniem-syntetyczne.png) | ![Polska](docs/screenshots/audyt-a-polska-bez-top5-syntetyczne.png) |

Zrzuty z wersji 3.3 (szare kreskowanie „mało danych o firmach”, Olsztynek vs Brzeg) są w `docs/screenshots/v33-*.png`.

Zrzuty z wersji 3.1 (okrąg wokół jednego miejsca, bez trybu „Cała Polska”) są w `docs/screenshots/v31-*.png`.

## Jak to działa (metoda)

Dla okręgu wokół wybranego miejsca serwer buduje **regularną siatkę** w metrach (lokalny układ metryczny wyrównany do północy; krok ok. promień/90, 50–300 m) i liczy na niej trzy wielkości. Każde źródło popytu *i* (komórka H3 z ludnością albo pozwoleniami, `d_i` osób) i każdy konkurent *k* (firma z OpenStreetMap albo Overture Maps) wpływa na punkt siatki *g* z wagą malejącą z odległością — **rozpad wykładniczy** `f(d) = exp(−d / zasięg)`, obcięty dla `d > 4·zasięg`:

```
Gdzie są klienci:  P(g) = Σ_i d_i · f(d_ig)
Gdzie są firmy:    K(g) = Σ_k f(d_kg)
Gdzie otworzyć:    E(g) = Σ_i d_i · f(d_ig) / ( f(d_ig) + C_i + A0 )     (model Huffa)
                   C_i  = Σ_k f(d_ik)   (siła istniejących konkurentów dla mieszkańca i),  A0 = exp(−1)
```

**Model Huffa (1963):** każdy mieszkaniec wybiera między firmami, a bliższa przyciąga go mocniej; `E(g)` to szacowana liczba klientów **nowej** firmy w punkcie *g*. **Opcja zewnętrzna `A0`** reprezentuje „inne możliwości” (firmy spoza obu baz, zakupy gdzie indziej) i częściowo kompensuje ich niekompletność. Wartości na siatce są zwracane przez `/api/surface`, a przeglądarka **interpoluje je** (×4, smoothstep) i dopiero potem koloruje — stąd gładka powierzchnia bez widocznych kwadratów. Po kliknięciu `/api/point` liczy dokładne liczby w okręgu zasięgu i ten sam wzór Huffa dla jednego punktu.

### Gotowa mapa Polski (v3.2; od v3.6 — silnik dużych obszarów)

Do v3.5 gotowa mapa była trybem „Cała Polska” (mgła na cały kraj od razu po wybraniu branży). Od v3.6 nic nie liczy się bez zaznaczenia obszaru i kliknięcia „Analizuj” (tester: „mapa policzyła się sama, choć nie kliknąłem Analizuj”), a gotowa mapa służy do analizy **dużych obszarów**: okrąg > 30 km albo prostokąt > 60 km boku (`/api/surface` → `national.run_area`: wartości z tabel `national_r*` przycięte do obszaru, podsumowanie z komórek res 7, bez listy najlepszych miejsc). Poniżej opis z v3.2 — metoda liczenia się nie zmieniła.

Ciągłe liczenie całej Polski przy każdym ruchu mapy było męczące (v2), więc robimy to **raz w ETL** (krok `national`, `etl/national.py`): dla środków komórek H3 **res 8** (~900 m między nimi; komórki z ludnością i ich sąsiedzi, ok. 420 tys. punktów) liczymy **te same wzory i funkcje co `/api/surface`** (Huff, potencjał popytu, zagęszczenie firm, trend budów; odległości w EPSG:2180) dla **typowego zasięgu**: z branżą — jej `bandwidth_km`, bez branży — `default_reach_km` czynnika (spis 1,5 km, pozwolenia 10 km). Warstw jest 92 (`open__{typ}__{czynnik}`, `rel__{typ}__{czynnik}` — patrz niżej, `comp__{typ}`, `demand__{czynnik}__{zasięg}`, `trend__{czynnik}`), w tabeli szerokiej `national_r8` (kolumna = warstwa). Grubsze poziomy `national_r7 … r5` powstają przez **maksimum z komórek-dzieci** — oddalona mapa pokazuje „najlepsze miejsce w tym rejonie”, a średnia zalałaby małe, dobre ośrodki mgłą bez kontrastu (dla trendu bierzemy wartość o największym module, ze znakiem). Tabela `national_meta` trzyma p5 i p99 wartości dodatnich: **stałą skalę kolorów** dla całego kraju (te same kolory znaczą te same liczby w Gdańsku i w Krakowie, i nie „pływają” przy przesuwaniu mapy).

`/api/national` wybiera rozdzielczość tak, by komórka H3 miała ≤ 4 px na ekranie (i nie więcej niż ~60 tys. komórek), układa wartości na siatce równej w rzucie Mercatora (żeby obraz przylegał do kafelków) i zwraca ją w tym samym kształcie co `/api/surface`, więc przeglądarka rysuje obie mgły tym samym kodem. Gdy dla wyboru nie ma gotowej warstwy (np. „Gdzie otworzyć” dla czynnika spoza zalecanych dla branży), odpowiedź mówi to w notatce, a użytkownik po przybliżeniu dostaje mapę na żywo. Mapa na żywo to `/api/surface` w trybie prostokąta widoku (`west,south,east,north`, bok ≤ 60 km): liczymy okrąg opisany na widoku, a maskę przycinamy do prostokąta, więc podsumowanie dotyczy „widocznego obszaru”.

### Wybór obszaru gestem (v3.4, zmieniony w v3.6)

**v3.6:** narzędzie wybiera się w lewym panelu (bez domyślnego), okrąg ma po kliknięciu stały rozmiar na ekranie (20% krótszego boku: `map.kmForScreenFraction`) i dwa uchwyty — środek (`circle-handle center`, przesuwanie) i krawędź (`circle-handle edge`, promień liczony jako odległość od środka po kuli) — a okrąg rysujemy wzorem na punkt w danej odległości i kierunku na kuli (`map.destination`), bo przy promieniu setek km przybliżenie płaskie dawałoby spłaszczony kształt. Promień zaokrąglamy (0,5 km do 5 km, 1 km do 50 km, potem 5 km). Karta (`ui.areaCard`) nie ma przycisku „Analizuj” bez branży i klientów. Opis z v3.4 poniżej (prostokąt działa tak samo, tylko włącza go przycisk w lewym panelu).

Zamiast formularza „miejsce + promień + Pokaż mapę” obszar wskazuje się na mapie. **Kliknięcie** tworzy *wybór*: pinezkę, przerywany okrąg podglądu i kartę (Leaflet `popup` z własnymi przyciskami) z liczbami punktu z `/api/point`, suwakiem promienia (jedna wartość w stanie, dwa widoki: karta i lewy panel) i przyciskiem ✓. **Prostokąt** rysuje się po kliknięciu „▭ Prostokąt”: wtedy `map.dragging.disable()`, a przeciągnięcie (**Pointer Events** — jeden kod dla myszy, palca i rysika) rysuje ramkę; po puszczeniu przesuwanie mapy wraca. Przycisk zamiast „przeciągnij gdziekolwiek” jest po to, żeby zwykłe przeciągnięcie (zwłaszcza palcem) dalej przesuwało mapę. Rogi to cztery przeciągalne markery (`divIcon`, 28 px na dotyk); ciągnięty róg zmienia prostokąt, a przeciwległy stoi w miejscu (przeciągnięcie „przez” niego odwraca prostokąt, nic się nie psuje). ✓ wysyła `/api/surface?area=rect&west=…&south=…&east=…&north=…`: serwer liczy tym samym kodem co „widoczny obszar” z v3.2, ale z gęstszą siatką (`divisions=90`), a podsumowanie nazywa się „Zaznaczony obszar: 12,7 × 8,2 km”. Limity boku to 0,6 km (rozdzielczość ludności ~300 m) i 60 km (jak dla widoku). Animacja wprowadzająca (`frontend/js/intro.js`) to czysty CSS (`@keyframes`) plus inline SVG; `prefers-reduced-motion` wyłącza ruch.

![Karta wyboru po kliknięciu: liczby, suwak 3 km (okrąg na żywo), ✓ i ✕](docs/screenshots/v34-b1-klik-karta-suwak-3km.png)

![Prostokąt na Wrocławiu z uchwytami w rogach i kartą z wymiarami](docs/screenshots/v34-d1-prostokat-wroclaw-uchwyty.png)

![Wynik dla prostokąta: mgła tylko w ramce, „Zaznaczony obszar”, top-5 w prostokącie](docs/screenshots/v34-d2-prostokat-wynik-zaznaczony-obszar.png)

### „Mało danych o firmach” — szare kreskowanie (v3.3)

Model Huffa wierzy danym. W miasteczku, w którym w OSM i Overture nie ma **ani jednego salonu**, „nowa firma zgarnia wszystkie klientki” — a to najczęściej luka w danych, nie okazja (przy takiej liczbie mieszkańców statystycznie byłoby ok. 4–6 salonów). Przed v3.3 na mapie Polski wygrywały więc Olsztynek, Sianów czy Nowe. Krok ETL **`gaps`** (`etl/gaps.py`) wykrywa takie miejsca, **osobno dla każdego typu firmy**:

```
oczekiwane = (mieszkańcy w promieniu 2 km od środka komórki res 9) × (firm tego typu w Polsce / mieszkańców Polski)
w danych   = firm tego typu (tabela poi) w promieniu 2 km
luka       = oczekiwane ≥ 3  ORAZ  w danych ≤ 0,25 · oczekiwane
```

- **Dlaczego 2 km, ≥ 3, ¼:** 2 km to promień małego miasta; poniżej 3 „oczekiwanych” firm brak firm bywa prawdziwy (wieś), więc nie oceniamy; „najwyżej ¼ średniej krajowej” to różnica, której nie tłumaczy specyfika miasteczka (miasteczka mają średnio *więcej* salonów na mieszkańca niż średnia krajowa — [docs/kompletnosc-danych.md](docs/kompletnosc-danych.md)). Progi ustalono pomiarem (w lukach mieszka 1,7% ludności dla salonów, 0,9% dla fryzjerów, 0,4% dla sklepów spożywczych; Brzeg, Oława i Wrocław bez luk) i są stałymi `GAP_*` w `backend/app/catalog.py`.
- **Udział klientów z luki:** drugi przebieg Huffa z wagami `d_i · luka_i` (ta sama dostępność konkurencji `C_i`) daje `E_luka`; **wiarygodni klienci** to `rel = E − E_luka`. Dla źródeł popytu w res < 9 (zasięg > 2 km) `luka_i` to udział ludności komórek-dzieci res 9 w luce (tabela `gap_share`).
- **Co widać:** kolor mgły się **nie zmienia** (model mówi, co mówi), ale miejsca, w których ponad połowa klientów mieszka w lukach (`rel < ½ E`), mają **szare ukośne kreskowanie**. Takie miejsca **nie trafiają do najlepszych miejsc** (top-5 jest sortowany po `rel`; pokazywana liczba to nadal `E` jak w dymku). Dymek po kliknięciu i podsumowanie obszaru pokazują ostrzeżenie z liczbami („w danych 0, a przy tej liczbie mieszkańców średnio w Polsce byłoby ok. 6”), a werdykt „mniej konkurencji niż przeciętnie” zastępuje „nie da się ocenić — za mało danych o firmach”.
- **Gdzie działa:** warstwa „Gdzie otworzyć” w obu trybach (`/api/national` czyta kolumny `rel__…`, `/api/surface` liczy `E` i `E_luka` jednym przebiegiem po parach punkt–źródło).
- **Ograniczenie:** miejscowość, w której spodziewamy się < 3 firm (np. 3-tysięczne miasteczko i salony), nie jest oceniana — przy tak małych liczbach brak firm może być prawdziwy, więc tam kreskowania nie będzie. Warstwa „Gdzie są firmy” (sam typ, bez popytu) na razie bez kreskowania. Wykrywamy tylko luki *względem średniej krajowej* — jeśli dane o firmach są słabe wszędzie podobnie, nic nie wychwycimy.

Najważniejsze decyzje metodyczne (szczegółowo w [docs/sciaga-do-obrony.md](docs/sciaga-do-obrony.md)):

- **Metoda dasymetryczna:** ludność ze spisu (kwadraty 1 km, EPSG:3035) rozkładamy na heksagony H3 **res 9** (~0,1 km²) proporcjonalnie do wagi budynków mieszkalnych z OSM (powierzchnia × kondygnacje × współczynnik typu); przy dużym zasięgu źródła są grubsze (res 8/7), żeby było szybko.
- **Powierzchnia ciągła zamiast heksagonów/choropletu:** wartości zmieniają się płynnie, więc pokazujemy izopletę-mgłę; drobne komórki dopiero po kliknięciu.
- **Skala logarytmiczna YlOrRd z przezroczystością:** kolor zależy od wartości; skala liczy się z komórek **widocznych na ekranie** (v3.6 — przybliżenie do miasta pokazuje różnice wewnątrz niego): górna granica = 99. percentyl wartości dodatnich, dolna = 5. percentyl, ale nie niżej niż 1/100 górnej i nie wyżej niż 1/4 górnej — skala obejmuje od 4× do 100×: mapa nie jest cała czerwona, różnica 20% to ledwie inny odcień, a 60% — wyraźnie inny. Małe wartości są przezroczyste.
- **Firmy z dwóch źródeł (Overture Maps + OSM):** OSM ma dla usług kilka razy mniej firm niż Overture (we Wrocławiu 340 salonów kosmetycznych w OSM wobec ok. 1 260 w Overture), więc `poi` = OSM ∪ Overture. Ten sam salon bywa w obu bazach, dlatego **deduplikacja przestrzenna**: obiekt Overture odpada, gdy w ≤ 50 m jest punkt OSM tego samego typu albo w ≤ 150 m punkt o podobnej nazwie (`difflib`, próg 0,6).
- **Podsumowanie i porównanie z podobnymi miejscami (v3.5):** surowa liczba firm nic nie mówi (duże miasto ma ich więcej), więc porównujemy liczbę firm w obszarze z **oczekiwaną** — ile byłoby ich, gdyby każda komórka miała tyle firm na mieszkańca, ile średnio mają w Polsce miejsca o **podobnej gęstości zaludnienia** (krok `gaps`: ludność Polski dzielimy na 5 równych części wg liczby mieszkańców w promieniu 2 km). Wcześniej punktem odniesienia była średnia krajowa, ale zaniżają ją wsie (salony: 4,1 na 10 tys. mieszkańców na wsi, 13,6–18,1 w miastach, średnia 8,45), więc miasta wychodziły „gęsto obsadzone” niezależnie od prawdy. Werdykt pada tylko przy różnicy wyraźnej (≤ 80% / ≥ 125% oczekiwanych) **i** mało prawdopodobnej jako przypadek (test Poissona, p < 10%); przy < 3 oczekiwanych firmach — „za mało firm, żeby ocenić”. Starsza baza bez tabel klas porównuje ze średnią krajową (napis to mówi).
- **Mapa trendu (zmiana w czasie):** dla czynników z pozwoleń liczymy różnicę „ostatnie 12 miesięcy minus poprzednie 12” (okno względem najnowszych danych), też z rozpadem odległości; paleta **rozbieżna** (niebieski = ubywa, czerwony = przybywa, zero przezroczyste), bo zmiana ma znak.
- **Rozdzielczość danych a sensowny zasięg:** ludność mamy w komórkach H3 res 9 (~300 m między środkami), więc zasięg poniżej 0,3 km nie dodaje informacji — suwak zaczyna się od 0,3 km.
- **Nazwy ulic w top-5:** z pliku OSM stawiamy punkty co ok. 100 m wzdłuż nazwanych dróg; nazwa miejsca = najbliższa ulica (≤ 150 m) + osiedle/miejscowość.
- **Odległości w metrach** (lokalny układ metryczny wokół miejsca, a dla danych EPSG:2180), nie w stopniach; bufor `4·zasięg` wokół okręgu usuwa efekt krawędzi.
- **Top-5** tylko spośród **lokalnych szczytów** (punkt, którego 8 sąsiadów leży w obszarze i żaden nie jest wyższy — punkt na krawędzi, gdzie wartości rosną na zewnątrz, to artefakt granicy), z odstępem ≥ max(zasięg, promień/5) (non-maximum suppression). Gdy na krawędzi jest wyżej niż w najlepszym szczycie, odpowiedź ma `top_edge`, a interfejs radzi przesunąć obszar. Na gotowej mapie Polski lista nie jest pokazywana (API ją liczy, odstęp 1/6 szerokości widoku).
- **Uczciwy katalog branż (v3.5):** „Stylizacja paznokci” jest w „Salonie kosmetycznym” — w danych każdy salon paznokci jest też salonem kosmetycznym, a osobny typ nie liczył salonów robiących manicure jako konkurencji (stare linki `type=nails` prowadzą do salonu, `TYPE_ALIASES`). Każdy typ może mieć jedno zdanie zastrzeżenia (`caveat`), pokazywane pod wyborem branży. Market budowlany domyślnie liczy mieszkańców, bo rejestr pozwoleń liczy blok jak jeden dom.
- **Uczciwy katalog branż (v3.2):** firmy pracujące u klienta (brukarz, ogrodnik, okna, kuchnie, instalator) znikły z listy „Typ działalności”: w OSM i Overture jest ich o rząd wielkości mniej niż w rzeczywistości ([docs/kompletnosc-danych.md](docs/kompletnosc-danych.md)), więc „mało konkurencji” znaczyłoby tylko „mało wpisów w bazach”. Czynniki popytu „nowe domy” zostają — brukarz wybiera klientów „nowe domy” bez branży i widzi, gdzie się buduje (także trend). ETL nadal zbiera te firmy do `poi` (`HIDDEN_TYPES`) pod przyszłe CEIDG.
- **Geokodowanie obrębów ewidencyjnych** (ULDK GUGiK) dla pozwoleń na budowę — dokładność do obrębu, stąd minimalny zasięg 1 km dla nowych domów.

## Zasady wizualizacji, z których korzystamy

- **Shneiderman (1996), „The Eyes Have It”:** *overview first, zoom and filter, then details-on-demand* → przepływ: wybór miejsca i promienia (zawężenie) → mapa okolicy (przegląd) → klik (szczegóły).
- **Huff (1963), „A Probabilistic Analysis of Shopping Center Trade Areas”** (używany też w ArcGIS Business Analyst) → liczba klientów nowej firmy zamiast surowego popytu.
- **Mapy izoplet / powierzchni ciągłej zamiast choropletów i hexbinów** dla wartości zmieniających się płynnie (mniej artefaktów granic, brak efektu MAUP w rysunku).
- **Borland & Taylor (2007), „Rainbow Color Map (Still) Considered Harmful”** i **Brewer, ColorBrewer** → sekwencyjna, jednobarwna skala YlOrRd, nie tęcza.
- **Skala logarytmiczna** dla skośnych rozkładów, **przezroczystość** małych wartości (efekt mgły, widać podkład i etykiety).
- **xkcd 1138 („Heatmap”)** — ostrzeżenie: mapa „tylko ludności” niczego nie wyjaśnia; stąd główna mapa odpowiada na pytanie „ilu klientów zdobędę”.
- Odrzucone: mapa dwuwymiarowa (bivariate) — trudna w odczycie; wtyczka Leaflet.heat — sumuje punkty w pikselach ekranu, więc obraz zależy od przybliżenia i nie odpowiada liczbom.

## Źródła danych i licencje

| Dane | Źródło | Licencja / atrybucja |
|---|---|---|
| Ludność (siatka 1 km, spis 2021) | Eurostat GISCO, Census GRID 2021 (V3) | © EU, Eurostat GISCO — dane zmodyfikowane (agregacja do H3) |
| Firmy, ulice i nazwy miejsc | OpenStreetMap (ekstrakt Geofabrik `poland-latest.osm.pbf`) | ODbL, © OpenStreetMap contributors |
| Firmy (drugie źródło) | Overture Maps Foundation, Places (wydanie 2026-10-21.0) | CDLA Permissive 2.0, © Overture Maps Foundation |
| Nowe budowy | GUNB — Rejestr Wniosków, Decyzji i Zgłoszeń (RWDZ), pliki CSV | dane publiczne GUNB |
| Granice obrębów | GUGiK ULDK | dane publiczne GUGiK |
| Podkład mapy | Esri World Light Gray (kafelki) | © Esri i współtwórcy |
| Wyszukiwarka adresów | Nominatim (OpenStreetMap) | ODbL; zapytania z limitem 1/s i pamięcią podręczną |

Podkład: pierwotnie planowano CARTO Positron, ale darmowe kafelki CARTO wymagają teraz klucza API, dlatego użyto jasnoszarego podkładu Esri (osobna warstwa podkładu i etykiet).

## Architektura

```
            (raz + odświeżanie)                                     (na żądanie)
 ┌────────────── ETL (Python) ───────────────┐      ┌──────── Backend FastAPI ────────┐     ┌──── Frontend ────┐
 │ Eurostat Census GRID 2021 → hex_pop_r9     │      │ /api/catalog                    │     │ index.html       │
 │ Geofabrik poland.osm.pbf  → poi, places,   │ ───▶ │ /api/surface (mgła: siatka,     │ ──▶ │ Leaflet          │
 │   streets, building_weights (dasymetria)   │DuckDB│   Huff, podsumowanie, trend,    │ JSON│ (bez buildowania)│
 │ Overture Places (S3)      → poi (dedup.)   │ plik │   top-5)                        │     │                  │
 │ GUNB RWDZ CSV + ULDK      → permits        │      │ /api/point (dymek punktu)       │     │                  │
 │ agregacja do H3 res 9 → 8 → 7 → 6 → 5      │      │ /api/national (gotowa mapa PL)  │     │                  │
 │ gaps: luki w danych o firmach (res 9 → 6)  │      │ /api/poi /api/geocode /api/meta │     │                  │
 │ national: Huff dla całej Polski (res 8,    │      │                                 │     │                  │
 │   piramida max → 7, 6, 5, stała skala)     │      │                                 │     │                  │
 └────────────────────────────────────────────┘      └─────────────────────────────────┘     └──────────────────┘
```

Dlaczego ETL zamiast zapytań na żywo: publiczne Overpass API blokuje automatyczne zapytania, a ULDK odpowiada ~0,35 s na działkę. Dane pobieramy hurtowo z otwartych plików i przetwarzamy raz do pliku DuckDB (`data/app.duckdb`) — backend tylko liczy na gotowych tabelach.

Struktura repozytorium:

```
backend/app/        FastAPI: main.py, config.py, db.py, catalog.py, api/routes.py,
                    analysis/{kernel,surface,service,layers,national}.py, services/geocode.py
etl/                download.py, osm_poi.py, overture.py, streets.py, buildings.py, population.py, permits.py,
                    geocode_obreby.py, aggregate.py, gaps.py, national.py, meta.py, run_all.py, sanity.py
frontend/           index.html, css/style.css, js/{app,api,map,ui,colors,intro}.js
tests/              pytest (małe fixture'y, baza testowa budowana w locie)
docs/               specyfikacja, plan, źródła danych, raport ETL, ściąga do obrony
```

## Instalacja i uruchomienie (Windows 11)

Wymagania: Windows 11, ≥ 16 GB RAM, ≥ 20 GB wolnego dysku, dostęp do internetu (jednorazowo ~3 GB danych).

```powershell
winget install --id=astral-sh.uv -e      # menedżer Pythona (po instalacji otwórz nową powłokę)
uv sync                                   # Python 3.13 + biblioteki (środowisko .venv)
uv run python -m etl.run_all              # ETL: pobieranie i przetwarzanie danych (kilka godzin, jednorazowo; budynki OSM ok. 16 min, luki w danych ok. 2 min, gotowa mapa Polski ok. 12 min)
uv run python -m etl.sanity               # kontrola jakości danych (powinno wypisać OK)
start.bat                                 # serwer: http://localhost:8000
```

Uwagi:
- Używamy Pythona 3.13 zarządzanego przez `uv` (`.python-version`); systemowego Pythona nie trzeba instalować.
- **Aktualizacja do v3.5:** wystarczy `uv run python -m etl.run_all --only gaps` (ok. 2 min, nowe tabele `density_cells` i `density_rates` — „podobne miejsca”), potem `uv run python -m etl.sanity`. Gotowej mapy Polski nie trzeba przeliczać.
- ETL można przerwać i wznowić — pobieranie i geokodowanie są wznawialne, a krok `national` pomija policzone warstwy (po zmianie danych o firmach lub ludności użyj `--only aggregate,gaps,national --force`; ok. 15 min — `gaps` liczy się zawsze od nowa, ale warstwy `rel__…` w `national` odświeża dopiero `--force`). `--only buildings,population,aggregate` uruchamia wybrane kroki, `--force` wymusza ponowne wykonanie.
- Serwer i ETL nie mogą działać jednocześnie (blokada pliku DuckDB).
- Serwer ULDK (GUGiK) może po godzinie intensywnych zapytań zablokować połączenie (przekierowanie na stronę-pułapkę). Geokodowanie przerywa się wtedy z komunikatem; odczekaj i dokończ: `uv run python -m etl.run_all --only geocode,permits_hex,aggregate --force` (szczegóły i aktualny stan: [docs/raport-etl.md](docs/raport-etl.md)).
- Testy: `uv run pytest -v`. Testy „jak użytkownik” (`tests/e2e`, prawdziwa przeglądarka, syntetyczna baza) wymagają jednorazowo `uv run playwright install chromium` — bez tego pomijają się same.

## Dostęp z innego urządzenia przez Tailscale

Aplikacja działa na komputerze domowym; z laptopa (np. na uczelni) otwierasz ją przez prywatną sieć Tailscale.

1. Zainstaluj Tailscale na komputerze z aplikacją i na laptopie (https://tailscale.com/download), zaloguj oba tym samym kontem.
2. Na komputerze z aplikacją zezwól na ruch przychodzący na port 8000 w Zaporze Windows (PowerShell jako administrator):
   `New-NetFirewallRule -DisplayName "Gdzie otworzyc 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private`
   (sieć Tailscale ma zwykle profil „prywatny”; w razie problemów dodaj regułę dla interfejsu Tailscale).
3. Uruchom `start.bat` i na laptopie wejdź na `http://<nazwa-komputera>:8000` (nazwę widać w aplikacji Tailscale, działa MagicDNS).
4. Opcjonalnie publiczny link dla prowadzącego: `tailscale funnel 8000` (wyłącz po pokazie).

## Ograniczenia danych

- **OpenStreetMap i Overture Maps są niekompletne**, zwłaszcza dla małych usług, dlatego typów „pracujących u klienta” (brukarze, ogrodnicy, instalatorzy) nie oferujemy; dla typów o ocenie „medium” (barber, paznokcie, tatuaż, fitness) aplikacja ostrzega łagodniej. Overture wyraźnie uzupełnia salony, fryzjerów i markety, ale wynik „mało konkurencji” może nadal oznaczać „mało wpisów w bazach”; dla typów z oceną „poor” aplikacja ostrzega, że to głównie mapa popytu. Deduplikacja jest heurystyką (odległość + podobieństwo nazw) — część duplikatów może zostać, a część różnych firm w jednym budynku zostać połączona.
- **Luki w danych o firmach wykrywamy tylko tam, gdzie jest wyraźnie mniej firm niż średnio w Polsce** (≤ ¼ przy ≥ 3 oczekiwanych w promieniu 2 km). Małe miejscowości (oczekiwane < 3) nie są oceniane, a warstwa „Gdzie są firmy” nie ma kreskowania; kreskowanie ostrzega, ale nie uzupełnia brakujących firm (to zrobi dopiero CEIDG).
- **Spis ludności jest z 2021 r.**; uzupełniają go pozwolenia na budowę.
- **Pozwolenie na budowę ≠ wybudowany dom** (budowa trwa 1–3 lata, część nie rusza), a lokalizacja jest z dokładnością do obrębu ewidencyjnego (miasto: osiedle, wieś: cała wieś) — dlatego zasięg dla nowych domów wynosi co najmniej 1 km.
- **Ludność w heksagonach to szacunek modelowy** (metoda dasymetryczna): spis podaje tylko kwadraty 1 km, a rozkład wewnątrz kwadratu wynika z wag budynków OSM (nie znamy liczby mieszkań w budynku).
- **Kolory są względne dla tego, co widać na ekranie** (skala logarytmiczna dopasowana do widocznej części obszaru — ten sam kolor po przybliżeniu znaczy co innego; dokładne liczby są w legendzie i w dymku), a liczby „klientów na firmę” bywają zawyżone, bo żadna baza nie zawiera wszystkich firm — dlatego porównujemy je ze średnią krajową liczoną tak samo.
- Liczba „nowych budynków wielorodzinnych” to liczba inwestycji, nie mieszkań (rejestr nie podaje liczby lokali).
- **Ten sam zasięg klienta w mieście i na wsi:** model nie widzi, że mieszkańcy wsi dojeżdżają do firm w mieście dalej niż 4 × zasięg, więc na słabo zaludnionym terenie liczba klientów jest zawyżona (interfejs mówi to przy werdykcie „za mało firm”). Poprawka (zasięg zależny od gęstości) wymaga kalibracji na prawdziwej bazie — [audyt](docs/audyt-przydatnosci.md), sekcja B4.
- **Popyt to miejsce zamieszkania (ludność „nocna”) ze spisu 2021** — bez miejsc pracy, dojazdów, turystów i ok. 1 mln osób z Ukrainy, które przyjechały po spisie; nie znamy zamożności. Najbardziej dotyczy to kawiarni i restauracji.
- **Każda firma jest tak samo atrakcyjna** w modelu Huffa (dyskont = mały sklep, duży market budowlany = sklep z narzędziami).
- Wynik jest rankingiem pomocniczym, nie prognozą zysku.

## Plany rozwoju (poza zakresem tej wersji)

- **M7** hot-spoty Getis-Ord Gi\*,
- **M8** model ML „luki rynkowej” (gradient boosting, walidacja przestrzenna po województwach),
- **M9** integracja CEIDG jako trzecie źródło konkurencji (kody PKD są już w katalogu),
- **M10** dokładne geokodowanie działek dla ostatnich 24 miesięcy.

Dokumentacja: [audyt przydatności (v3.5)](docs/audyt-przydatnosci.md), [specyfikacja v3](docs/superpowers/specs/2026-10-27-v3-mgla-huff-design.md), [plan v3](docs/superpowers/plans/2026-10-27-v3-mgla-huff.md), [plan v3.1 (Overture, podsumowanie, trend)](docs/superpowers/plans/2026-10-27-v31-overture-podsumowanie.md), [plan v3.2 (cała Polska)](docs/superpowers/plans/2026-10-28-v32-cala-polska.md), [plan v3.3 (mało danych o firmach)](docs/superpowers/plans/2026-10-28-v33-malo-danych.md), [plan v3.4 (wybór obszaru gestem)](docs/superpowers/plans/2026-10-28-v34-wybor-gestem.md), [kompletność danych](docs/kompletnosc-danych.md), [specyfikacja v1](docs/superpowers/specs/2026-10-26-gdzie-otworzyc-design.md), [specyfikacja v2](docs/superpowers/specs/2026-10-27-widok-dynamiczny-design.md), [plan v1](docs/superpowers/plans/2026-10-26-gdzie-otworzyc.md), [plan v2](docs/superpowers/plans/2026-10-27-widok-dynamiczny.md), [źródła danych](docs/zrodla-danych.md), [raport ETL](docs/raport-etl.md), [ściąga do obrony](docs/sciaga-do-obrony.md).
