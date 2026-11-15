"""Dependency-free PDF renderer for the annual astronomy calendar."""

from __future__ import annotations

import calendar
from datetime import datetime


PAGE_W, PAGE_H = 842, 595  # A4 landscape, points


def _pdf_text(value: object) -> str:
    text = str(value).encode("cp1252", errors="replace").decode("cp1252")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _text(x: float, y: float, value: object, size: int = 8, color: tuple[float, float, float] = (.20, .28, .34), bold: bool = False) -> str:
    r, g, b = color
    font = "F2" if bold else "F1"
    return f"{r:.3f} {g:.3f} {b:.3f} rg BT /{font} {size} Tf {x:.2f} {y:.2f} Td ({_pdf_text(value)}) Tj ET\n"


def _rect(x: float, y: float, w: float, h: float, fill: tuple[float, float, float] | None = None, stroke: tuple[float, float, float] = (.84,.88,.90)) -> str:
    ops = ""
    if fill:
        ops += f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg\n"
    ops += f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG .5 w {x:.2f} {y:.2f} {w:.2f} {h:.2f} re " + ("B\n" if fill else "S\n")
    return ops


def annual_calendar_pdf(year: int, events: list[dict[str, object]], timezone_name: str) -> bytes:
    """Render a month per page using only the Python standard library."""
    by_day: dict[str, list[dict[str, object]]] = {}
    for event in events:
        by_day.setdefault(str(event["exact_time_local"])[:10], []).append(event)
    pages: list[bytes] = []
    for month in range(1, 13):
        content = _text(38, PAGE_H-38, f"{calendar.month_name[month]} {year}", 20, (.09,.23,.33), True)
        content += _text(39, PAGE_H-55, f"Astro Market Analyzer  |  Tropical geocentric aspects  |  Times: {timezone_name}  |  Research reference only", 8, (.43,.49,.53))
        x0, y_top, grid_w, header_h = 38, PAGE_H-78, PAGE_W-76, 22
        col_w = grid_w / 7
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
        row_h = min(71, (y_top-35-header_h) / len(weeks))
        for col, weekday in enumerate(("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")):
            x = x0 + col*col_w
            content += _rect(x, y_top-header_h, col_w, header_h, (.09,.23,.33), (.09,.23,.33))
            content += _text(x+7, y_top-15, weekday, 8, (1,1,1), True)
        for wi, week in enumerate(weeks):
            row_top = y_top-header_h-wi*row_h
            for di, day in enumerate(week):
                x = x0 + di*col_w
                y = row_top-row_h
                fill = (.97,.98,.985) if di >= 5 else (1,1,1)
                content += _rect(x, y, col_w, row_h, fill)
                if not day:
                    continue
                content += _text(x+6, row_top-13, day, 9, (.09,.23,.33), True)
                key = f"{year:04d}-{month:02d}-{day:02d}"
                line_y = row_top-26
                for event in by_day.get(key, []):
                    local = str(event["exact_time_local"])
                    try:
                        clock = datetime.fromisoformat(local).strftime("%H:%M")
                    except ValueError:
                        clock = local[11:16]
                    label = f"{clock} {event['planet_1']}-{event['planet_2']} {event['aspect_name']}"
                    # Cell width allows roughly 31 characters at 6.5pt; clip long labels.
                    content += _text(x+6, line_y, label[:34], 6.5, (.28,.36,.42))
                    line_y -= 9
                    if line_y < row_top-row_h+4:
                        content += _text(x+6, line_y, "...", 6, (.55,.59,.62))
                        break
        content += _text(39, 20, f"{year} annual planetary aspect calendar  |  Calculated event timestamps; no market direction claims", 7, (.48,.54,.58))
        pages.append(content.encode("cp1252", errors="replace"))
    return _assemble_pdf(pages)


def research_detail_pdf(title: str, sections: list[tuple[str, list[str]]]) -> bytes:
    """Create a paginated plain-text research report with sourced notes."""
    pages: list[bytes] = []
    content = _text(38, PAGE_H-42, title[:90], 17, (.09,.23,.33), True)
    y = PAGE_H-68
    for heading, lines in sections:
        if y < 55:
            pages.append(content.encode("cp1252", errors="replace")); content = ""; y = PAGE_H-42
        content += _text(40, y, heading[:110], 10, (.13,.37,.43), True); y -= 18
        for raw in lines:
            line = str(raw)
            chunks = [line[i:i+105] for i in range(0, max(1, len(line)), 105)]
            for chunk in chunks:
                if y < 38:
                    pages.append(content.encode("cp1252", errors="replace")); content = ""; y = PAGE_H-38
                content += _text(48, y, chunk, 8, (.24,.31,.36)); y -= 12
        y -= 9
    if content:
        pages.append(content.encode("cp1252", errors="replace"))
    return _assemble_pdf(pages or [_text(38, PAGE_H-42, title, 17, (.09,.23,.33), True).encode()])


def _assemble_pdf(page_contents: list[bytes]) -> bytes:
    objects: list[bytes] = [b""]
    def add(data: bytes) -> int:
        objects.append(data)
        return len(objects)-1
    catalog_id = add(b"")
    pages_id = add(b"")
    font_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    page_ids = []
    for data in page_contents:
        stream_id = add(b"<< /Length " + str(len(data)).encode() + b" >>\nstream\n" + data + b"\nendstream")
        page_id = add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] /Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> >> /Contents {stream_id} 0 R >>".encode())
        page_ids.append(page_id)
    objects[catalog_id] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    kids = " ".join(f"{item} 0 R" for item in page_ids)
    objects[pages_id] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects[1:], 1):
        offsets.append(len(result))
        result += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(result)
    result += f"xref\n0 {len(objects)}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        result += f"{offset:010d} 00000 n \n".encode()
    result += f"trailer\n<< /Size {len(objects)} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(result)
