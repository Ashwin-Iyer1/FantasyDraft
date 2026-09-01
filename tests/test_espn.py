from fantasydraft.espn import (
    ESPNConfig,
    league_url,
    redact_private_fields,
    summarize_league,
)


def test_league_url() -> None:
    config = ESPNConfig(league_id=123, team_id=5, season=2026, swid="x", espn_s2="y")
    assert league_url(config).endswith("/seasons/2026/segments/0/leagues/123")


def test_summary_identifies_my_team() -> None:
    config = ESPNConfig(league_id=123, team_id=5, season=2026, swid="x", espn_s2="y")
    payload = {
        "id": 123,
        "seasonId": 2026,
        "settings": {
            "name": "Test League",
            "rosterSettings": {
                "lineupSlotCounts": {
                    "0": 1,
                    "2": 2,
                    "4": 2,
                    "6": 1,
                    "16": 1,
                    "17": 1,
                    "20": 7,
                    "21": 1,
                    "23": 1,
                }
            },
            "scoringSettings": {"scoringItems": [{"statId": 1}]},
            "draftSettings": {"type": "SNAKE", "timePerSelection": 90},
        },
        "teams": [{"id": 5, "location": "Cao", "nickname": "Caliphate"}],
        "draftDetail": {
            "drafted": False,
            "picks": [
                {"roundId": 1, "playerId": -1},
                {"roundId": 1, "playerId": 12345},
            ],
        },
    }
    summary = summarize_league(payload, config)
    assert summary["my_team"] == "Cao Caliphate"
    assert summary["roster_size"] == 16
    assert summary["starter_count"] == 9
    assert summary["draft"]["board_slots"] == 2
    assert summary["draft"]["completed_picks"] == 1
    assert summary["scoring_items"] == 1


def test_redaction_removes_account_identifiers() -> None:
    payload = {
        "members": [{"id": "private-owner-id", "notificationSettings": []}],
        "teams": [
            {
                "id": 5,
                "name": "Cao Caliphate",
                "owners": ["private-owner-id"],
                "primaryOwner": "private-owner-id",
            }
        ],
    }
    redacted = redact_private_fields(payload)
    assert "members" not in redacted
    assert "owners" not in redacted["teams"][0]
    assert "primaryOwner" not in redacted["teams"][0]
    assert redacted["teams"][0]["name"] == "Cao Caliphate"
