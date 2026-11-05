#!/usr/bin/env python3
"""
Módulo de inserción de datos de CVs en Microsoft SQL Server.
Implementa la lógica transaccional para insertar datos desde JSON a la BD,
respetando las reglas de negocio y validaciones definidas en las reuniones.
"""

# Standard library imports
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

# Third-party imports
import pyodbc

# Project imports
from .db_config import DatabaseConfig
from .db_schema import SchemaManager
from .db_validator import DuplicateValidator, CatalogValidator, ExperienceValidator

from config.settings import get_logger, DB_AUTOCOMMIT

# Importar mixins desde el subdirectorio db_inserter_dir
from .db_inserter_dir.direcciones import DireccionesManager
from .db_inserter_dir.candidato import CandidatoInserter
from .db_inserter_dir.catalogos import CatalogosManager
from .db_inserter_dir.conocimientos import ConocimientosInserter
from .db_inserter_dir.experiencia import ExperienciaInserter
from .db_inserter_dir.formacion import FormacionInserter
from .db_inserter_dir.idiomas import IdiomasInserter
from .db_inserter_dir.utils import format_date_for_sql,  insertar_texto_cv

# Logger específico para inserción
logger = get_logger(__name__)


# * Gestor de inserción de CVs en la base de datos.
class CVInserter(CandidatoInserter, CatalogosManager, ConocimientosInserter,
                 ExperienciaInserter, FormacionInserter, IdiomasInserter, DireccionesManager):

    """
    Clase principal que orquesta la inserción de CVs utilizando mixins especializados.

    Hereda de múltiples mixins que proporcionan funcionalidad específica:
    - CandidatoInserter: Inserción de candidatos
    - CatalogosManager: Gestión de catálogos maestros
    - ConocimientosInserter: Inserción de conocimientos
    - ExperienciaInserter: Inserción de experiencias profesionales
    - FormacionInserter: Inserción de formación académica
    - IdiomasInserter: Inserción de idiomas

    Implementa:
    - Inserción transaccional con rollback automático
    - Validación contra catálogos existentes
    - Detección de duplicados
    - Creación controlada de elementos auxiliares
    """

    # * Inicializa todas las dependencias necesarias para la correcta inserción de datos
    def __init__(self, db_config: DatabaseConfig = None):

        """
        Inicializa el insertor de CVs con todas sus dependencias.

        Args:
            db_config: Configuración de la base de datos. Si no se proporciona,
                      se crea una nueva instancia.
        """

        # Configurar la conexión a base de datos. Si no se pasa, se crea una nueva instancia
        self.db_config = db_config or DatabaseConfig()

        # Inicializar el gestor de esquemas de BD que maneja catálogos y estructura
        self.schema_manager = SchemaManager(self.db_config)

        # ---------------------------------------------------------------------------------------------- #

        # ? Inicializar validadores especializados

        # Validador de duplicados: verifica si el candidato ya existe por DNI/email/teléfono
        self.dup_validator = DuplicateValidator(self.db_config)

        # Validador de catálogos: verifica habilidades, idiomas contra tablas maestras
        self.cat_validator = CatalogValidator(self.db_config, self.schema_manager)

        # Validador de experiencias: clasifica entre experiencia profesional vs. prácticas
        self.exp_validator = ExperienceValidator(self.db_config)

        # ---------------------------------------------------------------------------------------------- #

        # ID del usuario sistema para campos de auditoría (UsuarioAlta, UsuarioModificacion). Debe existir
        self.default_user_id = 1

        # Diccionario para tracking de estadísticas del procesamiento
        self.stats = {'candidatos_insertados': 0, 'duplicados_detectados': 0, 'errores': 0, 'warnings': []}

        # Log de inicialización exitosa
        logger.info("CVInserter inicializado correctamente")

    # * Ejecuta el proceso completo de inserción de un CV con validaciones, orden referencial y manejo de errores
    def insert_cv_data(self, json_data: Dict[str, Any], json_filename: str) -> Dict[str, Any]:

        """
        Proceso principal de inserción completa de un CV en la base de datos.

        Implementa el flujo crítico de inserción respetando integridad referencial:
        validación de duplicados, inserción secuencial de candidato y relaciones,
        manejo transaccional con rollback automático en errores.

        Args:
            json_data (Dict[str, Any]): Datos estructurados del CV extraídos por IA
                con secciones: datos_contacto, experiencia_profesional, formacion,
                idiomas, habilidades
            json_filename (str): Nombre del archivo JSON para trazabilidad

        Returns:
            Dict[str, Any]: Resultado de la operación:
                - status: 'exitoso' | 'duplicado' | 'error'
                - candidato_id: ID generado o existente
                - warnings: Lista de advertencias no críticas
                - message: Descripción del resultado

        Raises:
            Exception: Errores críticos se capturan, registran y retornan como status 'error'

        Note:
            - Orden de inserción crítico para FKs: candidato → experiencias → formación → idiomas → conocimientos
            - Prácticas académicas se redirigen automáticamente a formación
            - Transacciones con rollback automático en fallos
        """

        # Inicializar variables de control y seguimiento
        candidato_id = None
        warnings = []

        try:
            logger.info(f"Iniciando inserción de CV desde: {json_filename}")

            # Obtener conexión transaccional con auto-manejo de recursos
            with self.db_config.get_connection() as conn:
                cursor = conn.cursor()

                # ? FASE 1: Validación de duplicados antes de cualquier inserción

                logger.debug("Verificando duplicados...")
                existing_id = self.dup_validator.check_candidate_exists(json_data.get('datos_contacto', {}))

                # Candidato ya existe - retornar información sin procesar
                if existing_id:
                    logger.warning(f"Candidato duplicado detectado. ID existente: {existing_id}")
                    self.stats['duplicados_detectados'] += 1
                    return {'status': 'duplicado', 'candidato_id': existing_id, 'message': f'Candidato existente con ID {existing_id}'}

                # ? FASE 2: Cálculo previo de duración total para campo obligatorio del candidato

                experiencias = json_data.get('experiencia_profesional', [])
                duracion_total = int(experiencias[0].get('duracion', 0)) if experiencias else 0

                # ? FASE 2.5: Identificar y preparar el último puesto del candidato

                ultimo_puesto_id = None
                ultimo_puesto_nombre = self.get_ultimo_puesto(experiencias)

                # Crear o buscar el puesto en el catálogo antes de insertar el candidato
                if ultimo_puesto_nombre:
                    ultimo_puesto_id = self._get_or_create_puesto_categoria_profesional(ultimo_puesto_nombre, cursor)
                    logger.info(f"Último puesto identificado: '{ultimo_puesto_nombre}' (ID: {ultimo_puesto_id})")

                # ? FASE 3: Inserción del candidato principal con duración calculada

                logger.debug("Insertando candidato...")

                # Enriquecer datos de contacto con duración total calculada
                datos_contacto_completos = json_data.get('datos_contacto', {}).copy()
                datos_contacto_completos['duracion_experiencia_total'] = duracion_total

                # Asignar el ID del último puesto al candidato
                datos_contacto_completos['id_puesto'] = ultimo_puesto_id

                # Insertar candidato usando mixin especializado
                candidato_id = self._insert_candidato(datos_contacto_completos, cursor)

                # Avisar si el proceso no se ejecuta con éxito
                if not candidato_id:
                    raise ValueError("No se pudo obtener el ID del candidato insertado")

                logger.info(f"Candidato insertado con ID: {candidato_id}")

                # ? FASE 3.5: Insertar el texto parseado del CV en la tabla CandidatosCv
                logger.debug("Insertando texto parseado del CV...")

                # Llamar a la función para insertar el texto del CV
                texto_insertado = insertar_texto_cv(json_data, candidato_id, conn)

                if texto_insertado:
                    logger.info(f"Texto del CV insertado correctamente para candidato {candidato_id}")
                else:
                    warnings.append("No se pudo insertar el texto del CV en CandidatosCv")
                    logger.warning(f"Fallo al insertar texto CV para candidato {candidato_id}")

                # El código completo de esa sección quedaría así:

                logger.info(f"Candidato insertado con ID: {candidato_id}")

                # ? FASE 4: Procesamiento diferenciado de experiencias vs prácticas académicas
                exp_count = 0
                practica_count = 0

                for exp in experiencias:

                    # Aplicar regla de negocio: prácticas van a formación, experiencias a tabla específica
                    if exp.get('es_practica', False):
                        practica_count += 1
                        self._insert_practica_como_formacion(candidato_id, exp, cursor)

                    # Insertar como experiencia profesional válida
                    else:
                        exp_id = self._insert_experiencia(candidato_id, exp, cursor)
                        if exp_id:
                            exp_count += 1

                            # Procesar proyectos asociados a la experiencia
                            for proyecto in exp.get('proyectos', []):
                                self._insert_proyecto(exp_id, proyecto, cursor)

                logger.debug(f"Insertadas {exp_count} experiencias y {practica_count} prácticas")

                # ? FASE 5: Inserción de formación académica reglada
                formacion_list = json_data.get('formacion', [])
                resultado = self.procesar_formacion_y_titulacion(candidato_id, formacion_list, cursor)
                logger.debug(f"Insertadas {resultado['formaciones_insertadas']} formaciones")

                # ? FASE 6: Inserción de idiomas con validación estricta contra catálogo oficial
                idiomas = json_data.get('idiomas', [])
                idiomas_result = self._insert_idiomas(candidato_id, idiomas, cursor)

                # Registrar idiomas rechazados como warning no crítico
                if idiomas_result['rechazados']:
                    warnings.append(f"Idiomas no catalogados: {idiomas_result['rechazados']}")

                # ? FASE 7: Inserción de conocimientos aplicando políticas diferenciadas por categoría
                habilidades = json_data.get('habilidades', {})
                conoc_result = self._insert_conocimientos(candidato_id, habilidades, cursor)

                # Registrar conocimientos rechazados/pendientes como warnings
                if conoc_result['tecnicos_rechazados']:
                    warnings.append(f"Conocimientos técnicos no catalogados: {conoc_result['tecnicos_rechazados']}")
                if conoc_result['negocio_rechazados']:
                    warnings.append(f"Conocimientos negocio no catalogados: {conoc_result['negocio_rechazados']}")
                if conoc_result['sin_especificar']:
                    warnings.append(
                        f"Conocimientos sin especificar (pendientes revisión): {conoc_result['sin_especificar']}")

                # ? FASE 8: Confirmación transaccional si autocommit está deshabilitado
                if not DB_AUTOCOMMIT:
                    conn.commit()

                # Actualizar estadísticas de éxito y registrar resultado final
                self.stats['candidatos_insertados'] += 1
                logger.info(f"✅ CV insertado exitosamente. ID: {candidato_id}")

                return {'status': 'exitoso', 'candidato_id': candidato_id,' warnings': warnings, 'message': f'CV insertado con ID {candidato_id}'}

        # Manejo de errores con rollback automático y logging detallado
        except Exception as e:
            logger.error(f"Error insertando CV: {e}")

            # Intentar rollback si la conexión está disponible y autocommit deshabilitado
            try:
                if 'conn' in locals() and not DB_AUTOCOMMIT:
                    conn.rollback()
            except:
                pass

            # Actualizar estadísticas de error
            self.stats['errores'] += 1

            return {'status': 'error', 'candidato_id': candidato_id, 'error': str(e), 'message': f'Error al procesar CV: {str(e)}'}

    # * Proporciona estadísticas acumuladas del proceso de inserción para análisis y debugging
    def get_stats(self) -> Dict[str, Any]:

        """
        Retorna estadísticas completas del procesamiento de CVs.

        Proporciona métricas detalladas sobre el rendimiento y resultados
        del proceso de inserción, incluyendo contadores de éxitos, errores
        y elementos procesados por categoría.

        Returns:
            Dict[str, Any]: Diccionario con estadísticas del procesamiento:
                - candidatos_insertados (int): Número de candidatos procesados exitosamente
                - duplicados_detectados (int): Candidatos rechazados por duplicación
                - errores_insercion (int): Fallos durante el proceso de inserción
                - idiomas_insertados (int): Total de idiomas válidos procesados
                - conocimientos_insertados (int): Suma de todas las categorías de skills
                - warnings (List[str]): Lista de advertencias generadas

        Note:
            - Retorna copia independiente para evitar modificaciones externas
            - Las estadísticas se actualizan automáticamente durante cada inserción
            - Útil para monitoreo de rendimiento y análisis de calidad de datos
        """

        # Retornar copia defensiva de las estadísticas internas para evitar mutaciones externas
        return self.stats.copy()

    # * Reinicia contadores y métricas de operaciones a valores iniciales para nueva sesión de procesamiento
    def reset_stats(self) -> None:

        """
        Reinicia las estadísticas de procesamiento a sus valores iniciales.

        Restablece todos los contadores de operaciones (inserciones exitosas, duplicados
        detectados, errores) y limpia la lista de warnings acumulados. Utilizado para
        iniciar sesiones de procesamiento limpio o después de reportes estadísticos.

        Returns:
            None: Métoodo de reinicio sin valor de retorno

        Note:
            - Mantiene la estructura original del diccionario de estadísticas
            - Registra la operación en logs para trazabilidad de sesiones
        """

        # Restablecer diccionario de estadísticas con contadores en cero
        self.stats = {'candidatos_insertados': 0, 'duplicados_detectados': 0, 'errores': 0, 'warnings': []}

        # Registrar reinicio para trazabilidad de sesiones
        logger.info("Estadísticas reiniciadas")
