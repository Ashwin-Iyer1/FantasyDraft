"""Read-only ESPN Fantasy Football league connector.

ESPN does not document this internal API. Private leagues authenticate with
the SWID and espn_s2 cookies from an already signed-in ESPN browser session.
This module never prints either value.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

from dotenv import load_dotenv
import requests


API_ROOT = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
DEFAULT_VIEWS = (
    "mSettings",
    "mTeam",
    "mRoster",
    "mDraftDetail",
    "mMatchup",
)


class ESPNConnectionError(RuntimeError):
    """Raised when ESPN cannot be read safely."""


@dataclass(frozen=True)
class ESPNConfig:
    league_id: int
    team_id: int
    season: int
    swid: str
    espn_s2: str

    @classmethod
    def from_environment(cls) -> "ESPNConfig":
        load_dotenv()
        required = {
            "ESPN_LEAGUE_ID": os.getenv("ESPN_LEAGUE_ID"),
            "ESPN_TEAM_ID": os.getenv("ESPN_TEAM_ID"),
            "ESPN_SEASON": os.getenv("ESPN_SEASON"),
            "ESPN_SWID": os.getenv("ESPN_SWID"),
            "ESPN_S2": os.getenv("ESPN_S2"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ESPNConnectionError(
                "Missing ESPN configuration: " + ", ".join(missing)
            )
        try:
            return cls(
                league_id=int(required["ESPN_LEAGUE_ID"]),
                team_id=int(required["ESPN_TEAM_ID"]),
                season=int(required["ESPN_SEASON"]),
                swid=str(required["ESPN_SWID"]),
                espn_s2=str(required["ESPN_S2"]),
            )
        except ValueError as exc:
            raise ESPNConnectionError(
                "League ID, team ID, and season must be integers."
            ) from exc


def league_url(config: ESPNConfig) -> str:
    return (
        f"{API_ROOT}/seasons/{config.season}/segments/0/"
        f"leagues/{config.league_id}"
    )


def fetch_league(
    config: ESPNConfig,
    views: Iterable[str] = DEFAULT_VIEWS,
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    """Fetch league data without mutating the ESPN account or league."""
    session = requests.Session()
    session.cookies.update({"SWID": config.swid, "espn_s2": config.espn_s2})
    response = session.get(
        league_url(config),
        params=[("view", view) for view in views],
        headers={
            "Accept": "application/json",
            "User-Agent": "FantasyDraft/0.1 (personal read-only draft tool)",
        },
        timeout=timeout_seconds,
    )
    if response.status_code in (401, 403):
        raise ESPNConnectionError(
            "ESPN rejected the session cookies. Refresh SWID and espn_s2 "
            "from a signed-in ESPN browser and try again."
        )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise ESPNConnectionError(
            f"ESPN returned HTTP {response.status_code}."
        ) from exc

    payload = response.json()
    if str(payload.get("id")) != str(config.league_id):
        raise ESPNConnectionError("ESPN returned an unexpected league payload.")
    return payload


def _team_name(team: dict[str, Any]) -> str:
    name = " ".join(
        value.strip()
        for value in (team.get("location", ""), team.get("nickname", ""))
        if isinstance(value, str) and value.strip()
    )
    return name or team.get("name") or f"Team {team.get('id', '?')}"


def summarize_league(payload: dict[str, Any], config: ESPNConfig) -> dict[str, Any]:
    settings = payload.get("settings") or {}
    roster = settings.get("rosterSettings") or {}
    draft_detail = payload.get("draftDetail") or {}
    draft_settings = settings.get("draftSettings") or {}
    picks = draft_detail.get("picks") or []
    teams = payload.get("teams") or []
    lineup_counts = roster.get("lineupSlotCounts") or {}
    bench_count = int(lineup_counts.get("20", lineup_counts.get(20, 0)) or 0)
    ir_count = int(lineup_counts.get("21", lineup_counts.get(21, 0)) or 0)
    total_lineup_slots = sum(int(value or 0) for value in lineup_counts.values())
    draft_roster_size = total_lineup_slots - ir_count
    starter_count = draft_roster_size - bench_count

    draft_timestamp = draft_settings.get("date")
    draft_time_utc = None
    if isinstance(draft_timestamp, (int, float)):
        draft_time_utc = datetime.fromtimestamp(
            draft_timestamp / 1000, tz=timezone.utc
        ).isoformat()

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "league_id": payload.get("id"),
        "season": payload.get("seasonId", config.season),
        "league_name": settings.get("name"),
        "team_count": len(teams),
        "my_team_id": config.team_id,
        "my_team": next(
            (_team_name(team) for team in teams if team.get("id") == config.team_id),
            None,
        ),
        "teams": [
            {
                "id": team.get("id"),
                "name": _team_name(team),
                "abbrev": team.get("abbrev"),
                "draft_day_projected_rank": team.get("draftDayProjectedRank"),
                "playoff_seed": team.get("playoffSeed"),
                "roster_entries": len((team.get("roster") or {}).get("entries") or []),
            }
            for team in sorted(teams, key=lambda item: item.get("id", 0))
        ],
        "roster_size": draft_roster_size,
        "starter_count": starter_count,
        "bench_count": bench_count,
        "ir_count": ir_count,
        "lineup_slot_counts": lineup_counts,
        "position_limits": roster.get("positionLimits"),
        "draft": {
            "drafted": draft_detail.get("drafted"),
            "in_progress": draft_detail.get("inProgress"),
            "type": draft_settings.get("type"),
            "order_type": draft_settings.get("orderType"),
            "time_per_pick_seconds": draft_settings.get("timePerSelection"),
            "scheduled_time_utc": draft_time_utc,
            "rounds": max((pick.get("roundId", 0) for pick in picks), default=0),
            "board_slots": len(picks),
            "completed_picks": sum(
                1 for pick in picks if isinstance(pick.get("playerId"), int) and pick["playerId"] > 0
            ),
        },
        "scoring_items": len(
            (settings.get("scoringSettings") or {}).get("scoringItems") or []
        ),
    }


def redact_private_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove ESPN account identifiers and member contact/notification data."""
    redacted = deepcopy(payload)
    redacted.pop("members", None)
    for team in redacted.get("teams") or []:
        team.pop("owners", None)
        team.pop("primaryOwner", None)
    return redacted


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a private ESPN fantasy-football league snapshot."
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/espn"), help="Local output folder"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = ESPNConfig.from_environment()
        payload = fetch_league(config)
        summary = summarize_league(payload, config)
    except ESPNConnectionError as exc:
        print(f"ESPN connection failed: {exc}")
        return 1

    stem = f"league-{config.league_id}-{config.season}"
    raw_path = args.output_dir / f"{stem}-raw.json"
    summary_path = args.output_dir / f"{stem}-summary.json"
    write_json_atomic(raw_path, redact_private_fields(payload))
    write_json_atomic(summary_path, summary)

    print(
        f"Connected to {summary.get('league_name') or config.league_id}: "
        f"{summary['team_count']} teams; "
        f"completed draft picks: {summary['draft']['completed_picks']}/"
        f"{summary['draft']['board_slots']}."
    )
    print(f"Redacted league snapshot: {raw_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
