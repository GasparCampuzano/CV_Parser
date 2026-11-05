
# src/azure_openai_client.py

"""
Cliente para Azure OpenAI API - CV Processor
Maneja la comunicación con Azure OpenAI para extracción de datos de CVs.
"""

# Librerías estándar de Python
import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# Dependencias externas
import requests

# Inicializar logger específico para este módulo
logger = logging.getLogger(__name__)

# Incluir el directorio padre en PYTHONPATH para permitir la importación de config
sys.path.insert(0, str(Path(__file__).parent.parent))

# Importar configuración global de la aplicación
from config.settings import (
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION,
    DEPLOYMENT_NAME, MAX_TOKENS, TEMPERATURE, AI_TIMEOUT, AI_MAX_RETRIES
)

# Importar generadores de prompts para distintas secciones del CV
from prompt_query import (
    create_contacto_prompt, create_habilidades_prompt, create_experiencia_prompt,
    create_idiomas_prompt, create_formacion_prompt
)

# * Verifica si Azure OpenAI está disponible
def check_azure_openai_status() -> bool:

    """
    Verificar si Azure OpenAI está disponible probando directamente el deployment.

    Returns:
        bool: True si Azure OpenAI está disponible, False en caso contrario
    """

    try:
        # Construcción de cabeceras con API Key y tipo de contenido
        headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}

        # Payload mínimo para validar el servicio
        test_payload = {"messages": [{"role": "user", "content": "Hello"}], "max_tokens": 10}

        # Construcción de la URL completa hacia el endpoint del deployment
        url = f"{AZURE_OPENAI_ENDPOINT}openai/deployments/{DEPLOYMENT_NAME}/chat/completions?api-version={AZURE_OPENAI_API_VERSION}"

        # Log de depuración con la URL del servicio
        logger.debug(f"Verificando estado de Azure OpenAI en: {url}")

        # Enviar la petición POST con timeout configurado
        response = requests.post(url, headers=headers, json=test_payload, timeout=AI_TIMEOUT)

        # Evaluar el código de estado de la respuesta
        if response.status_code == 200:
            logger.info(f"[OK] Azure OpenAI activo - Deployment: {DEPLOYMENT_NAME}")
            return True
        elif response.status_code == 404:
            logger.error(f"[ERROR] Deployment '{DEPLOYMENT_NAME}' no encontrado")
            logger.debug(f"Response: {response.text}")
            return False
        elif response.status_code == 401:
            logger.error("[ERROR] Autenticación fallida - API Key inválida")
            return False
        else:
            logger.warning(f"[WARN] Respuesta inesperada: {response.status_code}")
            logger.debug(f"Response: {response.text}")
            return False

    # Errores de conexión o red
    except requests.exceptions.RequestException as e_1:
        logger.error(f"[ERROR] Error de conexión: {e_1}")
        return False

    # Cualquier otro error inesperado
    except Exception as e_1:
        logger.error(f"[ERROR] Error inesperado verificando Azure OpenAI: {e_1}")
        return False

# * Parsea y limpia la respuesta cruda de Azure OpenAI con manejo robusto de errores
def parse_azure_openai_response(raw_response: str) -> Optional[Dict[str, Any]]:

    # Verificar que la respuesta no esté vacía
    if not raw_response:
        logger.warning("Respuesta vacía recibida")
        return None

    # Limpiar espacios iniciales y finales antes de procesar
    cleaned_response = raw_response.strip()

    # Quitar marcadores de inicio de bloque de código (```json o ```)
    if cleaned_response.startswith('```json'):
        cleaned_response = cleaned_response[7:]
    elif cleaned_response.startswith('```'):
        cleaned_response = cleaned_response[3:]

    # Quitar marcador de cierre de bloque de código (```)
    if cleaned_response.endswith('```'):
        cleaned_response = cleaned_response[:-3]

    # Limpieza final de espacios en blanco
    cleaned_response = cleaned_response.strip()

    # Intentar parsear la cadena limpia como JSON
    try:
        parsed_json = json.loads(cleaned_response)
        logger.debug("[OK] JSON parseado correctamente")
        return parsed_json

    # Manejo de error si la respuesta no es un JSON válido
    except json.JSONDecodeError as e:
        logger.error(f"[ERROR INESPERADO] JSON malformado de Azure OpenAI: {e}")
        logger.error(f"Response problemática: {raw_response[:500]}...")

        # Intento de fallback: extraer solo el bloque JSON válido usando regex
        try:
            import re
            json_match = re.search(r'\{.*}', cleaned_response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))

        # Error persistente al intentar el fallback
        except (json.JSONDecodeError, AttributeError):
            pass

        # Si tras esto falla, devolver None
        return None

# * Función auxiliar que realiza una llamada individual a la API de Azure OpenAI
def make_api_call(prompt: str, extraction_name: str, url: str, headers: dict, max_retries: int) -> Optional[Dict]:

    """Realiza una llamada individual a la API de Azure OpenAI"""

    # Construcción del payload con configuración del modelo
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "top_p": 0.9,
        "frequency_penalty": 0,
        "presence_penalty": 0
    }

    # Reintentar la petición hasta max_retries veces en caso de fallo
    for attempt in range(max_retries):

        try:

            logger.info(f"Extrayendo {extraction_name} (intento {attempt + 1}/{max_retries})...")

            # Enviar solicitud HTTP POST a la API
            response = requests.post(url, headers=headers, json=payload, timeout=AI_TIMEOUT)

            # Si la respuesta HTTP es exitosa
            if response.status_code == 200:

                # Convertir la respuesta en JSON y obtener 'choices'
                response_data = response.json()
                choices = response_data.get('choices', [])

                # Verificar si existen resultados en 'choices'
                if choices:

                    # Extraer y limpiar el contenido de la primera respuesta
                    raw_response = choices[0].get('message', {}).get('content', '').strip()

                    # Log de depuración con longitud de la respuesta
                    logger.debug(f"{extraction_name}: Respuesta de {len(raw_response)} caracteres")

                    # Parsear y validar la respuesta obtenida
                    parsed_data = parse_azure_openai_response(raw_response)

                    # Log de depuración sobre el éxito de la extracción
                    if parsed_data:
                        logger.info(f"✓ {extraction_name} extraído correctamente")
                        return parsed_data
                    else:
                        logger.warning(f"No se pudo parsear la respuesta para {extraction_name}")

                # Si no existen resultados en 'choices', reportar el error
                else:
                    logger.error(f"No se encontraron 'choices' para {extraction_name}")

            # Si la respuesta HTTP no es exitosa
            else:

                # Manejo de errores comunes según código HTTP
                error_handlers = {
                    401: "Error de autenticación. Verifica tu API key.",
                    404: f"Deployment '{DEPLOYMENT_NAME}' no encontrado.",
                    429: "Rate limit alcanzado. Esperando antes del siguiente intento...",
                    500: "Error interno del servidor Azure OpenAI.",
                    503: "Servicio temporalmente no disponible."
                }

                # Reportar mensaje de error correspondiente
                error_msg = error_handlers.get(response.status_code, f"Error HTTP {response.status_code}")
                logger.error(f"{extraction_name}: {error_msg}")

        # Timeout en la petición
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout extrayendo {extraction_name} en intento {attempt + 1}")

        # Error de red o conexión
        except requests.exceptions.RequestException as e:
            logger.error(f"Error de conexión extrayendo {extraction_name}: {e}")

        # Cualquier error inesperado
        except Exception as e:
            logger.error(f"Error inesperado extrayendo {extraction_name}: {e}", exc_info=True)

        # Esperar con backoff exponencial antes del siguiente intento
        if attempt < max_retries - 1:
            wait_time = min(2 ** attempt, 16)
            logger.info(f"Esperando {wait_time}s antes del siguiente intento...")
            time.sleep(wait_time)

    # Si todos los intentos fallan, devolver None
    return None

# * Envía texto del CV a Azure OpenAI y devuelve datos estructurados
def send_to_azure_openai(cv_text: str, max_retries: Optional[int] = None) -> Optional[str]:

    """
    Enviar texto del CV a Azure OpenAI y obtener datos estructurados.

    Args:
        cv_text (str): Texto extraído del CV
        max_retries (int, optional): Número máximo de reintentos. Si no se especifica, usa AI_MAX_RETRIES

    Returns:
        str: JSON estructurado con todos los datos extraídos o None si falla
    """

    # Usar valor por defecto de settings si no se especifica max_retries
    if max_retries is None:
        max_retries = AI_MAX_RETRIES

    # Verificar que el servicio Azure OpenAI esté disponible
    if not check_azure_openai_status():
        logger.error("Azure OpenAI no está disponible")
        return None

    # Validar que el texto del CV tenga contenido suficiente
    if not cv_text or len(cv_text.strip()) < 50:
        logger.warning("Texto del CV muy corto o vacío")
        return None

    # Diccionario final que contendrá todos los datos extraídos
    output_json = {}
    current_date = str(datetime.now())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    original_filename = "CV_procesado.pdf"

    # Configuración común para todas las llamadas a la API
    headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}
    url = f"{AZURE_OPENAI_ENDPOINT}openai/deployments/{DEPLOYMENT_NAME}/chat/completions?api-version={AZURE_OPENAI_API_VERSION}"

    # Definición de las secciones a extraer del CV
    extractions = [
        {"name": "datos_contacto", "prompt_function": create_contacto_prompt, "required": True},
        {"name": "habilidades", "prompt_function": create_habilidades_prompt, "required": False},
        {"name": "experiencia_profesional", "prompt_function": create_experiencia_prompt, "required": False},
        {"name": "idiomas", "prompt_function": create_idiomas_prompt, "required": False},
        {"name": "formacion", "prompt_function": create_formacion_prompt, "required": False}
    ]

    # Inicio del proceso de extracción
    logger.info("=" * 50)
    logger.info("Iniciando extracción completa del CV")
    logger.info("=" * 50)

    # Lista para registrar extracciones obligatorias que fallan
    failed_extractions = []

    # Iterar sobre todas las extracciones configuradas
    for extraction in extractions:


        try:
            # Crear prompt específico para la sección
            prompt = extraction["prompt_function"](cv_text, current_date)

            # Realizar la llamada a la API
            result = make_api_call(prompt, extraction["name"], url, headers, max_retries)

            # Si la API devolvió resultado válido
            if result:

                # Procesar datos de contacto
                if extraction["name"] == "datos_contacto":
                    output_json["datos_contacto"] = result.get("datos_contacto", {})

                # Procesar habilidades
                elif extraction["name"] == "habilidades":
                    output_json["habilidades"] = result.get("habilidades", {
                        "conocimientos_tecnicos": [], "conocimientos_negocio": [], "otros_conocimientos": [], "conocimientos_sin_especificar": []
                    })

                # Procesar experiencia profesional
                elif extraction["name"] == "experiencia_profesional":
                    experiencias = result.get("experiencia_profesional", [])
                    output_json["experiencia_profesional"] = experiencias

                    # Calcular duración total de la experiencia (en meses/años según prompt)
                    duracion_total = 0
                    for exp in experiencias:
                        if exp.get("duracion"):
                            try:
                                duracion_total += int(exp["duracion"])
                            except (ValueError, TypeError):
                                pass

                    output_json["duracion_experiencia_total"] = duracion_total

                # Procesar idiomas
                elif extraction["name"] == "idiomas":
                    output_json["idiomas"] = result.get("idiomas", [])

                # Procesar formación académica
                elif extraction["name"] == "formacion":
                    output_json["formacion"] = result.get("formacion", [])

            else:

                # Manejar fallo en extracción obligatoria
                if extraction["required"]:
                    logger.error(f"⚠ Fallo en extracción obligatoria: {extraction['name']}")
                    failed_extractions.append(extraction["name"])

                # Manejar fallo en extracción no obligatoria
                else:
                    logger.warning(f"No se pudo extraer {extraction['name']} (no obligatorio)")
                    if extraction["name"] == "idiomas":
                        output_json["idiomas"] = []

        # Manejo de errores inesperados en el procesamiento de cada extracción
        except Exception as e:
            logger.error(f"Error procesando {extraction['name']}: {e}")
            if extraction["required"]:
                failed_extractions.append(extraction["name"])

    # Verificar si hubo extracciones obligatorias fallidas
    if failed_extractions:
        logger.error(f"Extracciones fallidas: {', '.join(failed_extractions)}")
        logger.warning("Se continuará con los datos extraídos parcialmente")

    # Extraer el nombre base sin extensión
    if original_filename:
        base_name = os.path.splitext(original_filename)[0]
        unique_filename = f"cv_{timestamp}_{base_name}.json"
    else:
        unique_filename = f"cv_{timestamp}_sin_nombre.json"

    # Agregar metadatos generales al resultado
    output_json["_metadata"] = {
        "archivo_original": unique_filename,
        "fecha_procesamiento": datetime.now().isoformat(),
        "caracteres_extraidos": len(cv_text),
        "Original Text": cv_text
    }

    # Validar que al menos se hayan obtenido los datos de contacto
    if not output_json.get("datos_contacto"):
        logger.error("No se pudieron extraer ni siquiera los datos de contacto. Proceso fallido.")
        return None

    # Finalizar proceso de extracción
    logger.info("=" * 50)
    logger.info("Extracción completada")
    logger.info(f"Secciones extraídas: {len(output_json) - 1}")  # -1 por metadata
    logger.info("=" * 50)

    # Convertir resultado final a JSON string
    try:
        json_output = json.dumps(output_json, ensure_ascii=False, indent=2)
        return json_output
    except Exception as e:
        logger.error(f"Error convirtiendo resultado a JSON: {e}")
        return None
