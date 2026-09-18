# Quality bar

The collection is useful in proportion to how little junk is in it. A developer who receives one irrelevant precedent will discount the next three. So the default answer to "should this be a record?" is no.

## Capture when all three hold

**1. Contested.** A real alternative existed and someone had to argue against it. If there was one obvious answer, there is nothing to transfer. Test: can you name a second option and a specific reason it lost?

**2. Expensive.** Either the decision is hard to reverse (migration, data rewrite, public contract, vendor commitment), or rediscovering it costs real time (half a day or more of exploration, a failed implementation, a benchmark that had to be written). Test: would a colleague hitting this next month spend hours getting to the same place?

**3. Legible outside this repo.** The problem can be stated without naming the codebase and still make sense. Test: read the draft summary as if you worked at a different company on a different stack — is it still a recognizable problem?

## Skip when any of these hold

- Naming, formatting, file layout, or lint configuration.
- The choice was fully determined by an external mandate with no reasoning attached ("client requires Java 11"). Capture the *consequence* if it forced an interesting workaround; do not capture the mandate.
- Reversible in under an hour with blast radius inside one module.
- It duplicates a record already written in this session.
- The reasoning is not actually in the session — if the decision arrived by assertion and nobody wrote down why, there is nothing to compact. Capturing it would manufacture confidence that never existed.

## Borderline cases

**A failed approach with no chosen alternative yet.** Capture it. A record whose only content is "this path is a dead end, here is exactly where it breaks" is among the most valuable entries. Say in the summary that the approach was abandoned and what was fallen back to.

**A decision made under time pressure, on intuition.** Capture it, but say so in the summary — "chosen under deadline, untested" is genuinely useful information, unlike the same record read as settled precedent.

**A decision that reverses an earlier one.** Always capture, and say in the summary what it reverses and why. Reversals are the only mechanism by which the collection self-corrects.

## Volume expectation

A typical working session produces zero records. A session with a genuine architectural fork produces one. If a session is producing three or more, the bar is being applied too loosely — reread the "contested" test, which is the one most often waved through.