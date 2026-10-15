export type Position = "QB" | "RB" | "WR" | "TE";
export interface Player {
  id: number;
  rank: number;
  name: string;
  position: Position;
  positionRank: number;
  team: string;
  bye: number | null;
  projection: number;
  vor: number;
  tier: number;
  adp: number;
  espnAdp: number | null;
  ffcAdp: number | null;
  ecr: number | null;
  flag: string;
  adpSd: number;
  consensusRank: number;
}
export interface Board {
  schemaVersion: number;
  snapshot: string;
  season: number;
  settings: {
    teams: number;
    rounds: number;
    skillRounds: number;
    scoring: string;
  };
  provenance: {
    source: string;
    sourceRevision: string;
    sha256: string;
    repository: string;
    uncertainty: string;
  };
  replacement: Record<Position, number>;
  players: Player[];
}
export interface Pick {
  id: number;
  owner: "mine" | "room";
}
export interface Session {
  slot: number;
  picks: Pick[];
}
export interface Score {
  player: Player;
  fit: number;
  returnProbability: number;
  tierDrop: number;
  urgency: number;
  injuryPenalty: number;
  upsideBonus: number;
  score: number;
}
export const POSITIONS: Position[] = ["QB", "RB", "WR", "TE"];
export const STARTERS: Record<Position, number> = {
  QB: 1,
  RB: 2,
  WR: 2,
  TE: 1,
};
export const CAPS: Record<Position, number> = { QB: 2, RB: 6, WR: 7, TE: 2 };
export function validateBoard(value: unknown): Board {
  const b = value as Board;
  if (
    !b ||
    b.schemaVersion !== 1 ||
    !Array.isArray(b.players) ||
    b.players.length !== 200 ||
    b.settings?.teams !== 10 ||
    b.settings.skillRounds !== 14 ||
    typeof b.snapshot !== "string" ||
    !b.provenance?.sha256 ||
    !/^[a-f0-9]{40}$/.test(b.provenance.sourceRevision)
  )
    throw new Error("The archived player board is invalid.");
  if (
    new Set(b.players.map((p) => p.id)).size !== b.players.length ||
    b.players.some(
      (p) =>
        !p ||
        !POSITIONS.includes(p.position) ||
        !p.name ||
        !p.team ||
        !Number.isFinite(p.projection) ||
        !Number.isFinite(p.vor) ||
        !Number.isFinite(p.adp) ||
        !Number.isFinite(p.adpSd) ||
        p.adpSd <= 0 ||
        !Number.isInteger(p.id),
    )
  )
    throw new Error("The archived player records are invalid.");
  return b;
}
export function snakePicks(slot: number, teams = 10, rounds = 16): number[] {
  if (!Number.isInteger(slot) || slot < 1 || slot > teams)
    throw new Error("Choose a valid draft slot.");
  return Array.from({ length: rounds }, (_, i) =>
    i % 2 === 0 ? i * teams + slot : (i + 1) * teams - slot + 1,
  );
}
// Numerical Recipes erfc approximation. Maximum absolute error is approximately 1.2e-7.
export function erfc(x: number): number {
  const z = Math.abs(x),
    t = 1 / (1 + 0.5 * z);
  const result =
    t *
    Math.exp(
      -z * z -
        1.26551223 +
        t *
          (1.00002368 +
            t *
              (0.37409196 +
                t *
                  (0.09678418 +
                    t *
                      (-0.18628806 +
                        t *
                          (0.27886807 +
                            t *
                              (-1.13520398 +
                                t *
                                  (1.48851587 +
                                    t * (-0.82215223 + t * 0.17087277)))))))),
    );
  return x >= 0 ? result : 2 - result;
}
export function availability(player: Player, pick: number): number {
  return Math.min(
    1,
    Math.max(
      0,
      0.5 *
        erfc(
          (pick - 0.5 - player.adp) / Math.max(player.adpSd, 1) / Math.SQRT2,
        ),
    ),
  );
}
export function returnProbability(
  player: Player,
  current: number,
  next: number | null,
): number {
  const now = availability(player, current);
  return next === null || now <= 1e-6
    ? 0
    : Math.max(0, Math.min(1, availability(player, next) / now));
}
export function counts(roster: Player[]): Record<Position, number> {
  return Object.fromEntries(
    POSITIONS.map((pos) => [
      pos,
      roster.filter((p) => p.position === pos).length,
    ]),
  ) as Record<Position, number>;
}
export function rosterFit(
  player: Player,
  roster: Player[],
  round: number,
): number {
  const c = counts(roster),
    pos = player.position,
    n = c[pos];
  if (n >= CAPS[pos]) return 0;
  if (n < STARTERS[pos]) return 1;
  const flexFilled =
    Math.max(0, c.RB - 2) + Math.max(0, c.WR - 2) + Math.max(0, c.TE - 1) >= 1;
  if (pos !== "QB" && !flexFilled) return 1;
  if (pos === "RB")
    return ({ 3: 0.84, 4: 0.76, 5: 0.58 } as Record<number, number>)[n] ?? 0.38;
  if (pos === "WR")
    return (
      ({ 3: 0.8, 4: 0.66, 5: 0.5, 6: 0.3 } as Record<number, number>)[n] ?? 0.18
    );
  if (pos === "TE") return n === 1 && round >= 12 ? 0.22 : 0;
  return n === 1 && round >= 14 ? 0.08 : 0;
}
export function tierDrop(player: Player, available: Player[]): number {
  const lower = available.filter(
    (p) => p.position === player.position && p.tier > player.tier,
  );
  return Math.max(
    0,
    player.vor - (lower.length ? Math.max(...lower.map((p) => p.vor)) : 0),
  );
}
export function scorePlayer(
  player: Player,
  roster: Player[],
  round: number,
  slot: number,
  available: Player[],
): Score {
  const picks = snakePicks(slot),
    fit = rosterFit(player, roster, round),
    returning = returnProbability(
      player,
      picks[round - 1],
      picks[round] ?? null,
    ),
    drop = tierDrop(player, available);
  const urgency = (1 - returning) * drop,
    injuryPenalty =
      player.flag && !["ACTIVE", "NORMAL"].includes(player.flag)
        ? round <= 8
          ? 12
          : 5
        : 0;
  const upsideBonus =
    round >= 9 && ["RB", "WR"].includes(player.position)
      ? Math.min(12, 0.25 * Math.max(0, player.rank - player.consensusRank))
      : 0;
  return {
    player,
    fit,
    returnProbability: returning,
    tierDrop: drop,
    urgency,
    injuryPenalty,
    upsideBonus,
    score:
      fit > 0
        ? player.vor * fit + 0.8 * urgency - injuryPenalty + upsideBonus
        : -1e9,
  };
}
export function forcedPositions(roster: Player[], round: number): Position[] {
  const milestones: [number, Partial<Record<Position, number>>][] = [
    [3, { RB: 1, WR: 1 }],
    [6, { RB: 2, WR: 2 }],
    [9, { RB: 3, WR: 3 }],
    [12, { QB: 1, RB: 4, WR: 4, TE: 1 }],
    [14, { QB: 1, RB: 5, WR: 5, TE: 1 }],
  ];
  const c = counts(roster);
  for (const [deadline, targets] of milestones) {
    if (deadline < round) continue;
    const needed = Object.entries(targets).map(
      ([pos, n]) =>
        [pos, Math.max(0, n! - c[pos as Position])] as [Position, number],
    );
    return needed.reduce((sum, [, n]) => sum + n, 0) >= deadline - round + 1
      ? needed.filter(([, n]) => n > 0).map(([pos]) => pos)
      : [];
  }
  return [];
}
export function recommend(
  available: Player[],
  roster: Player[],
  round: number,
  slot: number,
): Score[] {
  if (round > 14) return [];
  const scores = available
    .map((player) => scorePlayer(player, roster, round, slot, available))
    .filter((score) => score.fit > 0);
  const forced = forcedPositions(roster, round),
    fitting = scores.filter((score) => forced.includes(score.player.position));
  return (fitting.length ? fitting : scores)
    .sort((a, b) => b.score - a.score || a.player.rank - b.player.rank)
    .slice(0, 3);
}
export function safeSession(value: unknown, board: Board): Session | null {
  const s = value as Session;
  if (
    !s ||
    !Number.isInteger(s.slot) ||
    s.slot < 1 ||
    s.slot > 10 ||
    !Array.isArray(s.picks) ||
    s.picks.length > 200
  )
    return null;
  const ids = new Set(board.players.map((p) => p.id));
  if (
    s.picks.some(
      (p) => !p || !ids.has(p.id) || !["mine", "room"].includes(p.owner),
    ) ||
    new Set(s.picks.map((p) => p.id)).size !== s.picks.length
  )
    return null;
  const mine = s.picks.filter((p) => p.owner === "mine");
  if (mine.length > 14) return null;
  const c = counts(
    mine.map((p) => board.players.find((player) => player.id === p.id)!),
  );
  return POSITIONS.some((pos) => c[pos] > CAPS[pos])
    ? null
    : { slot: s.slot, picks: s.picks };
}
export function simulateRoom(session: Session, board: Board): Session {
  const round = session.picks.filter((p) => p.owner === "mine").length + 1;
  if (round > 14) return session;
  const required = Math.max(
    0,
    snakePicks(session.slot)[round - 1] - 1 - session.picks.length,
  );
  const taken = new Set(session.picks.map((p) => p.id));
  const additions = board.players
    .filter((p) => !taken.has(p.id))
    .sort((a, b) => a.adp - b.adp)
    .slice(0, required)
    .map((p) => ({ id: p.id, owner: "room" as const }));
  return { ...session, picks: [...session.picks, ...additions] };
}
export function rosterCSV(session: Session, board: Board): string {
  const quote = (s: string) => `"${s.replaceAll('"', '""')}"`;
  return (
    [
      "owner,player,position,team,projection,vor,market_adp,snapshot",
      ...session.picks.map((pick) => {
        const p = board.players.find((p) => p.id === pick.id)!;
        return [
          pick.owner,
          quote(p.name),
          p.position,
          p.team,
          p.projection,
          p.vor,
          p.adp,
          board.snapshot,
        ].join(",");
      }),
    ].join("\r\n") + "\r\n"
  );
}
