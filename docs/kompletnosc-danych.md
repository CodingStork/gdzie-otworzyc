# Kompletność danych o firmach (analiza 2026-10-28, stan v3.1)

Dla agentów: co wiemy o tym, jak pełna jest tabela `poi` (OSM + Overture po deduplikacji), wg typu i wielkości miejscowości.
Skrypt analizy był jednorazowy (scratchpad); metoda poniżej, żeby dało się go odtworzyć.

## Metoda
- Każdą komórkę H3 res 9 z ludnością i każdą firmę przypisujemy do najbliższego węzła OSM `places` typu city/town/village (Voronoi).
  Ludność miejscowości = suma przypisanych komórek. W Polsce OSM `place=city` = 66 miast na prawach powiatu, `town` = ok. 980 pozostałych miast.
- Klasy: wielkie miasta (city > 300 tys. w przypisaniu — Warszawa, Łódź, Wrocław, Kraków, Poznań; przypisanie zaniża ich ludność, bo część dzielnic trafia do węzłów wsi),
  średnie (city lub town > 50 tys.), małe miasta 10–50 tys., miasteczka < 10 tys., wsie.
- Liczymy firmy na 10 tys. mieszkańców w klasie. Uwaga: `poi` ma wiersze typ×firma, więc ten sam salon może być i „fryzjerem”, i „salonem kosmetycznym”.

## Firmy na 10 tys. mieszkańców (OSM + Overture)

| Typ | wielkie | średnie | małe 10–50 tys. | miasteczka | wsie | udział Overture |
|---|---|---|---|---|---|---|
| Fryzjer | 12,2 | 8,6 | 9,4 | 9,0 | 2,5 | ~50% |
| Salon kosmetyczny | 18,1 | 14,0 | 13,6 | 10,9 | 4,1 | ~80% |
| Sklep spożywczy | 17,6 | 16,5 | 19,0 | 26,3 | 15,6 | ~20% |
| Restauracja | 30,8 | 17,0 | 16,8 | 21,6 | 8,8 | ~30% |
| Przedszkole | 6,5 | 5,6 | 5,5 | 5,4 | 3,3 | ~30% |
| Brukarstwo | 0,13 | 0,19 | 0,25 | 0,34 | 0,23 | ~35% |
| Instalator | 0,5 | 0,5 | 0,6 | 0,5 | 0,4 | ~65% |

Wniosek: **małe miasta nie są gorzej pokryte niż średnie** (po dodaniu Overture; sam OSM miał w małych miastach ok. 1/5 salonów).
Wielkie miasta mają więcej usług na mieszkańca (częściowo naprawdę — dojazdy do pracy, centra). Wsie mają mało — w dużej mierze naprawdę (usługi są w miastach), ale nie da się tego oddzielić od luk.

## Porównanie z liczbami zewnętrznymi (szacunki, nie oficjalne wyciągi z REGON)

| Typ | U nas | Odniesienie | Pokrycie |
|---|---|---|---|
| Restauracje (+ bary) | ok. 50 tys. | GUS przez BOŚ Bank: ok. 30 tys. restauracji + 26 tys. barów (2024) | ~90% |
| Sklepy spożywcze | ok. 63 tys. | Dun & Bradstreet: 90,6 tys. sklepów ogólnospożywczych (III kw. 2024) | ~70% |
| Przedszkola | ok. 16 tys. | GUS: ~23 tys. placówek wychowania przedszkolnego (ekstrapolacja z lubelskiego/warmińsko-mazurskiego 2024/25; z oddziałami w szkołach) | ~70% |
| Fryzjer + kosmetyka + barber + paznokcie | ok. 64 tys. wierszy (z nakładaniem) | 132,8 tys. zarejestrowanych (D&B 2025, w tym uśpione i dojazdowe); 47 tys. widocznych w Google Maps (Scrap.io 2026) | salony z lokalem: prawie wszystkie; zarejestrowane firmy: ~40% |
| Brukarstwo, instalatorzy, ogrodnicy, okna, kuchnie | setki – 1–5 tys. | rzeczywiście: tysiące–dziesiątki tysięcy (firmy bez lokalu) | bardzo niskie |

## Co z tego wynika dla produktu
- **Najdokładniej:** firmy z lokalem, do którego przychodzi klient (sklepy, gastronomia, przedszkola, salony), w miastach każdej wielkości.
- **Najsłabiej:** firmy, które pracują u klienta (brukarz, instalator, ogrodnik, okna, kuchnie) — w mapach ich prawie nie ma.
  Dla nich wartościowa jest warstwa popytu/trendu („gdzie budują”), a nie „konkurencja”. Uzupełni to dopiero CEIDG.
- Oceny `osm_quality` w `backend/app/catalog.py` warto zaktualizować na podstawie tej tabeli.
