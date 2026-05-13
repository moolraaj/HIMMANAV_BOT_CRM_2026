# services/pdf_generator.py
# Travel Package PDF Generator — Awaara Banjara style
# Generates a beautiful multi-page PDF with cover, booking summary,
# itinerary (one page per day with photo), inclusions, exclusions.

import os
import io
import re
import math
import requests
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)
from reportlab.platypus.flowables import Flowable
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from PIL import Image as PILImage

logger = logging.getLogger(__name__)

# ── Brand colours ─────────────────────────────────────────────────────────────
BRAND_ORANGE   = colors.HexColor("#F5A623")
BRAND_DARK     = colors.HexColor("#1A1A2E")
BRAND_WHITE    = colors.white
BRAND_LIGHT_BG = colors.HexColor("#F8F6F0")
ACCENT_GREEN   = colors.HexColor("#2ECC71")
TEXT_DARK      = colors.HexColor("#2C2C2C")
TEXT_MUTED     = colors.HexColor("#666666")
SECTION_BG     = colors.HexColor("#1A1A2E")

PAGE_W, PAGE_H = A4   # 595 × 842 pts
MARGIN         = 18 * mm


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_image(url: str, max_w: int = 800) -> Optional[io.BytesIO]:
    """Download image from URL and return BytesIO, or None on failure."""
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; TravelBot/1.0)"
        })
        if resp.status_code == 200:
            buf = io.BytesIO(resp.content)
            img = PILImage.open(buf)
            img.verify()
            buf.seek(0)
            return buf
    except Exception as e:
        logger.warning(f"Image fetch failed {url}: {e}")
    return None


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _fp(price) -> str:
    """Format price to Rs. X,XXX"""
    try:
        return f"Rs. {float(str(price).replace(',', '')):,.0f}"
    except (ValueError, TypeError):
        return f"Rs. {price}"


# ══════════════════════════════════════════════════════════════════════════════
# COVER PAGE — drawn directly on canvas via onFirstPage callback
# (NOT a Flowable — this avoids the "too large" frame error)
# ══════════════════════════════════════════════════════════════════════════════

def _draw_cover(canv, doc, img_buf, pkg_name, dest, nights, guests):
    """Draw the cover page directly onto the canvas — bypasses frame sizing."""
    c = canv

    # ── Background image ──
    if img_buf:
        try:
            img_buf.seek(0)
            ir = ImageReader(img_buf)
            c.drawImage(ir, 0, 0, PAGE_W, PAGE_H,
                        preserveAspectRatio=False, mask="auto")
        except Exception:
            c.setFillColor(BRAND_DARK)
            c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    else:
        c.setFillColor(BRAND_DARK)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # ── Dark overlay bottom 42% ──
    c.setFillColorRGB(0.1, 0.1, 0.14, 0.75)
    c.rect(0, 0, PAGE_W, PAGE_H * 0.42, fill=1, stroke=0)

    # ── Orange accent bar ──
    c.setFillColor(BRAND_ORANGE)
    c.rect(0, PAGE_H * 0.42, PAGE_W, 4, fill=1, stroke=0)

    # ── Package name ──
    c.setFillColor(BRAND_WHITE)
    c.setFont("Helvetica-Bold", 28)
    name = pkg_name[:50]
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.37, name)

    # ── Subtitle ──
    c.setFillColor(BRAND_ORANGE)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.33,
                        f"{dest}  ·  {nights} Nights  ·  {guests} Guests")

    # ── Bottom pills ──
    pill_data = [
        ("Destination", dest),
        ("Duration",    f"{nights}N"),
        ("Guests",      f"{guests} pax"),
    ]
    pill_w, pill_h, gap = 120, 28, 10
    total_w = len(pill_data) * pill_w + (len(pill_data) - 1) * gap
    start_x = (PAGE_W - total_w) / 2
    py = PAGE_H * 0.07

    for label, value in pill_data:
        c.setFillColor(BRAND_ORANGE)
        c.roundRect(start_x, py, pill_w, pill_h, 6, fill=1, stroke=0)
        c.setFillColor(BRAND_DARK)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(start_x + pill_w / 2, py + 14, label.upper())
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(start_x + pill_w / 2, py + 4, value)
        start_x += pill_w + gap

    # ── Footer ──
    c.setFillColor(BRAND_ORANGE)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(PAGE_W / 2, 12,
                        "TRAVEL PACKAGE  ·  POWERED BY YOUR TRAVEL ASSISTANT")


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM FLOWABLES
# ══════════════════════════════════════════════════════════════════════════════

class SectionBanner(Flowable):
    """Dark banner with white title."""

    def __init__(self, title, subtitle=""):
        super().__init__()
        self.title    = title
        self.subtitle = subtitle
        self.width    = PAGE_W - 2 * MARGIN
        self.height   = 44 if subtitle else 34

    def draw(self):
        c = self.canv
        c.setFillColor(SECTION_BG)
        c.roundRect(0, 0, self.width, self.height, 6, fill=1, stroke=0)
        c.setFillColor(BRAND_ORANGE)
        c.roundRect(0, 0, 5, self.height, 3, fill=1, stroke=0)
        c.setFillColor(BRAND_WHITE)
        c.setFont("Helvetica-Bold", 14)
        ty = self.height - 22 if self.subtitle else (self.height - 14) / 2
        c.drawString(16, ty, self.title.upper())
        if self.subtitle:
            c.setFillColor(BRAND_ORANGE)
            c.setFont("Helvetica", 10)
            c.drawString(16, 8, self.subtitle)


class DayCard(Flowable):
    """One day of the itinerary: image + badge + title + location + description."""

    def __init__(self, day_num, title, overview, location, img_buf, page_w):
        super().__init__()
        self.day_num  = day_num
        self.title    = title
        self.overview = _strip_html(overview)
        self.location = location
        self.img_buf  = img_buf
        self.page_w   = page_w
        self.width    = page_w - 2 * MARGIN
        self.height   = 250

    def draw(self):
        c     = self.canv
        W     = self.width
        img_h = 140

        # Card background
        c.setFillColor(BRAND_LIGHT_BG)
        c.roundRect(0, 0, W, self.height, 8, fill=1, stroke=0)

        # Image
        if self.img_buf:
            try:
                self.img_buf.seek(0)
                ir = ImageReader(self.img_buf)
                c.saveState()
                p = c.beginPath()
                p.roundRect(0, self.height - img_h, W, img_h, 8)
                c.clipPath(p, stroke=0)
                c.drawImage(ir, 0, self.height - img_h, W, img_h,
                            preserveAspectRatio=False, mask="auto")
                c.restoreState()
            except Exception:
                c.setFillColor(BRAND_DARK)
                c.roundRect(0, self.height - img_h, W, img_h, 8, fill=1, stroke=0)
        else:
            c.setFillColor(BRAND_DARK)
            c.roundRect(0, self.height - img_h, W, img_h, 8, fill=1, stroke=0)
            c.setFillColor(TEXT_MUTED)
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(W / 2, self.height - img_h + img_h / 2 - 5,
                                "No Image Available")

        # Day badge
        badge_x, badge_y = 10, self.height - img_h + 8
        c.setFillColor(BRAND_ORANGE)
        c.roundRect(badge_x, badge_y, 56, 22, 4, fill=1, stroke=0)
        c.setFillColor(BRAND_DARK)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(badge_x + 28, badge_y + 7, f"DAY {self.day_num}")

        # Title
        text_y = self.height - img_h - 6
        c.setFillColor(TEXT_DARK)
        c.setFont("Helvetica-Bold", 11)
        title = self.title[:70] + ("…" if len(self.title) > 70 else "")
        c.drawString(10, text_y - 12, title)

        # Location pill
        if self.location:
            loc_txt = f"  {self.location}"
            c.setFont("Helvetica", 9)
            tw = c.stringWidth(loc_txt, "Helvetica", 9) + 10
            c.setFillColor(BRAND_ORANGE)
            c.roundRect(10, text_y - 30, tw, 16, 4, fill=1, stroke=0)
            c.setFillColor(BRAND_DARK)
            c.drawString(15, text_y - 24, loc_txt)

        # Overview text
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 8.5)
        overview = self.overview[:220] + ("…" if len(self.overview) > 220 else "")
        words = overview.split()
        lines, line = [], ""
        max_line_w = W - 20
        for w in words:
            test = (line + " " + w).strip()
            if c.stringWidth(test, "Helvetica", 8.5) < max_line_w:
                line = test
            else:
                if line:
                    lines.append(line)
                line = w
        if line:
            lines.append(line)
        oy = text_y - 44
        for ln in lines[:4]:
            if oy < 6:
                break
            c.drawString(10, oy, ln)
            oy -= 12


# ══════════════════════════════════════════════════════════════════════════════
# STYLES
# ══════════════════════════════════════════════════════════════════════════════

def _styles():
    return {
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold",
                             fontSize=20, textColor=BRAND_DARK,
                             spaceAfter=6, leading=26),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold",
                             fontSize=14, textColor=BRAND_DARK,
                             spaceAfter=4, leading=18),
        "body": ParagraphStyle("body", fontName="Helvetica",
                               fontSize=10, textColor=TEXT_DARK,
                               spaceAfter=4, leading=15),
        "muted": ParagraphStyle("muted", fontName="Helvetica",
                                fontSize=9, textColor=TEXT_MUTED,
                                spaceAfter=3, leading=13),
        "label": ParagraphStyle("label", fontName="Helvetica-Bold",
                                fontSize=9, textColor=BRAND_ORANGE,
                                spaceAfter=2),
        "value": ParagraphStyle("value", fontName="Helvetica",
                                fontSize=10, textColor=TEXT_DARK,
                                spaceAfter=4),
        "bullet": ParagraphStyle("bullet", fontName="Helvetica",
                                 fontSize=10, textColor=TEXT_DARK,
                                 leftIndent=14, spaceAfter=3,
                                 bulletIndent=4, leading=14),
        "center": ParagraphStyle("center", fontName="Helvetica",
                                 fontSize=10, alignment=TA_CENTER,
                                 textColor=TEXT_MUTED),
        "total": ParagraphStyle("total", fontName="Helvetica-Bold",
                                fontSize=14, textColor=BRAND_WHITE,
                                alignment=TA_CENTER),
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def generate_package_pdf(
    package_data: Dict,
    context: Dict,
    output_path: str,
) -> str:
    """
    Generate a beautiful travel package PDF.

    Args:
        package_data : The selected_package dict from context
        context      : Full booking context (guests, dates, price_details, etc.)
        output_path  : Where to save the PDF

    Returns:
        output_path on success, raises on failure
    """
    os.makedirs(
        os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
        exist_ok=True
    )

    S = _styles()

    # ── Extract data ──────────────────────────────────────────────────────────
    pkg_name     = package_data.get("package_name") or package_data.get("title", "Travel Package")
    pkg_image    = package_data.get("package_image", "")
    itinerary    = package_data.get("itinerary", [])
    inclusions   = package_data.get("inclusion", [])
    exclusions   = package_data.get("exclusion", [])
    activities   = package_data.get("activities", [])
    locations    = package_data.get("locations", [])

    pd            = context.get("pkg_price_details", {})
    guests        = pd.get("guests", context.get("guests", 1))
    nights        = pd.get("nights", len(itinerary))
    check_in      = context.get("check_in", "")
    check_out     = context.get("check_out", "")
    dest          = context.get("destination", ", ".join(locations[:2]))
    hotel_cat     = context.get("hotel_category", "")
    room_cat      = context.get("room_category", "")
    vehicle_name  = pd.get("vehicle_name", "")
    total_hotel   = pd.get("total_hotel_price", 0)
    total_map     = pd.get("total_map_price", 0)
    vehicle_price = pd.get("vehicle_price", 0)
    pkg_margin    = pd.get("package_margin", 0)
    total_price   = pd.get("total_price", 0)

    # ── Fetch cover image ─────────────────────────────────────────────────────
    cover_buf = _fetch_image(pkg_image)

    # ── Build story (page 2 onwards — cover is drawn via callback) ────────────
    story = []

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 2: BOOKING SUMMARY
    # ════════════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 6))
    story.append(SectionBanner("Booking Summary", pkg_name))
    story.append(Spacer(1, 10))

    def _info_row(label, value):
        return [
            Paragraph(label, S["label"]),
            Paragraph(str(value) if value else "—", S["value"]),
        ]

    summary_rows = [
        _info_row("PACKAGE",     pkg_name),
        _info_row("DESTINATION", dest),
        _info_row("CHECK-IN",    check_in),
        _info_row("CHECK-OUT",   check_out),
        _info_row("NIGHTS",      str(nights)),
        _info_row("GUESTS",      str(guests)),
        _info_row("HOTEL CAT.",  hotel_cat),
        _info_row("ROOM CAT.",   room_cat),
        _info_row("VEHICLE",     vehicle_name or "—"),
        _info_row("MEAL PLAN",   "MAP (Breakfast + Dinner)"),
    ]

    col_w = PAGE_W - 2 * MARGIN
    t = Table(summary_rows, colWidths=[col_w * 0.32, col_w * 0.68])
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1),
         [BRAND_LIGHT_BG, colors.HexColor("#EEEAE0")]),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    # ── Price breakdown ───────────────────────────────────────────────────────
    story.append(SectionBanner("Price Breakdown"))
    story.append(Spacer(1, 8))

    price_rows = []
    price_rows.append([
        Paragraph(f"Hotel Cost ({nights} nights)", S["body"]),
        Paragraph(_fp(total_hotel), S["body"]),
    ])
    price_rows.append([
        Paragraph("MAP Meals (Breakfast + Dinner)", S["body"]),
        Paragraph(_fp(total_map), S["body"]),
    ])
    if vehicle_price > 0:
        price_rows.append([
            Paragraph(f"Vehicle — {vehicle_name}", S["body"]),
            Paragraph(_fp(vehicle_price), S["body"]),
        ])
    if pkg_margin > 0:
        price_rows.append([
            Paragraph("Service Charge", S["body"]),
            Paragraph(_fp(pkg_margin), S["body"]),
        ])
    price_rows.append([
        Paragraph("<b>GRAND TOTAL</b>", ParagraphStyle(
            "gt", fontName="Helvetica-Bold", fontSize=13,
            textColor=BRAND_WHITE)),
        Paragraph(f"<b>{_fp(total_price)}</b>", ParagraphStyle(
            "gtv", fontName="Helvetica-Bold", fontSize=13,
            textColor=BRAND_ORANGE, alignment=TA_RIGHT)),
    ])

    row_count = len(price_rows)
    pt = Table(price_rows, colWidths=[col_w * 0.65, col_w * 0.35])
    pt.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, row_count - 2),
         [BRAND_LIGHT_BG, colors.HexColor("#EEEAE0")]),
        ("BACKGROUND",    (0, row_count - 1), (-1, row_count - 1), SECTION_BG),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
    ]))
    story.append(pt)
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # PAGES 3+: ITINERARY
    # ════════════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 6))
    story.append(SectionBanner("Itinerary", f"{nights} Nights · {dest}"))
    story.append(Spacer(1, 10))

    for i, day in enumerate(itinerary):
        day_num  = i + 1
        title    = day.get("title", f"Day {day_num}")
        overview = day.get("overview", "")
        location = day.get("stay_location") or day.get("location", dest)
        gallery  = day.get("gallery", [])

        img_buf = None
        for img_url in gallery:
            img_buf = _fetch_image(img_url)
            if img_buf:
                break

        story.append(KeepTogether([
            DayCard(day_num, title, overview, location, img_buf, PAGE_W),
            Spacer(1, 10),
        ]))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # INCLUSIONS & EXCLUSIONS
    # ════════════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 6))
    story.append(SectionBanner("What's Included"))
    story.append(Spacer(1, 8))

    if inclusions:
        inc_rows = []
        for item in inclusions:
            clean = _strip_html(item)
            if clean:
                inc_rows.append([
                    Paragraph("✓", ParagraphStyle(
                        "tick", fontName="Helvetica-Bold", fontSize=11,
                        textColor=ACCENT_GREEN)),
                    Paragraph(clean, S["body"]),
                ])
        inc_t = Table(inc_rows, colWidths=[18, col_w - 18])
        inc_t.setStyle(TableStyle([
            ("ROWBACKGROUNDS", (0, 0), (-1, -1),
             [BRAND_LIGHT_BG, colors.HexColor("#EEEAE0")]),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(inc_t)
    else:
        story.append(Paragraph("Inclusions not specified.", S["muted"]))

    story.append(Spacer(1, 14))

    story.append(SectionBanner("What's Not Included"))
    story.append(Spacer(1, 8))

    if exclusions:
        exc_rows = []
        for item in exclusions:
            clean = _strip_html(item)
            if clean:
                exc_rows.append([
                    Paragraph("✗", ParagraphStyle(
                        "cross", fontName="Helvetica-Bold", fontSize=11,
                        textColor=colors.HexColor("#E74C3C"))),
                    Paragraph(clean, S["body"]),
                ])
        exc_t = Table(exc_rows, colWidths=[18, col_w - 18])
        exc_t.setStyle(TableStyle([
            ("ROWBACKGROUNDS", (0, 0), (-1, -1),
             [colors.HexColor("#FEF5F5"), colors.HexColor("#FDEAEA")]),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(exc_t)
    else:
        story.append(Paragraph("Exclusions not specified.", S["muted"]))

    # ── Activities ────────────────────────────────────────────────────────────
    if activities:
        story.append(Spacer(1, 14))
        story.append(SectionBanner("Activities & Experiences"))
        story.append(Spacer(1, 8))
        act_rows = []
        for act in activities:
            act_rows.append([
                Paragraph("★", ParagraphStyle(
                    "star", fontName="Helvetica-Bold", fontSize=11,
                    textColor=BRAND_ORANGE)),
                Paragraph(act, S["body"]),
            ])
        act_t = Table(act_rows, colWidths=[18, col_w - 18])
        act_t.setStyle(TableStyle([
            ("ROWBACKGROUNDS", (0, 0), (-1, -1),
             [BRAND_LIGHT_BG, colors.HexColor("#EEEAE0")]),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(act_t)

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # LAST PAGE: THANK YOU
    # ════════════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 60))
    story.append(Paragraph("Thank You For Choosing Us!", ParagraphStyle(
        "ty", fontName="Helvetica-Bold", fontSize=22,
        textColor=BRAND_DARK, alignment=TA_CENTER, spaceAfter=10)))

    story.append(Paragraph(
        f"Your journey to <b>{dest}</b> awaits. We have prepared every detail "
        f"to make your {nights}-night trip unforgettable.",
        ParagraphStyle("ty2", fontName="Helvetica", fontSize=11,
                       textColor=TEXT_MUTED, alignment=TA_CENTER,
                       spaceAfter=20, leading=16)
    ))

    fin_rows = [
        [Paragraph("TOTAL PACKAGE COST", ParagraphStyle(
            "fh", fontName="Helvetica-Bold", fontSize=11,
            textColor=BRAND_ORANGE, alignment=TA_CENTER))],
        [Paragraph(_fp(total_price), ParagraphStyle(
            "fv", fontName="Helvetica-Bold", fontSize=22,
            textColor=BRAND_WHITE, alignment=TA_CENTER))],
        [Paragraph(f"{guests} Guests  ·  {nights} Nights", ParagraphStyle(
            "fs", fontName="Helvetica", fontSize=10,
            textColor=colors.HexColor("#AAAAAA"), alignment=TA_CENTER))],
    ]
    fin_t = Table(fin_rows, colWidths=[col_w])
    fin_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), SECTION_BG),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
    ]))
    story.append(fin_t)
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", color=BRAND_ORANGE, thickness=1.5))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"This PDF was generated by your Travel Assistant  ·  "
        f"Generated on {datetime.now().strftime('%d %b %Y %I:%M %p')}",
        ParagraphStyle("footer", fontName="Helvetica", fontSize=8,
                       textColor=TEXT_MUTED, alignment=TA_CENTER)
    ))

    # ── Page callbacks ────────────────────────────────────────────────────────
    def _on_first_page(canv, doc):
        """Cover page — drawn directly, no frame involved."""
        _draw_cover(canv, doc, cover_buf, pkg_name, dest, nights, guests)

    def _on_later_pages(canv, doc):
        """Page number + orange line on every page after cover."""
        canv.saveState()
        canv.setFillColor(TEXT_MUTED)
        canv.setFont("Helvetica", 8)
        canv.drawRightString(PAGE_W - MARGIN, 10, f"Page {doc.page}")
        canv.setStrokeColor(BRAND_ORANGE)
        canv.setLineWidth(1.5)
        canv.line(MARGIN, 18, PAGE_W - MARGIN, 18)
        canv.restoreState()

    # ── Build PDF ─────────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=26,
        title=pkg_name,
        author="Travel Assistant",
    )
    doc.build(story, onFirstPage=_on_first_page, onLaterPages=_on_later_pages)
    logger.info(f"✅ PDF generated: {output_path}")
    return output_path


# ══════════════════════════════════════════════════════════════════════════════
# WHATSAPP SEND HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def download_pdf_from_url(pdf_url: str, package_name: str) -> Optional[str]:
    """Download PDF from URL and save locally."""
    try:
        os.makedirs("generated_pdfs", exist_ok=True)
        pkg_clean = "".join(
            c for c in package_name[:30] if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"generated_pdfs/{pkg_clean}_{ts}.pdf"
        resp     = requests.get(pdf_url, timeout=30)
        if resp.status_code == 200:
            with open(filename, "wb") as f:
                f.write(resp.content)
            return filename
        logger.error(f"PDF download failed: {resp.status_code}")
        return None
    except Exception as e:
        logger.error(f"PDF download error: {e}")
        return None


def upload_pdf_to_whatsapp(pdf_path: str, sender_phone_number_id: str) -> Optional[str]:
    """Upload PDF to WhatsApp Cloud API and return media_id."""
    from database.database import get_whatsapp_config, get_all_active_whatsapp_numbers
    ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
    try:
        sender_config = get_whatsapp_config(sender_phone_number_id)
        if not sender_config:
            active = get_all_active_whatsapp_numbers()
            if active:
                sender_config = get_whatsapp_config(active[0]["phone_number_id"])
            if not sender_config:
                return None

        url = f"https://graph.facebook.com/v18.0/{sender_config['phone_number_id']}/media"
        with open(pdf_path, "rb") as f:
            files = {
                "file": (os.path.basename(pdf_path), f, "application/pdf"),
                "messaging_product": (None, "whatsapp"),
                "type": (None, "application/pdf"),
            }
            headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
            resp = requests.post(url, headers=headers, files=files)
        if resp.status_code == 200:
            return resp.json().get("id")
        logger.error(f"Upload failed: {resp.status_code} {resp.text}")
        return None
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return None


def send_pdf_via_whatsapp(
    to_phone: str,
    pdf_path: str,
    caption: str = "",
    sender_phone_number_id: str = None,
) -> Optional[dict]:
    """Upload and send a PDF to a WhatsApp user."""
    from database.database import get_whatsapp_config, get_all_active_whatsapp_numbers
    ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
    try:
        if not sender_phone_number_id:
            active = get_all_active_whatsapp_numbers()
            if active:
                sender_phone_number_id = active[0]["phone_number_id"]
            else:
                return None

        media_id = upload_pdf_to_whatsapp(pdf_path, sender_phone_number_id)
        if not media_id:
            return None

        sender_config = get_whatsapp_config(sender_phone_number_id)
        if not sender_config:
            return None

        url = f"https://graph.facebook.com/v18.0/{sender_config['phone_number_id']}/messages"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        data = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "document",
            "document": {
                "id": media_id,
                "caption": caption or "📄 Your travel package details",
                "filename": os.path.basename(pdf_path),
            },
        }
        resp = requests.post(url, headers=headers, json=data, timeout=30)
        if resp.status_code == 200:
            logger.info(f"✅ PDF sent to {to_phone}")
            return resp.json()
        logger.error(f"Send failed: {resp.status_code} {resp.text}")
        return None
    except Exception as e:
        logger.error(f"Send PDF error: {e}")
        return None