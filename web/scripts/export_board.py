"""Export the tracked public draft board; never reads ESPN cookies or private data."""
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_REVISION = "483c04aefcef00e547542875bde98eed6b5e524f"
SOURCE_PATH = "draft_strategy/MASTER_BOARD.md"
sys.path.insert(0, str(ROOT / "src"))
from fantasydraft.strategy import Player, RosterPlan, candidate_score, conditional_return, roster_fit, snake_picks, tier_dropoff


def export():
    # Pin this historical demo even when the repository's current board advances.
    source_bytes = subprocess.check_output(
        ["git", "show", f"{SOURCE_REVISION}:{SOURCE_PATH}"], cwd=ROOT
    )
    text = source_bytes.decode("utf-8")
    if "Generated 2026-09-01" not in text:
        raise ValueError("The pinned source must match the September 1 snapshot")
    players = []
    for line in text.splitlines():
        if not re.match(r"^\| \d+ \|", line):
            continue
        row = [part.strip() for part in line.strip("|").split("|")]
        rank, name, pos_rank, team, bye, projection, vor, tier, adp, espn, ffc, ecr, flag = row
        position = re.sub(r"\d+", "", pos_rank)
        number = lambda value: float(value) if value not in {"—", "-", ""} else None
        observed = [x for x in [number(espn), number(ffc), number(ecr)] if x and x > 0]
        market = float(adp)
        base_sd = max(4, min(16, .16 * market))
        sigma = max(3, min(22, math.sqrt(base_sd ** 2 + statistics.pstdev(observed) ** 2)))
        players.append({"id": int(rank), "rank": int(rank), "name": name, "position": position,
                        "positionRank": int(re.sub(r"\D+", "", pos_rank)), "team": team,
                        "bye": int(bye) if bye.isdigit() else None, "projection": float(projection),
                        "vor": float(vor), "tier": int(tier), "adp": market, "espnAdp": number(espn),
                        "ffcAdp": number(ffc), "ecr": number(ecr), "flag": flag,
                        "adpSd": sigma, "consensusRank": statistics.median(observed)})
    if len(players) != 200 or len({p['id'] for p in players}) != 200:
        raise ValueError("Expected 200 unique players in the published snapshot")
    payload = {"schemaVersion": 1, "snapshot": "2026-09-01", "season": 2026,
               "settings": {"teams": 10, "rounds": 16, "skillRounds": 14, "scoring": "Full PPR"},
               "provenance": {"source": SOURCE_PATH, "sourceRevision": SOURCE_REVISION, "sha256": hashlib.sha256(source_bytes).hexdigest(),
                              "repository": "https://github.com/Ashwin-Iyer1/FantasyDraft",
                              "uncertainty": "Reconstructed proxy: base SD = clamp(0.16 × market ADP, 4, 16); combine with population SD of published ESPN ADP, FFC ADP and ECR; clamp result to [3,22]. The archived board does not include original FFC SD or ESPN rank."},
               "replacement": {"QB": 291.0, "RB": 203.3, "WR": 202.2, "TE": 172.3}, "players": players}
    public = ROOT / "web" / "public"
    public.mkdir(parents=True, exist_ok=True)
    (public / "board.json").write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    def as_player(p):
        return Player(p['id'], p['name'], p['position'], p['team'], p['projection'], market_adp=p['adp'],
                      adp_sd=p['adpSd'], vor=p['vor'], tier=p['tier'], board_rank=p['rank'],
                      consensus_rank=p['consensusRank'], injury_status=p['flag'] or 'ACTIVE')
    pool = [as_player(p) for p in players]
    cases = []
    for slot, round_no, roster_ids, player_id in [(5,1,[],1),(1,2,[1],12),(10,8,[1,5,12,20,23,31,35],48),(4,12,[1,5,12,20,23,31,35,42,55,65,78],90)]:
        roster = RosterPlan([p for p in pool if p.espn_id in roster_ids])
        available = [p for p in pool if p.espn_id not in roster_ids]
        player = next(p for p in pool if p.espn_id == player_id)
        picks = snake_picks(slot)
        current, following = picks[round_no-1], picks[round_no] if round_no < 16 else None
        cases.append({"slot":slot,"round":round_no,"rosterIds":roster_ids,"playerId":player_id,
                      "expected":{"fit":roster_fit(player,roster,round_no),"returnProbability":conditional_return(player,current,following),
                                  "tierDrop":tier_dropoff(player,available),"score":candidate_score(player,roster,round_no,current,following,available)}})
    fixture = ROOT / "web" / "src" / "test" / "python-parity.json"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(players)} public players; no private league identifiers. {len(cases)} Python parity cases.")


if __name__ == '__main__':
    export()
