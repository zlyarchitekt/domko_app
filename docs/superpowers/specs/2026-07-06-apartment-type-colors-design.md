# Kolory mieszkań wg typu (M1–M5) + koniec z „wylewaniem" mieszkania na ścianę

**Data:** 2026-07-06
**Status:** projekt (decyzje podjęte samodzielnie przez architekta — do
przeglądu; każda oznaczona „Decyzja:" + „Uzasadnienie:", user może
zakwestionować pojedynczą decyzję zamiast odpowiadać na otwarte pytania)
**Zależy od:** Etap „grubość ścian" (`2026-07-04-wall-thickness`, wdrożony,
commit e36d000 — daje `net_polygon`, `wall_bands`, `net_area_m2`) oraz
iteracyjny podział na mieszkania (`2026-07-04-apartment-division-iterations`
i `2026-07-05-circulation-iteration-selection-and-drag`, wdrożone — dają
`_serialize_unit_iteration` z geometrią per iteracja).

## Kontekst i cel

Dwie powiązane sprawy, obie dotyczą tego, JAK strefa mieszkania renderuje
się na płótnie (`frontend/app/CanvasEditor.tsx`), dlatego jeden spec+plan:

**A. Kolor wg typu mieszkania.** Dziś strefa mieszkania jest kolorowana
wg STATUSU walidacji (`STATUS_COLORS` w `CanvasEditor.tsx:225` — zielony
`ok` / żółty `warning` / czerwony `error`), a nie wg TYPU (M1–M5 z panelu
„Struktura mieszkań", `ProgramSection.tsx`). User chce: mały okrągły
przycisk-swatch przy każdym wierszu typu w panelu, klik → paleta/próbnik
koloru, przypisanie koloru do typu. Mieszkania tego typu mają się
wypełniać wybranym kolorem. Dotychczasowe kolorowanie statusem **nie
znika** — staje się kolorem OBRAMOWANIA (stroke), a WYPEŁNIENIE (fill)
przejmuje kolor per typ.

**B. Mieszkanie „wylewa się" na ścianę.** User zgłosił (ze zrzutu ekranu),
że kolorowa strefa mieszkania renderuje się na obszarze ściany, choć
powinna kończyć się na (wewnętrznym licu) ściany. Ten spec potwierdza,
że to REALNA usterka (dowody w §4), i naprawia ją przy okazji zmiany
wypełnienia z §A (nowe, bardziej kryjące kolory per typ pogłębiłyby ten
efekt, więc naprawa musi iść w parze).

## 1. Stan faktyczny (co przeczytano w kodzie)

- **`ApartmentResult.geometry` to poligon SUROWY (na osiach), we WSZYSTKICH
  trzech miejscach konstrukcji** w `backend/api/v1/endpoints/layout.py`:
  `layout_result_to_response` (:284), `_serialize_unit_iteration` (:457),
  `subdivide_units_endpoint` (:697) — każde robi
  `geometry=json.loads(json.dumps(a.polygon.__geo_interface__))`. Poligon
  „w świetle" (netto) NIE jest wysyłany na frontend w ogóle; jedyną
  pochodną netto w odpowiedzi jest LICZBA `net_area_m2` (:283/456/696),
  liczona z `net_polygon(polygon).area`.
- **`apt.type` przeżywa całą drogę** backend→frontend: `ApartmentResult.type
  = a.type` (:281 itd.), `api.ts` `ApartmentResult.type: string` (:194),
  renderer używa `apt.type` w etykiecie (`CanvasEditor.tsx:1196`). Więc
  dopasowanie typ→kolor po `apt.type` jest wykonalne bez zmian backendu
  dla §A.
- **Frontend renderuje dwa przebiegi `apartments.map`:** `CanvasEditor.tsx:1116`
  (wypełnienie + obramowanie — jeden `<Line closed fill=.. stroke=..>` per
  mieszkanie) oraz `:1189` (tylko etykiety `<Text>`, bez wypełnienia).
  **Autorytatywny dla fill/stroke jest przebieg :1116.** Drugi (`:1189`)
  liczy tylko środek bboxa dla tekstu — nie dotykamy jego geometrii.
- **`net_polygon` (`backend/services/wall_geometry.py:25`)** zwraca
  `polygon.buffer(-0.10, join_style="mitre")`, a dla komórek zbyt małych
  pustą `Polygon()` (nie None, nie wyjątek).
- **Brak biblioteki color-pickera** w `frontend/package.json` (jedyne
  zależności UI: `konva`/`react-konva`, `lucide-react` na ikony).

## 2. Sekcja A — kolor wg typu

### 2.1 Gdzie żyje mapowanie typ→kolor

**Decyzja:** nowe pole `typeColors: Record<string, string>` na
`SessionState` (`frontend/app/state/SessionContext.tsx`), kluczowane
STRINGIEM TYPU (`"M1"`…`"M5"`), wartość = hex `#rrggbb`. Domyślna paleta w
eksportowanej stałej `DEFAULT_TYPE_COLORS` (obok `DEFAULT_UNIT_WEIGHTS`,
:116). Trwałość: **automatyczna** — cały `state` jest już serializowany do
`localStorage` (`SessionContext.tsx:582-585`), więc `typeColors` zapisze
się bez nowego kodu zapisu.

**Uzasadnienie:** kluczowanie po typie (nie po `ProgramRow.id`) jest
zgodne z tym, po czym renderer dopasowuje kolor (`apt.type`), i przeżywa
usunięcie/dodanie wiersza programu. Wiele wierszy o tym samym typie
współdzieli kolor — to pożądane (kolor to własność TYPU na rysunku, nie
wiersza programu).

**Decyzja (backfill):** w akcji `RESTORE_STATE` (`SessionContext.tsx:571`)
trzeba domieszać `typeColors: { ...DEFAULT_TYPE_COLORS, ...parsed.typeColors }`
— dokładnie tak jak dziś domieszany jest `circulation` (:573), z tego
samego powodu: sesja zapisana przed tą zmianą nie ma pola `typeColors`,
więc `state.typeColors[apt.type]` rzuciłoby `TypeError` przy pierwszym
renderze. To ten sam wzorzec, przed którym ostrzega komentarz na
:563-569.

**Decyzja (domyślna paleta):** 5 rozróżnialnych kolorów czytelnych na obu
motywach (ciemny bg `#0c0c10`, jasny `#f4f4f5`):

```
M1 = #38bdf8  (sky)      M2 = #34d399  (emerald)   M3 = #a78bfa  (violet)
M4 = #fbbf24  (amber)    M5 = #f472b6  (pink)
```

Typ spoza palety (np. user wpisze „M6" — dziś `APARTMENT_TYPES` tego nie
pozwala, ale API `type` jest wolnym stringiem) dostaje fallback
`#9ca3af` (zinc-400) przy renderze.

### 2.2 Jaki próbnik koloru

**Decyzja:** natywny `<input type="color">`, ZERO nowych zależności.
Osadzony w okrągłym swatchu: `<label>` o `border-radius:9999px`,
`background` = aktualny kolor typu, zawierający wizualnie ukryty (opacity 0,
absolutny, 100% obszaru labela) `<input type="color">`. Klik w swatch
otwiera natywny próbnik OS; `onChange` → `setTypeColor(row.type, e.target.value)`.

**Uzasadnienie:** brak color-pickera w `package.json` (§1) + wytyczna
„preferuj zero nowych zależności". `<input type="color">` daje pełną
paletę systemową i zwraca `#rrggbb` gotowy do zapisania w `typeColors`.
Wzorzec „okrągły label + ukryty input" jest odporny cross-browser
(stylowanie `::-webkit-color-swatch` bywa zawodne, więc nie polegamy na
nim — pokazujemy kolor przez `background` labela).

### 2.3 Jak kolor trafia na płótno

**Decyzja:** w przebiegu `CanvasEditor.tsx:1116` rozdzielamy trzy pojęcia,
które dziś są zlepione w jeden obiekt `colors`:

- **fill** = kolor per typ: `hexToRgba(state.typeColors?.[apt.type] ??
  DEFAULT_TYPE_COLORS[apt.type] ?? "#9ca3af", 0.45)`. Nowy helper
  `hexToRgba(hex, alpha)` w `CanvasEditor.tsx`, bo `<input type="color">`
  zwraca kryjący `#rrggbb`, a chcemy pół-przezroczyste wypełnienie (żeby
  etykieta i pasy ścian pod spodem były czytelne). Alpha 0.45 ≈ dzisiejsza
  alpha statusu (0.35–0.4).
- **stroke** = kolor statusu walidacji: `STATUS_COLORS[status].stroke`
  (dziś `colors.stroke`). Zaznaczone mieszkanie nadal `#3b82f6` (niebieski),
  szerokość jak dziś.
- **geometria (ring)** = poligon NETTO (patrz §4) — wspólna dla fill i
  stroke.

**Decyzja (tryb Słońce):** gdy `state.solarResult` istnieje (widok analizy
słonecznej), fill/stroke ZOSTAJĄ wg dzisiejszej logiki słonecznej
(`CanvasEditor.tsx:1119-1126`) — kolor per typ obowiązuje tylko w widoku
domyślnym (bez danych słonecznych). **Uzasadnienie:** widok Słońce to
osobna wizualizacja (przechodzi/nie przechodzi WT nasłonecznienia) i jego
skala kolorów niesie inne znaczenie niż „typ mieszkania"; nakładanie na
siebie dwóch znaczeń koloru byłoby mylące. Zmiana GEOMETRII na netto (§4)
obowiązuje jednak w OBU widokach (usterka §B jest geometryczna, nie
zależy od trybu koloru).

## 3. Sekcja B — mieszkanie kończy się na ścianie

### 3.1 Dowód, że §B to realna usterka (nie nieporozumienie)

Trzy fakty z kodu składają się na widoczny efekt „wylania":

1. **Kolejność z-order (Konva rysuje późniejsze elementy NA WIERZCHU):**
   `wall_bands` renderują się jako PIERWSze (`CanvasEditor.tsx:835`, pod
   spodem), potem korytarz (:874), klatka (:886), a mieszkania DOPIERO
   na :1116 — czyli NA WIERZCHU ścian.
2. **Mieszkanie rysuje poligon SUROWY** (`ring = ringToPoints(apt.geometry)`,
   :1133), sięgający do osi ściany. Oś ściany zewnętrznej leży 0.10m WEWNĄTRZ
   lica wewnętrznego (`WALL_EXTERIOR_AXIS_TO_INTERIOR_FACE_M = 0.10`,
   `wall_geometry.py:14`), a oś wewnętrzna — na środku ściany 0.20m.
3. **Konsekwencja:** surowe wypełnienie mieszkania zakrywa wewnętrzny pas
   ściany na wierzchu. Między dwoma mieszkaniami surowe poligony stykają
   się DOKŁADNIE na osi (zerowa przerwa), więc pas ściany wewnętrznej
   (0.20m, liczony jako `interior_envelope.difference(union net_polygonów)`,
   `wall_geometry.py:46`) jest CAŁKOWICIE zasłonięty — między mieszkaniami
   nie widać ściany, kolory stykają się. Przy ścianie zewnętrznej surowy
   poligon wchodzi 0.10m w 0.40-metrowy pas, zakrywając jego wewnętrzny
   pasek. To jest to „wylanie", które user widzi.

**Czy regresja, czy stan wrodzony?** Stan WRODZONY funkcji grubości ścian.
`git log -L 835,843:CanvasEditor.tsx` pokazuje, że warstwa `wall_bands`
weszła jednym commitem e36d000 „feat: render wall bands and net-area label
on canvas" (Etap wall-thickness, 2026-07-04) — od początku POD mieszkaniami.
Mieszkania nigdy nie zostały przełączone na geometrię netto. Co więcej,
spec grubości ścian §5.3 zakładał ściany „pod istniejącymi warstwami
mieszkań … żeby ściany wizualnie **otaczały** już rysowane kształty
zamiast je przesłaniać" — a „otaczanie" działa TYLKO jeśli mieszkanie
rysuje się jako netto (skurczone). Implementacja dodała pas ścian pod
spodem, ale nie skurczyła mieszkań → ściany zostały przesłonięte. Więc
usterka = niedokończona realizacja pierwotnego zamysłu §5.3, nie świeży
regres.

### 3.2 Naprawa §B

**Decyzja:** backend dosyła poligon NETTO per mieszkanie
(`ApartmentResult.net_geometry: dict | None`), frontend renderuje
wypełnienie i obramowanie mieszkania na tym poligonie netto (fallback do
surowego, gdy `net_geometry` puste/nieobecne).

**Uzasadnienie:** to architektonicznie poprawna definicja — użytkowa
strefa mieszkania to powierzchnia w świetle ścian, ograniczona licami
ścian. Poligon netto skurczony o 0.10m z każdej strony zostawia dokładnie
tyle miejsca, ile zajmują pasy `wall_bands` (liczone jako różnica z
`net_polygon`ami), więc wypełnienie mieszkania + pasy ścian pokrywają
obrys bez nakładki i bez dziury — spójność jest GWARANTOWANA konstrukcyjnie
(oba korzystają z tej samej stałej `NET_SHRINK_M = 0.10`). Kolejność
z-order NIE wymaga zmiany: gdy mieszkania są netto, nie ma czego zasłaniać,
ściany po prostu wypełniają szczeliny między nimi.

**Dlaczego nie warianty odrzucone:**
- *Przełożyć `wall_bands` NA WIERZCH mieszkań (bez netto):* pas ściany ma
  wypełnienie pół-przezroczyste (`wallFill` alpha 0.35–0.45), więc nad
  kolorem mieszkania dałby tylko szarawy przydymiony pasek — kolor
  mieszkania nadal sięgałby do osi. To nie jest „mieszkanie kończy się na
  ścianie", tylko „ściana półprzezroczyście nakryta na mieszkanie".
- *Liczyć netto na froncie (buffer -0.10 w JS):* offset dowolnego poligonu
  w czystym JS jest zawodny (narożniki, samoprzecięcia), a shapely na
  backendzie już to liczy poprawnie dla `net_area_m2`. Dosłanie gotowej
  geometrii jest tańsze i zgodne ze wzorcem projektu (backend robi
  geometrię, front renderuje GeoJSON).

**Dual-surface (znany footgun z pamięci projektu — `net_area_m2` dwa razy
gubiło się na ścieżce dwukrokowej):** `net_geometry` MUSI zostać dodane we
WSZYSTKICH trzech miejscach konstrukcji `ApartmentResult`
(`layout.py:284` /generate, `:697` /units, `:457` per-iteracja), inaczej
przełączenie iteracji albo dwukrokowa ścieżka `/circulation`+`/units`
pokaże mieszkania znów „wylane".

**Serializacja bezpieczna:** helper `_net_geometry_json(polygon)` zwraca
`dict` tylko gdy `net_polygon(polygon)` jest niepustym, prostym
`Polygon`em; w przeciwnym razie `None`. Frontend: `apt.net_geometry ??
apt.geometry`. Dla komórki zbyt małej (netto puste) mieszkanie renderuje
się surowo jak dziś — degraduje łagodnie, nie znika.

## 4. Przypadki brzegowe

- **Sesja z `localStorage` sprzed tej zmiany:** brak `typeColors` →
  backfill w `RESTORE_STATE` (§2.1). Brak `net_geometry` w zapisanym
  `layoutResult` → renderer i tak bierze `apt.net_geometry ?? apt.geometry`,
  więc do następnego przeliczenia mieszkania rysują się surowo (bez błędu);
  po pierwszym „Generuj układ"/„Podziel na mieszkania" dostają netto.
- **Mieszkanie zbyt małe na netto** (`net_polygon` puste): `net_geometry =
  null` → fallback do surowego. To samo mieszkanie „wyleje się" jak dziś,
  ale przynajmniej się narysuje. Akceptowalne (skrajny przypadek).
- **`net_polygon` daje MultiPolygon** (np. mieszkanie w kształcie L z cienką
  szyjką): `_net_geometry_json` zwraca `None` (serializujemy tylko prosty
  `Polygon`, bo `ringToPoints` na froncie czyta `coordinates[0]`) →
  fallback do surowego. W praktyce mieszkania z `fit_program_to_rectangles`
  są prostokątami, więc to rzadkie.
- **Ręczna edycja wspólnej ściany** (`findSharedLines`/`moveSharedLine`,
  `CanvasEditor.tsx:240/288`) działa na geometrii SUROWEJ (na osiach) — bez
  zmian. Uchwyt przeciągania ściany leży na osi (środku pasa ściany), a
  wypełnienie mieszkania kończy się na licu netto — to semantycznie
  poprawne (chwytasz oś ściany, nie lico), nie wymaga korekty w tym specu.
- **Kolor typu = kolor statusu** (np. M2 domyślnie emerald ≈ zielony `ok`):
  fill jest pół-przezroczysty, stroke kryjący — wciąż rozróżnialne;
  a user może przemalować. Nie blokujące.
- **Wiele wierszy programu tego samego typu:** współdzielą jeden kolor
  (klucz = typ). Zamierzone (§2.1).

## 5. Weryfikacja

Backend (`backend/tests/`, pytest przez `.venv/Scripts/python.exe`):
- `/layout/generate`, `/layout/units` oraz każda iteracja w `iterations[]`
  zwracają `net_geometry` dla mieszkania normalnej wielkości; poligon netto
  ma bbox skurczony o 0.10m względem `geometry` (surowego).
- Mieszkanie zbyt małe → `net_geometry is None`, brak wyjątku.

Frontend (ręcznie, brak testów automatycznych — konwencja projektu):
1. Panel „Struktura mieszkań": przy każdym wierszu widoczny okrągły swatch
   w kolorze typu; klik → natywny próbnik; wybór koloru → mieszkania tego
   typu na płótnie zmieniają wypełnienie natychmiast.
2. Obramowanie mieszkania nadal zmienia kolor wg statusu walidacji
   (zielony/żółty/czerwony), niezależnie od wypełnienia per typ.
3. Kolor typu przeżywa odświeżenie strony (localStorage).
4. §B: wypełnienie mieszkania KOŃCZY się na wewnętrznym licu ściany —
   między dwoma mieszkaniami widać szary pas ściany (0.20m), przy elewacji
   widać pełny pas 0.40m; kolor nie wchodzi na ścianę.
5. Przełączenie iteracji podziału (klik w wiersz listy „Iteracje") →
   mieszkania nadal netto (nie „wylane") — potwierdza dual-surface.
6. Regresja: etykiety (`typ` + `m²`), etykieta netto na zaznaczonym,
   tryb Słońce, eksport — bez zmian.
