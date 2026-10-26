# Rozkłady Trójmiasta

Tablica linii komunikacji miejskiej w stylu IMHD.sk: trasy, rozkłady przystankowe, linie łączone i mapa sieci. Obszary: Gdańsk, Sopot i Gdynia (z koleją S1, S2 i S22), Krynica-Zdrój z Muszyną, Bydgoszcz, Nowy Sącz z okolicznymi gminami oraz Poznań, Kraków i Warszawa.

## Najprościej na Windows

Kliknij dwukrotnie `aktualizuj.bat`. Plik pobierze aktualne dane, zapisze je w `rozklady.html` (strona z wbudowanymi rozkładami, działa po otwarciu prosto z dysku) i otworzy ją w przeglądarce. Wymaga zainstalowanego Pythona 3 (python.org, z zaznaczoną opcją „Add python.exe to PATH”).

## Zawartość

- `index.html` – cała strona (HTML, CSS i JavaScript w jednym pliku), wczytuje dane z `data/` – do hostingu na serwerze.
- `rozklady.html` – ta sama strona z wbudowanymi danymi, do otwierania z dysku.
- `aktualizuj.bat` – aktualizuje dane i otwiera `rozklady.html` (Windows).
- `data/` – wygenerowane rozkłady: `index.json` (linie, przystanki) i `r/<linia>.json` (trasy i odjazdy jednej linii, wczytywane dopiero po jej otwarciu).
- `build.py` – skrypt, który pobiera aktualne otwarte dane i odtwarza katalog `data/`.
- `basemap.py` – tworzy podkład mapy z danych OpenStreetMap (`data/base.json`), wywoływany przez `build.py` raz w miesiącu.
- `schematic.py` – tworzy schematy oktylinearne (`data/schema_*.json`) za pomocą narzędzi LOOM, wywoływany przez `build.py`.
- `brygady.py` – rozkłady brygad (`data/bg/`) z plików GTFS przewoźników, które podają numery brygad (ZTM Gdańsk, Warszawa, Poznań, Kraków, Bydgoszcz); wywoływany na końcu `build.py`.
- `walknet.py` – sieć piesza z OpenStreetMap wokół przystanków (`data/walk/`), po której planer połączeń rysuje dojścia; odświeżana razem z podkładem mapy.
- `drogi.py` – sieć dróg z OpenStreetMap (kafelki OpenFreeMap) i wyznaczanie przebiegu tras między przystankami dla linii, których dane nie mają kształtu trasy (Nowy Sącz, Krynica-Zdrój i Muszyna, Bydgoszcz).
- `.github/workflows/update.yml` – codzienna automatyczna aktualizacja na GitHubie.

## Skąd są dane

| Źródło | Adres |
|---|---|
| ZTM w Gdańsku – GTFS | ckan.multimediagdansk.pl (zbiór „tristar”) |
| ZTM w Gdańsku – lista kursów (rozpoznawanie zjazdów do zajezdni) | ckan.multimediagdansk.pl, plik trips.json |
| ZKM w Gdyni – GTFS | api.zdiz.gdynia.pl/pt/gtfs.zip |
| Kolej (SKM, POLREGIO) – GTFS | mkuran.pl/gtfs/polish_trains.zip |
| ZDMiKP Bydgoszcz – GTFS (ZDMiKP nie publikuje GTFS sam; plik przetworzony z jego oficjalnych rozkładów, licencja CC0) | mkuran.pl/gtfs/bydgoszcz.zip |

Dlaczego strona nie pobiera GTFS sama w przeglądarce: serwery ZKM Gdynia i rozkładu kolei nie pozwalają na pobieranie z innych stron (brak nagłówków CORS), a pliki źródłowe mają łącznie ok. 80 MB (sam plik odjazdów ZTM po rozpakowaniu to ok. 130 MB). Dlatego dane przelicza `build.py`, a strona wczytuje gotowe, małe pliki JSON (ok. 1,5 MB łącznie, każda linia osobno).

## Aktualizacja danych

Ręcznie (Python 3.9 lub nowszy, bez dodatkowych pakietów):

```
python3 build.py
```

Skrypt pobiera dane, wybiera najbliższy dzień roboczy (środę), sobotę i niedzielę jako dni wzorcowe i nadpisuje katalog `data/`. Trwa to około pół minuty.

Automatycznie na serwerze – dodaj do crona, np. codziennie o 4:30:

```
30 4 * * * cd /ścieżka/do/strony && python3 build.py
```

Automatycznie na GitHub Pages – wrzuć cały katalog do repozytorium, włącz GitHub Pages (Settings → Pages, gałąź główna) i zostaw plik `.github/workflows/update.yml`. Rozkłady odświeżą się same każdej nocy, a ręcznie można je odświeżyć w zakładce Actions („Run workflow”).

## Uruchomienie lokalne

Strona wczytuje pliki z `data/`, więc trzeba ją otworzyć przez serwer, a nie bezpośrednio z dysku:

```
python3 -m http.server 8000
```

i wejść na http://localhost:8000.

## Reguły na stronie

- Układ strony jak w IMHD.sk: u góry logo ZbiorkomInfo i rozwijana lista miast (pogrupowanych według województw), po lewej czarny pasek: Rozkłady (tablica linii i rozkłady), Mapa (okno sieci obok paska; w nim widoki Linie, Mapa i Schemat) i Odjazdy. Na telefonie pasek jest na dole ekranu.
- **Odjazdy** (czarny pasek): tablica najbliższych odjazdów z wybranych przystanków, wzorowana na tablicy odjazdów ZTM Gdańsk (DepartureBoard): pasek z nazwą przystanku, nagłówek z zegarem, wiersze z symbolem linii, kierunkiem, czasem (minuty do odjazdu, potem godzina; tuż przed odjazdem trzy gasnące strzałki „>>>”) i peronem (numer słupka). Jedna albo dwie tablice obok siebie, motyw szaro-czarny lub jasny, liczba wierszy, zakres odjazdów, własne tytuły, kształt i kolory symboli linii, wybór słupków, pełny ekran (klawisz F), ustawienia pod klawiszem S. Przystanki wybiera się z dowolnego miasta (lista miast w ustawieniach), także różne miasta na dwóch tablicach. Dla przystanków ZTM Gdańsk tablica pobiera odjazdy na żywo (czasy szacowane z GPS, z kropką i opóźnieniem lub przyspieszeniem) z API ZTM; serwer ZTM nie wysyła nagłówka CORS, więc przeglądarka próbuje kolejno: bezpośrednio, przez corsproxy.io i przez allorigins. Gdy żadna droga nie działa (np. wewnątrz claude.ai) oraz w pozostałych miastach odjazdy są liczone z rozkładów strony (bieżący tydzień, po północy także następny dzień), z dopiskiem na dole, że są podawane wg rozkładów jazdy. Symbole autobusów są kwadratowe, tramwajów i pociągów okrągłe. Tryb pełnoekranowy (przycisk lub klawisz F, wyjście Esc) zakrywa całe okno, a gdzie przeglądarka pozwala, także cały ekran. Ustawienia zapisują się w przeglądarce.

- Kolorem oznaczone są linie, które w dzień roboczy jeżdżą częściej niż co 20 minut przez ponad 8 godzin na dobę albo w obu szczytach co 12 minut lub częściej. Linie kolejowe mają stałe kolory (S1 zielona, S2 i S22 czerwone).
- Kursy zjazdowe i wyjazdowe rozpoznawane są tylko dla ZTM w Gdańsku (na podstawie celu kursu „Zajezdnia …” lub „Baza …”).
- Wybór miasta, motywu, przełącznik zjazdów i własne łączenia linii zapisują się w przeglądarce (localStorage).
- Każdy rozkład przystankowy (pojedynczej linii i linii łączonych) ma przycisk „Eksport”, a w nim „Drukuj” i „Pobierz PDF”. Arkusz A4 w poziomie jest wzorowany na rozkładach wywieszanych na przystankach: godziny w wierszach, osobne kolumny dni (kolumny dni, w których linia nie kursuje, są pomijane), trasa z czasami przejazdu po prawej, objaśnienia i przewoźnik na dole. Przy liniach łączonych przy każdej minucie jest numer linii, a przy wielu liniach ich symbole w nagłówku się zmniejszają. PDF jest wektorowy (tekst, linie i kształty, nie obraz): rysuje go jsPDF z czcionką Roboto, a ikony svg2pdf; biblioteki są pobierane z CDN przy pierwszym użyciu. Przy długich trasach (np. Rafatex) przełącznik „Skrócona lista przystanków” zostawia końcowe, bieżący, główne przystanki miejscowości i co kilka pozostałych; pominięte odcinki są zaznaczone kropkowaną linią.
- W oknie schematu sieci, po wybraniu jednej linii, można wybrać wariant trasy (litery jak w uwagach rozkładu) w każdym widoku, także na schemacie: wariant jest rysowany po krawędziach schematu, linią przerywaną tam, gdzie linia na schemacie nie jeździ.

## Okno schematu sieci: trzy widoki

- **Linie** – trasy linii w położeniu geograficznym, bez podkładu.
- **Mapa** – te same trasy na spokojnym podkładzie z OpenStreetMap (woda, zieleń, zabudowa, ulice, tory). Podkład jest pobierany z kafelków wektorowych OpenFreeMap i zapisywany w `data/base.json`; `build.py` odświeża go raz w miesiącu, a od razu po dodaniu `--podklad`. Mapa: © współtwórcy OpenStreetMap (licencja ODbL).
- **Schemat** – schemat oktylinearny (linie tylko pod kątami 0°, 45° i 90°, wspólne odcinki obok siebie w ustalonej kolejności). Układ liczy pakiet [LOOM](https://github.com/ad-freiburg/loom) (Uniwersytet we Fryburgu): `topo` łączy wspólne odcinki, `loom` ustala kolejność linii, `octi` rozkłada sieć na siatce. Każdy obszar ma własny schemat (`data/schema_gda.json`, `schema_sop.json`, `schema_gdy.json`, `schema_all.json` dla Trójmiasta), z liniami, które tam kursują, uciętymi na granicy obszaru. Są trzy zakresy: tramwaje, trolejbusy i kolej; linie częste; wszystkie linie dzienne – każdy także w wersji z liniami nocnymi, pokazywanej po zaznaczeniu „linie nocne”. Linie z własnym kolorem (częste i kolej) mają osobne kreski; pozostałe linie dzienne są rysowane jako jedna szara kreska z rozgałęzieniami, a nocne jako jedna ciemna, z numerami linii na odcinkach.

LOOM to program w C++. Na GitHubie workflow buduje go sam (raz, potem z pamięci podręcznej). Na Linuksie lub macOS:

```
git clone --recurse-submodules https://github.com/ad-freiburg/loom.git
cmake -S loom -B loom/build -DCMAKE_BUILD_TYPE=Release && make -C loom/build topo loom octi
```

Katalog `loom` położony obok `build.py` zostanie znaleziony automatycznie (można też wskazać zmienną `LOOM_BIN`). Na Windows nie trzeba nic budować: paczka zawiera folder `loom-bin` z gotowymi `topo.exe`, `loom.exe` i `octi.exe` (Windows 64-bit, skompilowane z LOOM z drobnymi poprawkami pod Windows – `loom-bin/windows.patch`, licencja GPL v3 – `loom-bin/LICENSE.txt`), które `schematic.py` znajduje sam, więc `aktualizuj.bat` przelicza też schematy. Gdy LOOM nie jest dostępny, `build.py` zostawia poprzednie pliki `data/schema_*.json`, więc schemat nadal działa, tylko nie odświeża się po zmianach tras.

## Bydgoszcz

Osobny obszar „Bydgoszcz”, niewidoczny w widoku Trójmiasta. Dane ZDMiKP nie mają numerów słupków, więc słupki o tej samej nazwie są numerowane po kolei (01, 02…) według numerów przystanków; nie ma też kształtów tras, więc na mapie linie biegną prosto od przystanku do przystanku. Podkład mapy: `data/base_byd.json`. Schematu oktylinearnego dla Bydgoszczy nie ma.

## Krynica-Zdrój i Muszyna (rozkłady spisane z PDF)

Te dwie gminy nie publikują otwartych danych, więc rozkłady zostały spisane z plików PDF przewoźników do `reczne/krynica_muszyna.json` (przystanki z położeniem i wszystkie kursy). `build.py` dołącza je jako osobny obszar „Krynica-Zdrój i Muszyna”, niewidoczny w widoku Trójmiasta.

- Zapopradzie sp. z o.o. (gmina Muszyna), linie 1–9 → na stronie Z1–Z9 (zapopradzie.pl).
- MPGK Krynica-Zdrój, bezpłatna komunikacja uzdrowiskowa → jedna linia na każdy rozkład ze strony mpgk-krynica.pl: K1 Gondola – Słotwińska Pętla (1s, 2gs, 3sg; w soboty i niedziele Rozklad.pdf), K3 Zawodzie – Stara Droga Gazownia (5z, Staradroga-zawodzie-2), K4 Gondola – Tylicz (linia4a), K5 Krynica – sołectwa (linia5), K8 Gondola – Muszynka (8g), K9 Muszynka – Gondola/Zawodzie (9m-2), K6 soboty i K7 niedziele (arkusze 39sobotamuszynki.xlsx i Minutowka-40z-strona.xls, czytane przez `reczne/narzedzia/sheets.py`). Rozkład feryjny nie jest uwzględniony.
- Położenia przystanków: z OpenStreetMap, gdzie przystanek jest tam opisany; pozostałe postawione na drodze, którą jedzie autobus, w miejscu wynikającym z rozkładu (pole 5 w `stops`: osm / osm-near / place / est).
- Przebieg tras po ulicach: `legs` w pliku JSON – droga między każdymi dwoma kolejnymi przystankami, wyznaczona przez `reczne/narzedzia/route_km.py` na sieci dróg OpenStreetMap z kafelków OpenFreeMap (te same, co podkład mapy). Gdzie droga nie daje się sensownie wyznaczyć, zostaje prosta linia.
- Każda linia ma własny kolor (`color` w `lines`), niezależnie od częstotliwości – wyjątek od reguły obowiązującej w pozostałych miastach. Obszar ma też własny schemat oktylinearny (`data/schema_km.json`).

Dodatkowe kategorie tego obszaru:

- **Pociągi** – linia KR Krynica-Zdrój – Kraków Główny: wszystkie pociągi PKP Intercity i POLREGIO z Krynicy i do Krynicy (z rozkładu kolei GTFS, tak jak S1/S2/S22), każdy pokazany na odcinku między Krynicą a Krakowem; uwagi rozkładu mówią, dokąd pociąg jedzie dalej albo gdzie kończy bieg (np. Tarnów).
- **Autobusy transgraniczne** – linia BK Bardejovské Kúpele – Bardejov – Kurov – Tylicz – Krynica-Zdrój Dworzec PKP (SAD Prešov, linia 079388, ważny od 1.09.2026), codziennie po 3 kursy w każdą stronę, ze wszystkimi 23 przystankami z rozkładu przewoźnika.
- **Przewoźnicy prywatni** – linia RX RAFATEX Szczawnik – Muszyna – Krynica-Zdrój – Nowy Sącz. Godziny z rozkładów PDF przewoźnika (rafatex.pl, czytane przez `reczne/narzedzia/rafatex.py`), które podają tylko główne przystanki; pozostałe przystanki trasy i czasy przejazdu między nimi pochodzą z e-podroznik.pl i są wpasowane między godziny z PDF. Oznaczenia dni: D – kursy w każdy dzień roboczy, S – tylko w dni nauki szkolnej, 6 soboty, 7 niedziele, + święta. Linia ma czwartą kolumnę rozkładu „Dni robocze wolne od szkoły” (w danych dzień `f`): w „Dniach roboczych” są kursy D i S, w dniach wolnych od szkoły tylko kursy D. Strona i wydruk pokazują tę kolumnę tylko dla linii, które ją mają.

Linie BK i RX są w osobnym pliku `reczne/km_dodatkowe.json` (tworzy go `reczne/narzedzia/make_dodatkowe.py`, przebieg po drogach dodaje `route_km.py ../km_dodatkowe.json`), żeby ponowne spisanie rozkładów MPGK/Zapopradzia go nie nadpisało. Przystanki poza obszarem (Nowy Sącz, Bardejov) mają w polu 6 oznaczenie `kmx`: linie nadal należą do obszaru Krynicy i Muszyny, mapa i schemat skupiają się na nim, a na schemacie linie są ucięte na jego granicy z dopiskiem, dokąd jadą. Podkład `data/base_km.json` obejmuje też drogę do Nowego Sącza i Bardejowa (dokładnie tylko okolice Krynicy i Muszyny).

Po zmianie rozkładu przez przewoźnika plik trzeba poprawić ręcznie albo ponownie spisać skryptami z `reczne/narzedzia/` (transcribe.py czyta PDF-y, grid_ocr.py rozpoznaje tabele zapisane jako grafika, sheets.py czyta arkusze MPGK, make_km.py tworzy plik JSON, route_km.py dodaje przebieg tras po ulicach).

## Nowy Sącz

MPK Nowy Sącz nie publikuje GTFS. `build.py` pobiera aktualny rozkład z serwisu rozkładów na stronie przewoźnika (`https://www.mpk.nowysacz.pl/wp-json/mpk/v1/timetable/active` i `/line/<id>` – te same dane, z których korzysta rozkład na mpk.nowysacz.pl): wszystkie linie MPK, także do sąsiednich gmin (Stary Sącz, Nawojowa, Kamionka Wielka, Podegrodzie, Chełmiec, Łącko i inne), z kursami, dniami kursowania i położeniem przystanków. Numer przystanku MPK ma pięć cyfr; ostatnia to numer słupka. W dni świąteczne obowiązuje rozkład niedzielny.

Na tablicy linie są podzielone tak jak u przewoźnika: miejskie, podmiejskie i nocna. Dane nie zawierają przebiegu tras, więc `drogi.py` wyznacza go po sieci dróg OpenStreetMap; gdzie się nie da, zostaje prosta linia między przystankami. Obszar ma własny podkład mapy (`data/base_ns.json`) i schemat (`data/schema_ns.json`).

## Poznań, Kraków, Warszawa

Trzy osobne obszary z otwartych danych GTFS: ZTM Poznań (ztm.poznan.pl), ZTP Kraków (dwa pliki: autobusy A i tramwaje T) oraz ZTM Warszawa (w przetworzeniu mkuran.pl, z metrem i SKM jako koleją). Słupki: dwie ostatnie cyfry kodu przystanku (Poznań, Warszawa) albo numer słupka z danych (Kraków). Linie nocne: Poznań 2xx, Kraków 6xx, Warszawa N…; zastępcze: Poznań T…, Kraków 7xx, Warszawa Z…. Te miasta mają dużo linii, więc ich pliki tras są pakowane po 30 w `data/rp/<obszar>_<n>.json` (pole `pk` w index.json), a mapa sieci każdego z nich jest w osobnym pliku `data/map_<obszar>.json`, wczytywanym dopiero po wybraniu miasta. Podkłady mapy: `base_poz.json`, `base_krk.json`, `base_waw.json` (dokładnie tylko centra). Schematy: tramwaje i kolej, linie częste oraz (Poznań, Kraków) wszystkie linie dzienne; dla Warszawy bez schematu wszystkich linii autobusowych. Tablica odjazdów obsługuje te miasta według rozkładów.

Kolory tramwajów w Poznaniu pochodzą z pola `route_color` w GTFS ZTM Poznań (zgodne z oznaczeniami MPK); jasne kolory mają ciemne cyfry (`kt`). Tramwaje nocne 201 i 203 są liniami nocnymi. Linie łączone w tych trzech miastach są dobierane automatycznie (`bigGroups()`): łączone są tylko linie tego samego rodzaju, które mają wiele wspólnych przystanków (tramwaje ≥6, kolej ≥5, autobusy ≥8 i co najmniej 35% krótszej linii), czasem z trzecią linią; każda linia jest najwyżej w dwóch zestawach.


## Zmiany z października 2026 (2)

- `uruchom_serwer.bat` / `serwer.py` – uruchamia stronę na tym komputerze (http://localhost:8765) i przekazuje zapytania tablicy odjazdów do API ZTM Gdańsk, więc tablica pokazuje odjazdy na żywo.
- Aktualizacja (`aktualizuj.bat`) przelicza schematy tylko dla obszarów, w których zmieniły się trasy linii (odcisk tras w `data/schema_sig.json`; `--schematy` wymusza wszystkie). Przebiegi ulic w Nowym Sączu są zapamiętywane w `reczne/drogi_cache.json`, więc kafelki dróg pobiera się tylko dla nowych odcinków.
- Linie częste (co 15 min lub częściej) dostają kolor także wtedy, gdy kursują tylko w wybrane dni (np. linie C w Warszawie).
- Kolej w Krynicy: osobne linie PKP (PKP Intercity) i PR (POLREGIO) oraz łączenie PKP+PR.
- Trójmiasto: kategorie „Linie autobusowe pospieszne” (linie literowe), „Linie sezonowe i okolicznościowe” (Cxx, 3xx, 6x, 6xx), a 9x i 9xx wśród zastępczych. Linia 153 (ZKM) podzielona na kierunki Fikakowo i Starodworcowa; linia 7 znów z kursami weekendowymi.
- Schemat sieci dla Bydgoszczy.
- Wyszukiwarka na górnym pasku (linie, łączenia, przystanki) i strona przystanku z liniami, wszystkimi odjazdami dnia i małą tablicą odjazdów.
- Wydruki i PDF w formacie A4 lub A5 (wybór w menu Eksport); przy wielu kursach najpierw zmniejszają się numery linii.

## Zmiany z października 2026 (3)

- **Połączenia** (czarny pasek): planer podróży – przystanek, adres lub punkt na mapie, moja lokalizacja, zamiana kierunku, odjazd lub przyjazd o podanej godzinie; w ustawieniach (zębatka) preferencje (najszybsze, mniej przesiadek, mniej chodzenia) i środki transportu kursujące w danym mieście. Przejazdy rysowane wzdłuż tras, dojścia ścieżkami pieszymi (w `rozklady.html` z dysku dojścia są prostymi liniami, bo sieć piesza nie jest wbudowana).
- **Okulary** (górny pasek) pokazują na czarnym pasku przyciski **Takty** (łączny rozkład wybranych linii na wspólnym przystanku, odstępy, podświetlanie kursów, średni czas oczekiwania) i **Brygady** (zadania przewozowe na dany dzień; tabor planowany w Warszawie, na żywo w Gdańsku oraz – przez `serwer.py` – w Poznaniu i Krakowie).
- `serwer.py`: nowe adresy `/gps` (pozycje pojazdów ZTM Gdańsk) i `/rtveh?area=poz|krk` (pojazdy na brygadach z GTFS-Realtime).
- Wyszukiwarka przystanków z numerem peronu (np. „Chałubińskiego 01”) i przełączanie peronów na stronie przystanku.
- Bydgoszcz: przebieg linii po ulicach i torowiskach (OpenStreetMap, `drogi.py`); Wejherowo: przebiegi z danych przewoźnika.
- Płynniejsze przesuwanie i przybliżanie map; linie zaczynające się od litery na początku każdej sekcji, potem numery rosnąco.
