"""Build a printable draft-room cheat sheet from the generated Markdown kit."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = ROOT / "draft_strategy"
OUTPUT = ROOT / "output" / "pdf" / "2026_FantasyDraft_Printable_Cheat_Sheet.pdf"

NAVY = colors.HexColor("#17233D")
BLUE = colors.HexColor("#2D6CDF")
PALE_BLUE = colors.HexColor("#EAF1FF")
PALE_GREEN = colors.HexColor("#E9F7EF")
PALE_ORANGE = colors.HexColor("#FFF2DF")
PALE_PURPLE = colors.HexColor("#F1EAFE")
PALE_GRAY = colors.HexColor("#F2F4F7")
GRID = colors.HexColor("#BCC5D3")
MUTED = colors.HexColor("#5E6A7D")
WHITE = colors.white


@dataclass(frozen=True)
class SlotRow:
    round: str
    pick: str
    primary: str
    backup_1: str
    backup_2: str
    pivot: str
    faller: str
    roster: str


@dataclass(frozen=True)
class BoardRow:
    rank: str
    player: str
    position: str
    team: str
    adp: str
    vor: str
    flag: str


def clean(text: str) -> str:
    return (
        text.replace("—", "-")
        .replace("–", "-")
        .replace("’", "'")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .strip()
    )


def short_label(label: str) -> str:
    label = clean(label)
    match = re.fullmatch(r"(.+?) \((QB|RB|WR|TE|DST|K), ([A-Z]+)\)", label)
    if not match:
        return label
    name, position, team = match.groups()
    return f"<b>{name}</b><br/><font color='#5E6A7D'>{position} - {team}</font>"


def parse_slot(path: Path) -> list[SlotRow]:
    rows: list[SlotRow] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\| \d+ \| \d+ \|", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 9:
            raise ValueError(f"Unexpected slot row in {path}: {line}")
        backups = [part.strip() for part in cells[3].split(";")]
        backups += ["-"] * (2 - len(backups))
        rows.append(
            SlotRow(
                round=cells[0],
                pick=cells[1],
                primary=cells[2],
                backup_1=backups[0],
                backup_2=backups[1],
                pivot=cells[4],
                faller=cells[5],
                roster=cells[8],
            )
        )
    if len(rows) != 16:
        raise ValueError(f"Expected 16 rows in {path}, found {len(rows)}")
    return rows


def parse_board(path: Path) -> list[BoardRow]:
    rows: list[BoardRow] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\| \d+ \|", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 13:
            continue
        rows.append(
            BoardRow(
                rank=cells[0],
                player=cells[1],
                position=cells[2],
                team=cells[3],
                adp=cells[8],
                vor=cells[6],
                flag=cells[12],
            )
        )
    if len(rows) < 100:
        raise ValueError(f"Expected at least 100 board rows in {path}, found {len(rows)}")
    return rows


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def footer(canvas, document) -> None:  # ReportLab callback signature
    canvas.saveState()
    width, _ = landscape(letter)
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.4)
    canvas.line(0.28 * inch, 0.27 * inch, width - 0.28 * inch, 0.27 * inch)
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.3 * inch, 0.12 * inch, "Cao Caliphate - 10-team full PPR - data snapshot 2026-09-01")
    canvas.drawRightString(width - 0.3 * inch, 0.12 * inch, f"Page {document.page}")
    canvas.restoreState()


def position_color(label: str) -> colors.Color:
    if "(RB," in label:
        return PALE_GREEN
    if "(WR," in label:
        return PALE_BLUE
    if "(QB," in label:
        return PALE_ORANGE
    if "(TE," in label:
        return PALE_PURPLE
    return PALE_GRAY


def decision_box(number: str, title: str, body: str, styles) -> Table:
    number_style, title_style, body_style = styles
    data = [
        [paragraph(number, number_style), paragraph(title, title_style)],
        ["", paragraph(body, body_style)],
    ]
    box = Table(data, colWidths=[0.42 * inch, 4.32 * inch])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), NAVY),
                ("BACKGROUND", (1, 0), (1, -1), PALE_BLUE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("SPAN", (0, 0), (0, 1)),
                ("BOX", (0, 0), (-1, -1), 0.6, GRID),
                ("LEFTPADDING", (1, 0), (1, -1), 8),
                ("RIGHTPADDING", (1, 0), (1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return box


def cover_page(story: list, styles: dict[str, ParagraphStyle]) -> None:
    story.append(paragraph("2026 DRAFT-ROOM CHEAT SHEET", styles["hero"]))
    story.append(paragraph("Cao Caliphate | Big Ronalds Football League | 10-team full PPR", styles["subtitle"]))
    story.append(Spacer(1, 0.2 * inch))

    decision_styles = (styles["number"], styles["box_title"], styles["box_body"])
    left = [
        decision_box("1", "Find your draft slot", "ESPN reveals it one hour before the draft. Turn to the matching Slot 01-10 page.", decision_styles),
        Spacer(1, 0.12 * inch),
        decision_box("2", "At each pick, scan left to right", "Take Smash faller first if he truly fell and still fits. Otherwise: Primary, Backup 1, Backup 2, then Pivot.", decision_styles),
        Spacer(1, 0.12 * inch),
        decision_box("3", "Cross out drafted players", "Cross out every selected name, including players taken by opponents. Never wait on a player already gone.", decision_styles),
    ]
    right = [
        decision_box("4", "If the whole row is gone", "Use the Top 100 pages. Select the highest uncrossed RB/WR/TE/QB that keeps you on the roster milestones below.", decision_styles),
        Spacer(1, 0.12 * inch),
        decision_box("5", "Do not chase runs", "Early QB run: take RB/WR value. Position run: take the last name in a strong tier or pivot to the best value at another position.", decision_styles),
        Spacer(1, 0.12 * inch),
        decision_box("6", "Finish correctly", "One D/ST in Round 15 and one kicker in Round 16. Do not draft backups at either position.", decision_styles),
    ]
    columns = Table([[left, right]], colWidths=[4.9 * inch, 4.9 * inch])
    columns.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    story.append(columns)
    story.append(Spacer(1, 0.22 * inch))

    milestone_data = [
        [paragraph("CHECKPOINT", styles["table_head"]), paragraph("MINIMUM ROSTER CORE", styles["table_head"]), paragraph("WHY", styles["table_head"])],
        ["After Round 3", "1 RB + 1 WR", "Prevents an early one-position trap"],
        ["After Round 6", "2 RB + 2 WR", "Builds both starting lanes"],
        ["After Round 9", "3 RB + 3 WR", "Covers FLEX and first depth"],
        ["After Round 12", "1 QB + 4 RB + 4 WR + 1 TE", "All starters plus useful depth"],
        ["After Round 14", "1 QB + 5 RB + 5 WR + 1 TE", "Robust core before D/ST and K"],
    ]
    milestones = Table(milestone_data, colWidths=[1.55 * inch, 3.25 * inch, 4.95 * inch])
    milestones.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.45, GRID),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 8.5),
                ("LEADING", (0, 1), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(milestones)
    story.append(Spacer(1, 0.12 * inch))
    story.append(paragraph("Print tip: before the slot reveal, print the two Top 100 pages. After the reveal, print only your matching slot page. That gives you a three-page live-draft packet.", styles["callout"]))
    story.append(PageBreak())


def slot_page(story: list, slot: int, rows: list[SlotRow], styles: dict[str, ParagraphStyle]) -> None:
    picks = ", ".join(row.pick for row in rows)
    story.append(paragraph(f"SLOT {slot:02d} - YOUR 16-ROUND PLAN", styles["page_title"]))
    story.append(paragraph(f"Overall picks: {picks}", styles["small_subtitle"]))
    story.append(Spacer(1, 0.08 * inch))

    headers = ["RD", "PICK", "PRIMARY", "BACKUP 1", "BACKUP 2", "PIVOT", "SMASH FALLER", "ROSTER"]
    data: list[list] = [[paragraph(header, styles["table_head"]) for header in headers]]
    for row in rows:
        data.append(
            [
                paragraph(row.round, styles["center"]),
                paragraph(row.pick, styles["center"]),
                paragraph(short_label(row.primary), styles["player"]),
                paragraph(short_label(row.backup_1), styles["player"]),
                paragraph(short_label(row.backup_2), styles["player"]),
                paragraph(short_label(row.pivot), styles["player"]),
                paragraph(short_label(row.faller), styles["player"]),
                paragraph(clean(row.roster), styles["roster"]),
            ]
        )

    table = Table(
        data,
        colWidths=[0.3 * inch, 0.4 * inch, 1.75 * inch, 1.6 * inch, 1.6 * inch, 1.6 * inch, 1.6 * inch, 1.1 * inch],
        repeatRows=1,
    )
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 2.7),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 2.7),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for index, row in enumerate(rows, 1):
        commands.extend(
            [
                ("BACKGROUND", (0, index), (1, index), PALE_GRAY),
                ("BACKGROUND", (2, index), (2, index), position_color(row.primary)),
                ("BACKGROUND", (7, index), (7, index), PALE_GRAY),
            ]
        )
    table.setStyle(TableStyle(commands))
    story.append(table)
    story.append(Spacer(1, 0.08 * inch))
    story.append(paragraph("READ EACH ROW LEFT TO RIGHT: Smash faller (Rounds 1-14 only) -> Primary -> Backup 1 -> Backup 2 -> Pivot. If all five are gone, use the Top 100 board and honor the checkpoint roster counts.", styles["callout_small"]))
    story.append(PageBreak())


def board_half(rows: Iterable[BoardRow], styles: dict[str, ParagraphStyle]) -> list[list]:
    data = [[paragraph(value, styles["table_head"]) for value in ("#", "PLAYER", "POS", "TM", "ADP", "VOR")]]
    for row in rows:
        player = clean(row.player)
        if row.flag:
            player += " <font color='#A23B2A'><b>*</b></font>"
        data.append(
            [
                paragraph(row.rank, styles["center"]),
                paragraph(player, styles["board_player"]),
                paragraph(clean(row.position), styles["center"]),
                paragraph(clean(row.team), styles["center"]),
                paragraph(clean(row.adp), styles["center"]),
                paragraph(clean(row.vor), styles["center"]),
            ]
        )
    return data


def board_page(story: list, page_no: int, rows: list[BoardRow], styles: dict[str, ParagraphStyle]) -> None:
    start = (page_no - 1) * 50
    page_rows = rows[start : start + 50]
    left, right = page_rows[:25], page_rows[25:]
    first_rank, last_rank = page_rows[0].rank, page_rows[-1].rank
    story.append(paragraph(f"TOP 100 MASTER BOARD - RANKS {first_rank}-{last_rank}", styles["page_title"]))
    story.append(paragraph("Cross out every drafted player. When your slot row collapses, take the highest uncrossed player who fits your roster checkpoint. ADP controls timing; VOR controls value.", styles["small_subtitle"]))
    story.append(Spacer(1, 0.08 * inch))

    widths = [0.3 * inch, 2.15 * inch, 0.45 * inch, 0.42 * inch, 0.52 * inch, 0.48 * inch]
    left_table = Table(board_half(left, styles), colWidths=widths, repeatRows=1)
    right_table = Table(board_half(right, styles), colWidths=widths, repeatRows=1)
    shared_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("GRID", (0, 0), (-1, -1), 0.35, GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_GRAY]),
            ("TOPPADDING", (0, 1), (-1, -1), 3.2),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3.2),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]
    )
    left_table.setStyle(shared_style)
    right_table.setStyle(shared_style)
    wrapper = Table([[left_table, right_table]], colWidths=[5.2 * inch, 5.2 * inch])
    wrapper.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
    story.append(wrapper)
    story.append(Spacer(1, 0.08 * inch))
    story.append(paragraph("* ESPN status flag at generation time - verify injury/role news immediately before drafting. Negative VOR is normal later; prioritize contingent upside and opportunity.", styles["note"]))
    if page_no == 1:
        story.append(PageBreak())


def build(output: Path = OUTPUT) -> Path:
    if not STRATEGY_DIR.exists():
        raise FileNotFoundError("Run `py -m fantasydraft.strategy` first")
    slot_rows = {
        slot: parse_slot(STRATEGY_DIR / "slots" / f"SLOT_{slot:02d}.md")
        for slot in range(1, 11)
    }
    board_rows = parse_board(STRATEGY_DIR / "MASTER_BOARD.md")

    styles = getSampleStyleSheet()
    custom = {
        "hero": ParagraphStyle("hero", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=25, leading=28, textColor=NAVY, alignment=TA_CENTER, spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=11, leading=13, textColor=MUTED, alignment=TA_CENTER),
        "page_title": ParagraphStyle("page_title", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=18, textColor=NAVY, alignment=TA_LEFT, spaceAfter=2),
        "small_subtitle": ParagraphStyle("small_subtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=7.8, leading=9.2, textColor=MUTED),
        "number": ParagraphStyle("number", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=19, leading=20, textColor=WHITE, alignment=TA_CENTER),
        "box_title": ParagraphStyle("box_title", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=11, textColor=NAVY),
        "box_body": ParagraphStyle("box_body", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=9.4, textColor=colors.HexColor("#29364D")),
        "table_head": ParagraphStyle("table_head", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=6.8, leading=7.5, textColor=WHITE, alignment=TA_CENTER),
        "player": ParagraphStyle("player", parent=styles["Normal"], fontName="Helvetica", fontSize=6.6, leading=7.6, textColor=colors.black),
        "board_player": ParagraphStyle("board_player", parent=styles["Normal"], fontName="Helvetica", fontSize=7.2, leading=8.4, textColor=colors.black),
        "center": ParagraphStyle("center", parent=styles["Normal"], fontName="Helvetica", fontSize=7, leading=8, alignment=TA_CENTER),
        "roster": ParagraphStyle("roster", parent=styles["Normal"], fontName="Helvetica", fontSize=5.7, leading=6.6, textColor=MUTED, alignment=TA_CENTER),
        "callout": ParagraphStyle("callout", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=NAVY, backColor=PALE_ORANGE, borderColor=colors.HexColor("#E4B96B"), borderWidth=0.6, borderPadding=7),
        "callout_small": ParagraphStyle("callout_small", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=7.2, leading=8.5, textColor=NAVY, backColor=PALE_ORANGE, borderColor=colors.HexColor("#E4B96B"), borderWidth=0.5, borderPadding=4),
        "note": ParagraphStyle("note", parent=styles["Normal"], fontName="Helvetica-Oblique", fontSize=6.8, leading=8, textColor=MUTED),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output),
        pagesize=landscape(letter),
        leftMargin=0.2 * inch,
        rightMargin=0.2 * inch,
        topMargin=0.25 * inch,
        bottomMargin=0.34 * inch,
        title="2026 FantasyDraft Printable Cheat Sheet",
        author="FantasyDraft",
    )
    story: list = []
    cover_page(story, custom)
    for slot, rows in slot_rows.items():
        slot_page(story, slot, rows, custom)
    board_page(story, 1, board_rows, custom)
    board_page(story, 2, board_rows, custom)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output


def main() -> int:
    output = build()
    print(f"Created {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
