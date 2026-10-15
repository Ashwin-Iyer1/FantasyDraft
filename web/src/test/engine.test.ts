import { describe, expect, it } from "vitest";
import data from "../../public/board.json";
import fixtures from "./python-parity.json";
import {
  availability,
  counts,
  forcedPositions,
  recommend,
  rosterCSV,
  rosterFit,
  safeSession,
  scorePlayer,
  simulateRoom,
  snakePicks,
  validateBoard,
  type Session,
} from "../engine";
const board = validateBoard(data),
  player = (id: number) => board.players.find((p) => p.id === id)!;
describe("Python strategy parity with the same public inputs", () => {
  for (const fixture of fixtures)
    it(`matches slot ${fixture.slot}, round ${fixture.round}`, () => {
      const roster = fixture.rosterIds.map(player),
        available = board.players.filter(
          (p) => !fixture.rosterIds.includes(p.id),
        ),
        score = scorePlayer(
          player(fixture.playerId),
          roster,
          fixture.round,
          fixture.slot,
          available,
        );
      expect(score.fit).toBe(fixture.expected.fit);
      expect(score.tierDrop).toBeCloseTo(fixture.expected.tierDrop, 12);
      expect(score.returnProbability).toBeCloseTo(
        fixture.expected.returnProbability,
        6,
      );
      expect(score.score).toBeCloseTo(fixture.expected.score, 5);
    });
});
describe("draft decisions", () => {
  it("preserves snake order at both ends and rejects invalid slots", () => {
    expect(snakePicks(1).slice(0, 4)).toEqual([1, 20, 21, 40]);
    expect(snakePicks(10).slice(0, 4)).toEqual([10, 11, 30, 31]);
    expect(() => snakePicks(0)).toThrow();
    expect(() => snakePicks(1.5)).toThrow();
  });
  it("availability decreases as the draft advances", () => {
    const p = player(12);
    expect(availability(p, 10)).toBeGreaterThan(availability(p, 25));
    expect(availability(p, 25)).toBeGreaterThan(availability(p, 50));
  });
  it("blocks early duplicate QB and accounts for FLEX then bench", () => {
    expect(
      rosterFit(
        board.players.find((p) => p.position === "QB" && p.id !== 12)!,
        [player(12)],
        5,
      ),
    ).toBe(0);
    const r = [player(1), player(3)];
    expect(rosterFit(player(4), r, 3)).toBe(1);
    r.push(player(4));
    expect(rosterFit(player(8), r, 4)).toBe(0.84);
  });
  it("uses core milestones and stops after fourteen skill picks", () => {
    const roster = [player(12), player(2)];
    expect(forcedPositions(roster, 3)).toEqual(["RB"]);
    expect(
      recommend(
        board.players.filter((p) => ![12, 2].includes(p.id)),
        roster,
        3,
        5,
      ).every((s) => s.player.position === "RB"),
    ).toBe(true);
    expect(recommend(board.players, [], 15, 5)).toEqual([]);
  });
  it("simulates only enough opponent picks to reach the turn, without duplicates", () => {
    const first = simulateRoom({ slot: 5, picks: [] }, board);
    expect(first.picks).toHaveLength(4);
    expect(first.picks.every((p) => p.owner === "room")).toBe(true);
    expect(simulateRoom(first, board)).toEqual(first);
    const mine = board.players.find(
      (p) => !first.picks.some((x) => x.id === p.id),
    )!;
    const second = simulateRoom(
      { ...first, picks: [...first.picks, { id: mine.id, owner: "mine" }] },
      board,
    );
    expect(second.picks).toHaveLength(15);
    expect(new Set(second.picks.map((p) => p.id)).size).toBe(15);
    expect(second.picks.find((p) => p.owner === "mine")?.id).toBe(mine.id);
  });
  it("completes fourteen skill rounds in all ten slots with legal, filled starters", () => {
    for (let slot = 1; slot <= 10; slot++) {
      let session: Session = { slot, picks: [] };
      for (let round = 1; round <= 14; round++) {
        session = simulateRoom(session, board);
        const roster = session.picks
          .filter((p) => p.owner === "mine")
          .map((p) => player(p.id));
        const available = board.players.filter(
          (p) => !session.picks.some((pick) => pick.id === p.id),
        );
        const best = recommend(available, roster, round, slot)[0];
        expect(best).toBeDefined();
        session = {
          ...session,
          picks: [...session.picks, { id: best.player.id, owner: "mine" }],
        };
      }
      expect(safeSession(session, board)).not.toBeNull();
      const final = counts(
        session.picks
          .filter((p) => p.owner === "mine")
          .map((p) => player(p.id)),
      );
      expect(final.QB).toBeGreaterThanOrEqual(1);
      expect(final.RB).toBeGreaterThanOrEqual(2);
      expect(final.WR).toBeGreaterThanOrEqual(2);
      expect(final.TE).toBeGreaterThanOrEqual(1);
    }
  });
});
describe("state and provenance boundaries", () => {
  it("has only archived public skill-player records", () => {
    expect(board.players).toHaveLength(200);
    expect(Object.keys(counts(board.players))).toEqual([
      "QB",
      "RB",
      "WR",
      "TE",
    ]);
    expect(JSON.stringify(board)).not.toMatch(
      /SWID|espn_s2|leagueId|teamId|ownerId|members/,
    );
    expect(Object.keys(board).sort()).toEqual(
      [
        "schemaVersion",
        "snapshot",
        "season",
        "settings",
        "provenance",
        "replacement",
        "players",
      ].sort(),
    );
    expect(board.provenance.sourceRevision).toBe(
      "483c04aefcef00e547542875bde98eed6b5e524f",
    );
  });
  it("rejects unknown, duplicate, over-cap or malformed persisted selections", () => {
    expect(
      safeSession({ slot: 5, picks: [{ id: 1, owner: "mine" }] }, board),
    ).not.toBeNull();
    for (const session of [
      { slot: 0, picks: [] },
      { slot: 5, picks: [{ id: 999, owner: "mine" }] },
      {
        slot: 5,
        picks: [
          { id: 1, owner: "mine" },
          { id: 1, owner: "room" },
        ],
      },
      { slot: 5, picks: [{ id: 1, owner: "unknown" }] },
      {
        slot: 5,
        picks: board.players
          .filter((p) => p.position === "QB")
          .slice(0, 3)
          .map((p) => ({ id: p.id, owner: "mine" })),
      },
    ])
      expect(safeSession(session, board)).toBeNull();
  });
  it("CSV identifies ownership, units and the archive date", () => {
    const session: Session = {
      slot: 5,
      picks: [
        { id: 1, owner: "mine" },
        { id: 2, owner: "room" },
      ],
    };
    const csv = rosterCSV(session, board);
    expect(csv).toContain(
      "owner,player,position,team,projection,vor,market_adp,snapshot",
    );
    expect(csv).toContain(
      'mine,"Jahmyr Gibbs",RB,DET,365,161.7,1.4,2026-09-01',
    );
    expect(csv).toContain('room,"Puka Nacua"');
  });
  it("fails closed on invalid board schema", () => {
    expect(() => validateBoard({ ...data, schemaVersion: 2 })).toThrow();
    expect(() =>
      validateBoard({ ...data, players: data.players.slice(1) }),
    ).toThrow();
  });
});
