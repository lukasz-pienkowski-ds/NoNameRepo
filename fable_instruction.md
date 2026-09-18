# Wskazówki po przeglądzie kodu — do rozebrania przez zespół

Stan na 18 września 2026, commit `596c185` (`wip`) plus zmiany w indeksie.
Pełny raport z uzasadnieniem, numerami linii i pomiarami:
`../nonamerepo-fixes.md`. Ten plik jest listą zadań do wzięcia, nie raportem.

Każde zadanie ma: co jest nie tak, gdzie, co zrobić, jak sprawdzić. Odhacz po
zrobieniu i dopisz inicjały, żeby dwie osoby nie robiły tego samego.

---

## Ocena ogólna

Centrala, klient, ekstrakcja i adaptery claude/gemini **działają i są
zweryfikowane na żywo**. Architektura (jeden proces DuckDB, klucz z `uuid`
wiadomości, `NULL` jako kolejka, brak LLM-a w ekstrakcji) jest dobra i nie
wymaga zmian. Poniższe poprawki to godziny pracy, nie dni.

**Czego nie ma:** skilla emitującego `<decision_log>` i trybów
`grill` / `precedens`. To jest połowa demo i największe ryzyko. Poprawki z tego
pliku nie powinny opóźniać pracy nad skillem.

**Pierwsza rzecz do sprawdzenia, gdy zbierzemy się razem:** dostęp do centrali
z drugiej maszyny. Nikt tego jeszcze nie zrobił; wszystko szło host ↔ kontener
na jednym komputerze.

---

## A. Krytyczne — potwierdzone na działającej centrali

Zrób przed kolejnym `make build` i przed zasileniem bazy prawdziwymi sesjami.

### A1. Ponowny `make extract` kasuje status po code review  `[ ]`

- **Co:** `insert_decisions` nadpisuje wszystkie kolumny przy konflikcie, a
  ekstraktor zawsze wysyła `status: "unknown"`. Sprawdzone: `confirmed`
  wraca do `unknown` po jednym przebiegu.
- **Gdzie:** `db/client.py` (lista `updates` w `insert_decisions`),
  `db/extract.py` (`"status": "unknown"`).
- **Zrób:** wyłącz `status` z `ON CONFLICT DO UPDATE`; dopuść nadpisanie tylko
  gdy przychodzący status jest inny niż `unknown` (żeby seed z `confirmed`
  dalej działał). Zdecyduj to samo dla `developer_id` i `seniority_level`:
  dziś ostatni, kto puścił `make extract`, podpisuje wszystkie decyzje.
- **Sprawdź:** nowa asercja w `test_integration.py`: `set_status` →
  `insert_decisions` tego samego rekordu → status dalej `confirmed`.

### A2. `make detect` i `make extract` widzą zero sesji  `[ ]`

- **Co:** oba cele lecą przez `docker compose exec`, a kontener nie ma
  zamontowanego `~/.claude` ani `~/.gemini`. Sprawdzone: w kontenerze 0/0/0,
  na hoście claude 24, gemini 6.
- **Gdzie:** `Makefile` (cele `detect`, `extract`), `README.md` (quickstart),
  `docs/HANDOVER.md` §2b.
- **Zrób:** uruchamiaj te dwa cele na hoście przez `.venv/bin/python`
  (`db/client.py` czyta już token z `.env`, więc nic więcej nie trzeba).
  Dodaj `make extract-demo` z `--root data/sessions --provider claude`, ten
  może zostać w kontenerze. Popraw zdanie w README.
- **Sprawdź:** `make detect` na czystej maszynie pokazuje liczby większe od 0.

### A3. Obraz Dockera zawiera token, `.git` i kopię bazy  `[ ]`

- **Co:** brak `.dockerignore`, więc `COPY . .` wciąga `.env` z `QUACK_TOKEN`,
  `.git` i `data/` (razem z `.duckdb` i `.wal`). `CMD` w Dockerfile wskazuje
  na skasowany `db/init_db.py`. Compose ma domyślny token `hackathon`, więc
  brak `.env` nie jest błędem, tylko cichym startem ze znanym hasłem.
- **Gdzie:** `docker/Dockerfile` (linie `COPY . .` i `CMD`),
  `docker-compose.yml` (obie usługi, `QUACK_TOKEN`), `.env.example`.
- **Zrób:** dodaj `.dockerignore` (`.git`, `.env`, `.venv`, `__pycache__`,
  `data/db/`, `data/sessions/`, `*.duckdb*`, `.DS_Store`); `CMD ["python",
  "db/server.py"]`; w compose `${QUACK_TOKEN:?set QUACK_TOKEN in .env}`;
  w `.env.example` placeholder zamiast `hackathon`.
- **Sprawdź:** `docker run --rm --entrypoint sh <obraz> -c 'ls /app/.env
  /app/.git'` zwraca „No such file”.

### A4. Demo traci nazwiska autorów  `[ ]`

- **Co:** `data/sessions/.../demo.jsonl` ma `_meta: {developer, seniority}`
  na każdym rekordzie (michal, anna, piotr, cezary). Ekstraktor to ignoruje.
  Sprawdzone: wszystkie 15 rekordów demo w bazie ma `developer_id = 'demo'`.
  Bez tego nie ma „junior dostaje nazwisko” i nie działa `exclude_developer`.
- **Gdzie:** `common/sessions.py` (`Message`, `_claude_messages`),
  `db/extract.py` (`collect()`).
- **Zrób:** dodaj do `Message` opcjonalne pole `meta: dict | None`, wypełniaj
  z `record.get("_meta")` w adapterze claude. W `collect()` wartość z `meta`
  wygrywa nad flagą `--developer` / `--seniority`. Prawdziwe pliki Claude nie
  mają `_meta`, więc nic się dla nich nie zmienia.
- **Sprawdź:** asercja w `test_smoke.py`; po `make extract-demo` w bazie są
  cztery różne `developer_id`.

---

## B. Prawdopodobne błędy — tanie, do zrobienia w ciągu dnia

### B1. Brak `status` zapisuje `NULL`; `set_status` na złym id milczy  `[ ]`

- `db/client.py`: jeśli rekord nie ma `status`, wstaw `unknown` (to samo dla
  `decision_type` → `decision`). W `set_status` dodaj `RETURNING id` i rzuć
  błąd, gdy nic nie wróciło. Sprawdzone na żywo: dziś oba przypadki przechodzą
  bez słowa.

### B2. Znacznik czasu decyzji jest gubiony  `[ ]`

- `Message.timestamp` jest wypełniany i nigdy nie zapisywany. `created_at` to
  moment wstawienia (wszystkie rekordy seed mają tę samą sekundę), więc
  „świeżość” w rankingu to kolejność ekstrakcji.
- Dodaj kolumnę `decided_at TIMESTAMP` do schematu, do `_COLUMNS` w kliencie,
  wypełnij w `collect()`, sortuj po niej. Uwaga: schemat to `CREATE TABLE IF
  NOT EXISTS`, więc istniejąca baza nie dostanie kolumny. Dodaj w
  `server.open_db()` idempotentne `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
  To samo dotyczy każdej przyszłej zmiany schematu.

### B3. Dwa bloki tekstu w jednym rekordzie kolidują na id  `[ ]`

- `_claude_messages` daje osobny `Message` na każdy blok `text`, wszystkie z
  tym samym `uuid`. `#index` w `collect()` liczy się w obrębie jednego bloku,
  więc znacznik w bloku 1 i znacznik w bloku 2 dostają to samo id, drugi
  nadpisuje pierwszy. Na tej maszynie 0 z 44 rekordów ma dwa bloki, więc
  błąd jest uśpiony, ale poprawka to trzy linie: połącz teksty rekordu
  (`"\n\n".join`) i wydaj jeden `Message`. To samo w gemini i codex.

### B4. Test integracyjny ściga się z workerem  `[ ]`

- `make up` startuje worker, który co 5 s zabiera `NULL`-e. Test asertuje
  `nulls == 3` zaraz po wstawieniu i `nulls == 1` po zmianie treści. Gdy poll
  workera trafi w to okno, test jest czerwony bez powodu.
- W `Makefile`: `docker compose stop embedding-worker` przed testem i `start`
  po. Albo przerób dwie asercje na „embedding jest `NULL` lub równy
  `mock_embed(summary)`”.

### B5. Worker może nadpisać zresetowany wiersz starym wektorem  `[ ]`

- Sekwencja: worker czyta `(id, S1)` → ekstraktor zmienia treść na `S2` i
  resetuje `embedding` → worker zapisuje `embed(S1)`. Wiersz schodzi z kolejki
  z wektorem do nieistniejącego tekstu.
- `set_embedding`: dodaj `AND embedding IS NULL AND decision_summary IS NOT
  DISTINCT FROM <treść, którą policzono>`. W workerze owiń pętlę w
  `try/except` ze `sleep`, żeby restart centrali nie robił pętli restartów
  kontenera.

### B6. Adapter codex najpewniej odrzuci wszystko  `[ ]`

- Z wiedzy o formacie rollout, **niesprawdzone** (brak instalacji). Bloki
  treści mają typ `input_text` / `output_text`, a `_texts` przyjmuje tylko
  `text`. Pliki leżą w `sessions/RRRR/MM/DD/rollout-*.jsonl`, więc
  `path.parent.name` daje dzień miesiąca zamiast projektu. Id sesji i `cwd`
  są w rekordzie `session_meta`.
- Kto pierwszy będzie miał codex: zrzuć jeden prawdziwy plik do fixtures w
  `test_smoke.py` i popraw adapter pod to, co realnie jest.

### B7. Klient rzuca `SystemExit`  `[ ]`

- `DecisionStore.__init__` kończy interpreter przy braku tokenu. Test
  integracyjny łapie `Exception`, więc ścieżka „pomiń z kodem 0” nigdy nie
  zadziała; przyszły skill zostanie zabity tak samo. Rzucaj `ValueError`,
  zamieniaj na `SystemExit` w `main()` w `cli.py` i `extract.py`.

### B8. Serwer nie obsługuje SIGTERM  `[ ]`

- `docker stop` zabija proces bez `quack_stop`, `CHECKPOINT` i `con.close()`.
  W `data/db/` leży teraz `.wal`. DuckDB go odtworzy, ale to jest dokładnie
  ten scenariusz, który kończy się uszkodzonym plikiem po `down` w trakcie
  zapisu. `signal.signal(SIGTERM, ...)` rzucający `KeyboardInterrupt`, w
  `finally` `CHECKPOINT` i `close()`.

### B9. Dwie definicje szerokości wektora  `[ ]`

- `FLOAT[16]` w `decisions_schema.sql` i `EMBEDDING_DIM = 16` w
  `common/embeddings.py`. Gdy wejdzie model i zmieni się jedno, każdy
  `set_embedding` padnie błędem DuckDB. W `open_db()` odczytaj typ kolumny z
  `duckdb_columns()` i zakończ zdaniem, gdy się nie zgadza.

---

## C. Warto, jeśli zostanie czas

### C1. Jedna linia w `mock_embed`  `[ ]`

- Dziś wszystkie wektory celują w tę samą stronę (HANDOVER §5). Wycentrowanie
  bajtów: `(digest[i] - 127.5) / 127.5` zamiast `digest[i] / 255.0`. Zmierzone
  podobieństwo do „partycjonowanie tabeli zdarzen po miesiacu”:

  | Tekst | dziś | po zmianie |
  |---|---|---|
  | powiązany (partycjonowanie po dacie) | 0,983 | 0,544 |
  | inny temat (cache TTL) | 0,946 | 0,267 |
  | niepowiązany (rudy kot) | 0,957 | 0,196 |

  Zamień też `[a-z0-9]+` na `\w+`, żeby polskie litery były tokenami. Po
  zmianie `UPDATE decisions SET embedding = NULL`, worker przeliczy.

### C2. Drobiazgi  `[ ]`

- `cli.py load` sprawdza tylko tagi; `status`, `seniority_level`,
  `decision_type` to wolny tekst. Dodaj `CHECK` w schemacie albo walidację w
  `insert_decisions`. `marker.parse` nie sprawdza `type` wobec
  `DECISION_TYPES`.
- `extract.py` zwraca 0 nawet gdy odrzucił znaczniki. Dodaj `--strict`.
- Martwy kod: `mock_tag`, `_KEYWORD_TAGS` i docstring w
  `common/embeddings.py` (wymienia skasowane `db.py`, `ingest.py`,
  `query.py`). `pyproject.toml` ma nazwę i opis ze scaffoldu.
- `server.py` domyślnie binduje `0.0.0.0`; w kodzie daj `127.0.0.1`, compose
  i tak przekazuje `--host 0.0.0.0`.
- `make clean` przy działającym serwerze kasuje plik pod procesem. Uzależnij
  od `down`.
- Pętla dev: kod jest zapieczony w obrazie (HANDOVER 7c). Plik
  `docker-compose.override.yml` montujący `./db`, `./common` i pliki testów
  zdejmuje pułapkę bez ruszania produkcyjnego compose. Nie montuj `.`
  w całości, bo `.venv` z macOS nie zadziała w Linuksie.
- Worker embeduje tylko `decision_summary`. Przy prawdziwym modelu połącz
  summary + rationale + założenia i porównuj to samo w regule `IS DISTINCT
  FROM` w upsercie.
- Embedding zapytania liczy się na laptopie (`client._embed`). Z modelem na
  centrali to przestanie działać. Najprościej: mały endpoint HTTP obok
  `quack_serve`, który zwraca wektor dla tekstu.

---

## D. Dokumentacja

### D1. `docs/CENTRAL-STORE.md`  `[ ]`

- Zdublowany akapit „One thing to settle before a real model lands”.
- „The rest of this repo opens `context.duckdb` directly” i „Unlike the `ui`
  extension used elsewhere in this repo” opisują skasowany scaffold.
- `from client import DecisionStore` → `from db.client import DecisionStore`.
- `schema.sql` → `db/decisions_schema.sql` (to samo w `db/client.py` i
  `db/worker_embeddings.py`).

### D2. `README.md`, `docs/HANDOVER.md`  `[ ]`

- Zdanie o `make detect` jest nieprawdziwe, dopóki cel działa w kontenerze
  (A2).
- README mówi o 17 asercjach integracyjnych, w pliku jest 18.
- HANDOVER §6 numeruje 7, 7a, 7c, 7d, 7b.

### D3. `../docs/koncepcja.md`, `plan-hackathonu-v3.md`, `recykling-sesji.md`  `[ ]`

- Pokazują stary kontrakt znacznika (`summary`, `type`), polskie statusy
  (`nieznana`), `vss` i `FLOAT[1536]` w stosie. Nie edytuj trzech
  historycznych plików. Dodaj na górze każdego dwie linie: „dokument
  koncepcyjny, źródłem prawdy jest `NoNameRepo/docs/`”.

---

## Proponowana kolejność

1. **A1 + A4 + B1** razem: wszystko w `client.py` i `extract.py`, jeden
   przebieg testów.
2. **A2 + A3** przed kolejnym `make build`.
3. **B4**, żeby test integracyjny przestał być rzutem monetą.
4. **B2 + B8 + B9** przy najbliższym dotknięciu schematu.
5. **C1**, jeśli ranking po podobieństwie ma być w ogóle pokazywany.
6. Reszta przy okazji; **D** przed przekazaniem repo komuś nowemu.

Skill i tryby `grill` / `precedens` mają pierwszeństwo przed punktami B i C.
Bez nich poprawki nie mają czego pokazać.
