from fantasydraft.strategy import (
    Player,
    RosterPlan,
    milestone_forced_positions,
    normal_availability,
    snake_picks,
)


def test_snake_picks_at_both_ends() -> None:
    assert snake_picks(1)[:4] == [1, 20, 21, 40]
    assert snake_picks(10)[:4] == [10, 11, 30, 31]


def test_availability_falls_as_draft_advances() -> None:
    player = Player(1, "Example", "RB", "FA", 100, market_adp=50, adp_sd=10)
    assert normal_availability(player, 30) > normal_availability(player, 50)
    assert normal_availability(player, 50) > normal_availability(player, 70)


def test_progressive_core_milestone_forces_balance() -> None:
    roster = RosterPlan(
        [
            Player(1, "QB", "QB", "FA", 100),
            Player(2, "WR", "WR", "FA", 100),
        ]
    )
    assert milestone_forced_positions(roster, 3) == {"RB"}
