# FantasyDraft

Quantitative draft tooling for ESPN Fantasy Football.

## 2026 draft kit

The generated kit is tailored to Cao Caliphate's ten-team, full-PPR league:

- [`output/pdf/2026_FantasyDraft_Printable_Cheat_Sheet.pdf`](output/pdf/2026_FantasyDraft_Printable_Cheat_Sheet.pdf): print-ready instructions, all ten slot plans, and a two-page Top 100 fallback board.
- [`draft_strategy/README.md`](draft_strategy/README.md): draft-night instructions.
- [`draft_strategy/MASTER_BOARD.md`](draft_strategy/MASTER_BOARD.md): top 200 players ranked by league-scored value over replacement.
- [`draft_strategy/CONTINGENCIES.md`](draft_strategy/CONTINGENCIES.md): named backups, substitution ladders, fallers, and injury flags.
- [`draft_strategy/slots/`](draft_strategy/slots/): a 16-round plan for every possible draft slot.
- [`draft_strategy/METHODOLOGY.md`](draft_strategy/METHODOLOGY.md): formulas, data sources, assumptions, and limitations.

Refresh the projections, ADP, rankings, and all Markdown plans with:

```powershell
py -m fantasydraft.strategy
py -m fantasydraft.printable
```

## ESPN connection

This league is private, so ESPN requires the `SWID` and `espn_s2` cookies from
an ESPN browser session. The connector is read-only and downloads league
settings, teams, rosters, draft state, and matchups.

1. Copy `.env.example` to `.env`.
2. In Chrome while signed into ESPN, open DevTools (`F12`), then
   **Application → Cookies → https://fantasy.espn.com**.
3. Put the `SWID` and `espn_s2` values in `.env`. Do not commit `.env` or paste
   these values into an issue, commit, or chat.
4. Run:

   ```powershell
   py -m pip install -e .
   fetch-espn
   ```

Snapshots are written under `data/espn/` and ignored by Git. Member records,
owner account identifiers, and notification data are removed from the saved
payload. Running the command again refreshes the files, including draft state
once picks begin.

Current league identifiers are prefilled in `.env.example`:

- League: `1756082924`
- Team: `5`
- Season: `2026`

If ESPN returns 401 or 403, retrieve fresh cookies from the signed-in browser;
ESPN session cookies eventually expire.
