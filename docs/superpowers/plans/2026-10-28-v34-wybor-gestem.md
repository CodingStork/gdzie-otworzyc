# v3.4 — wybór obszaru gestem: kliknięcie (okrąg) i prostokąt (plan wykonawczy)

> Dla sesji implementującej (Sonnet). Najpierw przeczytaj `CLAUDE.md`. Commit po każdym zadaniu (po polsku, prefiksy jak w §7).
> Serwer Marcina na 8000 zostaw w spokoju; do sprawdzania uruchom drugi na 8001 (`uv run uvicorn backend.app.main:app --port 8001`).
> Frontend to czysty JS + Leaflet 1.9.4: bez nowych bibliotek, bez Node. Komentarze po polsku.

## Pomysł Marcina (2026-10-28), jego słowami w skrócie

Na wejściu animacja kursora pokazuje, że można **kliknąć** albo **zaznaczyć prostokąt** (jak Wycinanie w Windows).
- **Kliknięcie** → punkt, suwak z napisem, ile km ma promień, **podgląd okręgu na żywo**, przycisk **✓**, który uruchamia analizę.
- **Prostokąt** → po zaznaczeniu można zmieniać rozmiar, **łapiąc za rogi**; też **✓**, który uruchamia analizę.
- Marcin wybrał: prostokąt rysuje się po kliknięciu przycisku **„▭ Prostokąt”** (kursor → krzyżyk). Przeciąganie mapy bez tego przycisku
  dalej ją przesuwa (tak samo na telefonie).

Cel: użytkownik nie musi rozumieć formularza „miejsce + promień + Pokaż mapę”. Wskazuje obszar na mapie i potwierdza.

## Zasady projektu (ustalone przez agenta prowadzącego)

- **Kliknięcie w mapę** w trybie Cała Polska — i w trybie Wybrane miejsce poza okręgiem lub prostokątem bieżącej analizy — tworzy **wybór**:
  - pinezka + okrąg podglądu (przerywany) o promieniu z suwaka;
  - **karta wyboru** przy punkcie (Leaflet popup albo własny div przyklejony do punktu):
    - nagłówek: najbliższa nazwa, jeśli API ją daje; inaczej „Wybrany punkt”;
    - **to, co dziś pokazuje dymek w trybie Polski** (`ui.pointPopup`: liczby w zasięgu klienta, „Otwierając tu zdobyłbyś…”,
      ostrzeżenie o luce w danych) — ładowane asynchronicznie, karta pojawia się od razu;
    - **„Obszar analizy: X km”** + suwak 1–30 km (krok 0,5 km poniżej 5 km, potem 1 km).
      Ruch suwaka od razu zmienia okrąg na mapie, bez zapytań do serwera. Zsynchronizuj go z suwakiem `radius-input` w lewym panelu
      (jedna wartość w stanie, dwa widoki);
    - **✓ Analizuj obszar** (główny przycisk) i **✕** (anuluj: znika pinezka, okrąg i karta).
  - ✓ = dzisiejsze `analyzePlace` / `run({fit:true})`: przejście w tryb „Wybrane miejsce” i analiza okręgu.
  - Kliknięcie **wewnątrz** bieżącej analizy dalej pokazuje szczegóły punktu (jak teraz). W karcie szczegółów zostaje „Ustaw tu środek obszaru”.
  - Na telefonie karta ma szerokość ekranu minus marginesy i nie może być zasłonięta przez arkusz paneli (`ui.collapseSheet()`).
- **Przycisk „▭ Prostokąt”**:
  - kontrolka Leaflet pod przyciskami +/−, z tekstem, nie samą ikoną; aktywna jest podświetlona, Esc albo ponowne kliknięcie ją wyłącza;
  - w trybie rysowania: `map.dragging.disable()`, kursor `crosshair`, przeciągnięcie (mysz i dotyk — Pointer Events) rysuje prostokąt;
    po puszczeniu tryb się wyłącza, a przesuwanie mapy wraca;
  - gotowy prostokąt: 4 **uchwyty w rogach** (draggable markery z `divIcon`, min. 18 px; na dotyk 28 px).
    Ciągnięcie rogu zmienia prostokąt, przeciwległy róg stoi w miejscu. Mapa pod spodem dalej się przesuwa;
  - przy prostokącie mała karta:
    - napis z wymiarami „12,4 × 8,1 km”;
    - **✓ Analizuj obszar** i **✕**;
    - limity jak w API: bok ≤ 60 km i ≥ 0,6 km. Poza limitem ramka jest czerwona, ✓ nieaktywny, a napis mówi „Za duży obszar — maks. 60 km boku”
      albo „Za mały obszar”.
  - ✓ = analiza prostokąta: tryb „Wybrane miejsce” z prostokątem zamiast okręgu (Task 2).
- **Animacja wprowadzająca** (Task 3):
  - nakładka na mapie przy pierwszej wizycie (`localStorage`, odczyt i zapis w try/catch; bez dostępu → pokaż);
  - ok. 6 s, 2 pętle: kursor (SVG) klika i rozchodzi się kółko, pojawia się okrąg; potem kursor jedzie do przycisku „▭ Prostokąt”
    i przeciąga przerywaną ramkę;
  - podpis: „Kliknij mapę, żeby wybrać miejsce — albo zaznacz obszar przyciskiem ▭ Prostokąt”;
  - znika po pierwszym kliknięciu, przeciągnięciu, kółku myszy albo po „Rozumiem”; przycisk „?” przy kontrolkach mapy pokazuje ją ponownie;
  - czysty CSS (`@keyframes`) + inline SVG; `prefers-reduced-motion` → bez ruchu, tylko podpis z ikonami.
- Formularz w lewym panelu (wyszukiwarka + promień + „Pokaż mapę”) **zostaje** jako druga droga, np. dla kogoś, kto zna adres.
  Wybór z wyszukiwarki tworzy ten sam „wybór” (pinezka + karta z ✓). Teksty `intro-pl` / `intro-place` zaktualizuj: najpierw gest, potem formularz.

## Task 1 — kliknięcie: karta wyboru z suwakiem i ✓

- `map.js`: funkcje `showSelection(lat, lng, radiusKm, cardEl)`, `updateSelectionRadius(km)`, `clearSelection()`.
  Okrąg podglądu przerywany, w kolorze wyróżnienia.
- `ui.js`: `selectionCard({ radiusKm, onRadius, onConfirm, onCancel })`, która zwraca element i ma miejsce na wynik `pointPopup` (wstawiany po przyjściu odpowiedzi).
- `app.js`: `onMapClick` według zasad wyżej. Stan `state.selection = { kind: 'circle', lat, lng }`.
  Dzisiejsze `preview` / `NEW_PLACE_INFO` / `highlightShow` przy kliknięciu poza okręgiem zastępuje karta z ✓.
  Zostają tylko, gdy wybór przyszedł z wyszukiwarki, a wynik już jest — wtedy też pokaż kartę.
- Hash bez zmian dla okręgu (`mode=place&lat&lng&r&n`).

## Task 2 — prostokąt: rysowanie, uchwyty, analiza

- Backend: `/api/surface` z `west/south/east/north` liczy dziś „widok na żywo” (siatka rzadsza `divisions=60`, podsumowanie „Widoczny obszar”).
  Dodaj parametr `area=rect` (domyślnie `view`). Dla `rect`:
  - `divisions=90`;
  - podsumowanie „Zaznaczony obszar: 12,4 × 8,1 km”;
  - top-5 z odstępem jak dla okręgu.
  - Testy w `tests/test_surface_api.py`.
- `map.js`:
  - kontrolka „▭ Prostokąt”, tryb rysowania, `showRect(bounds, cardEl, onChange)` z uchwytami, `clearRect()`;
  - obramowanie prostokąta wyniku (jak okrąg wyniku: przygaszenie poza nim przez `veil`, jeśli da się prosto; jeśli nie — sama ramka);
  - `renderFog` przycina już do okręgu; dla prostokąta serwer zwraca `null` poza nim, więc wystarczy promień `NO_CIRCLE`.
- `app.js`:
  - `state.selection = { kind: 'rect', bounds }`; ✓ → `state.mode = 'place'`, `state.area = { kind: 'rect', bounds }`, zapytanie z `area=rect`;
  - kliknięcie wewnątrz prostokąta wyniku → szczegóły punktu;
  - hash: `mode=place&bbox=w,s,e,n` (zamiast `lat/lng/r`); stare linki z `lat/lng/r` działają jak dotąd;
  - lewy panel w trybie prostokąta: zamiast suwaka promienia napis „Obszar: prostokąt 12,4 × 8,1 km” + link „zmień na okrąg”
    (przywraca suwak; środek = środek prostokąta).
- Na telefonie (emulacja 375×812 w `resize_window`) sprawdź rysowanie dotykiem i ciągnięcie rogów.

## Task 3 — animacja wprowadzająca

Jak w zasadach. Plik `frontend/js/intro.js` + style w `style.css`. Musi działać i wyglądać dobrze na telefonie (inne położenie przycisku).

## Task 4 — sprawdzenie w przeglądarce, dokumentacja

Scenariusze (zrzuty do `docs/screenshots/v34-*.png`, port 8001):
- (a) świeża wizyta (wyczyść `localStorage`): animacja gra, znika po kliknięciu, „?” pokazuje ją ponownie;
- (b) Cała Polska → klik w Brzeg → karta z liczbami i suwakiem → suwak na 3 km zmienia okrąg na żywo → ✓ → wynik jak w v3.3
  (36 salonów, salon × kobiety);
- (c) ✕ na karcie czyści wybór;
- (d) „▭ Prostokąt” na Wrocław ~15 × 10 km → ciągnięcie rogu → wymiary się zmieniają → ✓ → mgła tylko w prostokącie, podsumowanie
  „Zaznaczony obszar”, top-5 w prostokącie; link z `bbox` po wklejeniu w nowej karcie odtwarza wynik;
- (e) prostokąt > 60 km → czerwona ramka, ✓ nieaktywny;
- (f) telefon: klik → karta → ✓; prostokąt dotykiem; animacja się mieści;
- (g) stary link `#mode=place&…&lat&lng&r` działa; wyszukiwarka nadal działa.

Na koniec:
- `uv run pytest -v` zielone;
- zaktualizuj README (jak używać), `CLAUDE.md` (tabela §4: v3.4, §5) i ściągę, jeśli dotyczy (np. pytanie o Pointer Events / dlaczego przycisk zamiast przeciągania);
- przegląd kodu, poprawki, push na `main`;
- raport: co odbiega od planu, scenariusze, zrzuty.
