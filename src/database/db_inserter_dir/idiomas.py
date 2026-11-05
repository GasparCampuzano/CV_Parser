#!/usr/bin/env python3
"""
Mixin para inserción de idiomas del candidato.
"""

# Importación de librerías estándar y utilidades de tipado
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
import pyodbc

# Añade el directorio raíz del proyecto al PYTHONPATH
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Importa el logger desde la configuración del proyecto
from config.settings import get_logger
logger = get_logger(__name__)

# * Mixin especializado para gestionar la inserción de idiomas de candidatos en la base de datos
class IdiomasInserter:

    """
    Mixin para la inserción y gestión de idiomas del candidato en la base de datos.

    Este mixin proporciona funcionalidad especializada para:
    - Validar idiomas contra el catálogo oficial de idiomas soportados
    - Insertar registros en la tabla relacional CandidatosIdiomas
    - Gestionar niveles de competencia lingüística (Básico, Intermedio, Avanzado, Nativo)
    - Controlar duplicados y violaciones de integridad referencial
    - Proporcionar trazabilidad completa de operaciones mediante logging

    Dependencias:
    - cat_validator: Validador de catálogos para verificar idiomas oficiales
    - default_user_id: ID del usuario del sistema para auditoría
    - Conexión activa a base de datos SQL Server mediante pyodbc
    """

    # * Método privado para obtener el ID de un nivel de idioma desde la base de datos
    def _get_nivel_idioma(self, nivel_descripcion: str, cursor) -> Optional[int]:
        """
        Recupera el identificador (ID) asociado a un nivel de idioma desde la base de datos.

        Mapea descripciones comunes a los niveles estándar almacenados en la tabla NivelIdiomas:
        - Certificaciones oficiales: A1, A2, B1, B2, C1, C2
        - Niveles subjetivos: Bajo, Bajo-Medio, Medio, Medio-Alto, Alto

        Args:
            nivel_descripcion (str): Descripción del nivel (ej: "Intermedio", "B2", "Avanzado")
            cursor: Cursor activo de la conexión a la base de datos

        Returns:
            Optional[int]: ID del nivel si se encuentra, 1 (Bajo) como valor por defecto
        """

        # Si no se proporciona descripción, retornar None para manejar después
        if not nivel_descripcion:
            logger.debug("Nivel de idioma vacío, usando valor por defecto")
            return None

        # Normalizar la entrada: eliminar espacios y convertir a minúsculas
        nivel_str = str(nivel_descripcion).strip().lower()

        # Diccionario completo de mapeo de términos comunes a niveles estándar de la BD
        # Diccionario de mapeo reducido - solo términos esenciales
        # Diccionario de mapeo reducido - incluye mayúsculas correctas
        nivel_map = {
            # === CERTIFICACIONES (mayúsculas y minúsculas) ===
            'a1': 'A1',
            'a2': 'A2',
            'b1': 'B1',
            'b2': 'B2',
            'c1': 'C1',
            'c2': 'C2',
            'A1': 'A1',
            'A2': 'A2',
            'B1': 'B1',
            'B2': 'B2',
            'C1': 'C1',
            'C2': 'C2',

            # === NIVELES ESTÁNDAR (con mayúsculas correctas) ===
            'bajo': 'Bajo',
            'bajo-medio': 'Bajo-Medio',
            'bajo medio': 'Bajo-Medio',
            'medio': 'Medio',
            'medio-alto': 'Medio-Alto',
            'medio alto': 'Medio-Alto',
            'alto': 'Alto',
            'nativo': 'Nativo',

            # Versiones con mayúsculas correctas (como las devolverá la IA)
            'Bajo': 'Bajo',
            'Bajo-Medio': 'Bajo-Medio',
            'Medio': 'Medio',
            'Medio-Alto': 'Medio-Alto',
            'Alto': 'Alto',
            'Nativo': 'Nativo',

            # === MAPEOS ESENCIALES (por si la IA falla) ===
            'básico': 'Bajo',
            'basico': 'Bajo',
            'elemental': 'Bajo',
            'principiante': 'Bajo',

            'intermedio': 'Medio',
            'intermedio bajo': 'Bajo-Medio',
            'intermedio-bajo': 'Bajo-Medio',
            'intermedio alto': 'Medio-Alto',
            'intermedio-alto': 'Medio-Alto',

            'avanzado': 'Alto',
            'fluido': 'Alto',
            'proficiente': 'Alto',

            'lengua materna': 'Nativo',
            'materno': 'Nativo',
            'bilingüe': 'Nativo',
            'bilingue': 'Nativo',

            # === INGLÉS BÁSICO (por compatibilidad) ===
            'native': 'Nativo',
            'basic': 'Bajo',
            'intermediate': 'Medio',
            'advanced': 'Alto',

            # === CERTIFICACIONES CAMBRIDGE ===
            'first': 'B2',
            'fce': 'B2',
            'cae': 'C1',
            'cpe': 'C2',
            'pet': 'B1',
            'ket': 'A2',
        }

        # Obtener el nivel mapeado
        nivel_normalizado = nivel_map.get(nivel_str)

        # Si no hay mapeo, intentar con la descripción original capitalizada
        if not nivel_normalizado:
            # Intentar buscar directamente si es un valor que ya existe en la BD
            nivel_normalizado = nivel_descripcion.strip()
            logger.debug(f"Nivel '{nivel_descripcion}' no mapeado, intentando búsqueda directa")

        try:
            # Consulta SQL para buscar el ID del nivel
            query = """
                SELECT IdNivelIdioma 
                FROM dbo.NivelIdiomas 
                WHERE LOWER(Descripcion) = LOWER(?)
            """

            # Intentar primero con el valor mapeado/normalizado
            cursor.execute(query, (nivel_normalizado,))
            result = cursor.fetchone()

            if result:
                logger.debug(f"Nivel encontrado: '{nivel_normalizado}' -> ID: {result[0]}")
                return result[0]

            # Si no se encuentra y es diferente del original, intentar con el original
            if nivel_normalizado.lower() != nivel_descripcion.strip().lower():
                cursor.execute(query, (nivel_descripcion.strip(),))
                result = cursor.fetchone()
                if result:
                    logger.debug(f"Nivel encontrado con descripción original: '{nivel_descripcion}' -> ID: {result[0]}")
                    return result[0]

            # Si no se encuentra ninguna coincidencia, buscar el ID de "Bajo" como default
            logger.warning(f"Nivel '{nivel_descripcion}' no encontrado en BD. Usando 'Bajo' por defecto")
            cursor.execute(query, ('Bajo',))
            result = cursor.fetchone()

            if result:
                return result[0]
            else:
                # Si ni siquiera existe "Bajo", retornar 1 como fallback absoluto
                logger.error("No se encuentra el nivel 'Bajo' en la BD. Usando ID=1 como fallback")
                return 1

        except Exception as e:
            logger.error(f"Error obteniendo nivel de idioma para '{nivel_descripcion}': {e}")
            return 1

    # * Método principal para procesar e insertar idiomas del candidato en la base de datos
    def _insert_idiomas(self, candidato_id: int, idiomas: List[Dict[str, str]], cursor: pyodbc.Cursor) -> Dict[str, Any]:

        """
        Procesa e inserta idiomas del candidato aplicando validación contra catálogo oficial.

        Solo se insertan idiomas que existen en el catálogo de idiomas oficiales y cooficiales.
        Los idiomas duplicados se detectan automáticamente y se registran como warnings.

        Args:
            candidato_id (int): Identificador único del candidato en la base de datos
            idiomas (List[Dict[str, str]]): Lista de diccionarios con datos de idiomas extraídos del CV
                Estructura esperada: [{'idioma': 'Español', 'nivel': 'Nativo'}, ...]
            cursor (pyodbc.Cursor): Cursor activo de conexión a SQL Server para ejecutar consultas

        Returns:
            Dict[str, Any]: Diccionario con resultados de la operación:
                {
                    'insertados': List[str] - Nombres de idiomas insertados exitosamente
                    'rechazados': List[str] - Nombres de idiomas rechazados por validación
                }

        Raises:
            Exception: Errores críticos durante la inserción se capturan y registran

        Note:
            - Los idiomas no catalogados se rechazan automáticamente
            - Se aplica nivel 'Básico' por defecto si no se especifica
            - Duplicados generan warning pero no interrumpen el proceso
        """

        # Inicializar listas para idiomas insertados con éxito e idiomas rechazados
        insertados = []
        rechazados = []

        try:
            # ? FASE 1: VALIDACIÓN CONTRA CATÁLOGO OFICIAL

            # Validar idiomas contra catálogo oficial y separar válidos de rechazados
            idiomas_validos, idiomas_rechazados = self.cat_validator.validate_languages(idiomas)
            rechazados = idiomas_rechazados

            # ? FASE 2: PROCESAMIENTO ITERATIVO DE IDIOMAS VÁLIDOS

            # Procesar cada idioma que superó la validación del catálogo
            for idioma_data in idiomas_validos:

                # Obtener el nivel desde el JSON original (prioridad) o datos procesados
                nivel_descripcion = (
                        idioma_data.get('nivel') or  # Nivel original del JSON
                        idioma_data.get('nivel_descripcion')  # Nivel procesado por el validador
                )

                # Log para debugging del nivel original
                logger.debug(f"Procesando idioma: {idioma_data.get('idioma_nombre', 'Desconocido')}, "
                             f"Nivel recibido: {nivel_descripcion}")

                # Convertir descripción textual del nivel a ID numérico usando el método interno
                nivel_id = self._get_nivel_idioma(nivel_descripcion, cursor)

                # Si no se pudo determinar el nivel, usar valor por defecto
                if not nivel_id:
                    logger.warning(f"No se pudo determinar nivel para '{nivel_descripcion}'. "
                                   f"Buscando nivel 'Bajo' por defecto")
                    # Intentar obtener el ID de "Bajo" como fallback
                    nivel_id = self._get_nivel_idioma('Bajo', cursor)
                    if not nivel_id:
                        nivel_id = 1  # Fallback absoluto

                logger.debug(f"Nivel ID resuelto: {nivel_id} para descripción: '{nivel_descripcion}'")

                # Definir consulta SQL parametrizada con campos de auditoría obligatorios
                query = """
                    INSERT INTO dbo.CandidatosIdiomas (
                        IdCandidato,           -- FK al candidato
                        IdIdioma,              -- FK al idioma del catálogo
                        IdNivelIdioma,         -- FK al nivel del idioma
                        FechaModificacion,     -- Timestamp de modificación
                        UsuarioModificacion,   -- ID del usuario que modifica
                        FechaAlta,             -- Timestamp de creación
                        UsuarioAlta            -- ID del usuario que crea
                    )
                    VALUES (?, ?, ?, GETDATE(), ?, GETDATE(), ?)
                """

                # Preparar tupla de parámetros para ejecución segura de la consulta SQL
                values = (
                    candidato_id,
                    idioma_data['idioma_id'],
                    nivel_id,
                    self.default_user_id,
                    self.default_user_id
                )

                try:
                    # Ejecutar la inserción del idioma
                    cursor.execute(query, values)

                    # Si llegamos aquí, la inserción fue exitosa
                    idioma_nombre = idioma_data.get('idioma_nombre', 'Idioma desconocido')
                    insertados.append(f"{idioma_nombre} (Nivel: {nivel_descripcion or 'Bajo'})")
                    logger.info(f"Idioma insertado exitosamente: {idioma_nombre} - "
                                f"Nivel: {nivel_descripcion or 'Bajo'} (ID: {nivel_id})")

                # Error 'Violación de constraint UNIQUE o PRIMARY KEY' producido si ya existe el candidato-idioma
                except pyodbc.IntegrityError:
                    logger.warning(
                        f"Idioma ya existe para candidato: {idioma_data.get('idioma_nombre', 'Idioma desconocido')}")

            # Log del resumen de la operación
            logger.info(f"Idiomas: {len(insertados)} insertados, {len(rechazados)} rechazados")

        # Capturar cualquier error no previsto durante el procesamiento
        except Exception as e:
            logger.error(f"Error insertando idiomas: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

        # Retornar diccionarios con las listas de nombres de idiomas insertados y nombres de idiomas rechazados
        return {'insertados': insertados, 'rechazados': rechazados}
