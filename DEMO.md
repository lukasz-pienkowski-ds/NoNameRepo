# Demo — przebieg krok po kroku

Scenariusz: decyzje seniora z jego sesji agentowych trafiają do wspólnej bazy,
a ktoś inny — w innym projekcie — znajduje je opisując własną sytuację słowami.

Około 5 minut. Wszystkie polecenia z katalogu repo.

---

## 0. Przygotowanie (raz, przed demem)

```bash
export PATH="$HOME/.docker/bin:$PATH"     # docker nie jest w domyslnym PATH
cd ~/Documents/REPOS/hackathon_2026/NoNameRepo
cp .env.example .env                       # ustaw QUACK_TOKEN, min. 4 znaki
```

Token czyta zarówno `docker compose`, jak i polecenia na hoście — **nie trzeba
niczego eksportować**.

**Świeży start**, żeby na scenie nie było resztek:

```bash
make down
make clean          # kasuje plik bazy
make up             # wraca dopiero, gdy centrala odpowiada
```

Kontrola:

```bash
make status         # decisions: 0
```

---

## 1. Pokaż, że decyzje powstają same

W repo leży sesja agentowa z 15 decyzjami, każda z blokiem `<decision_log>`
doklejonym w trakcie pracy:

```bash
head -c 400 data/sessions/projects/-demo-projekt/demo.jsonl
```

Sedno do powiedzenia: **to jest zwykły transkrypt**, nie osobny dokument.
Nikt nie pisał niczego dodatkowo.

---

## 2. Zbierz je do centrali

```bash
.venv/bin/python db/extract.py --root data/sessions/projects --detect
.venv/bin/python db/extract.py --root data/sessions/projects --provider claude --developer michal
make status
```

Powinno wyjść `upserted 15 decision(s): claude=15`, a `status` pokaże 15 i po
chwili tyle samo policzonych wektorów.

Warto pokazać, że **ekstrakcja jest darmowa** — żadnego modelu w tej ścieżce,
czysty SQL po `LIKE '%<decision_log>%'`.

---

## 3. Puenta: ktoś inny opisuje swoją sytuację własnymi słowami

```bash
.venv/bin/python db/cli.py find \
  --query "dostawca ponawia webhooki i dostajemy podwojne obciazenia" --limit 3
```

Pierwszy wynik to decyzja o kluczu idempotencji, z `relevance` około 3.8,
pozostałe 0. **Nie podano żadnego tagu** — dopasowanie idzie po treści.

Drugie pytanie, inna dziedzina:

```bash
.venv/bin/python db/cli.py find \
  --query "kasowanie starych zdarzen blokuje zapisy na dlugo" --limit 2
```

Do pokazania w wyniku: `rejected_options` — **co odrzucono i dlaczego**.
Tego nie odtworzysz z kodu, a właśnie to oszczędza komuś tygodnia.

---

## 4. „Brak trafień" to też odpowiedź

```bash
.venv/bin/python db/cli.py find \
  --query "konfiguracja drukarki iglowej w kadrach" --min-relevance 0.5
```

Wypisze `no precedent above the threshold`. Zdanie do sceny: przy pracy zły
precedens szkodzi bardziej niż brak precedensu, bo agent poda go tonem
„zespół już to rozwiązał".

---

## 5. Filtr po tagach (gdy ktoś zapyta o determinizm)

```bash
.venv/bin/python -c "import sys;sys.path.insert(0,'.');from common.tags import TAGS;print(*TAGS,sep='\n')"
.venv/bin/python db/cli.py find --tags integracja-zewnetrzna --limit 3
```

Tagi pochodzą z zamkniętej listy w `common/tags.py` — skill wybiera z niej,
a magazyn odrzuca wszystko spoza niej przy zapisie **i** przy zapytaniu.

---

## 6. Trzy laptopy na jednej bazie

```bash
make test-integration
```

23 asercje, w tym **30 równoległych zapisów od 3 klientów**. To odpowiedź na
pytanie „a jak to działa, gdy piszemy wszyscy naraz".

---

## Co pokazać, jeśli zostanie czas

**Kontrakt znacznika jest egzekwowany.** Znacznik bez założeń albo bez
uzasadnienia nie zostanie zapisany:

```bash
.venv/bin/python db/extract.py --root data/sessions/projects --provider claude --dry-run 2>&1 | tail -3
```

**Uniwersalność wobec narzędzi.** Ten sam kod czyta sesje Claude i Gemini:

```bash
.venv/bin/python db/extract.py --detect
```

---

## Czego NIE obiecywać ze sceny

- **Skill nie istnieje.** Znaczniki w pliku demo są przygotowane; nic ich
  jeszcze automatycznie nie dokleja. Tryby `grill` i `precedens` są
  zaprojektowane, nie napisane.
- **Ranking semantyczny to BM25, nie model.** Działa na wspólnych słowach.
  Zapytanie synonimami („kolejka komunikatów" zamiast „webhooki") nie trafi.
  `mock_embed` jest atrapą i nic nie wnosi do kolejności.
- **Adapter Codex niesprawdzony** — brak instalacji do przetestowania.
- **Dostęp z drugiej maszyny niesprawdzony** — wszystko szło host ↔ kontener
  na jednym komputerze. Jeśli demo ma iść z dwóch laptopów, przetestujcie to
  dzień wcześniej.

---

## Gdy coś nie działa

| Objaw | Przyczyna |
|---|---|
| `Could not find a Quack authentication token` | brak `.env`; skopiuj z `.env.example` |
| `decision-store nie dziala` | `make up` |
| test przechodzi na hoście, pada w kontenerze | obraz ma stary kod → `make build` |
| `Could not set lock on file` | ktoś otworzył plik bazy obok serwera; tylko serwer go trzyma |
| BM25 nie widzi świeżej decyzji | indeks przebudowuje worker po partii; `make logs` |

---

## Uwaga o danych

`data/seed/decisions.jsonl` to **alternatywny** punkt startu (6 rekordów
wpisywanych przez `make seed`). Pięć z nich pokrywa się tematycznie z sesją
demo, więc użycie obu naraz da bliźniacze trafienia. Na demo wybierz jedno —
powyższy przebieg używa wyłącznie sesji.
