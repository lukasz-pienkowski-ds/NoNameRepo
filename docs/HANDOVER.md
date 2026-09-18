# Centrala — założenia i przekazanie

Notatka dla człowieka albo dla agenta, który wraca do tego od zera.
`CENTRAL-STORE.md` obok jest referencją techniczną po angielsku; ten plik mówi
**dlaczego** rzeczy są tak zrobione i czego nie trzeba sprawdzać drugi raz.

Stan na 18 września 2026. Branch `czarek`, nic nie zacommitowane.

---

## 1. Co to jest

Centralna połowa systemu „DuckLake & Grill-Me": jeden proces DuckDB, który
trzyma bazę decyzji i serwuje ją wszystkim maszynom przez protokół `quack`.

Kod nie mieszka w osobnym folderze — jest rozłożony po katalogach repo:
`common/` dla rzeczy współdzielonych (`sessions.py`, `marker.py`, `tags.py`),
`db/` dla magazynu i dostępu (`server.py`, `client.py`, `extract.py`, `cli.py`,
`worker_embeddings.py`, `decisions_schema.sql`).

Pierwotny scaffold zespołu (tabela `documents`, `init_db.py`, `serve_ui.py`,
dwa skille, usługi `context-store` i `context-ui`) **został usunięty** — patrz
punkt 11. Zostało z niego tylko `common/embeddings.py`, bo to wyznaczony punkt
podmiany modelu i mój kod go używa.

Powód istnienia centrali: plik DuckDB ma dokładnie jednego writera, więc trzy
laptopy celujące w ten sam plik zakleszczą go albo uszkodzą. Tutaj jeden proces
jest właścicielem pliku, wszystkie zapisy idą przez niego, więc są
serializowane z definicji.

**Zasada, nie preferencja:** dopóki serwer działa, nikt inny nie otwiera pliku
bazy — nawet skrypt tylko do odczytu na tej samej maszynie. Dostanie
`Could not set lock on file`. Wszystko łączy się jako klient.

---

## 2. Start w 60 sekund

```bash
export PATH="$HOME/.docker/bin:$PATH"     # docker nie jest w domyslnym PATH
cd .../NoNameRepo
docker compose up -d --build decision-store embedding-worker
docker compose exec decision-store python db/cli.py load data/seed/decisions.jsonl
```

Z hosta (i z laptopa kolegi, po podmianie adresu):

```bash
export QUACK_URI="quack://127.0.0.1:8888" QUACK_TOKEN="sialababamak"
.venv/bin/python db/cli.py status
.venv/bin/python db/cli.py find --tags skalowanie wydajnosc
```

Token jest w `.env` (gitignorowany).

---

## 2b. Uniwersalność wobec LLM-a

Rozwiązanie nie jest związane z Claude'em. `sessions.py` wykrywa, które CLI ma
sesje na maszynie, i normalizuje je do jednego strumienia wiadomości — reszta
kodu nie wie, z jakiego narzędzia pochodzi sesja.

| CLI | Lokalizacja | Stan adaptera |
|---|---|---|
| claude | `~/.claude/projects/**`, `$CLAUDE_CONFIG_DIR`, `~/.claude-*` | ✅ sprawdzony na realnych sesjach (42 pliki) |
| gemini | `~/.gemini/tmp/<projekt>/chats/**` | ✅ sprawdzony na realnych sesjach (6 plików) |
| codex | `~/.codex/sessions/**` | ⚠️ **niesprawdzony** — brak instalacji na tej maszynie |

`python db/extract.py --detect` mówi, co realnie jest.

**Różnice między formatami są istotne, nie kosmetyczne:**

- Claude trzyma `uuid` i `sessionId` na **każdym** rekordzie. Gemini ma
  `sessionId` tylko w rekordzie nagłówkowym (1 z 52 linii) — trzeba go
  przeczytać i nieść dalej.
- Gemini powtarza wiadomości wewnątrz snapshotów `$set`, więc ta sama decyzja
  pojawia się dwa razy w jednym przebiegu. Deduplikacja po `id` jest w
  `collect()` **i** w `insert_decisions` — bo DuckDB przy dwóch tych samych
  kluczach w jednym `INSERT ... ON CONFLICT` **nie zgłasza błędu, tylko po cichu
  zostawia pierwszy**. Sprawdzone.
- Oba CLI używają dwóch kształtów pola `content` (lista bloków i goły string)
  i **nie zgadzają się, która rola używa którego**.
- Identyfikatory są unikalne tylko w obrębie jednego narzędzia, więc klucz jest
  prefiksowany: `claude:<uuid>`, `gemini:<id>`.

---

## 2c. Znacznik musi nieść trzy rzeczy

`marker.py` wymaga wszystkich trzech i **odrzuca** niekompletny znacznik,
zamiast zapisać ułomny rekord:

1. **decyzja** — co zostało wybrane
2. **założenia** — techniczne *i* biznesowe; bez nich nikt nie oceni, czy
   precedens w ogóle przenosi się na jego sytuację
3. **uzasadnienie** — dlaczego ta opcja i dlaczego odrzucono pozostałe; kod
   pokazuje, co zrobiono, nigdy czego nie zrobiono

Decyzja bez założeń to ta, którą stosuje się tam, gdzie nie pasuje — a to gorsze
niż nieznalezienie żadnej.

**Pułapka, na którą już się nadzialiśmy:** wszystko, co *opisuje* znaczniki,
zawiera znacznik. Ten plik, README, plik skilla i każda rozmowa o formacie są
wciągane przez ekstraktor. Zdarzyło się to realnie — ekstraktor puszczony na
sesjach tej maszyny znalazł dwa znaczniki z rozmowy, w której cytowano
specyfikację. Nie ma niezawodnego sposobu odróżnienia przykładu od prawdziwego
zapisu, więc obowiązuje konwencja: **przykłady zostawiają jedno wymagane pole
puste**, żeby się nie parsowały. `marker.TEMPLATE` tak właśnie robi.

---

## 3. Decyzje zamrożone — nie otwierać drugi raz

| Kwestia | Ustalenie | Dlaczego |
|---|---|---|
| Transport | `quack`, bez własnego API REST | zweryfikowane: zdalny odczyt, INSERT, DDL, 30 równoległych zapisów od 3 klientów |
| Klucz rekordu | **`uuid` wiadomości z pliku `.jsonl`** | patrz punkt 4 — to jedyny wariant, który nie gubi i nie duplikuje |
| Kto generuje `id` | nikt — bierze się z transportu | `client.insert_decisions` **odrzuca** rekord bez `id` zamiast go dogenerować |
| Wyszukiwanie | `array_cosine_similarity`, funkcja rdzeniowa | zweryfikowane: działa przy zerowej liczbie rozszerzeń. `vss` nie jest ładowany |
| Indeks ANN | brak | przy kilkudziesięciu wierszach pełny skan bije utrzymanie indeksu |
| Kolejność rankingu | **tagi sortują, podobieństwo rozstrzyga remisy** | patrz punkt 5 — przy `mock_embed` podobieństwo jest szumem |
| Embeddingi | na centrali, asynchronicznie po `embedding IS NULL` | zapis z laptopa nie czeka na model; padnięty model nie blokuje zapisów |
| Destylacja LLM | brak w ścieżce ekstrakcji | `<decision_log>` wyciąga się `LIKE`-iem, za darmo i deterministycznie |
| Graf krawędzi decyzji | nie budujemy | przy kilkunastu rekordach nikt ich nie utworzy |
| Surowa sesja w centrali | nie — zostaje na laptopie | w bazie tylko `session_uuid` jako wskaźnik |
| Wsparcie dla LLM-ów | claude + gemini sprawdzone, codex napisany na ślepo | adaptery w `sessions.py`, dodanie czwartego to jeden plik |
| Zawartość znacznika | decyzja + założenia (tech i biznes) + uzasadnienie | niekompletny znacznik jest zgłaszany, nie zapisywany |

---

## 4. Dlaczego klucz to `uuid` wiadomości

To jest najmniej oczywista decyzja w całym projekcie, więc warto ją rozumieć,
a nie tylko znać.

Sesja agenta to plik, który **rośnie**, a nie kolejka. Ekstraktor czyta go
w całości przy każdym uruchomieniu, a w ciągu dnia uruchomicie go wiele razy.
Zmierzone na trzech wariantach klucza, na sesji z **dwiema** decyzjami:

| Klucz | Po kilku przebiegach | |
|---|---|---|
| `sessionId`, lub `sessionId` + developer | **1 rekord z 2**, reszta znika bez błędu | sesja ma średnio 32 wiadomości asystenta, więc decyzje kolidują |
| `uuid()` w ekstraktorze | każda decyzja ×N | `ON CONFLICT` nie ma na czym zadziałać |
| **`uuid` wiadomości** | dokładnie 2, niezależnie od liczby przebiegów | ✅ |

Cicha utrata jest gorsza z tych dwóch porażek — dlatego klucz sesyjny jest
pułapką, a nie oczywistym wyborem. Zmierzone na realnych sesjach: 468
wiadomości, 468 unikalnych `uuid`, identycznych przy powtórnym odczycie.

---

## 5. Dlaczego tagi sortują przed podobieństwem

`mock_embed` z `common/embeddings.py` sumuje skróty bajtów bez zmiany znaku,
więc wszystkie wektory celują w tę samą stronę. Zmierzone:

```
partycjonowanie  vs  cache TTL                     0.9768
partycjonowanie  vs  "rudy kot spi na parapecie"   0.9801   <-- wyzej
```

Rozpiętość na pięciu niezwiązanych tekstach: 0.0335. Zdanie o kocie wygrywa
z powiązanym tematem. To nie jest błąd w okablowaniu — tak zachowuje się
atrapa oparta na haszu. Dwie konsekwencje, dopóki jest w użyciu:

- **`tag_overlap` sortuje pierwszy** — to jedyny sygnał niosący informację;
- **`min_similarity` domyślnie 0** i nic nie odcina; odcina filtr po tagach.

Gdy wejdzie prawdziwy model: zamienić dwie linie w `ORDER BY` w `client.py`
i podnieść próg. Jest tam komentarz, który to mówi.

---

## 6. Pułapki, które kosztowały po godzinie

Wszystkie znalezione przez **uruchomienie**, nie przez czytanie dokumentacji.
Jeśli wracasz do tego od zera, to jest lista rzeczy, o które się potkniesz.

1. **URI musi mieć schemat `quack://`.** `quack_serve('127.0.0.1:8888')` leci
   `Invalid DuckDB Quack RPC URI`. Po obu stronach, mimo że pod spodem HTTP.

2. **`quack_serve` nie zbinduje się na `0.0.0.0` bez `allow_other_hostname`.**
   *„Only localhost is allowed as a Quack RPC hostname by default."* To jest
   dokładnie to, czego potrzebuje kontener. `server.py` ustawia flagę sam, gdy
   host nie jest localhostem. Ostrzeżenie z komunikatu jest realne: tokenem stoi
   całe bezpieczeństwo, więc w prawdziwej sieci trzeba reverse proxy z TLS.

3. **Token musi mieć ≥4 znaki i nie ma trybu bez tokenu.** Quack sprawdza to
   dopiero po wystartowaniu, surowym wyjątkiem. `server.py` waliduje wcześniej
   i wypisuje zdanie.

4. **`QUALIFY` w DuckDB wymaga funkcji okna.** Próg po wyliczonym aliasie
   idzie do `WHERE`.

5. **`message.content` w plikach sesji ma dwa kształty** — tablicę bloków
   *i* goły `VARCHAR`. Naiwny filtr po blokach `text` gubi prompty człowieka,
   czyli najgęstszy materiał. Dotyczy osoby robiącej ekstrakcję.

6. **`docker compose run` to nowy kontener.** Polecenia gadające z działającym
   serwerem muszą iść przez `exec`, inaczej pod `127.0.0.1:8888` nic nie słucha.

7. **`docker` nie jest w domyślnym PATH** — `export PATH="$HOME/.docker/bin:$PATH"`.

7a. **`make` tuż po `--build` potrafi raz zwrócić kod 2** przy zielonych
   testach. Widziane raz, nieodtworzone w pięciu próbach; w tamtym przebiegu
   kontener miał „Up Less than a second", więc `docker compose exec` prawdopodobnie
   trafił w usługę, która jeszcze wstawała. Przyczyny nie ustaliłem — jeśli
   zobaczysz to przed demem, po prostu powtórz polecenie.

7b. **Nie kotwicz ścieżek na nazwie `tmp`.** Projekt Gemini brałem jako segment
   po `tmp` — na macOS działało, a w kontenerze `/tmp/...` trafiało w systemowy
   katalog i test padał. Kotwica jest teraz na `chats/`. Testy w kontenerze
   łapią to, czego testy na hoście nie złapią.

8. Gdyby ktoś dokładał `vss`: **musi go załadować proces serwera przy starcie.**
   Wysłanie `LOAD vss` przez `quack_query` zwraca `Success` i nie zmienia nic.
   A HNSW na trwałej bazie wymaga flagi eksperymentalnej z ostrzeżeniem
   o utracie danych.

---

## 7. Co zweryfikowane, a co nie

**Testy uruchamialne — obydwa pliki są w repo, nie w transkrypcie:**

- `make test` → `test_smoke.py`, **30 asercji**, bez serwera i bez frameworka:
  kontrakt znacznika, odczyt obu formatów sesji, ekstrakcja.
- `make test-integration` → `test_integration.py`, **17 asercji** przeciw
  działającej centrali: idempotencja, dedup duplikatu `id` w jednym `INSERT`,
  kolejka embeddingów, wyszukiwanie, pętla zwrotna, 30 równoległych zapisów
  od 3 klientów.
- `make test-all` → obydwa.

Test integracyjny pisze **wyłącznie pod własną nazwą projektu**
(`__integration_test__`) i kasuje ją w `finally`, więc można go puścić przeciw
bazie z prawdziwymi decyzjami — sprawdzone, stan bazy przed i po jest ten sam.
Bez centrali pomija się z kodem 0; przy **odrzuconym tokenie pada**, bo to
literówka w konfiguracji, a nie brak serwera.

Puszczaj testy **też w kontenerze** — jedna pułapka ze ścieżkami ujawniła się
wyłącznie tam.

**Zweryfikowane end-to-end, natywnie i w Dockerze:** budowanie obrazu,
healthcheck, worker sam podchwytujący nowe rekordy, dostęp z hosta przez
opublikowany port w obie strony, trwałość po `down` i `up`, idempotencja przy
czterech przebiegach, wyszukiwanie działające zanim policzą się wektory,
reingest niekasujący wektorów, brak trafień jako poprawna odpowiedź, odrzucenie
tagu spoza słownika, odrzucenie rekordu bez `id`, pętla zwrotna po review,
30 równoległych zapisów od 3 klientów (30/30, po 10).

Dodatkowo: wykrywanie providerów i normalizacja na **realnych** sesjach z tej
maszyny (48 plików, claude + gemini, skan w 0,25 s).

**Niezweryfikowane:**

1. **Dostęp z innej maszyny** w sieci — testowane tylko host ↔ kontener na
   jednym komputerze. Pierwsza rzecz do sprawdzenia, gdy zbierzecie się w trójkę.
2. **Adapter codex** — napisany z dokumentowanego kształtu, nigdy nie puszczony
   na prawdziwych danych. Zgaduje też, że rekordy nie mają własnych `id`, więc
   klucz robi z pliku i pozycji w nim.
3. **Emisja znaczników przez skill** — nic ich jeszcze nie produkuje. Ekstraktor
   czyta je poprawnie, ale ścieżka „rozmowa → otagowany rekord" jest domknięta
   tylko od strony odczytu.

---

## 8. Szwy dla reszty zespołu

- **Droga zapisu (ekstrakcja z sesji):** woła `store.insert_decisions(records)`
  z `id` = `uuid` wiadomości. Rekord bez `id` jest odrzucany celowo.
- **Skill:** woła `store.find_precedent(query_text=..., tags=[...], limit=3)`
  i dostaje **pustą listę**, gdy nic nie przechodzi progu. Pusta lista jest
  odpowiedzią, nie awarią — przy pracy zły precedens szkodzi bardziej niż brak.
- **Słownik tagów:** `tags.py`, 15 pozycji. Ten sam plik ma znać skill.
  `cli.py` odrzuca tag spoza listy przy zapisie **i** przy zapytaniu, żeby
  rozjazd wyszedł jako błąd, a nie jako po cichu pusty wynik.

---

## 9. Otwarte, do decyzji zespołu

1. **Model embeddingowy i wymiar.** `FLOAT[16]` jest dziś zgodne z
   `EMBEDDING_DIM` w `common/embeddings.py`. Tablica ma stały rozmiar, więc
   zmiana wymiaru to przebudowa kolumny i przeliczenie wszystkiego.
   **Najpierw model, potem liczba w schemacie.**
2. **Kto embeduje zapytanie.** Musi to być ten sam model co przy zapisie.
   Dziś klient robi to lokalnie, bo `mock_embed` to czysty Python. Gdy model
   stanie tylko na centrali — albo model idzie na każdą maszynę, albo
   wyszukiwanie z laptopa zostaje tylko po tagach, albo serwer dostaje endpoint
   zapytań.
3. **Statusy są po angielsku** (`unknown`/`confirmed`/`rejected`), bo repo jest
   po angielsku, ale **tagi zostały po polsku** jako zamrożony słownik danych.
   Jeśli zespół woli jednolicie — zmiana na kilka minut.
4. **Redakcja wobec umów z klientami** — do rozstrzygnięcia poza zespołem
   technicznym, zanim cokolwiek poza własnymi sesjami trafi do wspólnej bazy.

---

## 10. Mapa plików

Kod centrali jest rozłożony po katalogach repo, nie w osobnym folderze —
`common/` to rzeczy współdzielone i importowalne, `db/` to magazyn i dostęp
do niego.

```
common/sessions.py      wykrywanie i normalizacja sesji z dowolnego CLI
common/marker.py        kontrakt <decision_log> i parser
common/tags.py          zamrozony slownik 15 tagow, wspolny ze skillem
common/embeddings.py    (zespolu) mock_embed / mock_tag - punkt podmiany modelu

db/decisions_schema.sql tabela decisions + komentarze o kluczu i indeksie
db/server.py            otwiera baze, laduje quack, serwuje, waliduje token
db/client.py            transport + find_precedent / insert / set_status
db/worker_embeddings.py uzupelnia NULL-e; klient quack, nie otwiera pliku
db/extract.py           skan sesji -> decyzje -> centrala
db/cli.py               status / load / find / confirm
test_smoke.py           testy offline, 30 asercji (make test)
test_integration.py     testy przeciw dzialajacej centrali, 17 asercji
data/seed/decisions.jsonl   6 rekordow demo, w tym scenariusz DuckDB-vs-beads
data/db/decisions.duckdb    plik centrali (gitignorowany)

docker/Dockerfile       jeden obraz dla wszystkich uslug, z wbudowanym quack
docker-compose.yml      decision-store + embedding-worker
Makefile                up / status / seed / find / detect / extract / test / test-all
.env                    QUACK_TOKEN, gitignorowany
docs/                   ten plik, SCENARIUSZ.md, CENTRAL-STORE.md
```

`docs/SCENARIUSZ.md`: scenariusz w punktach, z mapą „krok → co przetestowane".
`docs/CENTRAL-STORE.md`: referencja techniczna (EN).

Dokumenty koncepcyjne są w `../../hackathon_2026/docs/`:
`koncepcja.md`, `recykling-sesji.md`, `plan-hackathonu-v3.md`,
`punkty-do-dyskusji.md`.

---

## 11. Co zostało usunięte z repo i dlaczego

Repo startowało ze scaffoldem zespołu: generyczna tabela `documents`,
`db/init_db.py`, `db/serve_ui.py`, `data/raw/sample.jsonl`, dwa skille
`.claude/skills/*` oraz usługi `context-store` i `context-ui`. Usunięte
decyzją zespołu, bo magazyn decyzji je zastępuje, a nic z obecnego kodu ich
nie importowało (sprawdzone przed kasowaniem).

Dwie rzeczy przemawiały za usunięciem mocniej niż sama redundancja —
zmierzone, nie założone:

- **`context-ui` nie działała na macOS.** Logowała serwowanie na porcie 4213,
  ale port nie odpowiadał (`curl` → HTTP 000). `network_mode: host` jest
  Linux-only, co README zespołu samo odnotowywało.
- **`context-store` padał przy zwykłym `docker compose up -d`** z
  `Could not set lock on file`, bo `context-ui` zdążyła wcześniej zająć
  `context.duckdb`. Czyli problem jednego writera wykładał scaffold na żywo.

Zostało `common/embeddings.py` — `mock_embed` i `EMBEDDING_DIM` są używane przez
`db/client.py`, `db/worker_embeddings.py` i `test_integration.py`.

**Drobiazg do sprzątnięcia:** `mock_tag` w tym pliku nie jest już przez nic
wywoływany (używał go tylko skasowany `ingest.py`). Zostawiony, bo to plik
zespołu i nie przeszkadza.