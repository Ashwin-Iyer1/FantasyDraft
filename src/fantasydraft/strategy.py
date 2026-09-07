"""Generate league-specific quantitative fantasy-football draft Markdown.

The generator combines ESPN's league-scored projections and platform ADP,
FantasyPros consensus rankings, and Fantasy Football Calculator 10-team PPR
ADP. It calculates replacement value, positional tiers, and the conditional
probability that a player returns at the drafter's next snake pick.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import re
import statistics
import unicodedata
from typing import Any, Iterable

import requests

from .espn import ESPNConfig, league_url


FPECR_URL = (
    "https://raw.githubusercontent.com/dynastyprocess/data/master/"
    "files/db_fpecr_latest.csv"
)
FFC_URL = "https://fantasyfootballcalculator.com/api/v1/adp/ppr"
ESPN_SEASON_URL = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
)

POSITION_BY_ESPN_ID = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}
TEAM_BY_ESPN_ID = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL",
    7: "DEN", 8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC",
    13: "LV", 14: "LAR", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO",
    19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC",
    25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR", 30: "JAX",
    33: "BAL", 34: "HOU",
}

DEDICATED_STARTERS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "DST": 1, "K": 1}
FLEX_POSITIONS = {"RB", "WR", "TE"}
POSITION_CAPS = {"QB": 2, "RB": 6, "WR": 7, "TE": 2, "DST": 1, "K": 1}
SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}
CORE_MILESTONES = (
    (3, {"RB": 1, "WR": 1}),
    (6, {"RB": 2, "WR": 2}),
    (9, {"RB": 3, "WR": 3}),
    (12, {"QB": 1, "RB": 4, "WR": 4, "TE": 1}),
    (14, {"QB": 1, "RB": 5, "WR": 5, "TE": 1}),
)


@dataclass
class Player:
    espn_id: int
    name: str
    position: str
    team: str
    projection: float
    bye: int | None = None
    espn_adp: float | None = None
    ffc_adp: float | None = None
    ffc_sd: float | None = None
    ffc_samples: int | None = None
    ecr: float | None = None
    ecr_sd: float | None = None
    espn_rank: float | None = None
    injured: bool = False
    injury_status: str = "ACTIVE"
    market_adp: float = 999.0
    adp_sd: float = 12.0
    replacement: float = 0.0
    vor: float = 0.0
    tier: int = 1
    board_rank: int = 999
    pos_rank: int = 999
    consensus_rank: float = 999.0

    @property
    def label(self) -> str:
        return f"{self.name} ({self.position}, {self.team})"


@dataclass
class RosterPlan:
    players: list[Player] = field(default_factory=list)

    def count(self, position: str) -> int:
        return sum(player.position == position for player in self.players)

    def add(self, player: Player) -> None:
        self.players.append(player)

    def compact(self) -> str:
        counts = {pos: self.count(pos) for pos in ("QB", "RB", "WR", "TE", "DST", "K")}
        return " ".join(f"{pos}{counts[pos]}" for pos in counts if counts[pos]) or "empty"


def _num(value: Any) -> float | None:
    if value in (None, "", "NA", "NaN"):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _integer(value: Any) -> int | None:
    parsed = _num(value)
    return int(parsed) if parsed is not None else None


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    text = text.lower().replace("d/st", "dst")
    text = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def _espn_session(config: ESPNConfig) -> requests.Session:
    session = requests.Session()
    session.cookies.update({"SWID": config.swid, "espn_s2": config.espn_s2})
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "FantasyDraft/0.1 (personal read-only draft tool)",
        }
    )
    return session


def fetch_espn_players(config: ESPNConfig, limit: int = 1000) -> tuple[list[Player], str]:
    fantasy_filter = {
        "players": {
            "filterSlotIds": {"value": [0, 2, 4, 6, 16, 17]},
            "filterStatsForExternalIds": {"value": [config.season]},
            "filterStatsForSourceIds": {"value": [1]},
            "filterStatsForSplitTypeIds": {"value": [0]},
            "sortAppliedStatTotal": {
                "sortAsc": False,
                "sortPriority": 1,
                "value": f"10{config.season}",
            },
            "sortDraftRanks": {
                "sortPriority": 2,
                "sortAsc": True,
                "value": "PPR",
            },
            "sortPercOwned": {"sortAsc": False, "sortPriority": 3},
            "limit": limit,
            "offset": 0,
            "filterRanksForScoringPeriodIds": {"value": [1]},
            "filterRanksForRankTypes": {"value": ["PPR"]},
            "filterRanksForSlotIds": {"value": [0, 2, 4, 6, 17, 16]},
            "filterStatsForTopScoringPeriodIds": {
                "value": 2,
                "additionalValue": [
                    f"00{config.season}",
                    f"10{config.season}",
                    f"02{config.season}",
                ],
            },
        }
    }
    with _espn_session(config) as session:
        response = session.get(
            league_url(config),
            params=[("scoringPeriodId", 0), ("view", "kona_player_info")],
            headers={
                "x-fantasy-filter": json.dumps(fantasy_filter),
                "x-fantasy-source": "kona",
            },
            timeout=30,
        )
    response.raise_for_status()
    payload = response.json()

    players: list[Player] = []
    ownership_dates: list[int] = []
    for item in payload.get("players") or []:
        raw = item.get("player") or item
        position = POSITION_BY_ESPN_ID.get(raw.get("defaultPositionId"))
        if not position:
            continue
        projection = None
        for stat in raw.get("stats") or []:
            if stat.get("statSourceId") != 1 or stat.get("statSplitTypeId") != 0:
                continue
            if stat.get("seasonId") == config.season and stat.get("appliedTotal") is not None:
                projection = float(stat["appliedTotal"])
                break
        if projection is None or projection <= 0:
            continue

        ownership = raw.get("ownership") or {}
        if isinstance(ownership.get("date"), int):
            ownership_dates.append(ownership["date"])
        ppr_rank = (raw.get("draftRanksByRankType") or {}).get("PPR") or {}
        team = TEAM_BY_ESPN_ID.get(raw.get("proTeamId"), "FA")
        players.append(
            Player(
                espn_id=int(raw.get("id") or item.get("id")),
                name=raw.get("fullName") or f"ESPN {item.get('id')}",
                position=position,
                team=team,
                projection=round(projection, 2),
                espn_adp=_num(ownership.get("averageDraftPosition")),
                espn_rank=_num(ppr_rank.get("rank")),
                injured=bool(raw.get("injured")),
                injury_status=str(raw.get("injuryStatus") or "ACTIVE"),
            )
        )

    as_of = "unknown"
    if ownership_dates:
        as_of = datetime.fromtimestamp(max(ownership_dates) / 1000, tz=timezone.utc).isoformat()
    return players, as_of


def fetch_byes(season: int) -> dict[str, int]:
    response = requests.get(
        ESPN_SEASON_URL.format(season=season),
        params={"view": "proTeamSchedules_wl"},
        headers={"User-Agent": "FantasyDraft/0.1"},
        timeout=30,
    )
    response.raise_for_status()
    teams = (response.json().get("settings") or {}).get("proTeams") or []
    return {
        str(team.get("abbrev") or TEAM_BY_ESPN_ID.get(team.get("id"), "")).upper(): int(team["byeWeek"])
        for team in teams
        if team.get("byeWeek") and (team.get("abbrev") or TEAM_BY_ESPN_ID.get(team.get("id")))
    }


def fetch_ffc(teams: int, season: int) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    response = requests.get(
        FFC_URL,
        params={"teams": teams, "year": season, "position": "all"},
        headers={"User-Agent": "FantasyDraft/0.1 (personal use)"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    rows: dict[str, dict[str, Any]] = {}
    for item in payload.get("players") or []:
        key = normalize_name(item.get("name") or "")
        if key:
            rows[key] = item
    return rows, payload.get("meta") or {}


def fetch_ecr() -> tuple[dict[str, dict[str, str]], str]:
    response = requests.get(FPECR_URL, headers={"User-Agent": "FantasyDraft/0.1"}, timeout=30)
    response.raise_for_status()
    rows: dict[str, dict[str, str]] = {}
    scrape_dates: set[str] = set()
    for row in csv.DictReader(io.StringIO(response.text)):
        if row.get("page_type") != "redraft-overall" or row.get("ecr_type") != "ro":
            continue
        key = normalize_name(row.get("player") or "")
        if key:
            rows[key] = row
        if row.get("scrape_date"):
            scrape_dates.add(row["scrape_date"])
    return rows, max(scrape_dates) if scrape_dates else "unknown"


def enrich_players(
    players: list[Player],
    ffc: dict[str, dict[str, Any]],
    ecr: dict[str, dict[str, str]],
    byes: dict[str, int],
) -> None:
    for player in players:
        key = normalize_name(player.name)
        ffc_row = ffc.get(key)
        ecr_row = ecr.get(key)
        if ffc_row:
            player.ffc_adp = _num(ffc_row.get("adp"))
            player.ffc_sd = _num(ffc_row.get("stdev"))
            player.ffc_samples = _integer(ffc_row.get("times_drafted"))
        if ecr_row:
            player.ecr = _num(ecr_row.get("ecr"))
            player.ecr_sd = _num(ecr_row.get("sd"))
            player.bye = _integer(ecr_row.get("bye"))
        if player.bye is None:
            player.bye = byes.get(player.team)

        adps = [x for x in (player.espn_adp, player.ffc_adp) if x and x > 0]
        if player.espn_adp and player.ffc_adp:
            player.market_adp = 0.75 * player.espn_adp + 0.25 * player.ffc_adp
        elif adps:
            player.market_adp = adps[0]
        elif player.ecr:
            player.market_adp = player.ecr

        ranks = [x for x in (player.espn_rank, player.ecr, player.ffc_adp) if x and x > 0]
        player.consensus_rank = statistics.median(ranks) if ranks else player.market_adp
        disagreement = statistics.pstdev(ranks) if len(ranks) >= 2 else 0.0
        base_sd = player.ffc_sd or max(4.0, min(16.0, 0.16 * player.market_adp))
        player.adp_sd = max(3.0, min(22.0, math.sqrt(base_sd**2 + disagreement**2)))


def calculate_vor(players: list[Player], teams: int = 10) -> dict[str, float]:
    by_pos = {
        pos: sorted((p for p in players if p.position == pos), key=lambda p: p.projection, reverse=True)
        for pos in DEDICATED_STARTERS
    }
    allocated = {pos: DEDICATED_STARTERS[pos] * teams for pos in DEDICATED_STARTERS}

    for _ in range(teams):
        candidates = []
        for pos in FLEX_POSITIONS:
            index = allocated[pos]
            if index < len(by_pos[pos]):
                candidates.append(by_pos[pos][index])
        if not candidates:
            break
        best = max(candidates, key=lambda player: player.projection)
        allocated[best.position] += 1

    replacement: dict[str, float] = {}
    for pos, pool in by_pos.items():
        index = allocated[pos]
        replacement[pos] = pool[index].projection if index < len(pool) else pool[-1].projection
        for player in pool:
            player.replacement = replacement[pos]
            player.vor = round(player.projection - replacement[pos], 2)
    return replacement


def assign_tiers_and_ranks(players: list[Player]) -> None:
    for position in DEDICATED_STARTERS:
        pool = sorted(
            (p for p in players if p.position == position),
            key=lambda p: p.vor,
            reverse=True,
        )
        for index, player in enumerate(pool, 1):
            player.pos_rank = index
        relevant = pool[:80]
        gaps = [max(relevant[i].vor - relevant[i + 1].vor, 0.0) for i in range(len(relevant) - 1)]
        positive = [gap for gap in gaps if gap > 0]
        threshold = 8.0
        if positive:
            median = statistics.median(positive)
            mad = statistics.median(abs(gap - median) for gap in positive)
            threshold = max(5.0, median + 2.5 * mad)
        tier = 1
        if pool:
            pool[0].tier = tier
        for index in range(1, len(pool)):
            if pool[index - 1].vor - pool[index].vor >= threshold:
                tier += 1
            pool[index].tier = tier

    # Kicker and D/ST seasonal VOR is not comparable to scarce skill-player
    # value because both positions are highly streamable. Keep them after the
    # draftable skill pool even when ESPN's median projection looks attractive.
    ordered = sorted(
        players,
        key=lambda p: (
            p.position in {"K", "DST"},
            -p.vor,
            p.consensus_rank,
            p.market_adp,
        ),
    )
    for index, player in enumerate(ordered, 1):
        player.board_rank = index


def normal_availability(player: Player, overall_pick: int) -> float:
    if player.market_adp >= 900:
        return 0.5
    z = (overall_pick - 0.5 - player.market_adp) / max(player.adp_sd, 1.0)
    return max(0.0, min(1.0, 0.5 * math.erfc(z / math.sqrt(2.0))))


def conditional_return(player: Player, current_pick: int, next_pick: int | None) -> float:
    if next_pick is None:
        return 0.0
    now = normal_availability(player, current_pick)
    if now <= 1e-6:
        return 0.0
    return max(0.0, min(1.0, normal_availability(player, next_pick) / now))


def snake_picks(slot: int, teams: int = 10, rounds: int = 16) -> list[int]:
    picks = []
    for round_no in range(1, rounds + 1):
        if round_no % 2:
            picks.append((round_no - 1) * teams + slot)
        else:
            picks.append(round_no * teams - slot + 1)
    return picks


def _fills_starter(player: Player, roster: RosterPlan) -> bool:
    pos = player.position
    if roster.count(pos) < DEDICATED_STARTERS[pos]:
        return True
    if pos in FLEX_POSITIONS:
        extras = sum(
            max(0, roster.count(p) - DEDICATED_STARTERS[p]) for p in FLEX_POSITIONS
        )
        return extras < 1
    return False


def roster_fit(player: Player, roster: RosterPlan, round_no: int) -> float:
    pos = player.position
    count = roster.count(pos)
    if count >= POSITION_CAPS[pos]:
        return 0.0
    if pos in {"K", "DST"}:
        if count:
            return 0.0
        return 1.0 if round_no >= 15 else 0.0
    if _fills_starter(player, roster):
        return 1.0
    if pos in {"RB", "WR"}:
        if pos == "RB":
            return {3: 0.84, 4: 0.76, 5: 0.58}.get(count, 0.38)
        return {3: 0.80, 4: 0.66, 5: 0.50, 6: 0.30}.get(count, 0.18)
    if pos == "TE":
        return 0.22 if count == 1 and round_no >= 12 else 0.0
    if pos == "QB":
        return 0.08 if count == 1 and round_no >= 14 else 0.0
    return 0.0


def tier_dropoff(player: Player, available: Iterable[Player]) -> float:
    lower = [
        candidate
        for candidate in available
        if candidate.position == player.position and candidate.tier > player.tier
    ]
    if not lower:
        return max(player.vor, 0.0)
    return max(player.vor - max(candidate.vor for candidate in lower), 0.0)


def candidate_score(
    player: Player,
    roster: RosterPlan,
    round_no: int,
    current_pick: int,
    next_pick: int | None,
    available: list[Player],
) -> float:
    fit = roster_fit(player, roster, round_no)
    if fit <= 0:
        return -1e9
    return_p = conditional_return(player, current_pick, next_pick)
    urgency = (1.0 - return_p) * tier_dropoff(player, available)
    base = player.vor * fit + 0.8 * urgency
    if player.injured or player.injury_status not in {"ACTIVE", "NORMAL"}:
        base -= 12.0 if round_no <= 8 else 5.0
    if round_no >= 9 and player.position in {"RB", "WR"}:
        # Late picks favor market-backed upside over low-ceiling point estimates.
        upside_gap = max(0.0, player.board_rank - player.consensus_rank)
        base += min(12.0, 0.25 * upside_gap)
    return base


def _realistic_candidates(
    players: list[Player], used: set[int], pick: int, minimum_probability: float = 0.18
) -> list[Player]:
    return [
        player
        for player in players
        if player.espn_id not in used and normal_availability(player, pick) >= minimum_probability
    ]


def milestone_forced_positions(roster: RosterPlan, round_no: int) -> set[str]:
    """Return positions that must be filled now to reach the next core deadline."""
    for deadline, targets in CORE_MILESTONES:
        if deadline < round_no:
            continue
        deficits = {
            pos: max(0, target - roster.count(pos))
            for pos, target in targets.items()
        }
        picks_remaining_including_now = deadline - round_no + 1
        if sum(deficits.values()) >= picks_remaining_including_now:
            return {pos for pos, deficit in deficits.items() if deficit > 0}
        return set()
    return set()


def validate_plan(rows: list[dict[str, Any]]) -> None:
    if len(rows) != 16:
        raise ValueError(f"Expected 16 draft rounds, received {len(rows)}")
    ids = [row["primary"].espn_id for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("A slot plan drafted the same player more than once")
    if rows[14]["primary"].position != "DST" or rows[15]["primary"].position != "K":
        raise ValueError("Rounds 15 and 16 must be D/ST and kicker, respectively")

    counts = {pos: 0 for pos in DEDICATED_STARTERS}
    milestones = dict(CORE_MILESTONES)
    for row in rows:
        counts[row["primary"].position] += 1
        targets = milestones.get(row["round"])
        if targets:
            short = {
                pos: target - counts[pos]
                for pos, target in targets.items()
                if counts[pos] < target
            }
            if short:
                raise ValueError(
                    f"Round {row['round']} core milestone missed: {short}"
                )


def plan_for_slot(players: list[Player], slot: int) -> list[dict[str, Any]]:
    picks = snake_picks(slot)
    used: set[int] = set()
    roster = RosterPlan()
    rows: list[dict[str, Any]] = []

    for index, pick in enumerate(picks):
        round_no = index + 1
        next_pick = picks[index + 1] if index + 1 < len(picks) else None
        candidates = _realistic_candidates(players, used, pick, minimum_probability=0.35)
        if not candidates:
            candidates = _realistic_candidates(players, used, pick, minimum_probability=0.08)

        if round_no == 15 and roster.count("DST") == 0 and roster.count("K") == 0:
            forced_positions = {"DST"}
        elif round_no == 16:
            forced_positions = {pos for pos in ("DST", "K") if roster.count(pos) == 0}
        else:
            forced_positions = set()
        if forced_positions:
            forced = [p for p in candidates if p.position in forced_positions]
            if forced:
                candidates = forced

        # Apply progressive deadlines so the plan cannot ignore RB or WR early
        # and then pretend it can repair the starting lineup with five late
        # picks. Two of the first 14 selections remain free for pure value.
        if round_no <= 14 and not forced_positions:
            needed_positions = milestone_forced_positions(roster, round_no)
            if needed_positions:
                needed = [p for p in candidates if p.position in needed_positions]
                if needed:
                    candidates = needed

        ranked = sorted(
            candidates,
            key=lambda p: candidate_score(p, roster, round_no, pick, next_pick, candidates),
            reverse=True,
        )
        primary = next((p for p in ranked if roster_fit(p, roster, round_no) > 0), ranked[0])
        same_pos = [
            p for p in ranked
            if p.position == primary.position
            and p.espn_id != primary.espn_id
            and roster_fit(p, roster, round_no) > 0
        ][:2]
        pivots = [
            p
            for p in ranked
            if p.position != primary.position and p.position not in {"K", "DST"}
            and roster_fit(p, roster, round_no) > 0
        ][:1]
        fallers = []
        if round_no <= 14:
            fallers = sorted(
                (
                    p for p in players
                    if p.espn_id not in used
                    and p.position not in {"K", "DST"}
                    and 0.04 <= normal_availability(p, pick) < 0.18
                    and roster_fit(p, roster, round_no) > 0
                ),
                key=lambda p: p.vor,
                reverse=True,
            )[:1]

        roster.add(primary)
        used.add(primary.espn_id)
        rows.append(
            {
                "round": round_no,
                "pick": pick,
                "primary": primary,
                "backups": same_pos,
                "pivot": pivots[0] if pivots else None,
                "faller": fallers[0] if fallers else None,
                "p_available": normal_availability(primary, pick),
                "p_return": conditional_return(primary, pick, next_pick),
                "roster": roster.compact(),
            }
        )
    validate_plan(rows)
    return rows


def _fmt(value: float | int | None, digits: int = 1) -> str:
    if value is None or value >= 900:
        return "—"
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def _pct(value: float) -> str:
    return f"{round(value * 100):d}%"


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell).replace("|", "/") for cell in row) + " |")
    return "\n".join(lines)


def render_master_board(players: list[Player], metadata: dict[str, Any]) -> str:
    ordered = sorted(players, key=lambda p: p.board_rank)[:200]
    rows = []
    for player in ordered:
        status = player.injury_status if player.injured or player.injury_status != "ACTIVE" else ""
        rows.append(
            [
                player.board_rank,
                player.name,
                f"{player.position}{player.pos_rank}",
                player.team,
                player.bye or "—",
                _fmt(player.projection),
                _fmt(player.vor),
                player.tier,
                _fmt(player.market_adp),
                _fmt(player.espn_adp),
                _fmt(player.ffc_adp),
                _fmt(player.ecr),
                status,
            ]
        )
    return f"""# League-Specific Master Draft Board

Generated {metadata['generated_at']} for **Big Ronalds Football League**: 10 teams, full PPR, one QB, one FLEX, 16 rounds.

Sort order is league-scored value over replacement (VOR), with consensus rank and market ADP used as tie-breakers. `Market ADP` is weighted 75% toward ESPN because this draft occurs on ESPN and 25% toward Fantasy Football Calculator's 10-team PPR pool.

{_md_table(['#', 'Player', 'Pos', 'Team', 'Bye', 'ESPN proj', 'VOR', 'Tier', 'Market ADP', 'ESPN ADP', 'FFC ADP', 'ECR', 'Flag'], rows)}

## Replacement baselines

{_md_table(['Position', 'Replacement points'], [[pos, _fmt(value)] for pos, value in metadata['replacement'].items()])}

Negative VOR is normal late in the draft: it means a player projects below the first non-starter at his position. Late bench picks should then be chosen for contingent upside, not their median projection.
"""


def render_slot(slot: int, rows: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
    table_rows = []
    for row in rows:
        backups = "; ".join(player.label for player in row["backups"]) or "—"
        pivot = row["pivot"].label if row["pivot"] else "—"
        faller = row["faller"].label if row["faller"] else "—"
        table_rows.append(
            [
                row["round"],
                row["pick"],
                row["primary"].label,
                backups,
                pivot,
                faller,
                _pct(row["p_available"]),
                _pct(row["p_return"]),
                row["roster"],
            ]
        )
    picks = ", ".join(str(row["pick"]) for row in rows)
    return f"""# Draft Plan — Slot {slot}

Your scheduled overall picks: **{picks}**.

This is a scenario plan, not a command to reach. At each pick, first take any `Smash faller` who is actually available and still fits the roster. Otherwise use the primary, same-position backups, then the cross-position pivot. `Return` is the conditional chance that the primary survives to your next selection, assuming he is available now.

{_md_table(['Rd', 'Overall', 'Primary', 'Same-position backups', 'Cross-position pivot', 'Smash faller', 'Avail now', 'Return', 'Planned roster'], table_rows)}

## Slot {slot} operating rules

- Do not chase the exact planned roster after a pivot. Re-rank by VOR and positional cliff after every real selection.
- A player with under 25% `Return` should be taken now if he is in your top value tier; waiting is usually the expensive choice.
- A premium quarterback is viable only in his market/value window; this is a one-QB league, so do not manufacture quarterback scarcity.
- Draft exactly one D/ST and one kicker, in Rounds 15–16. Stream later rather than spending bench capital on backups.
- Before every pick, verify current injury news. The board's injury flag comes from ESPN as of {metadata['espn_as_of']}.
"""


def render_contingencies(players: list[Player], metadata: dict[str, Any]) -> str:
    ordered = sorted(players, key=lambda p: p.board_rank)
    sections = []
    for pos in ("RB", "WR", "TE", "QB"):
        pool = [p for p in ordered if p.position == pos][:35]
        tiers: dict[int, list[Player]] = {}
        for player in pool:
            tiers.setdefault(player.tier, []).append(player)
        lines = [f"## {pos} substitution ladder", ""]
        for tier, members in list(tiers.items())[:8]:
            labels = ", ".join(
                f"{p.name} ({p.team}, ADP {_fmt(p.market_adp)})" for p in members
            )
            lines.append(f"- **Tier {tier}:** {labels}")
        sections.append("\n".join(lines))

    injuries = [
        p for p in ordered[:220] if p.injured or p.injury_status not in {"ACTIVE", "NORMAL"}
    ]
    injury_rows = [
        [p.name, p.position, p.team, p.injury_status, _fmt(p.market_adp), p.board_rank]
        for p in injuries
    ]

    values = sorted(
        (
            p for p in ordered[:220]
            if p.market_adp < 900 and p.board_rank + 12 < p.market_adp and p.position in SKILL_POSITIONS
        ),
        key=lambda p: p.market_adp - p.board_rank,
        reverse=True,
    )[:30]
    value_rows = [
        [p.name, p.position, p.team, p.board_rank, _fmt(p.market_adp), round(p.market_adp - p.board_rank)]
        for p in values
    ]

    rendered_sections = "\n\n".join(sections)

    return f"""# Live-Draft Contingencies and Substitutions

Use this file when a planned lane collapses. Stay within a tier when possible; cross positions when the remaining tier has flattened.

{rendered_sections}

## Projection-over-market values

These players rank at least 12 spots better by league-scored VOR than their market cost. They are not automatic reaches; they are the preferred names when they fall into the indicated ADP neighborhood.

{_md_table(['Player', 'Pos', 'Team', 'Board rank', 'Market ADP', 'Rank discount'], value_rows)}

## Injury/status audit

{_md_table(['Player', 'Pos', 'Team', 'ESPN status', 'Market ADP', 'Board rank'], injury_rows) if injury_rows else 'No ESPN injury flags among the top 220 at generation time.'}

## If the room behaves unexpectedly

- **RB run:** Take the last player in the current RB tier only when the drop to the next tier is larger than the best WR/TE value available. Do not draft a sixth RB before filling QB and TE.
- **WR run:** In full PPR, three starting-caliber WR/FLEX players are valuable, but the position is deeper than RB. Pivot to an RB tier cliff or elite TE rather than following a weak WR tier.
- **Early QB run:** Let it happen. This league starts only ten quarterbacks. Take the RB/WR value the room gives away, then use the QB ladder above.
- **Early TE run:** Draft the final clearly separated TE tier if value is close; otherwise wait and pair a later TE with strong RB/WR depth.
- **Autodraft emergency:** Sort by the master board, remove K/DST until the final two rounds, and cap QB/TE at two each.
- **Player ruled out or role changes:** Cross him off entirely, move every same-position player below him up one substitution slot, and prefer the cross-position pivot if the tier is exhausted.
"""


def render_methodology(metadata: dict[str, Any]) -> str:
    ffc_meta = metadata["ffc_meta"]
    return f"""# Quantitative Draft Methodology

## Objective

Maximize expected starting-lineup points above what can be replaced in this exact league, while accounting for the opportunity cost of waiting until the next snake pick. The method deliberately avoids fixed rules such as “RB-RB” or “zero RB”; those are outcomes, not objectives.

## Current inputs

- **ESPN league-scored 2026 projections and ESPN ADP:** fetched {metadata['espn_as_of']}. ESPN applies this league's full-PPR scoring to `appliedTotal`.
- **FantasyPros expert consensus:** DynastyProcess snapshot dated {metadata['ecr_as_of']}.
- **Fantasy Football Calculator 10-team PPR ADP:** {ffc_meta.get('total_drafts', '—')} drafts from {ffc_meta.get('start_date', '—')} through {ffc_meta.get('end_date', '—')}.
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
"""


def render_readme(metadata: dict[str, Any]) -> str:
    return f"""# 2026 Quantitative Draft Kit

Generated for **Cao Caliphate** in **Big Ronalds Football League** on {metadata['generated_at']}.

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
"""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def generate(output_dir: Path = Path("draft_strategy")) -> dict[str, Any]:
    config = ESPNConfig.from_environment()
    players, espn_as_of = fetch_espn_players(config)
    byes = fetch_byes(config.season)
    ffc, ffc_meta = fetch_ffc(teams=10, season=config.season)
    ecr, ecr_as_of = fetch_ecr()
    enrich_players(players, ffc, ecr, byes)
    replacement = calculate_vor(players, teams=10)
    assign_tiers_and_ranks(players)

    metadata = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "espn_as_of": espn_as_of,
        "ecr_as_of": ecr_as_of,
        "ffc_meta": ffc_meta,
        "replacement": {pos: round(value, 1) for pos, value in replacement.items()},
        "player_count": len(players),
    }

    write_text(output_dir / "README.md", render_readme(metadata))
    write_text(output_dir / "MASTER_BOARD.md", render_master_board(players, metadata))
    write_text(output_dir / "CONTINGENCIES.md", render_contingencies(players, metadata))
    write_text(output_dir / "METHODOLOGY.md", render_methodology(metadata))
    for slot in range(1, 11):
        rows = plan_for_slot(players, slot)
        write_text(output_dir / "slots" / f"SLOT_{slot:02d}.md", render_slot(slot, rows, metadata))

    data_dir = Path("data/strategy")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "generation-metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return metadata


def main() -> int:
    metadata = generate()
    print(
        f"Generated draft_strategy Markdown for {metadata['player_count']} ESPN-projected "
        f"players across all 10 draft slots."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
