# Audyt przydatności „Gdzie otworzyć?” (2026-11-03, wersja 3.5)

> **Aktualizacja v3.6 (2026-11-03):** po testach Marcina usunięto tryb „Cała Polska” (mapa liczyła się bez kliknięcia „Analizuj”); gotowa mapa Polski służy teraz do analizy dużych obszarów. Szczegóły: `docs/zadania-dla-agenta-lokalnego.md`.

Pytanie audytu: **czy osoba, która naprawdę otwiera salon, kawiarnię, przedszkole albo firmę brukarską, podejmie na podstawie tej mapy lepszą decyzję niż bez niej?** Jeśli mapa może ją wprowadzić w błąd, to błąd krytyczny — ważniejszy niż brakująca funkcja.

## Streszczenie dla właściciela

1. Najgroźniejszy błąd był w zdaniu, które użytkownik czyta najpierw: „mniej / więcej konkurencji niż średnio w Polsce”.
2. Średnią krajową zaniżają wsie (mieszkańcy wsi jeżdżą do salonu w mieście), więc prawie każde miasto wychodziło „gęsto obsadzone”, a każda wieś „wolna” — niezależnie od prawdy.
3. Teraz porównujemy obszar z miejscami w Polsce o **podobnej gęstości zaludnienia** (5 grup: od wsi po centra miast).
4. Werdykt pada tylko wtedy, gdy różnica jest wyraźna i nie jest zwykłym przypadkiem; gdy w obszarze powinny być 1–2 firmy, mówimy uczciwie „za mało firm, żeby ocenić”.
5. Lista „Najlepsze miejsca” na mapie całej Polski wskazywała wsie i miasteczka (Rudki, Pruchnik, Bierówki) z powodu braków w danych i modelu — usunęliśmy ją; najlepsze miejsca pokazujemy dopiero dla jednej okolicy.
6. Najlepsze miejsca nie są już punktami na krawędzi okręgu (to był przypadkowy punkt stoku), a gdy różnią się o mniej niż 20%, mapa mówi, że to mniej niż dokładność danych.
7. Kolory przestały robić z różnicy 20% przepaść między bielą a czerwienią.
8. „Stylizacja paznokci” zniknęła jako osobna branża — w danych każdy salon paznokci jest salonem kosmetycznym, a osobny typ udawał „brak konkurencji”.
9. Każda branża, w której mapa czegoś ważnego nie widzi (kawiarnie i restauracje — ruch ludzi; sklepy — dyskonty; przedszkola — dzieci urodzone po spisie), ma jedno zdanie zastrzeżenia pod wyborem branży.
10. Market budowlany liczy domyślnie mieszkańców, bo rejestr pozwoleń liczy blok z setką mieszkań jak jeden dom.
11. Z interfejsu zniknęły powtórzone notatki, karta po kliknięciu jest krótsza, a podsumowanie zaczyna się od jednego zdania z odpowiedzią.
12. Liczba „klientów” z modelu jest opisana jako szacunek do porównywania miejsc, a nie prognoza sprzedaży.
13. Zostaje poważny problem modelu: na wsi i w małych miasteczkach liczba klientów jest zawyżona (model nie widzi, że ludzie dojeżdżają do miasta) — poprawka wymaga przeliczenia danych i jest pierwsza na liście „do zrobienia”.
14. Największy skok jakości dadzą nowe dane: CEIDG (firmy bez lokalu, brukarze), zamożność gmin i dojazdy do pracy z GUS, rejestr przedszkoli.
15. U siebie musisz uruchomić tylko krok `gaps` (ok. 2 min) i sprawdzić scenariusze z końca tego raportu.

---

## 1. Jak pracował zespół

Dziesięć ról pracowało osobno, potem lider zestawił ustalenia. Spory rozstrzygaliśmy liczbami z `docs/kompletnosc-danych.md`, `docs/raport-etl.md`, zrzutów ekranu i źródeł zewnętrznych (lista na końcu).

| Rola | Za co odpowiadała |
|---|---|
| 1. Ekonomista lokalizacji | model Huffa, obszary rynkowe, czynniki sukcesu lokalu |
| 2. Specjalista danych o firmach | OSM, Overture, CEIDG, REGON, PKD 2025 |
| 3. Demograf | spis 2021, dasymetria, dzieci, uchodźcy, dojazdy |
| 4. Specjalista danych budowlanych | GUNB RWDZ, opóźnienia budów, bloki vs domy |
| 5. Geostatystyk | małe liczby, efekty brzegowe, MAUP, szum |
| 6. Kartograf | skala kolorów, legenda, mapa Polski |
| 7. Projektant UX | przepływ, język, telefon, liczba decyzji |
| 8. Inżynier backendu/ETL | wykonalność bez bazy, testy, wydajność |
| 9. Adwokat diabła | przedsiębiorca otwierający trzeci salon |
| 10. Lider | plan, priorytety, rozstrzygnięcia, raport |

### Ograniczenia tego audytu (ważne)

- **Nie było prawdziwej bazy.** Sieć środowiska blokuje Geofabrik, Eurostat, Overture (S3), GUS BDL, GUNB i ULDK (odpowiedź 403), więc nie dało się pobrać nawet próbki jednego województwa. Liczby o danych pochodzą z dokumentów w repozytorium (pomiary na prawdziwej bazie z 2026-10-26…28) i ze źródeł zewnętrznych.
- **Interfejs sprawdziliśmy na syntetycznej bazie** (dwa miasta i wsie wokół współrzędnych Brzegu i Opola, wymyślone liczby; skrypt w notatkach sesji) — bez podkładu mapy, bo kafelki Esri też są zablokowane. Zrzuty `docs/screenshots/audyt-*-syntetyczne.png` pokazują wygląd i teksty, **nie prawdziwe wyniki**.
- Zmiany wymagające przeliczenia ETL opisaliśmy z komendami (sekcja 8), zamiast zgadywać ich wynik.

### Plan lidera i hipotezy (spisane przed pisaniem kodu)

Plan: (1) każda rola ocenia osobno swój obszar, (2) lider zestawia tabelę werdyktów, (3) zmiany, które da się zrobić i przetestować bez bazy, wchodzą do tego PR-a z testami, (4) reszta trafia na listę z komendami, (5) adwokat diabła ocenia wynik.

| # | Hipoteza | Kto | Wynik |
|---|---|---|---|
| H1 | Werdykt porównuje ze średnią krajową, zaniżaną przez wsie → miasta wychodzą „więcej konkurencji”, wsie „mniej” | 1, 5 | **Potwierdzona** (sekcja B1) |
| H2 | Przy kilku oczekiwanych firmach werdykt i „1 firma na X” to szum | 5 | **Potwierdzona** (B2) |
| H3 | Top-5 w małym obszarze różni się o kilkanaście procent — mniej niż dokładność danych | 5, 9 | **Potwierdzona** (Brzeg: 600 / 490 / 480 / 480 / 450) |
| H4 | Top-5 przy krawędzi okręgu/prostokąta/widoku to artefakt | 5 | **Potwierdzona w kodzie** (`top_points` brał maksimum w masce bez sprawdzania, czy to szczyt) |
| H5 | Skala p5–p99 rozciąga małe różnice na całą paletę | 6 | **Potwierdzona** (Brzeg: 310–600 = od bieli do czerwieni) |
| H6 | Top-5 mapy całej Polski wskazuje wsie z powodu braków danych i modelu | 1, 9 | **Potwierdzona** (B4, B7) |
| H7 | Dla kawiarni i restauracji „mieszkańcy” to zły popyt | 1, 3 | **Potwierdzona** (źródło: walidacja modelu Huffa na danych transakcyjnych) |
| H8 | „Paznokcie” i „barber” to podzbiory „salonu” i „fryzjera” → konkurencja zaniżona | 2 | **Potwierdzona w katalogu** |
| H9 | Dzieci < 15 lat ze spisu 2021 nie mówią o przedszkolakach w 2026 | 3 | **Potwierdzona** (urodzenia: ok. 355 tys. w 2020 → ok. 252 tys. w 2024) |
| H10 | Pozwolenia z ostatnich 24 mies. to domy, które dopiero powstaną; blok liczy się jak dom | 4 | **Potwierdzona** (budowa domu trwa średnio ok. 52 mies.; rejestr nie podaje liczby mieszkań) |
| H11 | Interfejs dubluje notatki, podpowiedź dla rzemieślników wisi zawsze, podsumowanie ma 6 wierszy bez jednego zdania odpowiedzi | 6, 7 | **Potwierdzona** (sekcja C) |
| H12 | „Otwierając tu, zdobyłbyś ok. 600 klientów” brzmi jak prognoza | 1, 9 | **Potwierdzona** (liczba zależy od A0 i kompletności danych) |
| H13 | Jednakowy zasięg klienta w mieście i na wsi zawyża wynik na wsi | 1, 5 | **Potwierdzona** na danych syntetycznych i zgodna z top-5 v3.3 (B4) — **niezweryfikowana na prawdziwej bazie** |
| H14 | Spis 2021 nie obejmuje ok. 1 mln uchodźców z Ukrainy (od 2022) | 3 | **Potwierdzona** (PESEL UKR ok. 0,99 mln w 2025) — skutek dla miast niezmierzony |

---

## 2. Zadanie A — tabela werdyktów

Liczby firm: `docs/raport-etl.md` (v3.1, po deduplikacji), firm na 10 tys. mieszkańców wg wielkości miejscowości: `docs/kompletnosc-danych.md`.

### 2.1 Typy działalności × dane o firmach i popyt

| Typ | Firm w danych | Odniesienie zewnętrzne | Gdzie dane kłamią | Czy warstwa odpowiada na pytanie przedsiębiorcy | Ryzyko | Werdykt |
|---|---|---|---|---|---|---|
| Fryzjer | 20 539 | Google Maps: 47 tys. salonów fryzjerskich i kosmetycznych łącznie (Scrap.io); zarejestrowanych 132,8 tys. (D&B, z uśpionymi i dojazdowymi) | wieś: 2,5 na 10 tys. vs 9–12 w miastach (część to prawda — dojazdy) | tak, dla salonu z lokalem; popyt z miejsca zamieszkania (nie pracy) | średnie | **ZOSTAWIĆ** |
| Barber | 9 179 | brak | zwykli fryzjerzy nie liczą się jako konkurencja barbera | częściowo | średnie | **ZOSTAWIĆ Z OSTRZEŻENIEM** (zdanie pod branżą) |
| Salon kosmetyczny | 31 339 | j.w. | kosmetyczki pracujące w domu i dojazdowe prawie nieobecne | tak, dla salonu z lokalem | średnie | **ZOSTAWIĆ Z OSTRZEŻENIEM** |
| Stylizacja paznokci | 2 910 | brak | każdy taki punkt jest też „salonem kosmetycznym” (OSM `shop=beauty`, Overture `nail_salon` w obu typach), a salony kosmetyczne robiące manicure nie liczyły się jako konkurencja | **nie** — systematycznie „mało konkurencji” | wysokie | **USUNĄĆ — scalone z salonem kosmetycznym** (stare linki prowadzą do salonu) |
| Studio tatuażu | 3 557 | niezweryfikowane (brak publicznej liczby) | klienci jadą do artysty z daleka | słabo — bliskość domu ma mały wpływ | średnie | **ZOSTAWIĆ Z OSTRZEŻENIEM** |
| Market / hurtownia budowlana | 14 291 | niezweryfikowane | duży market = mały sklep (Huff bez „atrakcyjności”); popyt z pozwoleń liczył blok jak dom | częściowo | wysokie dla „nowych budynków” | **ZOSTAWIĆ Z OSTRZEŻENIEM**, domyślny popyt → mieszkańcy |
| Sklep spożywczy | 63 478 | D&B: 90,6 tys. sklepów ogólnospożywczych (~70%) | dyskont = mały sklep; najlepsze pokrycie na wsi (15,6 na 10 tys.) | tak (zakupy blisko domu — model Huffa tu najlepiej działa) | średnie | **ZOSTAWIĆ Z OSTRZEŻENIEM** |
| Kawiarnia | 9 951 | niezweryfikowane | — | **słabo**: kawiarnie żyją z ruchu (praca, studia, turystyka), którego nie mamy; mapa wskazuje osiedla bez kawiarni | wysokie dla lokalu w centrum | **ZOSTAWIĆ Z OSTRZEŻENIEM** („wynik pasuje do kawiarni osiedlowej”) |
| Restauracja / fast food | 50 326 | GUS przez BOŚ: ok. 56 tys. restauracji i barów (~90%) | — | słabo — jak kawiarnia; badanie na danych transakcyjnych: Huff dla restauracji jest niestabilny | wysokie | **ZOSTAWIĆ Z OSTRZEŻENIEM** |
| Siłownia / fitness | 8 466 (z jogą i pilatesem) | 3 307 klubów współpracujących z kartami sportowymi (dataplace.ai, 2024) — inna definicja | sieci i małe studia liczą się tak samo | częściowo (część ćwiczy blisko pracy) | średnie | **ZOSTAWIĆ Z OSTRZEŻENIEM** |
| Przedszkole / żłobek | 16 077 | GUS 2024/25: 22,3 tys. placówek, w tym 7 tys. oddziałów przy szkołach (~70%) | oddziały przedszkolne w szkołach (zwłaszcza na wsi) rzadko są w OSM; przedszkola publiczne i prywatne razem; żłobki z przedszkolami | **słabo**: popyt „dzieci < 15 lat” ze spisu 2021 — dzisiejsze 3–6-latki urodziły się głównie po spisie | wysokie | **ZOSTAWIĆ Z OSTRZEŻENIEM**; docelowo **ZASTĄPIĆ** rejestrem placówek (RSPO) i dziećmi 0–6 z BDL |
| Brukarstwo, ogrody, okna, kuchnie, instalatorzy | 837–4 696 | tysiące–dziesiątki tysięcy (firmy bez lokalu) | prawie ich nie ma | „konkurencja” byłaby fikcją | krytyczne | **USUNIĘTE** (od v3.2, bez zmian), wrócą z CEIDG |

### 2.2 Czynniki popytu („Twoi klienci to”)

| Czynnik | Źródło | Gdzie kłamie | Werdykt |
|---|---|---|---|
| Mieszkańcy, Kobiety, Mężczyźni, 15–64, 65+ | spis 2021, kwadraty 1 km rozłożone na budynki OSM | to ludność **nocna** (miejsce zamieszkania), nie dzienna; stan z 2021 r. (bez ok. 1 mln uchodźców z Ukrainy z PESEL UKR, skupionych w dużych miastach); rozkład w kwadracie to szacunek | **ZOSTAWIĆ** (w podsumowaniu dopisek „spis 2021”) |
| Dzieci (< 15 lat) | spis 2021 | dla przedszkola zły wiek (0–14 zamiast 3–6) i zła data: urodzenia spadły z ok. 355 tys. (2020) do ok. 252 tys. (2024) | **ZOSTAWIĆ Z OSTRZEŻENIEM** (zdanie przy przedszkolu); **ZASTĄPIĆ** BDL (dzieci 0–6 wg gminy, co rok) |
| Nowe domy jednorodzinne | GUNB RWDZ, dokładność do obrębu | pozwolenie ≠ dom; budowa domu trwa średnio ok. 52 mies. od rozpoczęcia (GUS); brukarz i ogrodnik pracują przy domach **kończonych**, czyli pozwoleniach sprzed 2–4 lat | **ZOSTAWIĆ Z OSTRZEŻENIEM**; dla rzemieślników **ZASTĄPIĆ** oknem „pozwolenia sprzed 2–4 lat” albo BDL „budynki oddane do użytkowania” |
| Nowe bloki | GUNB | rejestr liczy **inwestycję**, nie mieszkania (blok na 300 mieszkań = 1) | **ZOSTAWIĆ Z OSTRZEŻENIEM** (nowa nazwa „liczba budynków, nie mieszkań”); docelowo liczba mieszkań z kubatury (kolumna jest w pliku GUNB) |
| Wszystkie nowe budynki mieszkalne | GUNB | jak wyżej: dom = blok | **ZOSTAWIĆ Z OSTRZEŻENIEM** (nazwa „dom i blok liczą się tak samo”, notatka w legendzie); już nie jest domyślny dla marketu budowlanego |

### 2.3 Warstwy i elementy wyniku

| Warstwa / element | Problem | Werdykt |
|---|---|---|
| „Gdzie otworzyć” (Huff) | liczba bezwzględna zależy od A0 i kompletności danych; na wsi zawyżona (B4) | **ZOSTAWIĆ** jako ranking, z opisem „szacunek do porównań, nie prognoza” |
| „Gdzie są klienci” | to mapa ludności (xkcd 1138), ale potrzebna jako kontekst | **ZOSTAWIĆ** (druga warstwa, nie domyślna) |
| „Gdzie są {firmy}” | zagęszczenie, bez kreskowania luk | **ZOSTAWIĆ** |
| „Gdzie budowy przybywa” | krótkie szeregi, pozwolenia ≠ budowy | **ZOSTAWIĆ Z OSTRZEŻENIEM** (bez zmian) |
| Szare kreskowanie (luki) | nie ocenia miejscowości z < 3 oczekiwanymi firmami | **ZOSTAWIĆ** (progi bez zmian — nie ma nowego pomiaru) |
| Werdykt w podsumowaniu | porównanie ze średnią krajową; szum przy małych liczbach | **ZASTĄPIĆ** — podobne miejsca + test Poissona (zrobione) |
| Top-5 w okręgu/prostokącie/widoku | krawędź, małe różnice | **ZOSTAWIĆ** po poprawkach (szczyty, notatki) |
| Top-5 na gotowej mapie Polski | wsie przez braki danych i model | **USUNĄĆ** (zrobione; zostaje podpowiedź „przybliż”) |
| Mgła na gotowej mapie Polski | po oddaleniu prawie cała Polska pomarańczowa (maksimum w piramidzie) | **ZOSTAWIĆ** jako przegląd; osobna skala na poziom — do zrobienia |

---

## 3. Zadanie B — model

### B1. Średnia krajowa jako punkt odniesienia (naprawione)

Salony kosmetyczne na 10 tys. mieszkańców (OSM + Overture): wielkie miasta 18,1, średnie 14,0, małe 10–50 tys. 13,6, miasteczka 10,9, **wsie 4,1**; średnia krajowa **8,45** (`gap_rates`). Średnia leży niżej niż w każdej klasie miast, bo ciągną ją wsie — a mieszkańcy wsi korzystają z salonów w mieście. Porównanie ze średnią krajową z definicji mówi miastom „gęsto”, wsiom „pusto”.

Przykład z prawdziwych liczb (Brzeg, okrąg 3 km, v3.3): 36 salonów, ok. 18 700 kobiet ≈ 36 300 mieszkańców.
- Wg średniej krajowej oczekiwane 30,7 salonu → 36 to 117% → „konkurencja na poziomie średniej krajowej”.
- Wg miast tej wielkości (13,6 na 10 tys.) oczekiwane 49,4 → 36 to 73%, P(X ≤ 36) = 3% → „mniej konkurencji niż w podobnych miejscach”.

Werdykt **zmienia znaczenie**. (Przykład ilustracyjny: w aplikacji klasy wyznaczamy inaczej — kwintylami ludności wg gęstości zaludnienia okolicy, nie wg wielkości miejscowości; prawdziwy wynik dla Brzegu zobaczysz po przeliczeniu kroku `gaps`.) Dla sklepów spożywczych błąd był mały (wsie 15,6 vs średnia 17,1), dla salonów, fryzjerów i restauracji duży.

**Co zrobiliśmy:** krok `gaps` liczy dla każdej komórki z ludnością, ilu mieszkańców jest w promieniu 2 km, i dzieli ludność Polski na **5 równych części** (kwintyle ważone ludnością) — bez arbitralnych progów „miasto/wieś”. Dla każdej klasy i typu: firm na mieszkańca (firma należy do klasy najbliższej komórki z ludnością). Podsumowanie liczy „oczekiwane firmy” jako Σ mieszkańcy komórki × stawka jej klasy. Kod: `etl/gaps.py: density_classes, firms_by_class`, `backend/app/analysis/service.py: area_summary`. Starsza baza bez nowych tabel → porównanie ze średnią krajową jak wcześniej (napis to mówi).

### B2. Małe liczby (naprawione)

Liczba firm w obszarze jest losowa. Przy 3 oczekiwanych salonach brak salonu zdarza się w 5% przypadków, jeden salon w 15%. Stary werdykt mówił „mniej konkurencji” już przy 0 firm w obszarze, w którym spodziewamy się 0,5 firmy, i „więcej” przy 8 firmach zamiast 5.

**Co zrobiliśmy:** `service.verdict(observed, expected)`:
- oczekiwane < 3 → „Za mało firm, żeby ocenić konkurencję”;
- „mniej” tylko gdy firm ≤ 80% oczekiwanych **i** P(X ≤ firm) < 10% (X ~ Poisson);
- „więcej” tylko gdy ≥ 125% **i** P(X ≥ firm) < 10%;
- inaczej „typowa dla podobnych miejsc”.

| Oczekiwane | „mniej” od | „więcej” od |
|---|---|---|
| 3 | 0 firm | 6 firm |
| 5 | 1 | 9 |
| 10 | 5 | 15 |
| 20 | 13 | 27 |
| 50 | 40 | 63 |

Prawdziwe firmy skupiają się bardziej niż w rozkładzie Poissona, więc test jest raczej zbyt pobłażliwy niż zbyt surowy. „Mniej konkurencji” dostało dopisek „sprawdź na miejscu, czy na mapach nie brakuje firm” — to typowy objaw luki w danych.

### B3. Najlepsze miejsca (naprawione)

- **Krawędź:** `top_points` brał największe wartości w okręgu. Gdy osiedle leży tuż za okręgiem, największe wartości są na jego krawędzi i „najlepszym miejscem” zostaje przypadkowy punkt stoku. Teraz kandydatem jest tylko **lokalny szczyt** (wszyscy 8 sąsiedzi w obszarze i żaden wyższy, `surface.peaks_and_edge`), a gdy na krawędzi jest wyżej niż w najlepszym szczycie, odpowiedź ma `top_edge` i interfejs mówi „warto przesunąć obszar w tę stronę”.
- **Małe różnice:** Brzeg 3 km: 600 / 490 / 480 / 480 / 450. Jeśli miejsca różnią się o < 20%, pod listą pojawia się zdanie, że to mniej niż dokładność danych i decydują lokal, czynsz, ruch.

### B4. Jednakowy zasięg w mieście i na wsi (do zrobienia — najważniejsze)

Zasięg klienta (np. 1,5 km dla salonu) jest ten sam wszędzie, a wpływ ucinamy po 4 × zasięg (6 km). Mieszkanka wsi, która jeździ do salonu w mieście 8 km dalej, w modelu „nie ma konkurencji” i 73% szansy, że wybierze nowy salon w swojej wsi. Na danych syntetycznych: wieś z 430 kobietami w promieniu 1 km dostaje „ok. 500 klientów”. To ten sam mechanizm, który wyniósł na szczyt mapy Polski Rudki, Pruchnik i Bierówki (v3.3). **Teraz:** przy werdykcie „za mało firm” lista najlepszych miejsc ma zdanie, że liczba klientów jest zawyżona. **Poprawka:** zasięg zależny od klasy gęstości (np. wieś ×3) albo większe A0 w klasach 0–1, skalibrowane tak, by suma E nowych firm w klasie zgadzała się z liczbą firm; wymaga pomiaru na prawdziwej bazie i przeliczenia kroku `national` (sekcja 8).

### B5. Każda firma jest tak samo atrakcyjna (do zrobienia)

Huff ma tu atrakcyjność 1 dla wszystkich: Biedronka = sklepik osiedlowy, Castorama = sklep z narzędziami. Dla sklepów spożywczych i marketów budowlanych to zaniża konkurencję sieci. Poprawka: tagi `brand` (OSM) i `brands` (Overture) → waga sieci (np. dyskont 3, market budowlany 5). Do tego czasu — zdanie pod branżą.

### B6. Luki w danych (bez zmian, z zastrzeżeniem)

Progi `GAP_*` zostały — nie było nowego pomiaru (CLAUDE.md zabrania zmiany bez pomiaru). Wiadomo, że miejscowości z < 3 oczekiwanymi firmami nie są oceniane; nowy werdykt „za mało firm” mówi to samo w podsumowaniu. Kreskowanie wciąż porównuje ze średnią krajową, a werdykt — z podobnymi miejscami; to świadoma niespójność do czasu pomiaru (przejście luk na stawki klas zmieni udział ludności w lukach, który sprawdza `etl.sanity`).

### B7. Mapa całej Polski (częściowo)

Piramida „maksimum z dzieci” sprawia, że po oddaleniu prawie cały kraj jest pomarańczowo-czerwony (raport v3.2: mediana res 6 = 458 przy skali 116–993). Mapa jest przeglądem, ale ranking miejscowości z całego kraju mieszałby rynki o różnej zamożności i dojazdach, których nie mamy — **top-5 usunęliśmy** z gotowej mapy (zostaje podpowiedź „przybliż do swojej okolicy”). Osobna skala na poziom piramidy — do zrobienia.

### B8. Liczba z modelu Huffa (naprawione w opisie)

„Otwierając tu, zdobyłbyś ok. 600 klientów” → „Szacunek modelu: ok. 600 klientów dla nowej firmy w tym miejscu (do porównywania miejsc, nie prognoza sprzedaży)”. Pytajnik „Gdzie otworzyć” wymienia, czego model nie zna: miejsca pracy, zamożności, wielkości konkurentów.

### B9. Skala kolorów (naprawione)

Skala p5–p99 w Brzegu to 310–600: różnica 1,9× dostawała całą paletę, więc 20% różnicy wyglądało jak biel kontra czerwień. Teraz skala obejmuje **co najmniej 10×** (`colors.js: MIN_RATIO`, `national._scale_json`); o jeden odcień ciemniej = ok. 30–80% więcej. Pytajnik legendy nie mówi już nieprawdy („każdy krok to podwojenie”).

**Aktualizacja v3.6:** minimum zmienione na **4×**, a skala liczy się z komórek widocznych na ekranie — tester pokazał, że przy 10× w centrum Bydgoszczy punkty z 4 700 i 7 400 mężczyznami w okręgu miały prawie ten sam kolor (sekcja 29 ściągi).

---

## 4. Zadanie C — szum informacyjny (inwentarz interfejsu)

| Element | Co mówił | Problem | Decyzja |
|---|---|---|---|
| Podpowiedź dla rzemieślników | 3 zdania, zawsze widoczna | wisi także przy wybranym salonie | **tylko bez branży**, 1 zdanie |
| Ostrzeżenie „dane niepełne” (medium) | w prawym panelu pod listą | daleko od decyzji | **pod wyborem branży**, razem z nowym zastrzeżeniem branży; w prawym panelu nie powtarzamy |
| Podpowiedź pod suwakiem zasięgu (gotowa mapa) | długa | ok | **skrócona** |
| Notatka „Mapa Polski policzona dla typowego zasięgu…” | prawy panel | dubel podpowiedzi pod suwakiem | **usunięta** (API) |
| Notatka „Szare kreskowanie…” | prawy panel, 3 zdania | dubel pytajnika w legendzie | **usunięta** (API) |
| Notatka legendy mapy Polski | 1 długie zdanie | ok | **skrócona** |
| Podsumowanie obszaru | 6–7 wierszy, werdykt na końcu | brak odpowiedzi w pierwszym zdaniu | **werdykt pierwszy**, potem 3 wiersze liczb, jedno zdanie porównania |
| „Obszar: punkt na mapie, promień 3 km” | — | nic nie mówi | **„Obszar: Brzeg, promień 3 km”** (najbliższe miasto) |
| „Kobiety: ok. 18 700” | — | bez daty | **„(spis 2021)”** |
| Karta wyboru po kliknięciu | liczby + lista 5 najbliższych firm + suwak + ✓ | zasłaniała mapę (zwłaszcza na telefonie) | **bez listy firm** (jest w szczegółach po analizie) |
| Dymek: „Otwierając tu, zdobyłbyś…” | prognoza | patrz B8 | **„Szacunek modelu… nie prognoza”** |
| Top-5 mapy Polski | wsie | patrz B7 | **usunięte** |
| Pytajnik legendy | „każdy krok = podwojenie” | nieprawda | **poprawiony** |
| Pytajnik podsumowania | średnia krajowa | nieaktualny | **„podobne miejsca” + małe liczby** |
| Suwak „Przezroczystość mgły” | — | zbędny dla laika | zostaje (decyzja Marcina z v3) |
| Przełącznik „Cała Polska / Wybrane miejsce” | — | od v3.4 tryb zmienia się sam po ✓ | zostaje; propozycja niżej (D) |

---

## 5. Zadanie D — przepływ w ≤ 3 krokach

1. **Wybierz branżę** — klienci ustawiają się sami (pierwszy sugerowany czynnik), pod branżą od razu jedno zdanie, czego mapa nie widzi.
2. **Kliknij swoją okolicę** (albo „▭ Prostokąt”) → karta z liczbami punktu → **✓**.
3. **Przeczytaj pierwsze zdanie** po prawej, np. (liczby ilustracyjne z przykładu B1): „Mniej konkurencji niż zwykle w podobnych miejscach — sprawdź na miejscu…”, pod nim „Kobiety: ok. 18 700 (spis 2021) · Salony kosmetyczne: 36 · 1 firma na ok. 520 kobiet — w podobnych miejscach 1 na ok. 380” i najlepsze miejsca z ulicami.

Wybór gestem z v3.4 zostaje bez zmian (nie było powodu, by go cofać). Propozycje na później (do zrobienia, bez dowodu z testów z użytkownikiem): zastąpić przełącznik trybu przyciskiem „← Mapa Polski” po analizie; schować „Co pokazać na mapie” do legendy (zakładki nad paskiem kolorów); pokazać na wyniku wszystkie firmy z obszaru jako kropki (raz, bez zapytań przy ruchu mapy) — przedsiębiorca sam sprawdzi, czy zna „swoich” konkurentów, czyli czy dane są pełne.

---

## 6. Zadanie E — nowe źródła

| Źródło | Co daje | Dostęp i licencja | Koszt pracy | Wpływ na jakość decyzji |
|---|---|---|---|---|
| **CEIDG** (dane.biznes.gov.pl) | jednoosobowe firmy z PKD i adresem wykonywania działalności — brukarze, ogrodnicy, kosmetyczki bez lokalu | bezpłatny token JWT po wniosku (Profil Zaufany); dane publiczne; **dokumentacja API tylko po zalogowaniu — schematu odpowiedzi nie dało się sprawdzić** | duży: pobranie po PKD i statusie AKTYWNY, geokodowanie adresów (PRG punkty adresowe GUGiK), deduplikacja z OSM/Overture | **największy**: powrót rzemieślników, pełniejsza konkurencja salonów |
| PKD 2025 | od 2025 r. fryzjerstwo to **96.21.Z**, kosmetyka **96.22.Z** (dawniej oba 96.02.Z); okres przejściowy do końca 2026 r. | — | mały: w CEIDG szukać obu klasyfikacji; pozostałe kody sprawdzić w kluczu przejścia GUS (niezweryfikowane) | warunek poprawnego CEIDG |
| **GUS BDL** (API bez klucza, limity dla anonimowych) | dzieci 0–6 wg gminy (co rok), wynagrodzenia (powiat), dochody gmin z PIT na mieszkańca (zamożność), budynki oddane do użytkowania, podmioty REGON wg sekcji PKD (gmina) | otwarte | średni: tabela gmin + granice (PRG) | duży: zamożność i aktualne dzieci; REGON wg gmin do kalibracji luk |
| Dojazdy do pracy GUS (przepływy ludności związane z zatrudnieniem) | ludność dzienna gmin | publikacja GUS, otwarte (format niezweryfikowany) | średni | duży dla kawiarni, restauracji, siłowni |
| **RSPO** (rejestr szkół i placówek oświatowych MEN) | wszystkie przedszkola, punkty i oddziały przedszkolne z adresem | publiczna wyszukiwarka; istnienie API i współrzędnych **niezweryfikowane** | średni | duży dla przedszkoli (zamiast OSM ~70%) |
| Rejestr żłobków i klubów dziecięcych (MRiPS) | żłobki | publiczny wykaz (format niezweryfikowany) | mały | rozdzielenie żłobka od przedszkola |
| GUNB — kolumna `kubatura` (już pobierana) | przybliżona liczba mieszkań w bloku | mamy | mały (ETL `permits`) | bloki przestaną liczyć się jak jeden dom |
| OSM `brand`, Overture `brands` | atrakcyjność sieci w modelu Huffa | mamy (ODbL / CDLA) | mały–średni | sklepy, markety budowlane |
| REGON (BIR1) | dane jednej firmy po NIP/REGON | klucz na wniosek; **brak wyszukiwania hurtowego po PKD** | — | nie nadaje się do mapy |
| Google Places | bardzo pełne dane | regulamin zabrania trwałego przechowywania; scrapowanie łamie regulamin | — | **nie używamy** |

---

## 7. Lista zmian — wpływ na decyzję / koszt

| # | Zmiana | Wpływ | Koszt | Status |
|---|---|---|---|---|
| 1 | Werdykt wg podobnych miejsc (kwintyle gęstości) zamiast średniej krajowej | krytyczny | średni | **zrobione w tym PR** (wymaga kroku `gaps`) |
| 2 | Werdykt tylko przy istotnej różnicy (Poisson), „za mało firm” przy < 3 oczekiwanych | krytyczny | mały | **zrobione** |
| 3 | Bez top-5 na gotowej mapie Polski | wysoki | mały | **zrobione** |
| 4 | Top-5 tylko ze szczytów + zdania o krawędzi i małych różnicach | wysoki | mały | **zrobione** |
| 5 | Paznokcie scalone z salonem kosmetycznym | wysoki | mały | **zrobione** |
| 6 | Zastrzeżenie branży pod jej wyborem (kawiarnia, restauracja, sklep, market, przedszkole, barber, tatuaż, salon, fitness) | wysoki | mały | **zrobione** |
| 7 | Skala kolorów co najmniej 10× | średni | mały | **zrobione** |
| 8 | Market budowlany: domyślnie mieszkańcy; uczciwe nazwy popytu z pozwoleń, notatka „blok = 1 budynek” | średni | mały | **zrobione** |
| 9 | Podsumowanie od werdyktu, karta bez listy firm, bez dubli notatek, nazwa miasta, „spis 2021”, ostrożny opis Huffa | średni | mały | **zrobione** |
| 10 | Zasięg klienta zależny od gęstości (wieś > miasto), kalibracja | krytyczny | duży, wymaga bazy | do zrobienia |
| 11 | CEIDG (+ PKD 2025, geokodowanie PRG) | krytyczny | duży | do zrobienia (token Marcina) |
| 12 | Zamożność (BDL: PIT na mieszkańca) i ludność dzienna (dojazdy) | wysoki | średni | do zrobienia |
| 13 | Atrakcyjność sieci (`brand`) w Huffie | wysoki dla sklepów | średni | do zrobienia |
| 14 | Przedszkola z RSPO, dzieci 0–6 z BDL | wysoki dla przedszkoli | średni | do zrobienia |
| 15 | Pozwolenia „sprzed 2–4 lat” dla rzemieślników; liczba mieszkań z kubatury | średni | mały–średni | do zrobienia |
| 16 | Kropki wszystkich firm na wyniku (sprawdzalność danych) | średni | mały | do zrobienia |
| 17 | Luki wg stawek klas gęstości + test Poissona zamiast progu ¼ | średni | średni, wymaga pomiaru | do zrobienia |
| 18 | Osobna skala kolorów dla poziomów piramidy mapy Polski | niski–średni | średni | do zrobienia |

---

## 8. Co trzeba przeliczyć u siebie (komendy)

Tylko krok `gaps` (nowe tabele `density_cells`, `density_rates`; ok. 2 min, sąsiedzi w 2 km liczą się teraz raz zamiast 11 razy). Zatrzymaj serwer (blokada DuckDB), potem:

```powershell
uv run python -m etl.run_all --only gaps
uv run python -m etl.sanity
start.bat
```

Bez tego aplikacja działa, ale werdykt porównuje ze średnią krajową (napis „średnio w Polsce”), a `etl.sanity` zgłosi brak tabel `density_cells` / `density_rates`. Krok `national` **nie** wymaga przeliczenia (zmiana domyślnego popytu marketu budowlanego korzysta z istniejącej warstwy; warstwy „paznokci” zostają w bazie nieużywane).

## 9. Co przetestować (scenariusze dla Marcina)

1. Cała Polska, salon × kobiety: zamiast listy najlepszych miejsc jest podpowiedź „przybliż mapę”, pod branżą zdanie o salonach bez lokalu.
2. Kliknij Brzeg → karta bez listy firm → suwak 3 km → ✓: pierwsze zdanie po prawej to werdykt; „Obszar: Brzeg, promień 3 km”; porównanie „w podobnych miejscach 1 na ok. …”. Zapisz, co wyszło (przed audytem: „na poziomie średniej krajowej”, 1 na 520 vs 610).
3. Olsztynek 3 km: nadal „Nie da się ocenić — za mało danych o firmach”.
4. Mała wieś, okrąg 1 km: „Za mało firm, żeby ocenić konkurencję”, pod listą zdanie o zawyżonej liczbie klientów.
5. Kawiarnia we Wrocławiu (centrum i osiedle): zdanie o ruchu pod branżą; czy ranking ma sens.
6. Stary link z `type=nails` → otwiera salon kosmetyczny.
7. Telefon: karta wyboru mieści się nad arkuszem, werdykt widać od razu w „Wnioskach”.

---

## 10. Przegląd adwokata diabła (przedsiębiorca otwierający trzeci salon)

**Czy teraz podjąłbym lepszą decyzję?** W mieście — **tak, ostrożnie lepszą niż wcześniej**: mapa nie mówi mi już „za dużo konkurencji” tylko dlatego, że jestem w mieście, nie straszy mnie różnicą 20% w kolorze, nie każe otwierać salonu w Pruchniku i mówi wprost, kiedy nie wie. Najbardziej przydaje mi się teraz pierwsze zdanie podsumowania i liczba salonów, którą mogę sprawdzić z tym, co znam z okolicy.

**Co dalej jest dla mnie bezużyteczne albo mylące:**
- Na wsi i w miasteczku liczba „klientów” jest zawyżona — mapa sama to mówi, ale nadal pokazuje czerwień. To pierwsza poprawka (B4), zanim ktoś zacznie z tego korzystać na terenach wiejskich.
- Nie widzę zamożności ani tego, gdzie ludzie pracują — dla salonu premium i kawiarni w centrum to połowa decyzji.
- Nie widzę konkurentów jako kropek na wyniku — chcę sprawdzić, czy „moje” trzy salony z ulicy są w danych.
- Kawiarnia i restauracja: z zastrzeżeniem mapa jest uczciwa, ale niewiele mi daje poza mapą konkurencji.
- Brukarz: dalej tylko „gdzie się buduje”, i to z pozwoleń, które są 2–4 lata przed moją pracą.

**Wniosek lidera:** dla salonu, fryzjera, sklepu spożywczego i przedszkola w mieście przedsiębiorca podejmie teraz lepszą decyzję niż bez mapy, bo mapa przestała go wprowadzać w błąd w trzech najczęstszych sytuacjach (miasto vs średnia, małe liczby, ranking kraju). Dla wsi, gastronomii i rzemieślników mapa mówi uczciwie, czego nie wie, ale lepszej decyzji jeszcze nie umożliwia — to zadania 10–15 z listy, z których 10 (zasięg zależny od gęstości) robimy jako pierwsze po przetestowaniu tej wersji.

---

## Źródła zewnętrzne

- Liczba salonów (D&B, Google Maps): [wiadomoscikosmetyczne.pl](https://www.wiadomoscikosmetyczne.pl/biznes-kosmetyki/salon-kosmetyczny/salony-beauty-licza-na-sylwestra-ich-zadluzenie-to-prawie-55-mln-zl-2530897), [scrap.io](https://scrap.io/pl/baza-salonow-fryzjerskich), [rp.pl](https://pro.rp.pl/raporty-ekonomiczne/art41725071-w-dekade-liczba-salonow-pieknosci-sie-podwoila)
- PKD 2025 (96.21.Z / 96.22.Z, okres przejściowy): [wiadomoscikosmetyczne.pl](https://www.wiadomoscikosmetyczne.pl/biznes-kosmetyki/salony-beauty-musza-uwazac-na-automatyczna-zmiane-kodow-pkd-na-czym-to-polega-2538464), [kb.pl](https://kb.pl/aktualnosci/prawo-i-przepisy/nowe-kody-pkd/), [ZUS](https://www.zus.pl/en/-/pkd-2025-sprawd%C5%BA-czy-tw%C3%B3j-kod-jest-aktualny)
- Wychowanie przedszkolne 2024/25 (22,3 tys. placówek): [prawo.pl](https://www.prawo.pl/oswiata/liczba-uczniow-w-polsce-2025,535575.html), [GUS](https://publikacje.new.stat.gov.pl/en/publications-portal/education-school-year-20242025-preliminary-data)
- Kluby fitness (3 307, dataplace.ai): [wiadomoscihandlowe.pl](https://www.wiadomoscihandlowe.pl/franczyza-w-handlu/franczyza-spozywcza/franczyzobiorcy-coraz-chetniej-otwieraja-kluby-fitness-to-branza-przyszlosci-2523623)
- Urodzenia (ok. 252 tys. w 2024): [money.pl](https://www.money.pl/gospodarka/niepokojace-dane-tak-spadla-liczba-polakow-7119827218135840a.html), [interia.pl](https://biznes.interia.pl/gospodarka/news-w-2024-r-ubylo-prawie-150-tys-polakow-jakby-zniknela-zielona,nId,7902536)
- Obywatele Ukrainy (PESEL UKR, zezwolenia): [bankier.pl](https://www.bankier.pl/wiadomosc/W-Polsce-przebywa-blisko-milion-Ukraincow-poslugujacych-sie-numerami-PESEL-8846980), [UdSC](https://www.gov.pl/attachment/b3d326f5-4035-4398-9748-21c195865a59)
- Czas budowy domu (ok. 52 mies., GUS): [kb.pl](https://kb.pl/porady/ile-srednio-trwa-budowa-domu-w-polsce-znacznie-dluzej-niz-moze-sie-wydawac)
- Model Huffa na danych transakcyjnych (restauracje niestabilne): [arXiv 1902.03488](https://arxiv.org/pdf/1902.03488); model Huffa zależny od pory dnia: [UW–Madison](https://geography.wisc.edu/geods/wp-content/uploads/sites/28/2022/05/2020_TGIS_DynamicHuffModel.pdf)
- API GUS BDL (dostęp anonimowy, limity): [opis metod](https://api.stat.gov.pl/Content/files/bdl/Methods_Description_API_BDL_v1.pdf)
- RSPO (wyszukiwarka MEN): [portaloswiatowy.pl](https://www.portaloswiatowy.pl/komunikaty-men-i-cke/men-przedstawia-wyszukiwarke-szkol-i-placowek-15711.html)
