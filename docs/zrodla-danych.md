# Źródła danych — notatki z researchu (2026-10-26)

Dokument roboczy dla zespołu (czaty Claude). Wszystko zweryfikowane ręcznie w tej dacie, chyba że zaznaczono inaczej.

## 1. Pozwolenia na budowę / zgłoszenia — GUNB RWDZ (ZWERYFIKOWANE)

- Strona: https://wyszukiwarka.gunb.gov.pl/pobranie.html
- Pliki ZIP z CSV, aktualizowane **codziennie w nocy**, dane od 2016-01-01.
  - Per województwo: `https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_<woj>.zip`
    (`dolnoslaskie, kujawsko-pomorskie, lubelskie, lubuskie, lodzkie, mazowieckie, malopolskie, opolskie, podkarpackie, podlaskie, pomorskie, slaskie, swietokrzyskie, warminsko-mazurskie, wielkopolskie, zachodniopomorskie`)
  - Zgłoszenia (bez pozwolenia) ogólnopolskie: `wynik_zgloszenia_2016_2021.zip`, `wynik_zgloszenia_2022_up.zip` (~26 MB)
- Opolskie: ZIP 7,5 MB → CSV 57 MB, 119 045 wierszy.
- **Format faktyczny: separator `;`** (strona twierdzi `#` — nieprawda), UTF-8 z BOM, daty `YYYY-MM-DD 00:00:00`.
- Kolumny (wnioski o pozwolenie): `numer_urzad;numer_gunb;nazwa_organu;adres_organu;data_wplywu_wniosku;numer_decyzji_urzedu;data_wydania_decyzji;nazwa_inwestor;wojewodztwo;miasto;terc;cecha;cecha;ulica;ulica_dalej;nr_domu;rodzaj_inwestycji;kategoria;nazwa_zamierzenia_bud;nazwa_zam_budowlanego;kubatura;projektant_nazwisko;projektant_imie;projektant_numer_uprawnien;jednosta_numer_ew;obreb_numer;numer_dzialki;numer_arkusza_dzialki;jednostka_stara_numeracja_z_wniosku;stara_numeracja_obreb_z_wnioskiu;stara_numeracja_dzialka_z_wniosku`
  - UWAGA: kolumna `cecha` występuje dwa razy, `ulica` też ma duplikat znaczeniowy — czytać po indeksie albo z `header=None` + własne nazwy.
  - Pola tekstowe mogą zawierać znaki nowej linii w cudzysłowach — parsować modułem `csv`/pandas z `quotechar='"'`, NIE linia po linii.
  - Ok. 5% wierszy "budowa nowego" kat. I to **zmiany pozwoleń** (`nazwa_zam_budowlanego` zawiera "zmian") — wykluczać, żeby nie liczyć tego samego domu dwa razy.
- **Plik zgłoszeń ma INNE kolumny** (zweryfikowane, `wynik_zgloszenia_2022_up.csv`, 350 MB, ~939 tys. rekordów):
  `numer_ewidencyjny_system;numer_ewidencyjny_urzad;data_wplywu_wniosku_do_urzedu;nazwa_organu;wojewodztwo_objekt;obiekt_kod_pocztowy;miasto;terc;cecha;cecha;ulica;ulica_dalej;nr_domu;kategoria;nazwa_zam_budowlanego;rodzaj_zam_budowlanego;kubatura;stan;jednostki_numer;obreb_numer;numer_dzialki;numer_arkusza_dzialki;nazwisko_projektanta;imie_projektanta;projektant_numer_uprawnien;projektant_pozostali`
  - UWAGA zamiana znaczeń: tu `rodzaj_zam_budowlanego` = "budowa nowego/..." a `nazwa_zam_budowlanego` = opis tekstowy (odwrotnie niż w pozwoleniach!). Data = `data_wplywu_wniosku_do_urzedu`. Parcela: `jednostki_numer` + `obreb_numer` + `numer_dzialki`.
  - `stan` = zawsze "Brak sprzeciwu" (plik zawiera tylko skuteczne zgłoszenia).
  - 90% to kat. XXVI (sieci/drogi). Nowe domy jednorodzinne (kat. I + budowa nowego): ~6,5 tys./rok w całej PL — mało w porównaniu z pozwoleniami (~99 tys./rok), ale dodajemy.
- Kluczowe pola do analizy:
  - `kategoria` — kategoria obiektu budowlanego wg Prawa budowlanego (załącznik): **I = budynki mieszkalne jednorodzinne**, **XIII = budynki mieszkalne wielorodzinne / zamieszkania zbiorowego**, XXVI = drogi/ścieżki itp., XVII = obiekty handlowe/usługowe, XVIII = przemysłowe/magazynowe, VIII, III, II... (pełna lista do wpisania w kod z załącznika do ustawy Prawo budowlane).
  - `nazwa_zamierzenia_bud` — `budowa nowego/nowych obiektów budowlanych` | `rozbudowa ...` | `nadbudowa ...` | `rozbiórka ...` | `odbudowa ...` | `wykonanie robót budowlanych innych...`
  - `data_wydania_decyzji` — oś czasu.
  - `jednosta_numer_ew` (np. `160602_4`) + `obreb_numer` (np. `0038`) + `numer_dzialki` (np. `178/11`) → **pełny identyfikator działki** `160602_4.0038.178/11`. Wypełnione w 99,9% wierszy.
  - `terc` — 7-znakowy TERYT gminy (np. `1606024`) — fallback do agregacji na poziomie gminy.
- Statystyki Opolskie: kategoria I 40 245 wierszy; nowe jednorodzinne (I + "budowa nowego") 23 567 od 2016; ~8,5 tys. decyzji/rok w ostatnich latach (wszystkie kategorie).
- Skala PL (GUNB, 2024): ~99 tys. pozwoleń jednorodzinnych, ~16 tys. wielorodzinnych rocznie.

## 2. Geokodowanie działek — GUGiK ULDK (ZWERYFIKOWANE)

- `https://uldk.gugik.gov.pl/?request=GetParcelById&id=160602_4.0038.178/11&result=teryt,geom_wkt&srid=4326`
- Odpowiedź tekstowa: pierwsza linia `0` (= OK), druga `id|SRID=4326;POLYGON((...))`. Centroid liczymy sami (shapely).
- `result=centroid` NIE działa (pusta wartość).
- Czas odpowiedzi ~0,35 s / zapytanie. Cała Polska (miliony działek) = za wolno do geokodowania 1:1.
- **Strategia:** agregujemy pozwolenia do **obrębu ewidencyjnego** (`jednosta_numer_ew` + `obreb_numer` → id obrębu `160602_4.0038`) i geokodujemy tylko obręby (rzędu ~50 tys. w PL).
  - ZWERYFIKOWANE: `https://uldk.gugik.gov.pl/?request=GetRegionById&id=160602_4.0038&result=teryt,region,geom_wkt&srid=4326` → `0\n160602_4.0038|Namysłów|SRID=4326;MULTIPOLYGON(...)`.
  - `GetCommuneById&id=160602_4&result=teryt,commune` też działa (uwaga: zwrócił `160602_3` dla `_4` — gminy miejsko-wiejskie mają części _4 miasto / _5 obszar wiejski; nie polegać na tym przy joinach).
  - Pierwsza linia odpowiedzi `0` = sukces, `-1` = błąd/brak. Throttling: max ~5 równoległych zapytań, cache wyników na dysku (tabela `obreb_geom`), wznawialne.
  - Dokładne działki (`GetParcelById`) — opcjonalnie, tylko dla ostatnich 24 mies. kat. I/XIII, jako ulepszenie (ok. 230 tys. działek → kilka godzin w tle).
- Alternatywa / fallback: granice obrębów i gmin z PRG (GUGiK) do pobrania hurtowo.

## 3. Ludność — Eurostat Census GRID 2021 (ZWERYFIKOWANE URL)

- Strona: https://ec.europa.eu/eurostat/web/gisco/geodata/population-distribution/population-grids
- Najnowsza wersja **V3 (30.05.2026)**: https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip — **566 MB** (cała UE), CSV + GPKG + raster.
- Siatka 1 km², EPSG:3035 (ETRS89-LAEA). Dane finalne (stan 22.01.2025).
- Zawartość ZIP (zweryfikowane przez HTTP range): `ESTAT_Census_2021_V3.parquet` (**76 MB — użyć tego**, wyciągnąć z ZIP-a bez pobierania całości albo pobrać całość raz), `.csv` (340 MB), `.gpkg` (1,3 GB), `.tiff`, `read.me`.
- Kolumny: `GRD_ID,T,M,F,Y_LT15,Y_1564,Y_GE65,EMP,NAT,EU_OTH,OTH,SAME,CHG_IN,CHG_OUT,LAND_SURFACE,POPULATED,CNTR_ID`
  - `GRD_ID` np. `CRS3035RES1000mN2684000E4285000` → lewy dolny róg komórki: N=northing, E=easting w EPSG:3035; komórka = [E, E+1000] × [N, N+1000].
  - `CNTR_ID` — dla PL: `PL` oraz komórki graniczne `CZ-PL`, `DE-PL`, `LT-PL`, `PL-SK`, `CZ-DE-PL`, `CZ-PL-SK` → filtr: `'PL' in CNTR_ID.split('-')`.
  - `-9999` = brak danych, `-8888` = poufne.
- Statystyki PL (zweryfikowane): 314 181 komórek, 196 583 zamieszkanych, suma T = 37,09 mln (z komórkami granicznymi).
  - **T nigdy nie jest ukryte.** Podkategorie są ukryte (-9999) w małych komórkach: M/F w 24 tys. komórek (łącznie ~91 tys. osób), Y_GE65 w 57 tys., Y_LT15 w 53 tys., CHG_IN w 140 tys. (→ CHG_IN NIE używamy).
  - Imputacja: brakującą podkategorię = T × udział tej podkategorii w sąsiedztwie (komórki z danymi w promieniu ~5 km) albo — prościej — × udział krajowy (M 48,3%, F 51,5%, <15 15,3%, 15–64 65,1%, 65+ 18,7%). Zacząć od krajowego.
- Licencja: "© European Union 2026, Eurostat GISCO", zaznaczyć modyfikacje (agregacja do H3).
- Alternatywy:
  - Kontur Population (H3 400 m, CC BY) na HDX — HDX zwraca 403 dla WebFetch, nie zweryfikowano pobierania.
  - JRC 100 m population grid (07/2026) i **JRC 1 km dwelling grid (10/2025)** — liczba mieszkań — https://data.jrc.ec.europa.eu/dataset/50cfa4c6-406e-47ce-a092-64a2c5d18303
  - GUS BDL API (gminy, roczne) — https://bdl.stat.gov.pl — do danych dynamicznych (np. mieszkania oddane do użytkowania per gmina).

## 4. Biznesy (POI) — OpenStreetMap

- Overpass API (https://overpass-api.de/api/interpreter) — wymaga nagłówka User-Agent (bez niego 406).
- Zapytanie o całą Polskę dla 1 tagu: ~75 s. Po kilku zapytaniach publiczny endpoint **zaczyna odrzucać (rate limit)** i w odpowiedzi wprost pisze, że do automatycznego użycia trzeba lokalnej instancji.
- **Wniosek:** NIE odpytywać Overpass na żywo przy każdym kliknięciu użytkownika. Zamiast tego ETL z ekstraktu Geofabrik: https://download.geofabrik.de/europe/poland.html (`poland-latest.osm.pbf`, ok. 2 GB; dostępne też ekstrakty wojewódzkie) → filtrowanie po tagach (pyosmium / osmium-tool / quackosm) → tabela POI w lokalnej bazie.
- **Kompletność OSM jest słaba dla małych usług:** w PL `shop=hairdresser` = 10 749 obiektów (realnie salonów fryzjerskich jest wielokrotnie więcej); Opole (miasto, ~125 tys. mieszk.) beauty+hairdresser = 30. Trzeba to jasno komunikować w UI i/lub uzupełnić innym źródłem.
- Licencja ODbL — atrybucja "© OpenStreetMap contributors" na mapie.

## 5. Biznesy — CEIDG (rejestr jednoosobowych działalności)

- Najpełniejsze źródło dla małych usług (salony, brukarze, ogrodnicy to w większości JDG). Zawiera PKD, status, adres wykonywania działalności.
- API: `https://dane.biznes.gov.pl/api/ceidg/v2/...` — wymaga **tokenu JWT** (bezpłatny, przez wniosek na biznes.gov.pl). Dokumentacja tylko po zalogowaniu — NIE zweryfikowano endpointów.
- Problemy: adres bywa adresem domowym; trzeba filtrować status AKTYWNY; adres trzeba geokodować (GUGiK punkty adresowe / usługa UUG); od 2025 obowiązuje nowa klasyfikacja PKD 2025 — sprawdzić mapowanie kodów.
- Nie obejmuje spółek (KRS) — dla małych usług to akceptowalne.

## 6. Biznesy — Google Places API (New)

- Nearby Search Pro: **5 000 darmowych zapytań/miesiąc** (od 03.2025 progi per SKU zamiast kredytu $200), potem $32/1000. Max 20 wyników na zapytanie. Wymaga konta Google Cloud z kartą.
- Bardzo dobra kompletność, ale: limity, ToS zabrania trwałego przechowywania większości danych (cache tylko place_id) — nie nadaje się do mapy całej Polski, tylko do "sprawdzenia na żywo" małego promienia.
- **Scrapowanie Google Maps (bez API) łamie ToS — nie robimy.**

## 7. Podkłady i granice

- Kafelki OSM (Leaflet) — atrybucja wymagana; przy większym ruchu użyć np. CARTO light.
- Granice administracyjne: PRG GUGiK (gminy, powiaty, województwa) — do agregacji i wyboru "miasto/gmina".
