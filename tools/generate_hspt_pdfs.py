#!/usr/bin/env python3
"""Generate printable HSPT full-length exams from portal JSON files."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


SECTION_SPECS = [
    ("verbal_skills", "Verbal Skills", 60, 20),
    ("quantitative_skills", "Quantitative Skills", 52, 35),
    ("reading_comprehension", "Reading Comprehension", 62, 35),
    ("mathematics", "Mathematics", 64, 45),
    ("language", "Language", 60, 30),
]

BLUE = colors.HexColor("#2457D6")
NAVY = colors.HexColor("#10213D")
PALE_BLUE = colors.HexColor("#EAF0FF")
LIGHT_GRAY = colors.HexColor("#F2F4F7")
MID_GRAY = colors.HexColor("#667085")


def register_fonts() -> tuple[str, str]:
    candidates = [
        (
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ),
        (
            Path("/Library/Fonts/Arial.ttf"),
            Path("/Library/Fonts/Arial Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
        (
            Path(__import__("reportlab").__file__).parent / "fonts" / "Vera.ttf",
            Path(__import__("reportlab").__file__).parent / "fonts" / "VeraBd.ttf",
        ),
    ]
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            pdfmetrics.registerFont(TTFont("HSPTRegular", str(regular)))
            pdfmetrics.registerFont(TTFont("HSPTBold", str(bold)))
            return "HSPTRegular", "HSPTBold"
    raise RuntimeError("No suitable Unicode TrueType font was found.")


REGULAR_FONT, BOLD_FONT = register_fonts()


def safe(value: object) -> str:
    return html.escape(str(value or ""), quote=False).replace("\n", "<br/>")


def choices(question: dict) -> dict[str, str]:
    result = question.get("choices", {})
    if not isinstance(result, dict) or set(result) != set("ABCD"):
        raise ValueError(f"{question.get('id')}: invalid choices")
    return result


def make_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "CoverBrand",
            fontName=BOLD_FONT,
            fontSize=24,
            leading=29,
            textColor=BLUE,
            alignment=TA_CENTER,
            spaceAfter=9 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "CoverExam",
            fontName=BOLD_FONT,
            fontSize=24,
            leading=29,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=6 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "CoverSub",
            fontName=REGULAR_FONT,
            fontSize=12,
            leading=17,
            textColor=MID_GRAY,
            alignment=TA_CENTER,
            spaceAfter=7 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "SectionTitle",
            fontName=BOLD_FONT,
            fontSize=20,
            leading=24,
            textColor=NAVY,
            spaceAfter=3 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "SectionMeta",
            fontName=REGULAR_FONT,
            fontSize=9.5,
            leading=13,
            textColor=MID_GRAY,
            spaceAfter=5 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "StimulusLabel",
            fontName=BOLD_FONT,
            fontSize=10.5,
            leading=14,
            textColor=BLUE,
            spaceBefore=3 * mm,
            spaceAfter=1.5 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "StimulusText",
            fontName=REGULAR_FONT,
            fontSize=9.2,
            leading=13.2,
            textColor=colors.HexColor("#202939"),
            leftIndent=4 * mm,
            rightIndent=4 * mm,
            borderColor=colors.HexColor("#D0D5DD"),
            borderWidth=0.7,
            borderPadding=7,
            backColor=colors.HexColor("#FAFAFA"),
            spaceAfter=4 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "Question",
            fontName=BOLD_FONT,
            fontSize=9.6,
            leading=13.4,
            textColor=NAVY,
            spaceBefore=2.6 * mm,
            spaceAfter=1.2 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "Choice",
            fontName=REGULAR_FONT,
            fontSize=9.2,
            leading=12.8,
            leftIndent=5 * mm,
            firstLineIndent=-5 * mm,
            textColor=colors.HexColor("#202939"),
            spaceAfter=0.8 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "Body",
            fontName=REGULAR_FONT,
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#202939"),
            spaceAfter=2.5 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "Answer",
            fontName=REGULAR_FONT,
            fontSize=8.7,
            leading=12.3,
            textColor=colors.HexColor("#202939"),
            spaceAfter=1.2 * mm,
        )
    )
    return styles


STYLES = make_styles()


def load_exam(data_dir: Path, exam_no: int):
    sections = []
    all_questions = []
    for slug, label, expected, minutes in SECTION_SPECS:
        path = data_dir / f"hspt_{slug}_exam_{exam_no:02d}.json"
        content = json.loads(path.read_text(encoding="utf-8"))
        questions = content.get("questions", [])
        if len(questions) != expected:
            raise ValueError(f"{path.name}: expected {expected}, found {len(questions)}")
        sections.append((label, expected, minutes, questions))
        all_questions.extend(questions)
    if len(all_questions) != 298:
        raise ValueError(f"Exam {exam_no:02d}: expected 298 questions")
    return sections, all_questions


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D0D5DD"))
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
    canvas.setFont(REGULAR_FONT, 7.5)
    canvas.setFillColor(MID_GRAY)
    canvas.drawString(18 * mm, 9.5 * mm, "HSPT Exam Simulator")
    canvas.drawRightString(A4[0] - 18 * mm, 9.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def cover_story(exam_no: int):
    rows = [["Section", "Questions", "Time"]]
    for _, label, count, minutes in SECTION_SPECS:
        rows.append([label, str(count), f"{minutes} minutes"])
    table = Table(rows, colWidths=[92 * mm, 32 * mm, 38 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
                ("FONTNAME", (0, 1), (-1, -1), REGULAR_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D5DD")),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [
        Spacer(1, 24 * mm),
        Paragraph("HSPT Exam Simulator", STYLES["CoverBrand"]),
        Paragraph(f"Full-Length Practice Exam {exam_no:02d}", STYLES["CoverExam"]),
        Paragraph(
            "Complete printable test with 298 multiple-choice questions, "
            "answer key, and detailed explanations.",
            STYLES["CoverSub"],
        ),
        HRFlowable(width="100%", thickness=1.2, color=BLUE, spaceAfter=8 * mm),
        table,
        Spacer(1, 9 * mm),
        Paragraph("General Directions", STYLES["SectionTitle"]),
        Paragraph(
            "Work through each section within the recommended time. Choose the "
            "best answer for every question. Mark one answer (A-D) for each item. "
            "Use the answer key and explanations only after completing the test.",
            STYLES["Body"],
        ),
        Paragraph(
            "Recommended total testing time: 165 minutes. Calculators should be "
            "used only when permitted by the rules followed for your HSPT preparation.",
            STYLES["Body"],
        ),
        PageBreak(),
    ]


def question_story(question: dict, number: int):
    result = [
        Paragraph(
            f"{number}. {safe(question.get('prompt'))}",
            STYLES["Question"],
        )
    ]
    for letter, text in choices(question).items():
        result.append(Paragraph(f"<b>{letter})</b> {safe(text)}", STYLES["Choice"]))
    result.append(Spacer(1, 1.8 * mm))
    return result


def test_story(sections):
    story = []
    global_number = 0
    for index, (label, count, minutes, questions) in enumerate(sections, start=1):
        if index > 1:
            story.append(PageBreak())
        story.extend(
            [
                Paragraph(f"Section {index}: {safe(label)}", STYLES["SectionTitle"]),
                Paragraph(
                    f"{count} questions | Recommended time: {minutes} minutes",
                    STYLES["SectionMeta"],
                ),
                HRFlowable(width="100%", thickness=0.8, color=BLUE, spaceAfter=3 * mm),
            ]
        )
        shown_stimuli = set()
        for question in questions:
            stimulus_id = question.get("stimulusId")
            if stimulus_id and stimulus_id not in shown_stimuli:
                shown_stimuli.add(stimulus_id)
                title = question.get("stimulusTitle") or "Passage"
                kind = question.get("stimulusType") or "Stimulus"
                story.append(
                    Paragraph(f"{safe(kind)}: {safe(title)}", STYLES["StimulusLabel"])
                )
                story.append(
                    Paragraph(safe(question.get("stimulusText")), STYLES["StimulusText"])
                )
            global_number += 1
            story.append(KeepTogether(question_story(question, global_number)))
    return story


def answer_key_story(sections):
    story = [
        PageBreak(),
        Paragraph("Answer Key", STYLES["SectionTitle"]),
        Paragraph(
            "Question numbers continue across all five sections.",
            STYLES["SectionMeta"],
        ),
    ]
    offset = 0
    for label, _, _, questions in sections:
        story.append(Paragraph(safe(label), STYLES["StimulusLabel"]))
        cells = []
        for local_index, question in enumerate(questions, start=1):
            cells.append(f"{offset + local_index}. {question['correct']}")
        rows = [cells[i : i + 8] for i in range(0, len(cells), 8)]
        if rows and len(rows[-1]) < 8:
            rows[-1].extend([""] * (8 - len(rows[-1])))
        table = Table(rows, colWidths=[20.2 * mm] * 8)
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), REGULAR_FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.3),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.extend([table, Spacer(1, 3 * mm)])
        offset += len(questions)
    return story


def explanation_story(sections):
    story = [PageBreak(), Paragraph("Detailed Explanations", STYLES["SectionTitle"])]
    offset = 0
    for section_index, (label, _, _, questions) in enumerate(sections, start=1):
        if section_index > 1:
            story.append(PageBreak())
        story.append(Paragraph(safe(label), STYLES["SectionTitle"]))
        for local_index, question in enumerate(questions, start=1):
            number = offset + local_index
            correct = question["correct"]
            answer = choices(question)[correct]
            story.append(
                KeepTogether([Paragraph(
                    f"<b>{number}. {safe(question['id'])} - Answer {correct}: "
                    f"{safe(answer)}</b><br/>{safe(question.get('explanation'))}",
                    STYLES["Answer"],
                )])
            )
        offset += len(questions)
    return story


def build_pdf(data_dir: Path, output_dir: Path, exam_no: int) -> Path:
    sections, _ = load_exam(data_dir, exam_no)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"hspt_full_exam_{exam_no:02d}.pdf"
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=19 * mm,
        title=f"HSPT Full-Length Practice Exam {exam_no:02d}",
        author="HSPT Exam Simulator",
        subject="HSPT full-length practice examination",
    )
    story = []
    story.extend(cover_story(exam_no))
    story.extend(test_story(sections))
    story.extend(answer_key_story(sections))
    story.extend(explanation_story(sections))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output


def validate_pdf(path: Path, exam_no: int, data_dir: Path):
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if not reader.pages:
        raise ValueError(f"{path.name}: empty PDF")
    width = float(reader.pages[0].mediabox.width)
    height = float(reader.pages[0].mediabox.height)
    if abs(width - A4[0]) > 1 or abs(height - A4[1]) > 1:
        raise ValueError(f"{path.name}: page size is not A4")
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    expected_ids = []
    for slug, _, _, _ in SECTION_SPECS:
        content = json.loads(
            (data_dir / f"hspt_{slug}_exam_{exam_no:02d}.json").read_text(encoding="utf-8")
        )
        expected_ids.extend(question["id"] for question in content["questions"])
    missing_ids = [qid for qid in expected_ids if qid not in text]
    if missing_ids:
        raise ValueError(f"{path.name}: missing IDs in extracted text: {missing_ids[:5]}")
    for heading in ("Answer Key", "Detailed Explanations"):
        if heading not in text:
            raise ValueError(f"{path.name}: missing {heading}")
    return len(reader.pages), len(expected_ids), width, height


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("packs/hspt/data"))
    parser.add_argument("--output-dir", type=Path, default=Path("packs/hspt/pdf"))
    parser.add_argument("--exams", nargs="+", type=int, default=[5, 6, 7, 8])
    args = parser.parse_args()

    for exam_no in args.exams:
        output = build_pdf(args.data_dir, args.output_dir, exam_no)
        pages, questions, width, height = validate_pdf(output, exam_no, args.data_dir)
        print(
            f"CREATED: {output} | pages={pages} | questions={questions} | "
            f"A4={width:.1f}x{height:.1f}"
        )


if __name__ == "__main__":
    main()
