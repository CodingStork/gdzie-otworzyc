# Zadania dla agenta lokalnego (v3.6, 2026-11-03)

Ten plik jest dla agenta AI, który działa **na komputerze Marcina** i może sterować komputerem (przeglądarka, terminal, zrzuty ekranu).
Napisał go agent z sesji w chmurze, który **nie miał prawdziwej bazy danych** (sieć blokowała Geofabrik, Eurostat, Overture, GUS, GUNB, ULDK,
unpkg i kafelki Esri) — wszystko sprawdził na bazie syntetycznej. Twoje zadanie: sprawdzić to na prawdziwych danych i dokończyć to,
czego nie dało się zrobić bez nich. Najpierw przeczytaj `CLAUDE.md` (zasady pracy z Marcinem, końce linii CRLF, autor commitów).

## 1. Co zgłosił Marcin (2026-11-03) i co z tym zrobiono

| Uwaga Marcina | Co zrobiono w v3.6 | Gdzie w kodzie |
|---|---|---|
| Zaznaczył prostokąt, kliknął „Analizuj” → „wybierz branżę lub klientów”; po wybraniu klientów mapa policzyła się sama (dla całej Polski), choć nie kliknął „Analizuj” | Usunięty przełącznik „Cała Polska / Wybrane miejsce” i automatyczna mgła. Nic nie liczy się przed „Analizuj”. Karta przy obszarze nie ma przycisku „Analizuj”, dopóki nie wybrano branży lub klientów — zamiast niego jest zdanie, co wybrać, a pola w lewym panelu pulsują | `app.js: updateCardReady, confirmSelection, onFormChange`; `ui.js: areaCard, settingsAttention` |
| Okrąg po kliknięciu ma mieć stały rozmiar na ekranie (ok. 20%), kropkę na krawędzi do zmiany promienia, kropkę w środku do przesuwania, pole z km; mapa ma się płynnie wyśrodkować | Zrobione: promień = 20% krótszego boku mapy (przy widoku Polski ~200 km, w mieście kilka km), `map.panTo` z animacją, kropki to przeciągalne znaczniki Leaflet, pole „Promień: [ ] km” w karcie (przecinek i kropka) | `app.js: beginCircle, setCircleRadius`; `map.js: showCircle, kmForScreenFraction, panTo` |
| Duży okrąg (województwo) musi dać się zbadać | Okrąg > 30 km i prostokąt > 60 km boku (do 350 km / 700 km) liczy się z **gotowej mapy Polski** (krok ETL `national`, typowy zasięg) przyciętej do obszaru, z podsumowaniem; bez listy najlepszych miejsc (audyt: na dużym obszarze ranking zawyża wsie) | `backend/app/analysis/national.py: run_area`; `routes.py: surface` |
| Bez domyślnego narzędzia: użytkownik wybiera okrąg albo prostokąt z lewej; animacja ma to pokazać, a po wyborze — jak użyć narzędzia. Stara animacja klikała w Litwę | Przyciski „◯ Okrąg” / „▭ Prostokąt” w kroku 1 lewego panelu, bez domyślnego wyboru. Animacja w dwóch krokach: kursor jedzie do przycisków; po wyborze pokazuje okrąg z kropkami albo rysowanie prostokąta — zawsze na środku mapy (przy starcie: Polska) | `intro.js`, `style.css` (sekcja animacji) |
| „Mężczyźni” w Bydgoszczy: centrum prawie jednego koloru, a kliknięcia dają 4 700 i 7 400 | (1) Skala kolorów liczy się z wartości **widocznych na ekranie** i przelicza się po przybliżeniu (bez zapytań do serwera). (2) Minimalna rozpiętość skali 4× zamiast 10× (z audytu v3.5). (3) Dymek pokazuje „Kolor mapy w tym miejscu: …” — mapa pokazuje klientów ważonych odległością (także spoza okręgu), a dymek liczy ludzi w okręgu, więc to dwie różne liczby | `app.js: visibleValues, drawLayer, valueAt`; `colors.js: MIN_RATIO`; `ui.js: pointPopup` |
| „Proste testy symulujące użytkownika chyba nie istnieją” | 14 testów E2E w prawdziwej przeglądarce (Playwright): każdy to jeden scenariusz z perspektywy użytkownika | `tests/e2e/test_uzytkownik.py`, `tests/e2e/conftest.py`, `tests/e2e/synthetic.py` |

## 2. Przygotowanie (na komputerze Marcina)

1. **Nie zatrzymuj serwera Marcina bez pytania** (port 8000). Swój uruchamiaj na porcie 8001. ETL i serwer nie mogą działać naraz.
2. Pobierz zmiany (gałąź z PR-a v3.6 albo `main` po scaleniu), potem:
   ```powershell
   uv sync
   uv run playwright install chromium
   uv run pytest -q
   ```
   Oczekiwane: wszystkie testy zielone (ok. 300, w tym 14 E2E). Jeśli E2E są pominięte, sprawdź, czy `playwright install` się udał.
3. Jeśli Marcin nie uruchomił jeszcze kroku z v3.5 (tabele „podobnych miejsc”): zatrzymaj serwer (za jego zgodą) i
   ```powershell
   uv run python -m etl.run_all --only gaps
   uv run python -m etl.sanity
   ```
4. Serwer do sprawdzania: `uv run uvicorn backend.app.main:app --port 8001`, przeglądarka na `http://localhost:8001`
   (wyczyść `localStorage`, żeby zobaczyć animację jak przy pierwszej wizycie).

## 3. Scenariusze do przeklikania na prawdziwych danych (zrzuty do `docs/screenshots/v36-*.png`)

Przy każdym zadaj sobie pytanie z `CLAUDE.md`: **czy osoba otwierająca firmę podjęłaby lepszą decyzję i czy nic jej nie zmyli?**

| # | Scenariusz | Co sprawdzić | Zapisz |
|---|---|---|---|
| a | Pierwsza wizyta | Animacja wskazuje przyciski po lewej (nie klika w mapę ani w Litwę); po wyborze „Okrąg” pokazuje okrąg z kropkami na środku Polski | zrzut |
| b | **Bydgoszcz, mężczyźni** (scenariusz Marcina): „▭ Prostokąt” ok. 30 × 22 km, bez branży — karta bez „Analizuj”, pola pulsują; wybierz „Mężczyźni” — **nic się nie liczy**; „Analizuj”; przybliż do centrum | Czy po przybliżeniu centrum ma różne odcienie tam, gdzie dymek daje 4 700 i 7 400? Porównaj liczbę „Kolor mapy w tym miejscu” w obu punktach — jeśli różnią się mało (np. < 20%), kolor słusznie jest podobny, a różnica w okręgu 0,6 km to inna wielkość | dwa dymki, legenda przed/po przybliżeniu |
| c | Widok województwa (z ≈ 7), „Okrąg”, klik w Bydgoszcz | Promień ok. 100–150 km, karta mówi „Duży obszar”; czas od „Analizuj” do wyniku (cel < 5 s); czy mgła nie jest „schodkowa” (pikseloza gotowej mapy przy granicy okręgu) | czas, zrzut |
| d | Cała Polska (z = 6), okrąg na środek kraju (~300 km) | Czas odpowiedzi i pamięć serwera; czy podsumowanie ma sens (kobiety ~18 mln?, salony ~30 tys.?) | czas, zrzut |
| e | Brzeg, salon, okrąg 3 km | Werdykt (w v3.4: „na poziomie średniej krajowej”) — zanotuj nowy; czy top-5 ma notatkę o małych różnicach | zrzut podsumowania |
| f | Wrocław, kawiarnia, okrąg 5 km w centrum i na osiedlu | Zdanie o ruchu pod branżą; czy ranking ma sens | zrzuty |
| g | Pole km: wpisz „2,5”, „120”, „abc” | Okrąg się zmienia; przy 120 mapa się oddala; „abc” wraca do poprzedniej wartości | — |
| h | Telefon (narzędzia deweloperskie, 375 × 812) i — jeśli się da — prawdziwy telefon | Kropki okręgu da się złapać palcem; karta mieści się nad arkuszem; zakładka „Ustawienia” pulsuje, gdy trzeba wybrać klientów | zrzuty |

Pomiar czasów (PowerShell, serwer na 8001):
```powershell
Measure-Command { Invoke-WebRequest "http://localhost:8001/api/surface?type=beauty&demand=pop_f&lat=53.12&lng=18.0&radius_km=150&reach_km=1.5&px=1000" }
Measure-Command { Invoke-WebRequest "http://localhost:8001/api/surface?type=beauty&demand=pop_f&lat=52.0&lng=19.4&radius_km=300&reach_km=1.5&px=1000" }
```
Jeśli duży obszar trwa > 5 s: najdroższe jest zapewne `area_summary` (komórki res 7 przez `load_demand` i `density_cells` res 9 dla całego
prostokąta obejmującego okrąg). Poprawka: sumy w SQL (`GROUP BY cls` z warunkiem odległości w zapytaniu) zamiast pobierania komórek do Pythona.

## 4. Co chciałbym zmienić, a nie mogłem (potrzebna prawdziwa baza albo sterowanie komputerem)

Kolejność = wpływ na decyzję przedsiębiorcy / koszt.

1. **Zasięg klienta zależny od gęstości (najważniejsze, audyt B4).** Na wsi model zawyża liczbę klientów, bo nie widzi firm w mieście dalej
   niż 4 × zasięg. Metoda: dla każdej klasy gęstości z `density_rates` (kwintyle 0–4) dobierz mnożnik zasięgu `m_k` (np. 1, 1,5, 2, 3, 4
   od miasta do wsi) tak, żeby w każdej klasie suma `E` nowej firmy postawionej w miejscach istniejących firm była zbliżona do liczby
   mieszkańców klasy podzielonej przez liczbę firm (prosty test kalibracji). Potem przeliczyć `uv run python -m etl.run_all --only national --force`
   (ok. 13 min). Zmienić: `analysis/surface.py` (zasięg per źródło popytu), `layers.py`, testy. Opisać w ściądze.
2. **Sprawdzić kolory na prawdziwych danych.** Czy `MIN_RATIO = 4` (`colors.js`) i skala z widocznych komórek dają czytelne różnice
   w Bydgoszczy i Warszawie, a nie przesadzają w Brzegu? Jeśli najciemniejsze odcienie YlOrRd pod przezroczystością 0,85 zlewają się,
   rozważyć mniejszą przezroczystość górnej części skali (`colors.js: fogAlpha`) — nie zmieniać palety na tęczową (CLAUDE.md §4).
3. **Pikseloza mgły dla dużych obszarów** (pierwszy zrzut Marcina: schodki przy granicy) — gotowa mapa Polski ma komórki H3 res 7–8 i jest
   wypełniana „najbliższą komórką” (`national.run_national: to_grid`). Można wygładzić: siatka odpowiedzi gęstsza niż 4 px albo interpolacja
   z sąsiednich komórek zamiast najbliższej.
4. **Kropki wszystkich firm na wyniku** (jeden raz po „Analizuj”, `/api/poi` dla obszaru): przedsiębiorca sam sprawdzi, czy zna „swoich”
   konkurentów — czyli czy dane są pełne.
5. **CEIDG** (token Marcina w `.env`, nigdy w czacie ani repo) — `CLAUDE.md` §6 pkt 3.
6. **Testy E2E na Windows:** czy przechodzą u Marcina (`uv run pytest tests/e2e -v`). W chmurze zauważono, że bardzo szybkie kręcenie
   kółkiem w przeglądarce bez okna zawiesza animację przybliżania Leaflet — testy używają przycisku „+”. Jeśli na Windows coś jest
   niestabilne, dopisz `page.wait_for_timeout` w miejscu animacji, nie wyłączaj testu.
7. Pozostałe punkty z `docs/audyt-przydatnosci.md`, sekcja 7 (zamożność z BDL, ludność dzienna, atrakcyjność sieci, RSPO, kubatura GUNB).

## 5. Na koniec

- Zaktualizuj `CLAUDE.md` (tabela §4, stan §5, plan §6), README i ściągę, gdy coś zmienisz w metodzie.
- Commity po polsku z prefiksami, autor `164074465+CodingStork@users.noreply.github.com`, **zachowaj końce linii CRLF** w plikach, które je mają.
- Marcinowi streść wyniki w czacie, prostym językiem, ze zrzutami — on nie czyta plików md.
