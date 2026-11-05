"""
CV Extractor - ExtracciÃ³n de texto de archivos CV

MÃ³dulo para extraer texto de diferentes formatos de archivos de CV:
PDF, DOCX, DOC, TXT con limpieza y normalizaciÃ³n automÃ¡tica.
"""

import os
import re
import sys
import logging
import signal
from datetime import datetime
from pathlib import Path
from typing import Dict
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURACIÃ“N
# ============================================================================
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from config.settings import (MIN_TEXT_LENGTH, EXTRACTION_TIMEOUT, USE_OCR, TESSERACT_PATH, OCR_LANGUAGE, ALLOWED_EXTENSIONS)
except ImportError:
    MIN_TEXT_LENGTH = 100
    EXTRACTION_TIMEOUT = 60
    USE_OCR = False
    TESSERACT_PATH = '/usr/bin/tesseract'
    OCR_LANGUAGE = 'spa+eng'
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt'}

# ============================================================================
# IMPORTACIONES OPCIONALES
# ============================================================================

# ? DOCX
try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    Document = None
    logger.warning("python-docx no disponible. Instala con: pip install python-docx")

# ? PDF

# 1. pdfplumber
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    pdfplumber = None

# 2. PyPDF2
try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    PyPDF2 = None

# 3. PyMuPDF
try:
    import fitz
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    fitz = None

# 4. OCR (Para reconocer el texto del CV)
try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
    if TESSERACT_PATH and os.path.exists(TESSERACT_PATH):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
except ImportError:
    OCR_AVAILABLE = False
    pytesseract = None
    convert_from_path = None

# ============================================================================
# UTILIDADES
# ============================================================================
@contextmanager
def timeout(seconds):
    """Context manager para timeout en operaciones."""
    def timeout_handler(_signum, _frame):
        raise TimeoutError(f"OperaciÃ³n excediÃ³ el lÃ­mite de {seconds} segundos")

    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
    else:
        yield

# ============================================================================
# EXTRACCIÃ“N DE TEXTO POR FORMATO
# ============================================================================
def extract_text_from_txt(file_path: str) -> str:
    """Extraer texto de archivo TXT."""
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                text = file.read()
                logger.debug(f"TXT leÃ­do con encoding {encoding}: {len(text)} caracteres")
                return text
        except UnicodeDecodeError:
            continue

    # Fallback: leer con errores ignorados
    try:
        with open(file_path, 'rb') as file:
            content = file.read()
            return content.decode('utf-8', errors='ignore')
    except Exception as e:
        logger.error(f"Error leyendo TXT: {e}")
        return ""


def extract_text_from_docx(file_path: str) -> str:
    """Extraer texto de archivo DOCX."""
    if not DOCX_AVAILABLE:
        logger.error("python-docx no disponible")
        return ""

    try:
        doc = Document(file_path)
        text = ""

        # Extraer pÃ¡rrafos
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"

        # Extraer tablas
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text += cell.text + " "
                text += "\n"

        logger.info(f"DOCX extraÃ­do: {len(text)} caracteres")
        return text
    except Exception as e:
        logger.error(f"Error leyendo DOCX: {e}")
        return ""

# -------------------------------------------------------------------------------------------------------------------- #

# * Extraer texto de PDF probando mÃºltiples estrategias.
def extract_text_from_pdf(file_path: str) -> tuple[str, int]:

    # ? Estrategia 1: PyMuPDF (mÃ¡s rÃ¡pida y robusta)
    if PYMUPDF_AVAILABLE:
        text, num_pages = _try_pymupdf(file_path)
        if text and len(text.strip()) > MIN_TEXT_LENGTH:
            logger.info(f"Texto extraído con PyMuPDF: {len(text)} caracteres, {num_pages} página(s)")
            return text, num_pages

    # ? Estrategia 2: pdfplumber (mejor para tablas y layouts complejos)
    if PDFPLUMBER_AVAILABLE:
        text, num_pages = _try_pdfplumber(file_path)
        if text and len(text.strip()) > MIN_TEXT_LENGTH:
            logger.info(f"Texto extraído con pdfplumber: {len(text)} caracteres, {num_pages} página(s)")
            return text, num_pages

    # ? Estrategia 3: PyPDF2 (fallback ligero y rÃ¡pido)
    if PYPDF2_AVAILABLE:
        text, num_pages = _try_pypdf2(file_path)
        if text and len(text.strip()) > MIN_TEXT_LENGTH:
            logger.info(f"Texto extraído con PyPDF2: {len(text)} caracteres, {num_pages} página(s)")
            return text, num_pages

    # ? Estrategia 4: OCR (Ãºltimo recurso para PDFs escaneados)
    if USE_OCR and OCR_AVAILABLE:
        logger.info("Intentando OCR como último recurso...")
        text, num_pages = _try_ocr(file_path)
        if text and len(text.strip()) > MIN_TEXT_LENGTH:
            logger.info(f"Texto extraído con OCR: {len(text)} caracteres, {num_pages} página(s)")
            return text, num_pages

    logger.error(f"No se pudo extraer texto suficiente del PDF (mínimo: {MIN_TEXT_LENGTH})")
    return "", 0


def _try_pdfplumber(file_path: str) -> tuple[str, int]:
    """Intentar extracciÃ³n con pdfplumber."""
    try:
        text = ""
        with pdfplumber.open(file_path) as pdf:
            num_pages = len(pdf.pages)  # Nueva línea
            for page_num, page in enumerate(pdf.pages):
                page_text = page.extract_text(layout=True)
                if not page_text or len(page_text.strip()) < 10:
                    page_text = page.extract_text()
                if page_text and len(page_text.strip()) > 5:
                    text += f"\n--- Página {page_num + 1} ---\n{page_text}\n\n"
        return text, num_pages
    except Exception as e:
        logger.debug(f"Error con pdfplumber: {e}")
        return "", 0


def _try_pypdf2(file_path: str) -> tuple[str, int]:
    """Intentar extracciÃ³n con PyPDF2."""
    try:
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            num_pages = len(pdf_reader.pages)
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text and len(page_text.strip()) > 5:
                        text += f"\n--- Página {page_num + 1} ---\n{page_text}\n\n"
                except Exception:
                    continue
        return text, num_pages
    except Exception as e:
        logger.debug(f"Error con PyPDF2: {e}")
        return "", 0


def _try_pymupdf(file_path: str) -> tuple[str, int]:
    """Intentar extracciÃ³n con PyMuPDF."""
    try:
        text = ""
        doc = fitz.open(file_path)
        num_pages = len(doc)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            page_text = page.get_text()
            if page_text and len(page_text.strip()) > 5:
                text += f"\n--- Página {page_num + 1} ---\n{page_text}\n\n"
        doc.close()
        return text, num_pages
    except Exception as e:
        logger.debug(f"Error con PyMuPDF: {e}")
        return "", 0


def _try_ocr(file_path: str) -> tuple[str, int]:
    """Intentar extracciÃ³n con OCR."""
    try:
        text = ""
        num_pages = 0
        with timeout(EXTRACTION_TIMEOUT):
            # Convertir PDF a imÃ¡genes
            try:
                pages = convert_from_path(file_path, dpi=300)
            except:
                pages = convert_from_path(file_path, dpi=200)

            num_pages = len(pages)  # Nueva línea

            # OCR en cada pÃ¡gina
            for page_num, page_image in enumerate(pages):
                try:
                    custom_config = f'--oem 3 --psm 6 -l {OCR_LANGUAGE}'
                    page_text = pytesseract.image_to_string(page_image, config=custom_config)
                    if page_text and len(page_text.strip()) > 10:
                        text += f"\n--- Página {page_num + 1} ---\n{page_text}\n\n"
                except Exception as e:
                    logger.debug(f"Error OCR en pÃ¡gina {page_num + 1}: {e}")
                    continue
        return text, num_pages
    except TimeoutError:
        logger.error(f"OCR excediÃ³ timeout de {EXTRACTION_TIMEOUT} segundos")
        return "", 0
    except Exception as e:
        logger.error(f"Error en OCR: {e}")
        return "", 0


# ============================================================================
# LIMPIEZA DE TEXTO
# ============================================================================
def clean_and_normalize_text(text: str) -> str:
    """Limpiar y normalizar texto extraÃ­do."""
    if not text or not text.strip():
        return text

    # Eliminar caracteres de control
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]', '', text)

    # Normalizar espacios y saltos de lÃ­nea
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

    # Limpiar lÃ­neas
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)

    # Normalizar puntuaciÃ³n
    text = re.sub(r'\s*([.,;:!?])\s*', r'\1 ', text)

    return text.strip()


# ============================================================================
# PROCESAMIENTO DE DATOS DE CV
# ============================================================================

# * Procesar datos de CV agregando duraciÃ³n a experiencias profesionales
def process_cv_data_with_duration(cv_data: Dict) -> Dict:

    """
    Procesar datos de CV agregando duraciÃ³n a experiencias profesionales.

    Args:
        cv_data (dict): Datos estructurados del CV

    Returns:
        dict: Datos del CV con duraciones calculadas
    """

    if not isinstance(cv_data, dict):
        return cv_data

    # Procesar experiencias profesionales si existen
    if 'experiencia_profesional' in cv_data:
        experiencias = cv_data.get('experiencia_profesional', [])

        if isinstance(experiencias, list):

            for exp in experiencias:

                if isinstance(exp, dict):

                    fecha_inicio = exp.get('fecha_inicio')
                    fecha_fin = exp.get('fecha_fin')

                    # Calcular duraciÃ³n en meses
                    try:

                        if not fecha_inicio:
                            duracion = "0"
                        else:
                            # Si no hay fecha_fin, usar fecha actual
                            if not fecha_fin:
                                fecha_fin = datetime.now().strftime("%Y-%m-%d")

                            # Parsear fecha_inicio
                            if len(fecha_inicio) == 10:  # YYYY-MM-DD
                                inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d")
                            elif len(fecha_inicio) == 7:  # YYYY-MM
                                inicio = datetime.strptime(fecha_inicio + "-01", "%Y-%m-%d")
                            else:
                                continue

                            # Parsear fecha_fin
                            if len(fecha_fin) == 10:
                                fin = datetime.strptime(fecha_fin, "%Y-%m-%d")
                            elif len(fecha_fin) == 7:
                                fin = datetime.strptime(fecha_fin + "-28", "%Y-%m-%d")
                            else:
                                fin = datetime.now()

                            # Calcular diferencia
                            months_diff = (fin.year - inicio.year) * 12 + (fin.month - inicio.month)
                            if fin.day < inicio.day:
                                months_diff -= 1

                            if months_diff <= 0 and fin > inicio:
                                months_diff = 1

                            duracion = str(max(0, months_diff))

                            duracion_total = 0
                            if isinstance(experiencias, list) and len(experiencias) > 0:
                                # Ordenar por fecha_inicio
                                experiencias_ordenadas = sorted(
                                    experiencias,
                                    key=lambda x: x.get('fecha_inicio', '0000-00-00')
                                )

                                for exper in experiencias_ordenadas:
                                    if 'duracion' in exper:
                                        try:
                                            duracion_total += int(exper['duracion'])
                                        except:
                                            pass

                                cv_data['duracion_experiencia_total'] = duracion_total
                                logger.info(f"Duración total calculada: {duracion_total} meses")

                    except Exception as e:
                        logger.error(f"Error calculando duraciÃ³n: {e}")
                        duracion = "0"

                    exp['duracion'] = duracion
                    logger.info(f"Experiencia: {exp.get('empresa', 'N/A')} - {exp.get('puesto', 'N/A')}")
                    logger.info(
                        f"  PerÃ­odo: {fecha_inicio} a {exp.get('fecha_fin') or 'actualidad'} = {duracion} meses")

    return cv_data


# ============================================================================
# FUNCIÃ“N PRINCIPAL
# ============================================================================
def extract_text_from_file(file_path: str) -> tuple[str, int]:
    """
    FunciÃ³n principal para extraer texto de cualquier archivo soportado.

    Args:
        file_path (str): Ruta al archivo

    Returns:
        str: Texto extraÃ­do y limpio
    """
    if not os.path.exists(file_path):
        logger.error(f"Archivo no encontrado: {file_path}")
        return "", 0

    # Detectar extensión
    file_extension = Path(file_path).suffix.lower().lstrip('.')

    if file_extension not in ALLOWED_EXTENSIONS:
        logger.error(f"Tipo de archivo no soportado: .{file_extension}")
        return "", 0

    logger.info(f"Procesando archivo {file_extension.upper()}: {Path(file_path).name}")

    # Variable para páginas
    num_pages = 1
    # Extraer segÃºn tipo
    try:
        with timeout(EXTRACTION_TIMEOUT):
            if file_extension == 'pdf':
                raw_text, num_pages = extract_text_from_pdf(file_path)  # CAMBIO: Desempaquetar tupla
            elif file_extension in ['docx', 'doc']:
                raw_text = extract_text_from_docx(file_path)
                num_pages = 1
            elif file_extension == 'txt':
                raw_text = extract_text_from_txt(file_path)
                num_pages = 1
            else:
                logger.error(f"Tipo no implementado: {file_extension}")
                return "", 0
    except TimeoutError:
        logger.error(f"ExtracciÃ³n excediÃ³ timeout de {EXTRACTION_TIMEOUT} segundos")
        return "", 0
    except Exception as e:
        logger.error(f"Error durante extracciÃ³n: {e}")
        return "", 0

    # Limpiar texto
    clean_text = clean_and_normalize_text(raw_text)

    if len(clean_text) < MIN_TEXT_LENGTH:
        logger.warning(f"Texto muy corto: {len(clean_text)} caracteres (mÃ­nimo: {MIN_TEXT_LENGTH})")

    logger.info(f"Texto extraÃ­do: {len(clean_text)} caracteres")
    return clean_text, num_pages


# ============================================================================
# TESTING
# ============================================================================
if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    print("=== CV Extractor ===")

    # Test simple si se proporciona archivo
    if len(sys.argv) > 1:
        test_file = sys.argv[1]

        if os.path.exists(test_file):
            print(f"\nProcesando: {test_file}")
            extracted = extract_text_from_file(test_file)
            if extracted:
                print(f"✓ Extraídos {len(extracted)} caracteres")
                print(f"Preview: {extracted[:200]}...")
            else:
                print("✗ No se pudo extraer texto")
        else:
            print(f"Archivo no encontrado: {test_file}")
            print("\nUso: python cv_extractor.py <archivo_cv>")
    else:
        print("\nNo se proporcionó archivo")
        print("Uso: python cv_extractor.py <archivo_cv>")