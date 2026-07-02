from io import BytesIO
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def export_project_pdf(data: dict[str, Any]) -> bytes:
    """Generates a professional PDF report containing building specs, apartment lists,

    and facade sun exposure analysis against Polish building code (WT).
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()

    # Custom styles to maintain polished aesthetics
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1e3a8a"),
        spaceAfter=12,
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
        spaceAfter=15,
    )

    h2_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=12,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "BodyTextCustom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
    )

    body_bold = ParagraphStyle("BodyTextBold", parent=body_style, fontName="Helvetica-Bold")

    story = []

    # 1. Header Block
    story.append(
        Paragraph(
            f"RAPORT NASŁONECZNIENIA I WALIDACJI: {data.get('project_name', 'Projekt DOMKO')}",
            title_style,
        )
    )

    gps_info = f"Lokalizacja: {data.get('latitude', 52.2297):.4f}°N, {data.get('longitude', 21.0122):.4f}°E | Data analizy: {data.get('analysis_date', '21 marca (równonoc)')}"
    required_info = f"Wymagane nasłonecznienie: {data.get('required_hours', 3.0):.1f}h"
    story.append(Paragraph(f"{gps_info} | {required_info}", subtitle_style))

    story.append(Spacer(1, 5))

    # 2. Project Metrics Summary
    story.append(Paragraph("Podsumowanie projektu i zgodności WT", h2_style))
    score = data.get("score", 0)
    score_color = "#15803d" if score >= 90 else "#b45309" if score >= 60 else "#b91c1c"

    summary_data = [
        [
            Paragraph("<b>Wynik końcowy:</b>", body_style),
            Paragraph(f"<font color='{score_color}'><b>{score}/100</b></font>", body_bold),
            Paragraph("<b>Powierzchnia obrysu:</b>", body_style),
            Paragraph(f"{data.get('footprint_area_m2', 0.0):.1f} m²", body_style),
        ],
        [
            Paragraph("<b>Powierzchnia użytkowa:</b>", body_style),
            Paragraph(f"{data.get('usable_area_m2', 0.0):.1f} m²", body_style),
            Paragraph("<b>Powierzchnia komunikacji:</b>", body_style),
            Paragraph(f"{data.get('circulation_area_m2', 0.0):.1f} m²", body_style),
        ],
    ]
    summary_table = Table(summary_data, colWidths=[4.5 * cm, 4 * cm, 4.5 * cm, 4 * cm])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ]
        )
    )
    story.append(summary_table)

    story.append(Spacer(1, 10))

    # 3. Apartments list
    story.append(Paragraph("Wykaz lokali mieszkalnych", h2_style))

    apt_rows = [
        [
            Paragraph("<b>Lp.</b>", body_bold),
            Paragraph("<b>ID lokalu</b>", body_bold),
            Paragraph("<b>Typ</b>", body_bold),
            Paragraph("<b>Powierzchnia m²</b>", body_bold),
            Paragraph("<b>Szerokość min.</b>", body_bold),
            Paragraph("<b>Status WT</b>", body_bold),
        ]
    ]

    apts = data.get("apartments", [])
    for idx, apt in enumerate(apts):
        status_text = (
            "<font color='#16a34a'><b>Spełnia §94</b></font>"
            if apt.get("passed", True)
            else "<font color='#dc2626'><b>Błąd §94</b></font>"
        )
        apt_rows.append(
            [
                Paragraph(str(idx + 1), body_style),
                Paragraph(apt.get("apartment_id", ""), body_style),
                Paragraph(apt.get("type", ""), body_style),
                Paragraph(f"{apt.get('area_m2', 0.0):.1f} m²", body_style),
                Paragraph(f"{apt.get('min_width_m', 0.0):.2f} m", body_style),
                Paragraph(status_text, body_style),
            ]
        )

    apts_table = Table(apt_rows, colWidths=[1.2 * cm, 3.2 * cm, 2.3 * cm, 3.8 * cm, 3.8 * cm, 3.7 * cm])
    apts_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("PADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(apts_table)

    story.append(Spacer(1, 10))

    # 4. Facades analysis
    facades = data.get("facades", [])
    if facades:
        story.append(Paragraph("Analiza nasłonecznienia elewacji lokali (§13 WT)", h2_style))

        facade_rows = [
            [
                Paragraph("<b>Lokal</b>", body_bold),
                Paragraph("<b>Orientacja</b>", body_bold),
                Paragraph("<b>Azymut</b>", body_bold),
                Paragraph("<b>Długość elewacji</b>", body_bold),
                Paragraph("<b>Godziny słońca</b>", body_bold),
                Paragraph("<b>Zgodność §13</b>", body_bold),
            ]
        ]

        for f in facades:
            meets_text = (
                "<font color='#16a34a'><b>Spełnia</b></font>"
                if f.get("meets_wt", True)
                else "<font color='#dc2626'><b>Brak słońca</b></font>"
            )
            facade_rows.append(
                [
                    Paragraph(f.get("apartment_id", ""), body_style),
                    Paragraph(f.get("orientation", ""), body_style),
                    Paragraph(f"{f.get('azimuth_deg', 0.0):.1f}°", body_style),
                    Paragraph(f"{f.get('length_m', 0.0):.1f} m", body_style),
                    Paragraph(f"{f.get('hours_total', 0.0):.2f} h", body_style),
                    Paragraph(meets_text, body_style),
                ]
            )

        facades_table = Table(
            facade_rows, colWidths=[3.2 * cm, 2.3 * cm, 1.8 * cm, 3.8 * cm, 3.8 * cm, 3.1 * cm]
        )
        facades_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("PADDING", (0, 0), (-1, -1), 5),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(facades_table)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
