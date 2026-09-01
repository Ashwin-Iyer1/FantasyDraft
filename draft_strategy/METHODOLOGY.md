# Quantitative Draft Methodology

## Objective

Maximize expected starting-lineup points above what can be replaced in this exact league, while accounting for the opportunity cost of waiting until the next snake pick. The method deliberately avoids fixed rules such as “RB-RB” or “zero RB”; those are outcomes, not objectives.

## Current inputs

- **ESPN league-scored 2026 projections and ESPN ADP:** fetched 2026-09-01T15:30:16.451000+00:00. ESPN applies this league's full-PPR scoring to `appliedTotal`.
- **FantasyPros expert consensus:** DynastyProcess snapshot dated 2026-08-28.
- **Fantasy Football Calculator 10-team PPR ADP:** 8101 drafts from 2026-08-25 through 2026-09-01.
- **League configuration:** 10 teams; QB, 2 RB, 2 WR, TE, FLEX, D/ST, K; seven bench; 16-round snake; no keepers.

## Core calculations

```text
replacement(position) = projection of the first player who is not a league starter
VOR(player)            = ESPN projected points - replacement(position)

P(available at pick k) = 1 - NormalCDF(k - 0.5; market_ADP, ADP_uncertainty)

P(return | here now)   = P(available at next pick) / P(available now)

urgency                = (1 - P(return)) × drop to the next positional tier
pick score             = roster_fit × VOR + 0.8 × urgency
```

Dedicated starter demand is 10 QB, 20 RB, 20 WR, and 10 TE. The ten FLEX slots are allocated greedily to the highest remaining RB/WR/TE projections before replacement levels are set. This makes positions comparable without pretending that raw quarterback points equal running-back scarcity.

Market ADP is 75% ESPN and 25% Fantasy Football Calculator because opponents draft in ESPN's room. FFC standard deviation and disagreement among ESPN rank, FFC ADP, and ECR expand the availability uncertainty band.

## Strategy derived from the model

1. **Rounds 1–4:** Accumulate elite VOR. Break close calls with conditional return probability and positional cliffs.
2. **Rounds 5–8:** Complete most RB/WR/FLEX demand. Draft QB or TE when the remaining tier is unlikely to survive the turn—not because the round number says so.
3. **Rounds 9–14:** Favor RB/WR contingent upside and market-backed ceiling. A second QB is low value in a ten-team one-QB league; take one only late and only if the starter is risky.
4. **Rounds 15–16:** One D/ST and one kicker. No backups at either position.

## Limits

- A pre-draft plan cannot know the randomized slot, room-specific reaches, or breaking injury news. That is why there are ten slot files and substitution ladders.
- ESPN is a single point-projection source. ECR and two ADP sources reduce ordering risk, but they do not create an independent projection ensemble.
- ADP is a market forecast, not player value. It controls timing; VOR controls preference.
- The model optimizes expected value, not certainty. Late-round upside picks will fail often by design.

## Reference implementations reviewed

- [fantasy-football-draft-agent](https://github.com/ColemanDavis1/fantasy-football-draft-agent): league-scored ESPN projections, replacement value, tier cliffs, conditional survival, and roster-fit logic.
- [TripleCrown](https://github.com/sengi12/triplecrown): VOR/VONA concepts, multi-source player context, and projection-data engineering.
- [ffanalytics](https://github.com/FantasyFootballAnalytics/ffanalytics): projection aggregation, VOR, tiers, ECR, ADP, and uncertainty.
- [DynastyProcess data](https://github.com/dynastyprocess/data): automated FantasyPros rankings and cross-platform player identifiers.
- [Fantasy Football Calculator ADP API](https://help.fantasyfootballcalculator.com/article/42-adp-rest-api): league-size-specific ADP distribution and sample counts.

The cloned reference repositories are kept under `research/repos/` and excluded from the project output.
