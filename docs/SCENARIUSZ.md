# Scenariusz, pod który to rozwiązanie pasuje

Zwięźle: co ten kod obsługuje, co z tego zostało przetestowane i gdzie są
granice. Stan na 18 września 2026.

---

## 1. Scenariusz w punktach

1. Senior pracuje z agentem (Claude, Gemini albo Codex) nad decyzją techniczną.
2. Skill prowadzi rozmowę tak, żeby decyzja została nazwana, i **dokleja do
   wiadomości blok `<decision_log>`** z trzema częściami: decyzja, założenia
   techniczne i biznesowe, uzasadnienie wyboru i odrzucenia.
3. Blok zostaje w pliku sesji `.jsonl` — nikt nie pisze nic dodatkowo.
4. Ekstraktor skanuje sesje **niezależnie od tego, które CLI je stworzyło**,
   wyciąga bloki zwykłym dopasowaniem tekstu i wysyła je do centrali.
5. Centrala to jeden proces DuckDB w kontenerze, dostępny dla całego zespołu
   przez `quack`. Embeddingi liczą się tam, asynchronicznie.
6. Tydzień później junior w **innym projekcie** staje przed podobnym problemem.
7. Jego agent odpytuje centralę: filtr po tagach, ranking, próg odcięcia.
8. W trybie `grill` dostaje **pytanie o ograniczenie**, nie gotowca.
   W trybie `precedens` (senior) — decyzję, uzasadnienie i nazwisko autora.
9. Po code review status decyzji wraca do bazy.

---

## 2. Do czego to pasuje

- Zespół **kilku osób**, pracujących w **różnych projektach**, na **różnych
  narzędziach agentowych**.
- Wiedza, która dziś ginie: co odrzucono i dlaczego — czego z kodu nie odtworzysz.
- Skala **dziesiątek do setek** rekordów. Wtedy pełny skan jest szybszy niż indeks.
- Praca u klientów: do centrali idzie tylko to, co otagowane; surowa sesja
  zostaje na laptopie, w bazie jest tylko wskaźnik.

## 3. Do czego NIE pasuje

- Skala tysięcy rekordów — wtedy trzeba indeksu ANN i prawdziwych embeddingów.
- Zastąpienie dokumentacji. To zapis, jak **było**, a nie jak **ma być**.
- Zespół na jednym projekcie i jednym narzędziu — wtedy wystarczy CLAUDE.md.
- Sytuacje, gdzie precedens musi być pewny. Dziś każdy rekord ma `status`
  `unknown`, dopóki ktoś nie domknie pętli po review.

---

## 4. Co przetestowane, krok po kroku

| Krok scenariusza | Stan | Czym potwierdzone |
|---|---|---|
| 1. Praca z agentem | — | poza zakresem kodu |
| 2. **Skill dokleja blok** | ❌ **brak** | nic jeszcze nie emituje znaczników |
| 3. Blok w pliku sesji | ✅ | ekstraktor znalazł 2 realne znaczniki w sesjach tej maszyny |
| 4. Odczyt z dowolnego CLI | ✅ claude, gemini<br>⚠️ codex | 10 asercji + skan 48 realnych plików w 0,25 s |
| 4b. Parsowanie znacznika | ✅ | 12 asercji, w tym odrzucenie każdej z 3 brakujących części |
| 4c. Wysyłka do centrali | ✅ | 8 asercji + test na żywo |
| 5. Centrala w kontenerze | ✅ | build, healthcheck, dostęp z hosta, trwałość po restarcie |
| 5b. Embeddingi asynchroniczne | ✅ | worker sam podchwycił 6 rekordów po `load` |
| 6-7. Zapytanie o precedens | ✅ | BM25 po treści, filtr po tagach, próg, brak trafień jako wynik |
| 8. **Tryby grill / precedens** | ❌ **brak** | zaprojektowane, nieistniejące w kodzie |
| 9. Pętla zwrotna po review | ✅ | `UPDATE` po `id`, status zmieniony |

---

## 5. Testy — co konkretnie sprawdzono

**Offline, uruchamialne** (`make test`) — 30 asercji,
przechodzą na hoście i w kontenerze:

- kontrakt znacznika (12): trzy części wymagane, każdy brak osobno odrzucony,
  zły JSON, płaska lista założeń, dwa znaczniki w wiadomości, odrzucone opcje
- odczyt sesji (10): wykrywanie providerów, oba kształty `content`,
  pominięcie sidechainów i `tool_result`, `sessionId` z nagłówka Gemini,
  projekt ze ścieżki, brak kolizji kluczy między CLI
- ekstrakcja (8): zebrane decyzje, brak duplikatu z `$set`, provider w rekordzie,
  założenia obecne, tag spoza słownika zgłoszony i niezapisany

**Na żywo, przeciw działającej centrali** (`make test-integration`) — 23 asercje:
idempotencja przy 4 przebiegach, odrzucenie rekordu bez `id`, dedup duplikatu
`id` w jednym `INSERT`, kolejka embeddingów, wyszukiwanie działające zanim
policzą się wektory, reingest niekasujący wektorów, zmiana treści wracająca do
kolejki, filtr po tagu, brak trafień, próg odcięcia, wykluczenie autora, pętla
zwrotna, oraz **30 równoległych zapisów od 3 klientów** → 30/30.

**Docker:** build obu usług, healthcheck, worker liczący sam, dostęp z hosta
przez opublikowany port w obie strony, trwałość danych po `down` + `up`.

**Pomiary, które zmieniły decyzje projektowe:**

- `read_json(union_by_name)` — 12 sesji o 19 zestawach kluczy w 0,14 s
- filtr do bloków tekstowych — 8,2% objętości
- `uuid` w sesjach Claude — 468 wiadomości, 468 unikalnych, stabilnych
- trzy warianty klucza — `sessionId` gubi 1 rekord z 2, `uuid()` duplikuje
- `array_cosine_similarity` — funkcja rdzeniowa, działa bez `vss`
- `mock_embed` — rozpiętość podobieństwa 0,0335; „rudy kot" bije „cache TTL"

---

## 6. Trzy błędy, które wyszły wyłącznie z uruchomienia

1. **DuckDB po cichu gubi drugi wiersz**, gdy ten sam klucz trafi dwa razy
   w jednym `INSERT ... ON CONFLICT`. Bez błędu. Gemini wywołuje to rutynowo
   przez snapshoty `$set`.
2. **`quack_serve` nie zbinduje `0.0.0.0`** bez `allow_other_hostname` — czyli
   dokładnie tego, czego potrzebuje kontener. Testy lokalne na `127.0.0.1`
   tego nie pokazały.
3. **Test przeszedł na hoście, padł w kontenerze** — ścieżka kotwiczona na
   segmencie `tmp` trafiała w kontenerze w systemowy `/tmp`.

---

## 7. Granice, o których trzeba pamiętać przy prezentacji

- **Skill nie istnieje.** Kroki 2 i 8 scenariusza — emisja znaczników i tryb
  grill — są zaprojektowane, ale nie napisane. To połowa demo.
- **Adapter codex napisany na ślepo**, brak instalacji do sprawdzenia.
- **Dostęp z drugiej maszyny niesprawdzony** — wszystko szło host ↔ kontener
  na jednym komputerze.
- **Ranking tekstowy to BM25, nie model.** Dopasowuje wspólne słowa, nie
  znaczenie — pytanie synonimami nie trafi. `mock_embed` pozostaje atrapą
  i nie wnosi nic do kolejności.
- **Wszystko, co opisuje znaczniki, zawiera znacznik.** Ekstraktor wciągnął
  przykład zacytowany w rozmowie. Konwencja: przykłady zostawiają jedno
  wymagane pole puste.

---

Przebieg demo krok po kroku: `DEMO.md` w katalogu głównym repo.
