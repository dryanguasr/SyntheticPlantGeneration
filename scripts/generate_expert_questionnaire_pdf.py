"""Generate the fillable expert questionnaire for synthetic uchuva fidelity.

The PDF is deliberately generated from repository code so its questions,
version and provenance remain reproducible. It does not modify source images.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


VERSION = "1.0.0"
PAGE_W, PAGE_H = A4
MARGIN_X = 36
TOP_Y = PAGE_H - 48
BOTTOM_Y = 38
GREEN = colors.HexColor("#315C3A")
LIGHT_GREEN = colors.HexColor("#EAF1E9")
PALE = colors.HexColor("#F5F7F3")
INK = colors.HexColor("#213128")
MUTED = colors.HexColor("#5D6A61")
LINE = colors.HexColor("#A7B3AA")
FIELD_FILL = colors.HexColor("#FFFDF4")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/pdf/cuestionario_expertos_fidelidad_uchuva_v1.pdf"),
    )
    return parser.parse_args()


class FormPDF:
    def __init__(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self.output = output
        self.c = canvas.Canvas(str(output), pagesize=A4, pageCompression=1)
        self.c.setTitle("Cuestionario para expertos: fidelidad sintética de uchuva")
        self.c.setAuthor("Proyecto SyntheticPlantGeneration")
        self.c.setSubject("Mediciones para calibrar morfología, materiales, entorno y captura")
        self.page = 0

    def header(self, title: str, subtitle: str = "") -> None:
        self.page += 1
        self.c.setFillColor(GREEN)
        self.c.rect(0, PAGE_H - 72, PAGE_W, 72, stroke=0, fill=1)
        self.c.setFillColor(colors.white)
        self.c.setFont("Helvetica-Bold", 15)
        self.c.drawString(MARGIN_X, PAGE_H - 34, title)
        if subtitle:
            self.c.setFont("Helvetica", 8.5)
            self.c.drawString(MARGIN_X, PAGE_H - 51, subtitle)
        self.c.setFillColor(MUTED)
        self.c.setFont("Helvetica", 7.5)
        self.c.drawRightString(PAGE_W - MARGIN_X, 21, f"v{VERSION} · página {self.page}")
        self.c.setStrokeColor(LINE)
        self.c.line(MARGIN_X, 29, PAGE_W - MARGIN_X, 29)

    def finish_page(self) -> None:
        self.c.showPage()

    def save(self) -> None:
        self.c.save()

    def wrapped(self, text: str, x: float, y: float, width: float, size: float = 9, leading: float = 12, bold: bool = False, color=INK) -> float:
        font = "Helvetica-Bold" if bold else "Helvetica"
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        words = text.split()
        line = ""
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if stringWidth(candidate, font, size) <= width:
                line = candidate
            else:
                self.c.drawString(x, y, line)
                y -= leading
                line = word
        if line:
            self.c.drawString(x, y, line)
            y -= leading
        return y

    def section(self, text: str, y: float) -> float:
        self.c.setFillColor(LIGHT_GREEN)
        self.c.roundRect(MARGIN_X, y - 18, PAGE_W - 2 * MARGIN_X, 24, 4, stroke=0, fill=1)
        self.c.setFillColor(GREEN)
        self.c.setFont("Helvetica-Bold", 11)
        self.c.drawString(MARGIN_X + 8, y - 10, text)
        return y - 30

    def field(self, name: str, label: str, x: float, y: float, width: float, height: float = 18, font_size: float = 8, multiline: bool = False) -> None:
        self.c.setFillColor(INK)
        self.c.setFont("Helvetica", 7.5)
        self.c.drawString(x, y + height + 3, label)
        self.c.acroForm.textfield(
            name=name,
            tooltip=label,
            x=x,
            y=y,
            width=width,
            height=height,
            borderWidth=0.8,
            borderColor=LINE,
            fillColor=FIELD_FILL,
            textColor=INK,
            fontName="Helvetica",
            fontSize=font_size,
            fieldFlags="multiline" if multiline else "",
            forceBorder=True,
            maxlen=3000 if multiline else 160,
        )

    def checkbox(self, name: str, label: str, x: float, y: float, size: float = 10) -> None:
        self.c.acroForm.checkbox(
            name=name,
            tooltip=label,
            x=x,
            y=y,
            size=size,
            buttonStyle="check",
            borderWidth=0.8,
            borderColor=LINE,
            fillColor=FIELD_FILL,
            textColor=GREEN,
            forceBorder=True,
            fieldFlags="",
        )
        self.c.setFillColor(INK)
        self.c.setFont("Helvetica", 8)
        self.c.drawString(x + size + 4, y + 1, label)

    def table_field(self, name: str, x: float, y: float, width: float, height: float = 18) -> None:
        self.c.acroForm.textfield(
            name=name,
            tooltip=name,
            x=x + 1,
            y=y + 1,
            width=width - 2,
            height=height - 2,
            borderWidth=0,
            fillColor=FIELD_FILL,
            textColor=INK,
            fontName="Helvetica",
            fontSize=7,
            forceBorder=False,
            maxlen=80,
        )


def draw_cover(pdf: FormPDF) -> None:
    pdf.header("Cuestionario de fidelidad sintética de uchuva", "Mediciones expertas para Physalis peruviana · versión 1")
    y = PAGE_H - 104
    y = pdf.wrapped(
        "Objetivo: convertir diferencias visuales entre datos reales y sintéticos en parámetros medibles de morfología, superficie, manejo del cultivo, fondo y captura. Las respuestas no cambian automáticamente el modelo: primero se registran con su incertidumbre y evidencia.",
        MARGIN_X, y, PAGE_W - 2 * MARGIN_X, 10.5, 15, True,
    )
    y -= 10
    y = pdf.section("Cómo responder", y)
    for i, text in enumerate([
        "Use milímetros o centímetros y anote siempre la unidad.",
        "Identifique ecotipo/cultivar, localidad, altitud, edad del cultivo y estado fenológico.",
        "Cuando estime visualmente, marque estimado; cuando mida, indique instrumento y número de muestras.",
        "Adjunte fotografías originales, preferiblemente RAW/JPEG sin filtros, junto con carta de color y regla en el mismo plano.",
        "Si una característica varía, entregue mínimo, mediana y máximo; no fuerce una sola cifra.",
    ], start=1):
        y = pdf.wrapped(f"{i}. {text}", MARGIN_X + 8, y, PAGE_W - 2 * MARGIN_X - 16, 9, 13)
    y -= 8
    y = pdf.section("Información que la literatura ya restringe", y)
    facts = [
        "El capacho fructífero es inflado, reticulado, persistente y piloso; no se modela como una esfera plástica lisa.",
        "La hoja es pubescente y su arquitectura vascular reportada llega a cuarto orden; la forma y margen muestran variación.",
        "Lolium perenne forma macollas con culmos de 30–90 cm y láminas de 2–6 mm de ancho.",
        "El kikuyo forma tapetes con rizomas y estolones; sus culmos usuales son mucho más bajos que los de Lolium.",
        "Espaldera, conducción vertical y sistemas X/V están documentados, pero la geometría del predio objetivo debe medirse.",
    ]
    for fact in facts:
        pdf.checkbox(f"cover_confirm_{facts.index(fact)}", fact, MARGIN_X + 8, y - 2)
        y -= 27
    y -= 2
    y = pdf.section("Estado de la evidencia", y)
    y = pdf.wrapped(
        "literature_reported = publicación primaria; measured_local = medición del predio; estimated = juicio experto sin instrumento; to_be_measured = dato todavía desconocido. Marque el nivel en cada sección cuando sea posible.",
        MARGIN_X + 8, y, PAGE_W - 2 * MARGIN_X - 16, 8.5, 12,
    )
    pdf.finish_page()


def draw_identity(pdf: FormPDF) -> None:
    pdf.header("1. Identificación y contexto del cultivo", "La comparación sólo es válida si conocemos el material vegetal y el manejo")
    y = PAGE_H - 112
    w = (PAGE_W - 2 * MARGIN_X - 16) / 2
    for row, (left, right) in enumerate([
        (("expert_name", "Nombre del experto"), ("expert_role", "Profesión / rol")),
        (("expert_org", "Institución / finca"), ("expert_contact", "Contacto")),
        (("site_name", "Predio / lote"), ("site_location", "Municipio, departamento")),
        (("site_altitude", "Altitud (m s. n. m.)"), ("visit_date", "Fecha de observación")),
        (("ecotype", "Ecotipo / cultivar / procedencia"), ("plant_age", "Edad del cultivo (días/meses)")),
        (("phenology", "Estado fenológico dominante"), ("management", "Convencional / orgánico / otro")),
    ]):
        yy = y - row * 51
        pdf.field(left[0], left[1], MARGIN_X, yy, w)
        pdf.field(right[0], right[1], MARGIN_X + w + 16, yy, w)
    y -= 6 * 51 + 6
    y = pdf.section("Condiciones de la observación", y)
    labels = ["Cielo despejado", "Parcialmente nublado", "Nublado", "Invernadero", "Después de lluvia", "Cultivo húmedo"]
    for i, label in enumerate(labels):
        pdf.checkbox(f"context_{i}", label, MARGIN_X + (i % 3) * 170, y - (i // 3) * 24)
    y -= 60
    pdf.field("context_time", "Hora local", MARGIN_X, y, 110)
    pdf.field("context_temp", "Temperatura aproximada (°C)", MARGIN_X + 130, y, 150)
    pdf.field("context_notes", "Observaciones de manejo, estrés o sanidad", MARGIN_X + 300, y - 45, PAGE_W - MARGIN_X - (MARGIN_X + 300), 63, multiline=True)
    y -= 76
    y = pdf.section("Nivel de evidencia de esta visita", y)
    for i, label in enumerate(["Medición instrumental", "Conteo manual", "Fotografía calibrada", "Estimación visual", "Registros históricos"]):
        pdf.checkbox(f"evidence_visit_{i}", label, MARGIN_X + (i % 3) * 170, y - (i // 3) * 24)
    pdf.finish_page()


def draw_calyx_measurements(pdf: FormPDF, state_key: str, state_label: str, page_number: int) -> None:
    pdf.header(f"{page_number}. Capacho: mediciones de {state_label}", "Ideal: 15 capachos intactos, unidos a la planta y seleccionados sin sesgo de tamaño")
    y = PAGE_H - 106
    y = pdf.wrapped(
        "Mida la longitud desde la inserción del pedicelo hasta el ápice y el diámetro máximo perpendicular. El espesor requiere instrumento adecuado; si no se mide, deje la celda vacía. Puntúe costillas y pliegues de 0 (ausente) a 3 (marcado).",
        MARGIN_X, y, PAGE_W - 2 * MARGIN_X, 8.5, 11,
    )
    y -= 6
    headers = ["N", "Long.\nmm", "Diám.\nmm", "Espesor\nmm", "Costillas\n0–3", "Pliegues\n0–3", "Tricomas\n0–3", "Notas / daño"]
    widths = [24, 62, 62, 62, 64, 64, 64, 121]
    x_positions = [MARGIN_X]
    for width in widths[:-1]:
        x_positions.append(x_positions[-1] + width)
    header_h = 31
    row_h = 22
    table_top = y
    pdf.c.setFillColor(GREEN)
    pdf.c.rect(MARGIN_X, table_top - header_h, sum(widths), header_h, stroke=0, fill=1)
    pdf.c.setFillColor(colors.white)
    pdf.c.setFont("Helvetica-Bold", 7)
    for x, width, label in zip(x_positions, widths, headers):
        lines = label.split("\n")
        for idx, line in enumerate(lines):
            pdf.c.drawCentredString(x + width / 2, table_top - 12 - idx * 9, line)
    y_row = table_top - header_h
    for row in range(1, 16):
        y_row -= row_h
        pdf.c.setFillColor(PALE if row % 2 == 0 else colors.white)
        pdf.c.rect(MARGIN_X, y_row, sum(widths), row_h, stroke=0, fill=1)
        pdf.c.setStrokeColor(LINE)
        pdf.c.rect(MARGIN_X, y_row, sum(widths), row_h, stroke=1, fill=0)
        pdf.c.setFillColor(INK)
        pdf.c.setFont("Helvetica", 7)
        pdf.c.drawCentredString(MARGIN_X + widths[0] / 2, y_row + 7, str(row))
        for col, width in enumerate(widths[1:], start=1):
            pdf.table_field(f"{state_key}_r{row}_c{col}", x_positions[col], y_row + 2, width, row_h - 4)
        for x in x_positions[1:]:
            pdf.c.line(x, y_row, x, y_row + row_h)
    y = y_row - 34
    pdf.field(f"{state_key}_sampling", "Criterio de muestreo e instrumento", MARGIN_X, y, 245)
    pdf.field(f"{state_key}_range", "Mínimo / mediana / máximo observados", MARGIN_X + 263, y, 260)
    y -= 54
    pdf.field(f"{state_key}_geometry_notes", "¿Qué irregularidad es estructural y cuál corresponde a vena, secado, daño o manipulación?", MARGIN_X, y - 34, PAGE_W - 2 * MARGIN_X, 48, multiline=True)
    pdf.finish_page()


def draw_surface(pdf: FormPDF) -> None:
    pdf.header("5. Superficie, color y respuesta a la luz", "La apariencia plástica no se corrige con un número de roughness inferido de JPEG")
    y = PAGE_H - 108
    y = pdf.section("A. Capacho", y)
    questions = [
        ("calyx_surface_touch", "Descripción táctil por estado: papiráceo, coriáceo, ceroso, quebradizo u otro"),
        ("calyx_hair_density", "Tricomas: densidad aproximada, longitud y distribución (costillas / intercostal / toda la superficie)"),
        ("calyx_translucency", "Contraluz: ¿se distingue el fruto, venas o sólo silueta? Indique estado y condición"),
        ("calyx_fold_origin", "Número y orientación de pliegues reales; diferencie pliegue de vena o costilla"),
        ("calyx_color_state", "Rangos de color y manchas por estado, incluida base o venación púrpura/café"),
    ]
    for name, label in questions:
        pdf.field(name, label, MARGIN_X, y - 30, PAGE_W - 2 * MARGIN_X, 32, multiline=True)
        y -= 59
    y = pdf.section("B. Hoja", y)
    pdf.field("leaf_surface", "Haz y envés: brillo, textura, pilosidad, venas visibles y daños frecuentes", MARGIN_X, y - 33, PAGE_W - 2 * MARGIN_X, 46, multiline=True)
    y -= 72
    pdf.field("leaf_shape", "Forma/margen: distribución de entero, sinuado y dentado; asimetría, acopamiento y torsión por estrato", MARGIN_X, y - 33, PAGE_W - 2 * MARGIN_X, 46, multiline=True)
    y -= 72
    pdf.field("leaf_thickness", "Espesor de lámina por edad/estrato, instrumento y número de muestras", MARGIN_X, y, PAGE_W - 2 * MARGIN_X)
    y -= 36
    y = pdf.section("Protocolo fotográfico recomendado", y)
    for i, label in enumerate(["RAW disponible", "Carta de color en cuadro", "Regla en el mismo plano", "Haz y envés", "Contraluz", "Tres ángulos de vista", "Iluminación anotada", "Archivo original sin filtros"]):
        pdf.checkbox(f"surface_photo_{i}", label, MARGIN_X + (i % 2) * 260, y - (i // 2) * 22)
    pdf.finish_page()


def draw_canopy(pdf: FormPDF) -> None:
    pdf.header("6. Arquitectura, tutorado y competencia por luz", "Medir por estratos: bajo, medio y alto")
    y = PAGE_H - 108
    y = pdf.section("Geometría del cultivo", y)
    y -= 24
    fields = [
        ("plant_spacing", "Distancia entre plantas (cm)"), ("row_spacing", "Distancia entre hileras (cm)"),
        ("canopy_height", "Altura de copa (cm)"), ("canopy_width", "Ancho de copa (cm)"),
        ("wire_heights", "Alturas de alambres (cm)"), ("wire_distance", "Separación lateral de alambres (cm)"),
    ]
    w = (PAGE_W - 2 * MARGIN_X - 12) / 2
    for idx in range(0, len(fields), 2):
        yy = y - (idx // 2) * 48
        pdf.field(fields[idx][0], fields[idx][1], MARGIN_X, yy, w)
        pdf.field(fields[idx + 1][0], fields[idx + 1][1], MARGIN_X + w + 12, yy, w)
    y -= 3 * 48 + 8
    y = pdf.section("Muestreo por estrato", y)
    headers = ["Estrato", "Altura (cm)", "Cobertura foliar %", "Hojas visibles / 0,25 m²", "Orientación dominante", "Claros al tallo/suelo %"]
    widths = [65, 74, 88, 105, 102, 89]
    x = MARGIN_X
    pdf.c.setFillColor(GREEN)
    pdf.c.rect(x, y - 28, sum(widths), 28, stroke=0, fill=1)
    pdf.c.setFillColor(colors.white)
    pdf.c.setFont("Helvetica-Bold", 6.7)
    for label, width in zip(headers, widths):
        pdf.c.drawCentredString(x + width / 2, y - 17, label)
        x += width
    for row, label in enumerate(["Bajo", "Medio", "Alto"]):
        yy = y - 28 - (row + 1) * 29
        x = MARGIN_X
        pdf.c.setFillColor(PALE if row == 1 else colors.white)
        pdf.c.rect(x, yy, sum(widths), 29, stroke=1, fill=1)
        pdf.c.setFillColor(INK)
        pdf.c.setFont("Helvetica-Bold", 8)
        pdf.c.drawCentredString(x + widths[0] / 2, yy + 10, label)
        x += widths[0]
        for col, width in enumerate(widths[1:], start=1):
            pdf.table_field(f"stratum_{row}_{col}", x, yy + 3, width, 23)
            pdf.c.line(x, yy, x, yy + 29)
            x += width
    y -= 28 + 3 * 29 + 40
    pdf.field("training_sequence", "Secuencia real: expansión lateral, elección de ramas, amarres, elevación del ápice y poda", MARGIN_X, y - 35, PAGE_W - 2 * MARGIN_X, 49, multiline=True)
    y -= 77
    pdf.field("light_competition", "¿Cómo cambia la postura foliar durante el día y entre plantas? Indique observación o método de medición", MARGIN_X, y - 35, PAGE_W - 2 * MARGIN_X, 49, multiline=True)
    y -= 77
    pdf.field("canopy_images", "Nombres de fotos/croquis adjuntos y punto de vista", MARGIN_X, y, PAGE_W - 2 * MARGIN_X)
    pdf.finish_page()


def draw_understory(pdf: FormPDF) -> None:
    pdf.header("7. Piso, malezas y fondo verde", "Cinco cuadrantes sugeridos de 0,5 × 0,5 m: cerca, medio y fondo")
    y = PAGE_H - 108
    y = pdf.wrapped(
        "Registre especies reales. No asuma que todo pasto alto es Lolium ni que todo tapete es kikuyo. La suma de coberturas puede superar 100 % si hay estratos superpuestos; anótelo.",
        MARGIN_X, y, PAGE_W - 2 * MARGIN_X, 9, 12, True,
    )
    y -= 8
    headers = ["Cuad.", "Especie / morfotipo", "Cobertura %", "Altura min–med–máx cm", "Suelo visible %", "Hojarasca %"]
    widths = [42, 145, 78, 120, 70, 68]
    x = MARGIN_X
    pdf.c.setFillColor(GREEN)
    pdf.c.rect(x, y - 28, sum(widths), 28, stroke=0, fill=1)
    pdf.c.setFillColor(colors.white)
    pdf.c.setFont("Helvetica-Bold", 7)
    for label, width in zip(headers, widths):
        pdf.c.drawCentredString(x + width / 2, y - 17, label)
        x += width
    for row in range(1, 11):
        yy = y - 28 - row * 26
        x = MARGIN_X
        pdf.c.setFillColor(PALE if row % 2 == 0 else colors.white)
        pdf.c.rect(x, yy, sum(widths), 26, stroke=1, fill=1)
        pdf.c.setFillColor(INK)
        pdf.c.setFont("Helvetica", 7)
        pdf.c.drawCentredString(x + widths[0] / 2, yy + 9, str((row + 1) // 2))
        x += widths[0]
        for col, width in enumerate(widths[1:], start=1):
            pdf.table_field(f"weed_r{row}_c{col}", x, yy + 3, width, 20)
            pdf.c.line(x, yy, x, yy + 26)
            x += width
    y -= 28 + 10 * 26 + 40
    pdf.field("understory_pattern", "Patrón espacial: macollas, tapete, parches, senderos, suelo desnudo, humedad y residuos", MARGIN_X, y - 38, PAGE_W - 2 * MARGIN_X, 52, multiline=True)
    y -= 82
    pdf.field("background_depth", "¿Qué ocupa el fondo fuera de foco? Hileras, bosque, malla, cielo, malezas, suelo u otros", MARGIN_X, y - 38, PAGE_W - 2 * MARGIN_X, 52, multiline=True)
    pdf.finish_page()


def draw_capture_annotation(pdf: FormPDF) -> None:
    pdf.header("8. Captura real y política de anotación", "Metadatos necesarios para reproducir perspectiva, desenfoque y etiquetas")
    y = PAGE_H - 108
    y = pdf.section("Cámara y captura", y)
    y -= 24
    pairs = [
        (("camera_model", "Cámara / sensor"), ("lens", "Lente / focal equivalente")),
        (("image_resolution", "Resolución original"), ("camera_distance", "Distancia típica al capacho (cm)")),
        (("camera_height", "Altura de cámara (cm)"), ("view_angle", "Ángulo / orientación predominante")),
        (("exposure", "ISO, apertura, velocidad"), ("focus", "Enfoque / profundidad de campo")),
    ]
    w = (PAGE_W - 2 * MARGIN_X - 14) / 2
    for row, pair in enumerate(pairs):
        yy = y - row * 49
        pdf.field(pair[0][0], pair[0][1], MARGIN_X, yy, w)
        pdf.field(pair[1][0], pair[1][1], MARGIN_X + w + 14, yy, w)
    y -= len(pairs) * 49 + 6
    pdf.field("capture_variability", "Variación entre sesiones: luz, clima, cámara, distancia, compresión, orientación y operador", MARGIN_X, y - 34, PAGE_W - 2 * MARGIN_X, 47, multiline=True)
    y -= 76
    y = pdf.section("Clase vigente: 0 = calyx", y)
    y = pdf.wrapped(
        "Estas preguntas no cambian la clase; fijan cómo dibujar la caja cuando el capacho está truncado, ocluido, dañado o apenas visible.",
        MARGIN_X + 8, y, PAGE_W - 2 * MARGIN_X - 16, 8.5, 11,
    )
    for i, label in enumerate([
        "Anotar capacho truncado por borde", "Anotar capacho con oclusión >50 %", "Anotar capacho seco/deteriorado",
        "Anotar capacho muy pequeño", "Caja sólo sobre píxeles visibles", "Incluir pedicelo dentro de la caja",
        "Incluir flor sin capacho", "Excluir capacho dudoso / no identificable",
    ]):
        pdf.checkbox(f"annotation_policy_{i}", label, MARGIN_X + (i % 2) * 260, y - (i // 2) * 23)
    y -= 112
    pdf.field("annotation_thresholds", "Umbrales recomendados: píxeles mínimos, oclusión máxima y regla para truncamiento", MARGIN_X, y - 33, PAGE_W - 2 * MARGIN_X, 46, multiline=True)
    y -= 72
    pdf.field("annotation_examples", "IDs de ejemplos positivos, negativos y casos frontera adjuntos", MARGIN_X, y, PAGE_W - 2 * MARGIN_X)
    pdf.finish_page()


def draw_priorities(pdf: FormPDF) -> None:
    pdf.header("9. Priorización, entregables y validación", "Cierre de la consulta experta")
    y = PAGE_H - 108
    y = pdf.section("Prioridad de correcciones", y)
    items = [
        "Forma y proporción del capacho", "Superficie papirácea / pliegues", "Color y estado de madurez",
        "Hoja: forma, espesor y postura", "Densidad y oclusión de la copa", "Tutorado y arquitectura",
        "Malezas y suelo", "Cámara, luz y profundidad de campo", "Política de anotación",
    ]
    pdf.c.setFont("Helvetica", 8)
    pdf.c.setFillColor(MUTED)
    pdf.c.drawString(MARGIN_X, y, "Asigne 1 a la corrección más importante y 9 a la menos importante.")
    y -= 24
    for i, item in enumerate(items):
        yy = y - i * 27
        pdf.field(f"priority_{i}", "", MARGIN_X, yy, 42, 16, 8)
        pdf.c.setFillColor(INK)
        pdf.c.setFont("Helvetica", 8.5)
        pdf.c.drawString(MARGIN_X + 56, yy + 5, item)
    y -= len(items) * 27 + 8
    y = pdf.section("Archivos adjuntos", y)
    for i, label in enumerate([
        "Fotos RAW/JPEG originales", "Carta de color y regla", "Fotos de haz/envés", "Fotos de contraluz",
        "Croquis y medidas del tutorado", "Cuadrantes de malezas", "Metadatos EXIF", "Ejemplos de anotación",
    ]):
        pdf.checkbox(f"deliverable_{i}", label, MARGIN_X + (i % 2) * 260, y - (i // 2) * 22)
    y -= 102
    pdf.field("file_location", "Enlace, carpeta o nombres de archivos", MARGIN_X, y, PAGE_W - 2 * MARGIN_X)
    y -= 50
    pdf.field("expert_summary", "Tres cambios que más aumentarían la similitud con el cultivo real", MARGIN_X, y - 58, PAGE_W - 2 * MARGIN_X, 72, multiline=True)
    y -= 98
    pdf.field("expert_limitations", "Limitaciones de la observación y datos que aún faltan", MARGIN_X, y - 45, PAGE_W - 2 * MARGIN_X, 59, multiline=True)
    y -= 86
    pdf.field("expert_signature", "Nombre / firma", MARGIN_X, y, 240)
    pdf.field("expert_sign_date", "Fecha", MARGIN_X + 270, y, 150)
    pdf.finish_page()


def draw_references(pdf: FormPDF) -> None:
    pdf.header("10. Fuentes y protocolo de retorno", "Las fuentes acotan el modelo; las cifras locales siguen requiriendo medición")
    y = PAGE_H - 108
    refs = [
        "Kew, Plants of the World Online. Physalis peruviana: descripción morfológica, hoja y cáliz fructífero.",
        "Mazorra et al. (2006). Aspectos anatómicos de la formación y crecimiento del fruto de uchuva. Acta Biológica Colombiana 11(1):69–81.",
        "Bhat et al. (2018). Systematic studies of Physalis: micromorfología y arquitectura foliar. Plant Archives 18(2):2229–2238.",
        "Rodrigues et al. (2021). Characterization of physiological maturity of Physalis peruviana fruits. DOI 10.5433/1679-0359.2021v42n3p929.",
        "Lima et al. (2021). Pruning, training system, and climate conditions for perennial physalis. DOI 10.1590/S1678-3921.pab2021.v56.01850.",
        "Kretzschmar et al. (2012). Different training systems for Physalis peruviana in Southern Brazil. DOI 10.17660/ActaHortic.2012.926.74.",
        "Kew/GrassBase. Lolium perenne y Cenchrus clandestinus: hábito y dimensiones de culmos y láminas.",
    ]
    for i, ref in enumerate(refs, start=1):
        y = pdf.wrapped(f"{i}. {ref}", MARGIN_X, y, PAGE_W - 2 * MARGIN_X, 8.5, 12)
        y -= 4
    y -= 8
    y = pdf.section("Qué devolver", y)
    y = pdf.wrapped(
        "1) Este PDF diligenciado; 2) archivos originales en una carpeta sin recomprimir; 3) una tabla o nota que relacione cada foto con planta, órgano, estado y escala; 4) consentimiento para usar las observaciones sólo con fines de calibración del modelo y documentación científica del proyecto.",
        MARGIN_X + 8, y, PAGE_W - 2 * MARGIN_X - 16, 9, 13,
    )
    y -= 30
    pdf.field("return_contact", "Persona y medio para aclaraciones", MARGIN_X, y, PAGE_W - 2 * MARGIN_X)
    y -= 50
    pdf.field("return_notes", "Comentarios finales", MARGIN_X, y - 115, PAGE_W - 2 * MARGIN_X, 130, multiline=True)
    y -= 160
    pdf.c.setFillColor(LIGHT_GREEN)
    pdf.c.roundRect(MARGIN_X, y - 58, PAGE_W - 2 * MARGIN_X, 70, 6, stroke=0, fill=1)
    pdf.wrapped(
        "Gracias, Omar y demás expertos. Este formulario existe para que el generador aprenda del cultivo real sin convertir intuiciones valiosas en constantes falsamente precisas.",
        MARGIN_X + 14, y - 9, PAGE_W - 2 * MARGIN_X - 28, 10, 14, True, GREEN,
    )
    pdf.finish_page()


def generate(output: Path) -> Path:
    pdf = FormPDF(output)
    draw_cover(pdf)
    draw_identity(pdf)
    draw_calyx_measurements(pdf, "calyx_green", "verde / en expansión", 2)
    draw_calyx_measurements(pdf, "calyx_straw", "pajizo / maduro", 3)
    draw_calyx_measurements(pdf, "calyx_dry", "seco / deteriorado", 4)
    draw_surface(pdf)
    draw_canopy(pdf)
    draw_understory(pdf)
    draw_capture_annotation(pdf)
    draw_priorities(pdf)
    draw_references(pdf)
    pdf.save()
    return output


def main() -> None:
    args = parse_args()
    path = generate(args.output.resolve())
    print(path)


if __name__ == "__main__":
    main()
