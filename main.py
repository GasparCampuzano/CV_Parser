#!/usr/bin/env python
"""
CV Processor - CLI Interface v2
Mantiene compatibilidad con modo Flask durante transición
"""

import sys
import os
import argparse
import json
import logging
import time
import traceback
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Agregar directorios al path para imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / 'src'))

# Importar configuración
try:
    from config.settings import (
        STORAGE_DIR,
        ALLOWED_EXTENSIONS,
        MIN_TEXT_LENGTH,
        DEBUG,
        HOST,
        PORT,
        LOG_DIR,
        AZURE_OPENAI_ENDPOINT,
        AZURE_OPENAI_API_KEY,
        IS_DEVELOPMENT,
        get_logger
    )
    settings_loaded = True
except ImportError as e:
    print(json.dumps({
        "status": "ERROR",
        "message": f"Error cargando configuración: {str(e)}"
    }))
    sys.exit(99)


def setup_logging(mode: str) -> logging.Logger:

    """
    Configurar logging según el modo de ejecución.

    Args:
        mode: 'cli' o 'flask'

    Returns:
        Logger configurado
    """

    if mode == 'cli':
        # En modo CLI, solo logs a archivo, nunca a stdout/stderr
        logger = get_logger('main_cli')  # CAMBIO: Quitado segundo parámetro

        # Remover cualquier handler de consola para evitar contaminar stdout
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.StreamHandler):
                logger.removeHandler(handler)

        # Ya no necesitamos crear un handler adicional porque get_logger() ya lo hace
        # ELIMINADAS las líneas 21-33 que creaban cv_processor_cli.log

    else:
        # En modo Flask, usar la configuración estándar
        logger = get_logger('main_flask')  # CAMBIO: Quitado segundo parámetro

    return logger


def validate_file(file_path: Path) -> Optional[str]:
    """
    Validar que el archivo existe y tiene extensión válida.

    Args:
        file_path: Ruta al archivo

    Returns:
        Mensaje de error si hay problemas, None si toodo está bien
    """
    if not file_path.exists():
        return f"Archivo no encontrado: {file_path}"

    if not file_path.is_file():
        return f"La ruta no es un archivo: {file_path}"

    extension = file_path.suffix.lower().lstrip('.')
    if extension not in ALLOWED_EXTENSIONS:
        return f"Extensión no permitida: .{extension}. Use: {', '.join(ALLOWED_EXTENSIONS)}"

    # Verificar tamaño
    file_size = file_path.stat().st_size
    if file_size == 0:
        return "El archivo está vacío"

    if file_size > 16 * 1024 * 1024:  # 16MB
        return f"Archivo demasiado grande: {file_size / (1024 * 1024):.2f}MB (máximo 16MB)"

    return None


def process_cv_file(file_path: str, logger: logging.Logger) -> Optional[Dict[str, Any]]:
    """
    Procesar un archivo CV: extracción → Azure OpenAI → JSON estructurado
    (Mismo flujo que app.py pero sin guardar archivos intermedios por defecto)

    Args:
        file_path: Ruta al archivo CV
        logger: Logger para registrar eventos

    Returns:
        Diccionario con datos estructurados del CV o None si falla
    """
    try:
        from src.cv_extractor import extract_text_from_file, process_cv_data_with_duration
        from src.azure_openai_client import send_to_azure_openai, parse_azure_openai_response

        # Paso 1: Extraer texto
        logger.info("Extrayendo texto del documento...")
        text, num_pages = extract_text_from_file(file_path)

        if not text or len(text.strip()) < MIN_TEXT_LENGTH:
            logger.warning(f"Texto insuficiente extraído: {len(text) if text else 0} caracteres")
            return None

        logger.info(f"Texto extraído: {len(text)} caracteres")

        # Paso 2: Procesar con Azure OpenAI
        logger.info("Procesando con Azure OpenAI...")
        raw_response = send_to_azure_openai(text)

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

        # Añadir metadata
        structured_data['_metadata'] = {
            'archivo_original': Path(file_path).name,
            'fecha_procesamiento': datetime.now().isoformat(),
            'caracteres_extraidos': len(text),
            'Original Text':text
        }

        return structured_data

    except Exception as e:
        logger.error(f"Error procesando CV: {e}")
        return None

# AQUI DEBO AHCERLO
def insert_cv_to_database(json_data: Dict[str, Any], json_filename: str, logger: logging.Logger) -> Dict[str, Any]:
    """
    Insertar datos del CV en la base de datos.

    Args:
        json_data: Datos estructurados del CV
        json_filename: Nombre del archivo JSON
        logger: Logger para registrar eventos

    Returns:
        Diccionario con el resultado de la inserción
    """
    try:
        from src.database.db_config import DatabaseConfig
        from src.database.db_inserter import CVInserter

        logger.info("Conectando con base de datos...")
        db_config = DatabaseConfig()
        cv_inserter = CVInserter(db_config)

        logger.info("Insertando datos en base de datos...")
        result = cv_inserter.insert_cv_data(json_data, json_filename)

        # Cerrar conexión
        db_config.close()

        return result

    except ImportError as e:
        logger.error(f"Módulos de BD no disponibles: {e}")
        return {
            'status': 'error',
            'message': 'Módulos de base de datos no disponibles',
            'error': str(e)
        }
    except Exception as e:
        logger.error(f"Error insertando en BD: {e}")
        return {
            'status': 'error',
            'message': 'Error al insertar en base de datos',
            'error': str(e)
        }

# * Pipeline completo de procesamiento
def run_cli_mode(args: argparse.Namespace) -> None:

    """
    Modo CLI - Pipeline completo de procesamiento.

    Flujo:
    1. Validar archivo existe o recibir por stdin
    2. Extraer texto (cv_extractor.py)
    3. Procesar con Azure OpenAI (azure_openai_client.py)
    4. Validar datos (db_validator.py)
    5. Insertar en BD (db_inserter.py)
    6. Devolver JSON y exit code
    """

    # Inicializar variables de ejecución: logger, tiempo de inicio y control de temporales
    logger = setup_logging('cli')
    start_time = time.time()
    cleanup_temp = False
    temp_path = None

    # Crear estructura base de la respuesta
    response = {"status": "ERROR", "message": "", "data": {}}

    try:
        # ? Determinar origen del archivo

        # Caso 1: leer el archivo desde stdin y guardarlo como temporal
        if args.stdin:

            try:
                # Leer bytes desde stdin
                logger.info("Leyendo archivo desde stdin...")
                file_data = sys.stdin.buffer.read()

                # Validar que se recibieron datos por stdin; si no, devolver error y terminar ejecución
                if not file_data:
                    response["message"] = "No se recibieron datos por stdin"
                    print(json.dumps(response, ensure_ascii=False), flush=True)
                    sys.exit(1)

                # Detectar extensión a partir de magic bytes (PDF=%PDF, DOCX=PK) o asumir PDF por defecto
                if file_data[:4] == b'%PDF':
                    extension = '.pdf'
                elif file_data[:2] == b'PK':
                    extension = '.docx'
                else:
                    extension = '.pdf'

                # Generar nombre único y ruta para el archivo temporal
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                temp_filename = f"temp_cv_{timestamp}{extension}"
                temp_path = STORAGE_DIR / temp_filename

                # Guardar los datos recibidos en el archivo temporal
                with open(temp_path, 'wb') as f:
                    f.write(file_data)

                # Marcar el archivo como temporal y registrar la creación en logs
                file_path = temp_path
                cleanup_temp = True
                logger.info(f"Archivo temporal creado: {file_path}")

            except Exception as e:
                response["message"] = f"Error leyendo desde stdin: {str(e)}"
                print(json.dumps(response, ensure_ascii=False), flush=True)
                sys.exit(1)

        # Caso 2: usar archivo existente pasado por argumento --file
        elif args.file:

            # Obtener ruta absoluta del archivo y registrar en logs
            file_path = Path(args.file).resolve()
            logger.info(f"Procesando archivo: {file_path}")

            # Validar archivo; si hay error, devolver mensaje y finalizar ejecución
            error_msg = validate_file(file_path)
            if error_msg:
                response["message"] = error_msg
                print(json.dumps(response, ensure_ascii=False), flush=True)
                sys.exit(1)

        # Caso 3: no se indicó ni --file ni --stdin, devolver error y terminar ejecución
        else:
            response["message"] = "Debe especificar --file o --stdin"
            print(json.dumps(response, ensure_ascii=False), flush=True)
            sys.exit(1)

        # ? Procesar CV (extracción + Azure OpenAI)
        cv_data = process_cv_file(str(file_path), logger)

        if not cv_data:
            response["message"] = "Error procesando el CV con Azure OpenAI"
            print(json.dumps(response, ensure_ascii=False), flush=True)
            sys.exit(3)  # AI_SERVICE_ERROR

        # Obtener nombre del candidato
        candidate_name = cv_data.get('datos_contacto', {}).get('nombre_completo', 'Desconocido')

        # Guardar JSON si está configurado
        if args.save_json:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_filename = f"cv_{timestamp}_{file_path.stem}.json"
            json_path = STORAGE_DIR / json_filename

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(cv_data, f, indent=2, ensure_ascii=False)

            logger.info(f"JSON guardado en: {json_path}")
        else:
            # Usar nombre temporal para la inserción
            json_filename = f"{file_path.stem}.json"

        # Inserción en BD (si no se omite)
        if not args.skip_database:
            db_result = insert_cv_to_database(cv_data, json_filename, logger)

            if db_result['status'] == 'exitoso':
                # Procesamiento exitoso
                processing_time = time.time() - start_time

                response["status"] = "SUCCESS"
                response["message"] = "CV procesado e insertado correctamente"
                response["data"] = {
                    "candidate_id": db_result.get('candidato_id'),
                    "candidate_name": candidate_name,
                    "processing_time": round(processing_time, 2),
                    "file_name": file_path.name
                }

                # Agregar warnings si hay
                if db_result.get('warnings'):
                    response["data"]["warnings"] = db_result['warnings']

                logger.info(f"CV procesado exitosamente. ID: {db_result.get('candidato_id')}")

                # Limpiar archivo temporal antes de salir con éxito
                if cleanup_temp and temp_path and temp_path.exists():
                    try:
                        temp_path.unlink()
                        logger.info("Archivo temporal eliminado")
                    except Exception as e:
                        logger.warning(f"No se pudo eliminar archivo temporal: {e}")

                print(json.dumps(response, ensure_ascii=False), flush=True)
                sys.exit(0)  # SUCCESS

            elif db_result['status'] == 'duplicado':
                # Candidato duplicado
                response["status"] = "DUPLICATE"
                response["message"] = f"Candidato duplicado. ID existente: {db_result.get('candidato_id')}"
                response["data"] = {
                    "candidate_id": db_result.get('candidato_id'),
                    "candidate_name": candidate_name
                }

                logger.warning(f"Candidato duplicado detectado. ID: {db_result.get('candidato_id')}")
                print(json.dumps(response, ensure_ascii=False), flush=True)
                sys.exit(4)  # VALIDATION_ERROR

            else:
                # Error en BD
                response["message"] = db_result.get('message', 'Error insertando en base de datos')
                response["data"]["error_details"] = db_result.get('error')
                print(json.dumps(response, ensure_ascii=False), flush=True)
                sys.exit(5)  # DATABASE_ERROR
        else:
            # Sin inserción en BD, solo procesamiento
            processing_time = time.time() - start_time

            response["status"] = "SUCCESS"
            response["message"] = "CV procesado correctamente (sin inserción en BD)"
            response["data"] = {
                "candidate_name": candidate_name,
                "processing_time": round(processing_time, 2),
                "file_name": file_path.name,
                "json_structure": list(cv_data.keys())
            }

            logger.info("CV procesado sin inserción en BD")

            # Limpiar archivo temporal antes de salir con éxito
            if cleanup_temp and temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                    logger.info("Archivo temporal eliminado")
                except Exception as e:
                    logger.warning(f"No se pudo eliminar archivo temporal: {e}")

            print(json.dumps(response, ensure_ascii=False), flush=True)
            sys.exit(0)

    except KeyboardInterrupt:
        response["message"] = "Procesamiento interrumpido por el usuario"
        print(json.dumps(response, ensure_ascii=False), flush=True)
        sys.exit(99)
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)
        response["message"] = "Error inesperado durante el procesamiento"
        response["data"]["error"] = str(e)
        print(json.dumps(response, ensure_ascii=False), flush=True)
        sys.exit(99)  # UNKNOWN_ERROR


def main() -> None:
    """Punto de entrada principal con modo dual."""
    parser = argparse.ArgumentParser(
        description='CV Processor - Extracción y análisis de currículums',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  Modo CLI (default):
    python main.py --file cv.pdf
    python main.py --file cv.pdf --save-json
    python main.py --file cv.pdf --skip-database
    
Códigos de salida:
  0: SUCCESS
  1: FILE_NOT_FOUND
  2: EXTRACTION_ERROR
  3: AI_SERVICE_ERROR
  4: VALIDATION_ERROR
  5: DATABASE_ERROR
  99: UNKNOWN_ERROR
        """
    )

    parser.add_argument(
        '--file',
        type=str,
        help='Ruta al archivo CV a procesar (requerido en modo CLI)'
    )

    # Opciones adicionales para modo CLI
    parser.add_argument(
        '--save-json',
        action='store_true',
        default=True,  # Añadir esto
        help='Guardar JSON procesado en storage'
    )

    parser.add_argument(
        '--skip-database',
        action='store_true',
        help='Procesar CV sin insertar en base de datos'
    )

    parser.add_argument(
        '--config',
        type=str,
        help='Archivo de configuración alternativo (no implementado)'
    )

    parser.add_argument(
        '--stdin',
        action='store_true',
        help='Leer archivo desde stdin como bytes'
    )

    # Parsear argumentos
    args = parser.parse_args()

    # Validar que sea CLI con file o stdin
    if args.stdin and args.file:
        parser.error("No se puede usar --stdin y --file al mismo tiempo")
    if not args.stdin and not args.file:
        parser.error("Debe especificar --file o --stdin en modo CLI")

    run_cli_mode(args)


if __name__ == "__main__":
    main()