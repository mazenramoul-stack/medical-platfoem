"""PDF report generator for combined MRI + ECG medical analyses.

Uses reportlab's platypus framework (flowables) plus a custom Canvas to emit
a `Page X of Y` footer. All content is rendered via Paragraph/Table/Image
flowables so it pages correctly without manual coordinate math.
"""

from __future__ import annotations

import datetime
import os
import re
from typing import Optional

from django.conf import settings
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---- visual identity ------------------------------------------------------

PRIMARY = colors.HexColor('#1e40af')     # blue
SECONDARY = colors.HexColor('#374151')   # gray-700
ACCENT = colors.HexColor('#dc2626')      # red-600
LIGHT = colors.HexColor('#f3f4f6')       # gray-100
ALT_ROW = colors.HexColor('#eff6ff')     # blue-50
BORDER = colors.HexColor('#cbd5e1')      # slate-300


# ---- numbered canvas -----------------------------------------------------

class NumberedCanvas(rl_canvas.Canvas):
    """Canvas subclass that buffers pages so we can write 'Page X of Y'."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states = []

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total_pages: int) -> None:
        self.setFont('Helvetica', 8)
        self.setFillColor(SECONDARY)
        self.drawCentredString(LETTER[0] / 2, 0.4 * inch, f'Page {self._pageNumber} of {total_pages}')
        self.drawRightString(LETTER[0] - 0.6 * inch, 0.4 * inch,
                             'Multimodal Medical AI Platform')


# ---- helpers --------------------------------------------------------------

def _ascii(text: Optional[str]) -> str:
    """Substitute Unicode box-drawing chars that base Helvetica can't render."""
    if not text:
        return ''
    table = str.maketrans({
        '═': '=', '─': '-', '│': '|', '┌': '+', '┐': '+', '└': '+', '┘': '+',
        '├': '+', '┤': '+', '┬': '+', '┴': '+', '┼': '+',
        '•': '-',
    })
    return text.translate(table)


def _resolve_media_path(rel_or_abs: Optional[str]) -> Optional[str]:
    """Convert a media-relative path (as stored in DB) to an absolute filesystem path."""
    if not rel_or_abs:
        return None
    p = str(rel_or_abs)
    if os.path.isabs(p) and os.path.exists(p):
        return p
    candidate = os.path.join(settings.MEDIA_ROOT, p.lstrip('/\\').replace('/', os.sep))
    return candidate if os.path.exists(candidate) else None


def _sized_image(path: str, max_width_in: float = 5.5, max_height_in: float = 5.5) -> Optional[Image]:
    """Build a platypus Image flowable that fits within max_width x max_height while preserving aspect ratio."""
    if not path or not os.path.exists(path):
        return None
    try:
        with PILImage.open(path) as im:
            w, h = im.size
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    aspect = h / w
    width = max_width_in * inch
    height = width * aspect
    if height > max_height_in * inch:
        height = max_height_in * inch
        width = height / aspect
    return Image(path, width=width, height=height)


def _parse_mri_extras(report_text: Optional[str]) -> dict:
    """Pull tumor_area_pixels and seg_confidence out of the inference report text."""
    out: dict = {}
    if not report_text:
        return out
    m = re.search(r'Tumor Area:\s*(\d+)\s*pixels', report_text)
    if m:
        out['tumor_area'] = int(m.group(1))
    m = re.search(r'Segmentation Confidence:\s*([\d.]+)\s*%', report_text)
    if m:
        out['seg_confidence'] = float(m.group(1)) / 100.0
    # Cross-model verdict (added 2026-06; absent from older records)
    m = re.search(r'Overall Verdict:\s*(consistent|uncertain)', report_text, re.IGNORECASE)
    if m:
        out['overall_verdict'] = m.group(1).lower()
    return out


# ---- the generator -------------------------------------------------------

class MedicalReportGenerator:
    """Build a multi-section PDF medical report from a Patient and optional analyses."""

    def __init__(self, patient, mri_analysis=None, ecg_analysis=None, echo_analysis=None,
                 eeg_analysis=None, doctor=None):
        self.patient = patient
        self.mri = mri_analysis
        self.ecg = ecg_analysis
        self.echo = echo_analysis
        self.eeg = eeg_analysis
        self.doctor = doctor or patient.doctor
        self.generated_at = datetime.datetime.now()
        self._styles = self._build_styles()

    # ---- styles -------------------------------------------------------

    def _build_styles(self) -> dict:
        s = getSampleStyleSheet()
        return {
            'title':       ParagraphStyle('Title', parent=s['Heading1'], fontName='Helvetica-Bold',
                                          fontSize=18, textColor=PRIMARY, alignment=TA_CENTER, spaceAfter=8),
            'subtitle':    ParagraphStyle('Subtitle', parent=s['Normal'], fontName='Helvetica',
                                          fontSize=10, textColor=SECONDARY, alignment=TA_CENTER, spaceAfter=2),
            'h2':          ParagraphStyle('H2', parent=s['Heading2'], fontName='Helvetica-Bold',
                                          fontSize=14, textColor=PRIMARY, spaceBefore=12, spaceAfter=6),
            'h3':          ParagraphStyle('H3', parent=s['Heading3'], fontName='Helvetica-Bold',
                                          fontSize=11, textColor=SECONDARY, spaceBefore=8, spaceAfter=4),
            'body':        ParagraphStyle('Body', parent=s['Normal'], fontName='Helvetica',
                                          fontSize=10, textColor=SECONDARY, leading=14,
                                          alignment=TA_JUSTIFY, spaceAfter=6),
            'mono':        ParagraphStyle('Mono', parent=s['Normal'], fontName='Courier',
                                          fontSize=8, textColor=SECONDARY, leading=10, alignment=TA_LEFT),
            'disclaimer':  ParagraphStyle('Disclaimer', parent=s['Normal'], fontName='Helvetica-Oblique',
                                          fontSize=8, textColor=SECONDARY, alignment=TA_CENTER, spaceBefore=4),
            'image_cap':   ParagraphStyle('Caption', parent=s['Normal'], fontName='Helvetica-Oblique',
                                          fontSize=8, textColor=SECONDARY, alignment=TA_CENTER, spaceAfter=8),
        }

    # ---- header drawn on every page ----------------------------------

    def _on_page(self, canv, doc) -> None:
        canv.saveState()
        # Title block
        canv.setFont('Helvetica-Bold', 11)
        canv.setFillColor(PRIMARY)
        canv.drawString(0.75 * inch, LETTER[1] - 0.55 * inch, 'Multimodal Medical AI Platform')
        canv.setFont('Helvetica', 8)
        canv.setFillColor(SECONDARY)
        canv.drawString(0.75 * inch, LETTER[1] - 0.72 * inch, 'Cardiology & Oncology Decision Support')
        canv.drawString(0.75 * inch, LETTER[1] - 0.86 * inch, "Université Abdelhamid Mehri – Constantine 2")
        # Horizontal rule below header
        canv.setStrokeColor(BORDER)
        canv.setLineWidth(0.5)
        canv.line(0.75 * inch, LETTER[1] - 0.96 * inch, LETTER[0] - 0.75 * inch, LETTER[1] - 0.96 * inch)
        canv.restoreState()

    # ---- section builders --------------------------------------------

    def _patient_block(self) -> list:
        p = self.patient
        gender_map = {'M': 'Male', 'F': 'Female', 'O': 'Other'}
        data = [
            ['Patient ID',     str(p.pk)],
            ['Full Name',      p.full_name],
            ['Age',            str(p.age)],
            ['Gender',         gender_map.get(p.gender, p.gender)],
            ['Attending Dr.',  getattr(self.doctor, 'full_name', '—')],
            ['Report Date',    self.generated_at.strftime('%Y-%m-%d %H:%M:%S')],
        ]
        t = Table(data, colWidths=[1.6 * inch, 4.4 * inch])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), PRIMARY),
            ('TEXTCOLOR', (1, 0), (1, -1), SECONDARY),
            ('BACKGROUND', (0, 0), (-1, -1), LIGHT),
            ('GRID', (0, 0), (-1, -1), 0.25, BORDER),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return [
            Paragraph('PATIENT INFORMATION', self._styles['h2']),
            t,
            Spacer(1, 0.12 * inch),
        ]

    def _models_used_paragraph(self, models_used_str: str) -> Paragraph:
        items = [m.strip() for m in (models_used_str or '').split('|') if m.strip()]
        html = '<b>Models Used:</b><br/>' + '<br/>'.join(f'• {m}' for m in items) if items else '<i>No model metadata recorded.</i>'
        return Paragraph(html, self._styles['body'])

    def _summary_table(self, rows: list[tuple[str, str]]) -> Table:
        t = Table(rows, colWidths=[2.2 * inch, 3.8 * inch])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), PRIMARY),
            ('TEXTCOLOR', (1, 0), (1, -1), SECONDARY),
            ('GRID', (0, 0), (-1, -1), 0.25, BORDER),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, ALT_ROW]),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        return t

    def _mri_section(self) -> list:
        flow = [Paragraph('BRAIN MRI ANALYSIS', self._styles['h2'])]
        flow.append(self._models_used_paragraph(self.mri.model_used))

        extras = _parse_mri_extras(self.mri.result_report)
        detected = 'YES' if self.mri.result_tumor_detected else 'NO'
        type_str = self.mri.result_tumor_type or '—'
        cls_conf = f'{(self.mri.result_confidence or 0) * 100:.2f}%' if self.mri.result_confidence is not None else '—'
        seg_conf = f'{extras["seg_confidence"] * 100:.2f}%' if 'seg_confidence' in extras else '—'
        area = f'{extras["tumor_area"]} pixels' if 'tumor_area' in extras else '—'

        flow.append(Spacer(1, 0.08 * inch))
        flow.append(Paragraph('Result Summary', self._styles['h3']))
        flow.append(self._summary_table([
            ('Tumor Detected', detected),
            ('Tumor Type', type_str),
            ('Classification Confidence', cls_conf),
            ('Segmentation Confidence', seg_conf),
            ('Tumor Area', area),
        ]))

        # Cross-model caution. Older records lack the verdict — default to no note.
        if extras.get('overall_verdict', 'consistent') == 'uncertain':
            flow.append(Spacer(1, 0.06 * inch))
            flow.append(Paragraph(
                '<b>Note:</b> the segmentation and classification models disagree on '
                'this image - findings should be reviewed by a radiologist.',
                self._styles['body']))

        # Overlay image (preferred) — falls back to analysis or mask
        overlay = _resolve_media_path(self.mri.result_overlay_path) or _resolve_media_path(self.mri.result_analysis_path)
        if overlay:
            flow.append(Spacer(1, 0.12 * inch))
            img = _sized_image(overlay, max_width_in=5.0, max_height_in=4.5)
            if img is not None:
                flow.append(img)
                flow.append(Paragraph('Figure: MRI segmentation overlay (red = predicted tumor).',
                                      self._styles['image_cap']))

        # Full text report
        if self.mri.result_report:
            flow.append(Paragraph('Detailed Inference Report', self._styles['h3']))
            flow.append(Paragraph(_ascii(self.mri.result_report).replace('\n', '<br/>'), self._styles['mono']))

        # Clinical recommendation paragraph
        rec = _mri_recommendation(
            self.mri.result_tumor_type,
            self.mri.result_tumor_detected,
            self.mri.result_confidence,
        )
        flow.append(Spacer(1, 0.06 * inch))
        flow.append(Paragraph(f'<b>Clinical Recommendation.</b> {rec}', self._styles['body']))
        return flow

    def _ecg_section(self) -> list:
        flow = [Paragraph('12-LEAD ECG ANALYSIS', self._styles['h2'])]
        flow.append(self._models_used_paragraph(self.ecg.model_used))

        hrv = self.ecg.result_hrv_metrics or {}
        conf = f'{(self.ecg.result_confidence or 0) * 100:.2f}%' if self.ecg.result_confidence is not None else '—'
        hr_value = hrv.get('heart_rate_bpm')
        hr = f'{hr_value:.1f} bpm' if isinstance(hr_value, (int, float)) else '—'
        hr_cls = hrv.get('hr_classification') or '—'

        flow.append(Spacer(1, 0.08 * inch))
        flow.append(Paragraph('Result Summary', self._styles['h3']))
        flow.append(self._summary_table([
            ('Primary Diagnosis', self.ecg.result_arrhythmia_type or '—'),
            ('Diagnosis Confidence', conf),
            ('Heart Rate', hr),
            ('HR Classification', hr_cls),
        ]))

        # HRV metrics table
        flow.append(Spacer(1, 0.10 * inch))
        flow.append(Paragraph('Heart Rate Variability (HRV)', self._styles['h3']))
        flow.append(self._summary_table([
            ('RMSSD', f'{hrv.get("RMSSD_ms", 0):.2f} ms'),
            ('SDNN',  f'{hrv.get("SDNN_ms",  0):.2f} ms'),
            ('pNN50', f'{hrv.get("pNN50_percent", 0):.2f} %'),
        ]))

        # Pathology probabilities table
        probs = self.ecg.result_pathology_probabilities or {}
        if probs:
            flow.append(Spacer(1, 0.10 * inch))
            flow.append(Paragraph('Per-Pathology Probabilities', self._styles['h3']))
            rows = [['Code', 'Pathology', 'Probability', 'Detected']]
            full_names = {
                'AFIB': 'Atrial Fibrillation', '1AVB': '1st Degree AV Block',
                'STACH': 'Sinus Tachycardia', 'SBRAD': 'Sinus Bradycardia',
                'IRBBB': 'Incomplete RBBB', 'CRBBB': 'Complete RBBB',
                'RBBB': 'Right Bundle Branch Block', 'LBBB': 'Left Bundle Branch Block',
                'PVC': 'Premature Ventricular Complex',
            }
            for code, r in sorted(probs.items(), key=lambda kv: -kv[1].get('probability', 0)):
                rows.append([
                    code,
                    full_names.get(code, code),
                    f'{r.get("probability", 0) * 100:.2f}%',
                    '✓' if r.get('detected') else '',
                ])
            t = Table(rows, colWidths=[0.7 * inch, 2.7 * inch, 1.2 * inch, 0.8 * inch], repeatRows=1)
            t.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (2, 0), (3, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.25, BORDER),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ALT_ROW]),
                ('TEXTCOLOR', (0, 1), (-1, -1), SECONDARY),
            ]))
            flow.append(t)

        # Embedded ECG plot
        plot = _resolve_media_path(self.ecg.result_plot_path)
        if plot:
            flow.append(Spacer(1, 0.12 * inch))
            img = _sized_image(plot, max_width_in=5.5, max_height_in=5.0)
            if img is not None:
                flow.append(img)
                flow.append(Paragraph('Figure: 12-lead ECG (Lead II R-peaks marked in red).',
                                      self._styles['image_cap']))

        # Rule-based flags
        flags = hrv.get('additional_flags') or []
        if flags:
            flow.append(Paragraph('Rule-Based Flags', self._styles['h3']))
            for f in flags:
                flow.append(Paragraph(f'• {f}', self._styles['body']))

        # Full text report
        if self.ecg.result_report:
            flow.append(Paragraph('Detailed Inference Report', self._styles['h3']))
            flow.append(Paragraph(_ascii(self.ecg.result_report).replace('\n', '<br/>'), self._styles['mono']))

        return flow

    def _echo_section(self) -> list:
        flow = [Paragraph('ECHOCARDIOGRAPHY ANALYSIS', self._styles['h2'])]
        flow.append(self._models_used_paragraph(self.echo.model_used))

        ef = self.echo.result_ef
        ef_str = f'{ef:.1f}%' if isinstance(ef, (int, float)) else '—'
        flow.append(Spacer(1, 0.08 * inch))
        flow.append(Paragraph('Result Summary', self._styles['h3']))
        flow.append(self._summary_table([
            ('Ejection Fraction', ef_str),
            ('EF Category', self.echo.result_ef_category or '—'),
            ('End-diastolic LV area', f'{self.echo.result_ed_area} px' if self.echo.result_ed_area is not None else '—'),
            ('End-systolic LV area', f'{self.echo.result_es_area} px' if self.echo.result_es_area is not None else '—'),
        ]))

        img_path = _resolve_media_path(self.echo.result_overlay_path)
        if img_path:
            img = _sized_image(img_path, max_width_in=5.5, max_height_in=3.5)
            if img:
                flow.append(Spacer(1, 0.10 * inch))
                flow.append(Paragraph('LV Segmentation (end-diastole)', self._styles['h3']))
                flow.append(img)
        return flow

    def _eeg_section(self) -> list:
        flow = [Paragraph('EEG HARMFUL-BRAIN-ACTIVITY ANALYSIS', self._styles['h2'])]
        flow.append(self._models_used_paragraph(self.eeg.model_used))

        dominant = self.eeg.result_dominant_pattern or '—'
        harmful = self.eeg.result_harmful
        harmful_str = 'YES' if harmful else ('NO' if harmful is not None else '—')
        flow.append(Spacer(1, 0.08 * inch))
        flow.append(Paragraph('Result Summary', self._styles['h3']))
        flow.append(self._summary_table([
            ('Dominant IIIC Pattern', dominant),
            ('Harmful Activity (SZ/LPD/GPD)', harmful_str),
        ]))

        # per-class distribution table
        dist = self.eeg.result_class_distribution or {}
        if dist:
            order = ['SZ', 'LPD', 'GPD', 'LRDA', 'GRDA', 'Other']
            names = {
                'SZ': 'Seizure', 'LPD': 'Lateralized Periodic Discharges',
                'GPD': 'Generalized Periodic Discharges',
                'LRDA': 'Lateralized Rhythmic Delta', 'GRDA': 'Generalized Rhythmic Delta',
                'Other': 'Other / background',
            }
            flow.append(Spacer(1, 0.10 * inch))
            flow.append(Paragraph('IIIC Class Distribution', self._styles['h3']))
            rows = [['Code', 'Pattern', '% of recording']]
            for code in order:
                if code in dist:
                    rows.append([code, names.get(code, code), f'{dist[code] * 100:.1f}%'])
            t = Table(rows, colWidths=[0.8 * inch, 3.4 * inch, 1.4 * inch], repeatRows=1)
            t.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.25, BORDER),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ALT_ROW]),
                ('TEXTCOLOR', (0, 1), (-1, -1), SECONDARY),
            ]))
            flow.append(t)

        img_path = _resolve_media_path(self.eeg.result_plot_path)
        if img_path:
            img = _sized_image(img_path, max_width_in=5.5, max_height_in=3.0)
            if img:
                flow.append(Spacer(1, 0.10 * inch))
                flow.append(Paragraph('IIIC distribution & timeline', self._styles['h3']))
                flow.append(img)

        if self.eeg.result_report:
            flow.append(Paragraph('Detailed Inference Report', self._styles['h3']))
            flow.append(Paragraph(_ascii(self.eeg.result_report).replace('\n', '<br/>'), self._styles['mono']))

        flow.append(Spacer(1, 0.06 * inch))
        flow.append(Paragraph(
            '<b>Scope.</b> Functional screening for harmful brain activity — the complement to '
            'the structural MRI tumour analysis. This does not diagnose a tumour; it flags harmful '
            'electrical patterns (which a tumour is one acute cause of). IIIC is critical-care EEG '
            'from a general critically-ill cohort, not a tumour cohort.',
            self._styles['body']))
        return flow

    def _combined_interpretation(self) -> list:
        if not (self.mri and self.ecg):
            return []
        tumor = bool(self.mri.result_tumor_detected)
        arrhythmia = bool(self.ecg.result_arrhythmia_detected)
        ttype = (self.mri.result_tumor_type or '').lower()
        dx = self.ecg.result_arrhythmia_type or 'unspecified arrhythmia'

        if tumor and arrhythmia:
            text = (
                f"This patient presents with concurrent radiological findings ({ttype or 'tumor signal'}) "
                f"and cardiac rhythm abnormality ({dx}). "
                "In neuro-oncology, mass lesions can disrupt autonomic regulation via raised intracranial "
                "pressure or direct involvement of brainstem / hypothalamic centers, producing repolarization "
                "abnormalities or arrhythmia even with a structurally normal heart. Consider 24-hour Holter "
                "monitoring alongside neurosurgical evaluation, and reassess HR/HRV after any decompressive "
                "intervention."
            )
        elif tumor:
            text = (
                f"Imaging suggests a {ttype or 'tumor'} on MRI; ECG is within reassuring limits. "
                "Recommend neurosurgical/oncology follow-up and a routine cardiology baseline before any "
                "surgical or chemotherapeutic intervention that could affect cardiac function."
            )
        elif arrhythmia:
            text = (
                f"MRI did not demonstrate a focal mass lesion; ECG identifies {dx}. "
                "Recommend cardiology follow-up with extended rhythm monitoring as clinically indicated."
            )
        else:
            text = (
                "Both modalities are without major abnormality on this study. Recommend routine follow-up "
                "and re-imaging only if symptoms evolve."
            )
        return [
            Paragraph('COMBINED CLINICAL INTERPRETATION', self._styles['h2']),
            Paragraph(text, self._styles['body']),
        ]

    def _disclaimer(self) -> list:
        return [
            Spacer(1, 0.2 * inch),
            HRFlowable(width='100%', thickness=0.5, color=BORDER, spaceBefore=4, spaceAfter=6),
            Paragraph('<b>Report generated automatically by AI.</b>', self._styles['disclaimer']),
            Paragraph('This is a decision-support tool. Clinical decisions must be made by qualified '
                      'medical professionals.', self._styles['disclaimer']),
            Paragraph(f'Generated: {self.generated_at.strftime("%Y-%m-%d %H:%M:%S")}',
                      self._styles['disclaimer']),
            Paragraph("Université Abdelhamid Mehri – Constantine 2", self._styles['disclaimer']),
        ]

    # ---- public entry point ------------------------------------------

    def build(self, output) -> None:
        """Render the PDF to `output` (file path or file-like buffer)."""
        doc = SimpleDocTemplate(
            output,
            pagesize=LETTER,
            leftMargin=0.75 * inch, rightMargin=0.75 * inch,
            topMargin=1.1 * inch, bottomMargin=0.7 * inch,
            title=f'Medical Report — Patient {self.patient.pk}',
            author='Multimodal Medical AI Platform',
        )
        story: list = []
        story.append(Paragraph('MEDICAL ANALYSIS REPORT', self._styles['title']))
        story.append(Paragraph(f'Generated {self.generated_at.strftime("%Y-%m-%d %H:%M:%S")}',
                               self._styles['subtitle']))
        story.append(Spacer(1, 0.18 * inch))

        story.extend(self._patient_block())

        if self.mri is not None:
            story.append(Spacer(1, 0.08 * inch))
            story.extend(self._mri_section())

        if self.ecg is not None:
            story.append(Spacer(1, 0.08 * inch))
            story.extend(self._ecg_section())

        if self.echo is not None:
            story.append(Spacer(1, 0.08 * inch))
            story.extend(self._echo_section())

        if self.eeg is not None:
            story.append(Spacer(1, 0.08 * inch))
            story.extend(self._eeg_section())

        if self.mri is not None and self.ecg is not None:
            story.append(Spacer(1, 0.1 * inch))
            story.extend(self._combined_interpretation())

        story.extend(self._disclaimer())

        doc.build(story, onFirstPage=self._on_page, onLaterPages=self._on_page,
                  canvasmaker=NumberedCanvas)


# ---- standalone clinical recommendation (separated for reuse / unit-testing) ----

def _normalize_tumor_label(tumor_type: Optional[str]) -> str:
    """Strip the '_tumor' suffix used by some HuggingFace classifier labels."""
    if not tumor_type:
        return ''
    t = tumor_type.lower().strip()
    if t in ('no_tumor', 'notumor'):
        return t
    return t[:-len('_tumor')] if t.endswith('_tumor') else t


def _mri_recommendation(tumor_type: Optional[str], detected: Optional[bool],
                        cls_conf: Optional[float] = None) -> str:
    """Build a clinical recommendation fusing U-Net + ViT verdicts. See
    `apps.inference.mri_pipeline.generate_clinical_note` for the decision table.
    """
    normalized = _normalize_tumor_label(tumor_type)
    is_no_tumor = normalized in ('no_tumor', 'notumor', '')
    confident_tumor_class = (
        cls_conf is not None and cls_conf >= 0.70 and not is_no_tumor
    )

    by_type = {
        'glioma':     'glioma — recommend neurosurgical consultation and contrast-enhanced follow-up MRI',
        'meningioma': 'meningioma — typically slow-growing; consider neurosurgical evaluation and serial imaging',
        'pituitary':  'pituitary adenoma — recommend endocrinology workup and dedicated sellar MRI',
    }
    type_phrase = by_type.get(normalized, f'{normalized or tumor_type} — specialist review')
    conf_str = f'{cls_conf * 100:.1f}%' if cls_conf is not None else 'n/a'

    if detected and not is_no_tumor:
        return (f'Tumor confirmed by both segmentation and classifier ({conf_str} classifier confidence). '
                f'Diagnosis: {type_phrase}.')

    if detected and is_no_tumor:
        return ('Ambiguous: segmentation flagged tissue but the classifier rejected it. '
                'Recommend manual radiologist review before any further workup.')

    if not detected and confident_tumor_class:
        return (f'Likely {type_phrase} (classifier confidence {conf_str}). '
                'Segmentation was inconclusive on this image — recommend manual radiologist '
                'review of the localization.')

    return 'No tumor detected. Recommend routine follow-up only if clinically indicated.'
