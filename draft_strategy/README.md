# 2026 Quantitative Draft Kit

Generated for **Cao Caliphate** in **Big Ronalds Football League** on 2026-09-01T10:36:11-05:00.

## Start here

1. At 7:30 PM CDT on draft day, ESPN reveals the randomized slot.
2. Open the matching file under [`slots/`](slots/).
3. Keep [`MASTER_BOARD.md`](MASTER_BOARD.md) beside it for unexpected fallers.
4. Use [`CONTINGENCIES.md`](CONTINGENCIES.md) when a positional run or injury breaks the planned lane.
5. Read [`METHODOLOGY.md`](METHODOLOGY.md) for formulas, assumptions, and source freshness.

## Non-negotiable rules

- Draft value, not a predetermined position sequence.
- Do not take a second QB early in this ten-team, one-QB league.
- Take exactly one D/ST and one kicker in the final two rounds.
- When two players are close, choose the one least likely to return at your next pick.
- Recheck injuries immediately before the draft; the generated flags are a snapshot.

## Files

- [`MASTER_BOARD.md`](MASTER_BOARD.md): top 200 players with projections, VOR, tiers, ADP, ECR, and flags.
- [`CONTINGENCIES.md`](CONTINGENCIES.md): substitution ladders, projection values, injuries, and run responses.
- [`METHODOLOGY.md`](METHODOLOGY.md): the auditable quantitative model.
- [`slots/SLOT_01.md`](slots/SLOT_01.md) through [`slots/SLOT_10.md`](slots/SLOT_10.md): all 16 rounds for every possible draft position.

Refresh everything with:

```powershell
py -m fantasydraft.strategy
```
