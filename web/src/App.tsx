import { useEffect, useMemo, useRef, useState } from "react";
import {
  CAPS,
  counts,
  forcedPositions,
  POSITIONS,
  recommend,
  rosterCSV,
  safeSession,
  scorePlayer,
  simulateRoom,
  snakePicks,
  STARTERS,
  validateBoard,
  type Board,
  type Player,
  type Position,
  type Score,
  type Session,
} from "./engine";

const STORAGE = "fantasydraft-room:v1";
const EMPTY: Session = { slot: 5, picks: [] };
const pct = (x: number) => `${Math.round(x * 100)}%`;
const signed = (x: number) => `${x > 0 ? "+" : ""}${x.toFixed(1)}`;
function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function PositionTag({ position }: { position: Position }) {
  return (
    <span className={`position ${position.toLowerCase()}`}>{position}</span>
  );
}
function Arrow() {
  return <span aria-hidden="true">↗</span>;
}

function Methodology({
  board,
  dialogRef,
}: {
  board: Board;
  dialogRef: React.RefObject<HTMLDialogElement | null>;
}) {
  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="method-title"
      className="method-dialog"
      onClick={(e) => {
        if (e.target === e.currentTarget) e.currentTarget.close();
      }}
    >
      <div className="dialog-content">
        <button
          className="close-dialog"
          onClick={() => dialogRef.current?.close()}
          aria-label="Close methodology"
        >
          ×
        </button>
        <div className="eyebrow">Behind the board</div>
        <h2 id="method-title">Every pick has a tradeoff.</h2>
        <p>
          This workbench translates the repository’s quantitative draft strategy
          into an interactive scenario. It uses the published September 1, 2026
          board, with no ESPN account or live feed.
        </p>
        <div className="formula">
          Value × roster fit + 0.8 × urgency
          <br />
          <small>− archived status penalty + late-round upside bonus</small>
        </div>
        <h3>Value over replacement</h3>
        <p>
          VOR compares each player’s projected full-PPR points with the first
          player outside the league’s starting demand at that position. The
          original calculation allocates ten FLEX spots before setting
          replacement levels.
        </p>
        <div className="baseline-grid">
          {POSITIONS.map((pos) => (
            <div key={pos}>
              <PositionTag position={pos} />
              <strong>{board.replacement[pos].toFixed(1)}</strong>
              <span>replacement pts</span>
            </div>
          ))}
        </div>
        <h3>The cost of waiting</h3>
        <p>
          Conditional return is the estimated probability that a player still
          available at your current pick survives to your next snake pick.
          Urgency multiplies the probability of losing that player by the VOR
          drop to the next available positional tier.
        </p>
        <p>
          <strong>Uncertainty is reconstructed.</strong> The public Markdown
          lacks original FFC standard deviations and ESPN ranks. This demo
          combines an ADP-scaled spread with disagreement among published ESPN
          ADP, FFC ADP and ECR. Return percentages are a scenario proxy, not
          calibrated odds or the exact original plan probabilities.
        </p>
        <h3>Roster-aware choices</h3>
        <p>
          The original roster-fit multipliers, positional caps, early RB/WR
          milestones, archived injury penalties and late-round upside bonus are
          preserved. Recommendations adapt to your roster and the players you
          mark taken. They are heuristic rankings, not a globally optimal draft
          solver.
        </p>
        <h3>A bounded, honest snapshot</h3>
        <ul>
          <li>
            200 skill players; QB, RB, WR and TE. The quantified board covers
            your first 14 selections. Reserve rounds 15–16 for one D/ST and one
            kicker.
          </li>
          <li>
            Projected points, teams, bye weeks, ranks and status flags are
            frozen at September 1, 2026. No current injury or roster claims are
            made.
          </li>
          <li>
            Market ADP blends 75% ESPN and 25% Fantasy Football Calculator.
            FantasyPros consensus comes from the August 28 DynastyProcess
            snapshot.
          </li>
          <li>
            “Simulate room” removes remaining players in ADP order until the
            current pick. It is deterministic and can be undone; real rooms
            behave differently.
          </li>
          <li>
            Changing draft slot retains your selections. Picks belong only to
            this scenario and are never sent to ESPN.
          </li>
        </ul>
        <p className="privacy-note">
          All selections stay in this browser. Exports contain only this local
          scenario and public archived player data.
        </p>
        <a
          className="button orange"
          target="_blank"
          rel="noreferrer"
          href={`${board.provenance.repository}/blob/${board.provenance.sourceRevision}/draft_strategy/METHODOLOGY.md`}
        >
          Read the original methodology <Arrow />
        </a>
      </div>
    </dialog>
  );
}

function Recommendation({
  score,
  index,
  onDraft,
  disabled,
}: {
  score: Score;
  index: number;
  onDraft: (id: number) => void;
  disabled: boolean;
}) {
  return (
    <article className={`recommendation ${index === 0 ? "leading" : ""}`}>
      <div className="recommendation-top">
        <span>
          {index === 0 ? "Model preference" : `Alternative 0${index + 1}`}
        </span>
        <PositionTag position={score.player.position} />
      </div>
      <h3>{score.player.name}</h3>
      <p className="player-meta">
        {score.player.team} <span>·</span> Tier {score.player.tier}{" "}
        <span>·</span> ADP {score.player.adp.toFixed(1)}
      </p>
      <div className="rec-numbers">
        <div>
          <strong>{signed(score.player.vor)}</strong>
          <span>value above replacement</span>
        </div>
        <div>
          <strong>{pct(score.returnProbability)}</strong>
          <span>return at next pick*</span>
        </div>
      </div>
      <p className="rec-reason">
        {score.fit === 1
          ? "Fills a starter or FLEX need."
          : `Bench value weighted at ${pct(score.fit)}.`}{" "}
        {score.tierDrop > 0
          ? `${score.tierDrop.toFixed(1)} pts separate the next lower tier.`
          : "No lower-tier value gap remains."}
        {score.injuryPenalty > 0
          ? " Archived status flag lowers the score."
          : ""}
      </p>
      <button
        className={index === 0 ? "button orange" : "button outline"}
        onClick={() => onDraft(score.player.id)}
        disabled={disabled}
      >
        Draft to my roster <span aria-hidden="true">+</span>
      </button>
    </article>
  );
}

function Comparison({
  players,
  scores,
  onRemove,
}: {
  players: Player[];
  scores: Map<number, Score>;
  onRemove: (id: number) => void;
}) {
  return (
    <section className="comparison panel" aria-label="Player comparison">
      <div className="section-title">
        <div>
          <span className="eyebrow">Side by side</span>
          <h2>Make the tradeoff visible.</h2>
        </div>
        <span className="muted">Up to 3 players</span>
      </div>
      <div className="compare-grid">
        {players.map((p) => {
          const score = scores.get(p.id);
          return (
            <article key={p.id}>
              <div className="compare-name">
                <PositionTag position={p.position} />
                <button
                  aria-label={`Remove ${p.name} from comparison`}
                  onClick={() => onRemove(p.id)}
                >
                  ×
                </button>
              </div>
              <h3>{p.name}</h3>
              <dl>
                <div>
                  <dt>Projected points</dt>
                  <dd>{p.projection.toFixed(1)}</dd>
                </div>
                <div>
                  <dt>Value over replacement</dt>
                  <dd>{signed(p.vor)}</dd>
                </div>
                <div>
                  <dt>Positional tier</dt>
                  <dd>{p.tier}</dd>
                </div>
                <div>
                  <dt>Market ADP</dt>
                  <dd>{p.adp.toFixed(1)}</dd>
                </div>
                <div>
                  <dt>Return at next pick*</dt>
                  <dd>{score ? pct(score.returnProbability) : "—"}</dd>
                </div>
                <div>
                  <dt>Roster-fit weight</dt>
                  <dd>{score ? pct(score.fit) : "—"}</dd>
                </div>
                <div>
                  <dt>Bye week</dt>
                  <dd>{p.bye ?? "—"}</dd>
                </div>
                <div>
                  <dt>Archived status</dt>
                  <dd>{p.flag || "No flag"}</dd>
                </div>
              </dl>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function Room({ board }: { board: Board }) {
  const [session, setSession] = useState<Session>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE) || "null");
      return saved?.version === 1
        ? safeSession(saved.session, board) || EMPTY
        : EMPTY;
    } catch {
      return EMPTY;
    }
  });
  const [history, setHistory] = useState<Session[]>([]);
  const [query, setQuery] = useState(""),
    [position, setPosition] = useState<Position | "ALL">("ALL"),
    [status, setStatus] = useState("available"),
    [sort, setSort] = useState("rank"),
    [page, setPage] = useState(0);
  const [compare, setCompare] = useState<number[]>([]),
    [notice, setNotice] = useState(
      "Choose a draft slot, then mark the room’s picks or simulate the turn.",
    ),
    [storageError, setStorageError] = useState(false);
  const [importText, setImportText] = useState(""),
    [importError, setImportError] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const pickMap = useMemo(
    () => new Map(session.picks.map((p) => [p.id, p.owner])),
    [session.picks],
  );
  const roster = useMemo(
    () =>
      session.picks
        .filter((p) => p.owner === "mine")
        .map((p) => board.players.find((player) => player.id === p.id)!),
    [session.picks, board],
  );
  const available = useMemo(
    () => board.players.filter((p) => !pickMap.has(p.id)),
    [board, pickMap],
  );
  const round = roster.length + 1,
    complete = round > 14,
    picks = snakePicks(session.slot),
    current = picks[Math.min(round - 1, 15)],
    next = picks[round] ?? null,
    rosterCounts = counts(roster);
  const recommendations = useMemo(
    () => recommend(available, roster, round, session.slot),
    [available, roster, round, session.slot],
  );
  const scores = useMemo(
    () =>
      new Map(
        board.players.map((p) => [
          p.id,
          scorePlayer(p, roster, Math.min(round, 14), session.slot, available),
        ]),
      ),
    [board, roster, round, session.slot, available],
  );
  const needs = forcedPositions(roster, round);
  const filtered = useMemo(
    () =>
      board.players
        .filter(
          (p) =>
            (position === "ALL" || p.position === position) &&
            `${p.name} ${p.team}`.toLowerCase().includes(query.toLowerCase()) &&
            (status === "all" ||
              (status === "available"
                ? !pickMap.has(p.id)
                : status === "mine"
                  ? pickMap.get(p.id) === "mine"
                  : pickMap.get(p.id) === "room")),
        )
        .sort((a, b) =>
          sort === "vor"
            ? b.vor - a.vor
            : sort === "adp"
              ? a.adp - b.adp
              : sort === "projection"
                ? b.projection - a.projection
                : sort === "fit"
                  ? scores.get(b.id)!.score - scores.get(a.id)!.score ||
                    a.rank - b.rank
                  : a.rank - b.rank,
        ),
    [board, position, query, status, sort, pickMap, scores],
  );
  const maxPage = Math.max(0, Math.ceil(filtered.length / 20) - 1),
    effectivePage = Math.min(page, maxPage),
    visible = filtered.slice(effectivePage * 20, effectivePage * 20 + 20);
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE, JSON.stringify({ version: 1, session }));
      setStorageError(false);
    } catch {
      setStorageError(true);
    }
  }, [session]);
  function change(nextSession: Session, message: string) {
    setHistory((rows) => [...rows.slice(-29), session]);
    setSession(nextSession);
    setNotice(message);
  }
  function draft(id: number) {
    const p = board.players.find((p) => p.id === id)!;
    if (
      complete ||
      pickMap.has(id) ||
      rosterCounts[p.position] >= CAPS[p.position]
    )
      return;
    change(
      { ...session, picks: [...session.picks, { id, owner: "mine" }] },
      `${p.name} drafted. ${round === 14 ? "Your skill roster is complete." : `Next selection: round ${round + 1}, pick ${next}.`}`,
    );
  }
  function markTaken(id: number) {
    if (pickMap.has(id)) return;
    const p = board.players.find((p) => p.id === id)!;
    change(
      { ...session, picks: [...session.picks, { id, owner: "room" }] },
      `${p.name} marked taken by the room.`,
    );
  }
  function release(id: number) {
    const p = board.players.find((p) => p.id === id)!;
    change(
      { ...session, picks: session.picks.filter((p) => p.id !== id) },
      `${p.name} restored to the available board.`,
    );
  }
  function undo() {
    const previous = history.at(-1);
    if (!previous) return;
    setSession(previous);
    setHistory((rows) => rows.slice(0, -1));
    setNotice("Last action undone.");
  }
  function toggleCompare(id: number) {
    setCompare((ids) =>
      ids.includes(id)
        ? ids.filter((x) => x !== id)
        : ids.length < 3
          ? [...ids, id]
          : ids,
    );
  }
  function exportScenario() {
    download(
      `fantasydraft-scenario-${board.snapshot}.json`,
      JSON.stringify(
        {
          schemaVersion: 1,
          snapshot: board.snapshot,
          settings: board.settings,
          provenance: board.provenance,
          session,
        },
        null,
        2,
      ),
      "application/json",
    );
    setNotice("Scenario JSON downloaded.");
  }
  function importScenario() {
    try {
      const value = JSON.parse(importText);
      if (
        value.schemaVersion !== 1 ||
        value.snapshot !== board.snapshot ||
        value.provenance?.sha256 !== board.provenance.sha256
      )
        throw new Error(
          "Use a scenario exported from this September 1, 2026 board.",
        );
      const restored = safeSession(value.session, board);
      if (!restored)
        throw new Error("The scenario has invalid or duplicate selections.");
      change(
        restored,
        "Exported scenario restored. Undo returns to your previous draft.",
      );
      setImportError("");
      setImportText("");
    } catch (error) {
      setImportError(
        error instanceof SyntaxError
          ? "Paste the complete exported JSON file."
          : (error as Error).message,
      );
    }
  }
  return (
    <>
      <a className="skip-link" href="#draft-board">
        Skip to player board
      </a>
      <header className="topbar">
        <a href="#" className="brand">
          <span className="brand-icon">D</span>Fantasy<span>Draft</span>
        </a>
        <nav aria-label="Primary">
          <a className="active" href="#draft-board">
            Draft room
          </a>
          <button onClick={() => dialogRef.current?.showModal()}>
            How it works
          </button>
          <a
            href={board.provenance.repository}
            target="_blank"
            rel="noreferrer"
          >
            Source <Arrow />
          </a>
        </nav>
        <span className="archive-pill">
          <i />
          2026 ARCHIVE
        </span>
      </header>
      <main>
        <section className="hero">
          <div>
            <span className="eyebrow">
              The draft room / Quantitative strategy
            </span>
            <h1>
              Make every pick
              <br />
              <em>count for more.</em>
            </h1>
            <p>
              Value, scarcity, and the cost of waiting.
              <br />A clear reason behind your next selection.
            </p>
          </div>
          <div className="hero-context">
            <span className="eyebrow">September 1, 2026 snapshot</span>
            <strong>
              10 teams. Full PPR.
              <br />
              One decision at a time.
            </strong>
            <p>200 skill players · 16-round snake draft</p>
            <button onClick={() => dialogRef.current?.showModal()}>
              Explore the model & assumptions <Arrow />
            </button>
          </div>
        </section>
        <div className="snapshot-banner">
          <span className="snapshot-icon" aria-hidden="true">
            ◷
          </span>
          <p>
            <strong>Historical draft simulation.</strong> Projections, teams and
            status flags reflect the archived snapshot. Return odds use a
            disclosed uncertainty proxy.
          </p>
          <button onClick={() => dialogRef.current?.showModal()}>
            Details <Arrow />
          </button>
        </div>
        <div className="room-controls">
          <div className="slot-control">
            <label htmlFor="slot">Your draft slot</label>
            <select
              id="slot"
              value={session.slot}
              onChange={(e) =>
                change(
                  { ...session, slot: Number(e.target.value) },
                  `Draft slot ${e.target.value} selected. Existing selections retained.`,
                )
              }
            >
              {Array.from({ length: 10 }, (_, i) => (
                <option value={i + 1} key={i}>
                  Slot {i + 1} of 10
                </option>
              ))}
            </select>
          </div>
          <div className="turn-stat">
            <span>Current selection</span>
            <strong>
              {complete
                ? "Skill roster complete"
                : `Round ${round} / Pick ${current}`}
            </strong>
          </div>
          <div className="turn-stat next-stat">
            <span>Next selection</span>
            <strong>
              {complete
                ? "D/ST + kicker"
                : `Pick ${next} · ${next! - current - 1} picks between`}
            </strong>
          </div>
          <div className="room-buttons">
            <button
              className="button outline"
              onClick={undo}
              disabled={!history.length}
            >
              ↶ Undo
            </button>
            <button
              className="button outline"
              disabled={complete || session.picks.length >= current - 1}
              onClick={() => {
                const simulated = simulateRoom(session, board);
                change(
                  simulated,
                  `Room simulated in ADP order: ${simulated.picks.length - session.picks.length} players marked taken. Undo restores the board.`,
                );
              }}
            >
              Simulate room <span aria-hidden="true">→</span>
            </button>
          </div>
        </div>
        <div className="session-notice" role="status">
          {notice}
        </div>
        <div className="room-layout">
          <div className="main-column">
            <section className="recommendations">
              <div className="section-title">
                <div>
                  <span className="eyebrow">On the clock</span>
                  <h2>
                    {complete
                      ? "A roster with a purpose."
                      : "A shortlist with a point of view."}
                  </h2>
                </div>
                <span className="model-label">
                  {!complete && needs.length
                    ? `${needs.join(" / ")} milestone`
                    : "ROSTER-AWARE MODEL"}
                </span>
              </div>
              {complete ? (
                <div className="complete-panel">
                  <strong>Your 14 skill selections are complete.</strong>
                  <p>
                    The published board covers skill positions. Finish the
                    16-round draft with one D/ST and one kicker. Review or
                    export your roster below.
                  </p>
                </div>
              ) : recommendations.length ? (
                <div className="recommendation-grid">
                  {recommendations.map((score, index) => (
                    <Recommendation
                      key={score.player.id}
                      score={score}
                      index={index}
                      onDraft={draft}
                      disabled={complete}
                    />
                  ))}
                </div>
              ) : (
                <div className="complete-panel">
                  <strong>No eligible recommendation remains.</strong>
                  <p>
                    Check your roster caps, restore taken players, or undo the
                    last action.
                  </p>
                </div>
              )}
              <p className="proxy-note">
                *Conditional survival to your next turn, given the player is
                here now. Reconstructed ADP uncertainty; not live or calibrated
                odds.
              </p>
            </section>
            {compare.length > 0 ? (
              <Comparison
                players={compare.map(
                  (id) => board.players.find((p) => p.id === id)!,
                )}
                scores={scores}
                onRemove={toggleCompare}
              />
            ) : null}
            <section id="draft-board" className="board-panel panel">
              <div className="section-title">
                <div>
                  <span className="eyebrow">The complete picture</span>
                  <h2>Your draft board</h2>
                </div>
                <span className="board-count">
                  {available.length}
                  <small> / 200 available</small>
                </span>
              </div>
              <div className="board-filters">
                <div className="position-tabs" aria-label="Position filters">
                  {(["ALL", ...POSITIONS] as const).map((pos) => (
                    <button
                      key={pos}
                      className={pos === position ? "selected" : ""}
                      aria-pressed={pos === position}
                      onClick={() => {
                        setPosition(pos);
                        setPage(0);
                      }}
                    >
                      {pos === "ALL" ? "All players" : pos}
                    </button>
                  ))}
                </div>
                <label className="search">
                  <span className="sr-only">Search player or team</span>
                  <span aria-hidden="true">⌕</span>
                  <input
                    placeholder="Search player or team"
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      setPage(0);
                    }}
                  />
                </label>
              </div>
              <div className="board-options">
                <label>
                  Show
                  <select
                    value={status}
                    onChange={(e) => {
                      setStatus(e.target.value);
                      setPage(0);
                    }}
                  >
                    <option value="available">Available players</option>
                    <option value="mine">My roster</option>
                    <option value="taken">Taken by room</option>
                    <option value="all">All players</option>
                  </select>
                </label>
                <label>
                  Sort
                  <select
                    value={sort}
                    onChange={(e) => {
                      setSort(e.target.value);
                      setPage(0);
                    }}
                  >
                    <option value="rank">Original board rank</option>
                    <option value="vor">Value over replacement</option>
                    <option value="adp">Market ADP</option>
                    <option value="projection">Projected points</option>
                    <option value="fit">Current pick score</option>
                  </select>
                </label>
                <span>Select up to 3 to compare</span>
              </div>
              <div
                className="table-scroll"
                tabIndex={0}
                aria-label="Player draft board"
              >
                <table>
                  <thead>
                    <tr>
                      <th>
                        <span className="sr-only">Compare</span>
                      </th>
                      <th>#</th>
                      <th>Player</th>
                      <th>Proj.</th>
                      <th>
                        <abbr title="Value over replacement in season points">
                          VOR
                        </abbr>
                      </th>
                      <th>ADP</th>
                      <th>Return*</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((p) => {
                      const owner = pickMap.get(p.id),
                        score = scores.get(p.id)!;
                      return (
                        <tr
                          key={p.id}
                          className={
                            owner === "mine"
                              ? "my-player"
                              : owner
                                ? "taken-player"
                                : ""
                          }
                        >
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Compare ${p.name}`}
                              checked={compare.includes(p.id)}
                              disabled={
                                !compare.includes(p.id) && compare.length >= 3
                              }
                              onChange={() => toggleCompare(p.id)}
                            />
                          </td>
                          <td className="rank">{p.rank}</td>
                          <td>
                            <div className="player-cell">
                              <PositionTag position={p.position} />
                              <div>
                                <strong>{p.name}</strong>
                                <span>
                                  {p.team} <i>·</i> Tier {p.tier} <i>·</i> Bye{" "}
                                  {p.bye ?? "—"}{" "}
                                  {p.flag ? (
                                    <b title={`Archived status: ${p.flag}`}>
                                      FLAG
                                    </b>
                                  ) : null}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td>{p.projection.toFixed(1)}</td>
                          <td className={p.vor > 0 ? "positive" : ""}>
                            {signed(p.vor)}
                          </td>
                          <td>{p.adp.toFixed(1)}</td>
                          <td>
                            {complete || owner ? (
                              "—"
                            ) : (
                              <span
                                className={
                                  score.returnProbability < 0.25
                                    ? "low-return"
                                    : ""
                                }
                              >
                                {pct(score.returnProbability)}
                              </span>
                            )}
                          </td>
                          <td>
                            {owner ? (
                              <button
                                className="restore-button"
                                onClick={() => release(p.id)}
                              >
                                {owner === "mine" ? "On roster" : "Taken"}{" "}
                                <span>↶</span>
                              </button>
                            ) : (
                              <div className="row-actions">
                                <button
                                  className="draft-button"
                                  onClick={() => draft(p.id)}
                                  disabled={
                                    complete ||
                                    rosterCounts[p.position] >= CAPS[p.position]
                                  }
                                  aria-label={`Draft ${p.name}`}
                                >
                                  Draft
                                </button>
                                <button
                                  className="taken-button"
                                  onClick={() => markTaken(p.id)}
                                  aria-label={`Mark ${p.name} taken`}
                                >
                                  Taken
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {!visible.length ? (
                <div className="empty-board">
                  <h3>No players match this view.</h3>
                  <p>Try another position, availability filter or search.</p>
                  <button
                    className="button outline"
                    onClick={() => {
                      setQuery("");
                      setPosition("ALL");
                      setStatus("available");
                      setPage(0);
                    }}
                  >
                    Clear filters
                  </button>
                </div>
              ) : null}
              <div className="pagination">
                <span>
                  {filtered.length
                    ? `${effectivePage * 20 + 1}–${Math.min((effectivePage + 1) * 20, filtered.length)} of ${filtered.length} players`
                    : "0 players"}
                </span>
                <div>
                  <button
                    aria-label="Previous page"
                    disabled={effectivePage === 0}
                    onClick={() => setPage(effectivePage - 1)}
                  >
                    ←
                  </button>
                  <span>
                    {effectivePage + 1} / {maxPage + 1}
                  </span>
                  <button
                    aria-label="Next page"
                    disabled={effectivePage === maxPage}
                    onClick={() => setPage(effectivePage + 1)}
                  >
                    →
                  </button>
                </div>
              </div>
            </section>
            <div className="model-footnote">
              <span className="eyebrow">Read the board, not just the rank</span>
              <p>
                Tier numbers are positional. A Tier 2 quarterback and a Tier 2
                running back are not equivalent values. Negative VOR is normal
                for late bench players; the model discounts roster fit and adds
                market-backed upside.
              </p>
            </div>
          </div>
          <aside className="roster-panel panel">
            <div className="roster-heading">
              <span className="eyebrow">Your build</span>
              <span>
                {roster.length}
                <small> / 14</small>
              </span>
            </div>
            <h2>The roster</h2>
            <div
              className="roster-progress"
              aria-label={`${roster.length} of 14 skill selections filled`}
            >
              <i style={{ width: `${(roster.length / 14) * 100}%` }} />
            </div>
            <div className="position-counts">
              {POSITIONS.map((pos) => (
                <div key={pos}>
                  <PositionTag position={pos} />
                  <strong>
                    {rosterCounts[pos]}
                    <small> / {STARTERS[pos]}</small>
                  </strong>
                </div>
              ))}
            </div>
            <p className="starter-note">
              Counts / dedicated starter slots.
              <br />
              Plus one RB/WR/TE FLEX and seven bench.
            </p>
            <div className="roster-list">
              {roster.length ? (
                roster.map((p, index) => (
                  <div className="roster-player" key={p.id}>
                    <span className="roster-round">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <strong>{p.name}</strong>
                      <span>
                        {p.position} · {p.team} · {p.projection.toFixed(1)}{" "}
                        projected pts
                      </span>
                    </div>
                    <button
                      onClick={() => release(p.id)}
                      aria-label={`Remove ${p.name} from roster`}
                    >
                      ×
                    </button>
                  </div>
                ))
              ) : (
                <div className="roster-empty">
                  <span aria-hidden="true">▤</span>
                  <strong>Your first pick starts here.</strong>
                  <p>
                    Draft from the shortlist or the board. Recommendations adapt
                    after each selection.
                  </p>
                </div>
              )}
            </div>
            <div className="roster-total">
              <span>Drafted projected points</span>
              <strong>
                {roster.reduce((sum, p) => sum + p.projection, 0).toFixed(1)}
              </strong>
              <p>
                Sum of player projections, including bench. This is not an
                optimal lineup or team-season forecast.
              </p>
            </div>
            <div className="roster-actions">
              <button className="button navy" onClick={exportScenario}>
                Export scenario <span>↓</span>
              </button>
              <button
                className="button outline"
                disabled={!session.picks.length}
                onClick={() => {
                  download(
                    `fantasydraft-picks-${board.snapshot}.csv`,
                    rosterCSV(session, board),
                    "text/csv;charset=utf-8",
                  );
                  setNotice("Draft picks CSV downloaded.");
                }}
              >
                Export picks CSV <span>↓</span>
              </button>
              <button
                className="reset-button"
                disabled={!session.picks.length}
                onClick={() =>
                  change(
                    { ...session, picks: [] },
                    "Draft reset. Undo restores your previous selections.",
                  )
                }
              >
                Reset this draft
              </button>
            </div>
            <details className="restore-scenario">
              <summary>Restore an exported scenario</summary>
              <label htmlFor="scenario-json">Paste your scenario JSON</label>
              <textarea
                id="scenario-json"
                rows={5}
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
                placeholder="Paste the contents of your exported .json file"
              />
              <button className="button outline" onClick={importScenario}>
                Restore scenario
              </button>
              {importError ? (
                <p className="import-error" role="alert">
                  {importError}
                </p>
              ) : null}
            </details>
            <p className="local-note">
              {storageError
                ? "Browser storage is unavailable. Export your scenario to keep a copy."
                : "Saved on this device. No account or ESPN connection required."}
            </p>
          </aside>
        </div>
        <footer>
          <span>
            FantasyDraft <i>/</i> Turn research into better decisions.
          </span>
          <a
            href={board.provenance.repository}
            target="_blank"
            rel="noreferrer"
          >
            View the source <Arrow />
          </a>
        </footer>
      </main>
      <Methodology board={board} dialogRef={dialogRef} />
    </>
  );
}

export default function App() {
  const [board, setBoard] = useState<Board | null>(null),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    fetch(`${import.meta.env.BASE_URL}board.json`, {
      signal: controller.signal,
    })
      .then((r) => {
        if (!r.ok)
          throw new Error("The archived draft board could not be loaded.");
        return r.json();
      })
      .then((value) => setBoard(validateBoard(value)))
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [retry]);
  return board ? (
    <Room board={board} />
  ) : (
    <main className="load-state" aria-live="polite">
      <span className="eyebrow">FantasyDraft / Draft room</span>
      <h1>
        {error ? "The board is unavailable." : "Preparing the draft room."}
      </h1>
      <p>{error || "Loading the public 2026 projection snapshot…"}</p>
      {error ? (
        <button
          className="button orange"
          onClick={() => setRetry((n) => n + 1)}
        >
          Try again
        </button>
      ) : null}
    </main>
  );
}
