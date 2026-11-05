"""
Flask Application - CV Processor

Aplicación web para subida y procesamiento de CVs.
Separada del orquestador principal para mejor organización.
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime
import json
import uuid
import sys
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any

# Añadir el directorio padre al path para importar config
sys.path.insert(0, str(Path(__file__).parent.parent))

# Añadir después de los otros imports de src/
try:
    from database.db_config import DatabaseConfig
    from database.db_inserter import CVInserter
    db_modules_loaded = True
except ImportError:
    db_modules_loaded = False

# Importar configuración desde settings
try:
    from config.settings import (
        SECRET_KEY,
        MAX_CONTENT_LENGTH,
        DEBUG,
        HOST,
        PORT,
        STORAGE_DIR,
        ALLOWED_EXTENSIONS,
        MIN_TEXT_LENGTH
    )

    settings_loaded = True
except ImportError as e:
    print(f"[WARN] No se pudo cargar settings: {e}")
    # Valores por defecto si no se puede cargar settings
    SECRET_KEY = 'dev-key-cambiar-en-produccion'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    DEBUG = True
    HOST = '127.0.0.1'
    PORT = 5000
    STORAGE_DIR = Path('storage')
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt'}
    MIN_TEXT_LENGTH = 100
    settings_loaded = False

# Imports desde el mismo directorio (ya estamos en src/)
try:
    from cv_extractor import extract_text_from_file, process_cv_data_with_duration
    from azure_openai_client import send_to_azure_openai, parse_azure_openai_response, check_azure_openai_status

    modules_loaded = True
except ImportError as e:
    print(f"[ERROR] No se pudieron cargar los módulos necesarios: {e}")
    modules_loaded = False

    # Definiciones por defecto en caso de error de importación
    def extract_text_from_file_error():
        raise ImportError("Función 'extract_text_from_file_error' no disponible")

    def process_cv_data_with_duration():
        raise ImportError("Función 'process_cv_data_with_duration' no disponible")

    def send_to_azure_openai():
        raise ImportError("Función 'send_to_azure_openai' no disponible")

    def parse_azure_openai_response():
        raise ImportError("Función 'parse_azure_openai_response' no disponible")

    def check_azure_openai_status():
        raise ImportError("Función 'check_azure_openai_status' no disponible")


# Configurar logger - Solo warnings y errores
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

# Ajuste del folder de plantillas
BASE_DIR = Path(__file__).parent  # ...\procesador_cv\src
TEMPLATES_DIR = BASE_DIR.parent / 'templates'

# Crear la aplicación Flask
app = Flask(__name__, template_folder=str(TEMPLATES_DIR))

# Configuración de Flask desde settings
app.config['SECRET_KEY'] = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['DEBUG'] = DEBUG

# Configuración adicional de Flask
app.config['JSON_AS_ASCII'] = False  # Para manejar caracteres UTF-8 en JSON
app.config['JSON_SORT_KEYS'] = False  # Mantener orden de keys en JSON

# Crear directorio de almacenamiento si no existe
Path(STORAGE_DIR).mkdir(parents=True, exist_ok=True)


def allowed_file(filename: str) -> bool:
    """
    Verificar si el archivo tiene una extensión permitida.

    Args:
        filename (str): Nombre del archivo

    Returns:
        bool: True si la extensión está permitida
    """
    if not filename:
        return False

    # Obtener extensión sin el punto
    extension = Path(filename).suffix.lower().lstrip('.')
    return extension in ALLOWED_EXTENSIONS


def generate_unique_filename(original_filename: str) -> str:
    """
    Generar nombre único para evitar colisiones.

    Args:
        original_filename (str): Nombre original del archivo

    Returns:
        str: Nombre único con timestamp y UUID
    """
    # Sanitizar el nombre original
    safe_filename = secure_filename(original_filename)
    file_extension = Path(safe_filename).suffix.lower()

    # Si no hay extensión o no es válida, usar .txt por defecto
    if not file_extension or file_extension.lstrip('.') not in ALLOWED_EXTENSIONS:
        file_extension = '.txt'

    unique_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return f"cv_{timestamp}_{unique_id}{file_extension}"


def process_cv_complete(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Procesar CV completo: extracción → Azure OpenAI → JSON

    Args:
        file_path (str): Ruta al archivo CV subido

    Returns:
        dict: Datos estructurados del CV o None si falla
    """
    try:
        # Paso 1: Extraer texto
        cv_text, num_pages = extract_text_from_file(file_path)

        if not cv_text or len(cv_text.strip()) < MIN_TEXT_LENGTH:
            logger.warning(f"Texto insuficiente extraído ({len(cv_text.strip())} caracteres)")
            return None

        logger.info(f"Texto extraído exitosamente: {len(cv_text)} caracteres, {num_pages} página(s)")

        # Paso 2: Procesar con Azure OpenAI
        raw_response = send_to_azure_openai(cv_text)

        if not raw_response:
            logger.error("No se recibió respuesta de Azure OpenAI")
            return None

        # Paso 3: Parsear respuesta
        structured_data = parse_azure_openai_response(raw_response)

        if not structured_data:
            logger.error("Error parseando la respuesta JSON")
            return None

        # Paso 4: Agregar duración a experiencias profesionales
        structured_data = process_cv_data_with_duration(structured_data)

        # Paso 5: Obtener nombre del candidato
        nombre_candidato = structured_data.get('datos_contacto', {}).get('nombre_completo', 'unknown')

        # Paso 6: Guardar JSON procesado
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Limpiar nombre para usar como filename
        nombre_limpio = re.sub(r'[^\w\s-]', '', nombre_candidato).strip()
        nombre_limpio = re.sub(r'[-\s]+', '_', nombre_limpio)

        json_filename = f"cv_{timestamp}_{nombre_limpio}.json"
        json_path = STORAGE_DIR / json_filename

        with open(json_path, 'w', encoding='utf-8') as json_file:
            json.dump(structured_data, json_file, indent=2, ensure_ascii=False)

        logger.info(f"CV procesado exitosamente: {nombre_candidato} ({num_pages} página(s))")

        return structured_data

    except Exception as e:
        logger.error(f"Error procesando CV: {e}", exc_info=True)
        return None


# ========================
# RUTAS FLASK
# ========================

@app.route('/')
def index():
    """Página principal con el formulario de upload."""
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error cargando template: {e}")
        return jsonify({"error": "Error cargando la página"}), 500


@app.route('/upload', methods=['POST'])
def upload_cv():
    """Manejar la subida y procesamiento de CVs."""
    try:
        # Validar que hay archivo
        if 'cv_file' not in request.files:
            flash('No se seleccionó ningún archivo', 'error')
            return redirect(url_for('index'))

        file = request.files['cv_file']

        if file.filename == '':
            flash('No se seleccionó ningún archivo', 'error')
            return redirect(url_for('index'))

        # Validar extensión
        if not allowed_file(file.filename):
            extensions_str = ', '.join(sorted(ALLOWED_EXTENSIONS))
            flash(f'Tipo de archivo no permitido. Use: {extensions_str.upper()}', 'error')
            return redirect(url_for('index'))

        # Generar nombre único y guardar archivo
        unique_filename = generate_unique_filename(file.filename)
        file_path = STORAGE_DIR  / unique_filename

        # Guardar archivo
        file.save(str(file_path))

        flash(f'CV subido exitosamente', 'info')

        # Procesar CV completo
        cv_data = process_cv_complete(str(file_path))

        if cv_data:
            nombre = cv_data.get('datos_contacto', {}).get('nombre_completo', 'Desconocido')
            flash(f'✅ CV de "{nombre}" procesado correctamente', 'success')
        else:
            flash('⚠️ Error procesando el CV. Verifique el formato del archivo.', 'error')

        return redirect(url_for('index'))

    except Exception as e:
        logger.error(f"Error en upload_cv: {e}")
        flash(f'Error al procesar el archivo', 'error')
        return redirect(url_for('index'))


@app.route('/status')
def status():
    """Endpoint para verificar el estado del sistema."""
    try:
        # Verificar Azure OpenAI
        azure_status = check_azure_openai_status() if modules_loaded else False

        # Contar archivos procesados
        processed_count = len(list(STORAGE_DIR.glob('*.json'))) if STORAGE_DIR.exists() else 0

        response = {
            "status": "ok" if azure_status else "degraded",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "azure_openai": "available" if azure_status else "unavailable"
            },
            "statistics": {
                "processed_cvs": processed_count
            }
        }

        http_code = 200 if azure_status else 503
        return jsonify(response), http_code

    except Exception as e:
        logger.error(f"Error en status: {e}")
        return jsonify({
            "status": "error",
            "timestamp": datetime.now().isoformat()
        }), 500


@app.route('/health')
def health():
    """Endpoint simple de health check."""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


@app.errorhandler(413)
def request_entity_too_large(_error):
    """Manejar archivos demasiado grandes."""
    max_mb = MAX_CONTENT_LENGTH / (1024 * 1024)
    flash(f'Archivo demasiado grande. Máximo: {max_mb:.0f} MB', 'error')
    return redirect(url_for('index'))


@app.errorhandler(500)
def internal_error(error):
    """Manejar errores internos del servidor."""
    logger.error(f"Error interno del servidor: {error}")
    return jsonify({
        "error": "Error interno del servidor"
    }), 500


def create_app():
    """
    Factory function para crear la aplicación Flask.

    Returns:
        Flask: Aplicación Flask configurada
    """
    return app


if __name__ == '__main__':
    # Solo para development - main.py manejará la ejecución en producción
    app.run(debug=DEBUG, host=HOST, port=PORT)