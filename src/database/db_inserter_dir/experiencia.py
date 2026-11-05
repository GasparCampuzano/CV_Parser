#!/usr/bin/env python3
"""
Mixin para inserción de experiencias profesionales y prácticas.
"""

# Importación de librerías estándar y utilidades de tipado
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
import pyodbc
from datetime import datetime

# Añade el directorio raíz del proyecto al PYTHONPATH
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Importación de librería propia
from src.database.db_validator import ExperienceValidator
from .utils import format_date_for_sql

# Importa el logger desde la configuración del proyecto
from config.settings import get_logger
logger = get_logger(__name__)

# * Mixin especializado en la inserción de experiencias profesionales y prácticas académicas
class ExperienciaInserter:

    """
    Mixin especializado en la inserción de experiencias profesionales y prácticas académicas.

    Este mixin maneja la lógica de negocio para insertar diferentes tipos de experiencias
    en la base de datos, incluyendo la creación automática de entidades relacionadas
    (empresas, puestos) y el cálculo de duraciones sin solapamientos.

    Funcionalidades principales:
        - Inserción de experiencias profesionales con validación de datos
        - Conversión de prácticas académicas a registros de formación
        - Creación automática de empresas y puestos no catalogados
        - Cálculo automático de duración de experiencias

    Notas:
        - Implementa las reglas establecidas en las reuniones 4 y 5
        - Las prácticas se registran como formación, no como experiencia profesional
        - Requiere conexión activa a base de datos SQL Server
    """

    # * Calcula la duración total de experiencia profesional válida excluyendo prácticas
    def _calculate_total_experience_duration(self, experiencias: List[Dict[str, Any]]) -> int:

        """
        Calcula la duración acumulada de experiencia profesional válida.

        Implementa las reglas establecidas en las reuniones 4 y 5:
        - Solo cuenta experiencias profesionales con empresa y contrato
        - Excluye prácticas académicas, becas y contratos de formación
        - Suma duraciones ya calculadas previamente sin solapamientos

        Args:
            experiencias (List[Dict[str, Any]]): Lista de experiencias extraídas del CV
                con estructura: {'empresa': str, 'puesto': str, 'duracion': int,
                'es_practica': bool, ...}

        Returns:
            int: Duración total en meses de experiencia profesional válida

        Note:
            - Las duraciones ya vienen calculadas sin solapamientos por el validador
            - El campo 'es_practica' determina exclusión según reglas de negocio
            - Maneja errores de conversión retornando 0 para valores inválidos
        """

        # Inicializar contador de duración total acumulada
        duracion_total = 0

        # Iterar sobre cada experiencia para validación y suma
        for exp in experiencias:

            # Excluir prácticas del cálculo
            if exp.get('es_practica', False):
                continue

            # Validar existencia y sumar la duración previamente calculada al total
            if 'duracion' in exp and exp['duracion']:
                try:
                    duracion_total += int(exp['duracion'])
                except (ValueError, TypeError):
                    pass

        # Registrar resultado final para trazabilidad
        logger.info(f"Duración total calculada: {duracion_total} meses")
        return duracion_total

    def _calculate_duration_months(self, fecha_inicio_str: str, fecha_fin_str: Optional[str]) -> int:

        """
        Calcula la duración en meses entre dos fechas.
        Si fecha_fin es None (empleo actual), usa la fecha actual.

        Args:
            fecha_inicio_str: Fecha de inicio en formato YYYY-MM-DD
            fecha_fin_str: Fecha de fin en formato YYYY-MM-DD o None si es actual

        Returns:
            int: Número de meses de duración
        """

        try:
            # Parsear fecha de inicio
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')

            # Si no hay fecha fin, usar fecha actual
            if fecha_fin_str is None:
                fecha_fin = datetime.now()
                logger.debug(f"Experiencia actual - calculando desde {fecha_inicio_str} hasta hoy")
            else:
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d')

            # Calcular diferencia en meses
            # Fórmula: años_diferencia * 12 + meses_diferencia
            years_diff = fecha_fin.year - fecha_inicio.year
            months_diff = fecha_fin.month - fecha_inicio.month

            # Si el día del fin es menor que el día del inicio, restar un mes
            if fecha_fin.day < fecha_inicio.day:
                months_diff -= 1

            total_months = years_diff * 12 + months_diff

            # Asegurar que no sea negativo
            total_months = max(0, total_months)

            logger.debug(f"Duración calculada: {total_months} meses")
            return total_months

        except Exception as e:
            logger.error(f"Error calculando duración: {e}")
            return 0

    def get_ultimo_puesto(self, experiencias: List[Dict[str, Any]]) -> Optional[str]:
        """
        Obtiene el puesto del empleo más reciente del candidato.

        Prioridad:
        1. Empleos actuales (fecha_fin = null)
        2. Empleos más recientes por fecha_fin
        3. Excluye prácticas (es_practica = true)
        """
        if not experiencias:
            return None

        # Filtrar solo experiencias reales (no prácticas)
        experiencias_reales = [
            exp for exp in experiencias
            if not exp.get('es_practica', False)
        ]

        if not experiencias_reales:
            logger.warning("No se encontraron experiencias profesionales reales (todas son prácticas)")
            return None

        # Ordenar: empleos actuales primero, luego por fecha más reciente
        experiencias_ordenadas = sorted(
            experiencias_reales,
            key=lambda x: (
                x.get('fecha_fin') is None,  # True (empleo actual) va primero
                x.get('fecha_fin', '9999-12-31') if x.get('fecha_fin') else '9999-12-31',
                x.get('fecha_inicio', '0000-01-01') if x.get('fecha_inicio') else '0000-01-01'
            ),
            reverse=True
        )

        ultimo_puesto = experiencias_ordenadas[0].get('puesto') if experiencias_ordenadas else None

        if ultimo_puesto:
            logger.debug(f"Último puesto identificado: {ultimo_puesto}")

        return ultimo_puesto

    # * Inserta una experiencia profesional completa en la base de datos con validaciones
    def _insert_experiencia(self, candidato_id: int, exp_data: Dict[str, Any], cursor: pyodbc.Cursor) -> Optional[int]:

        """
        Inserta una experiencia profesional completa en la tabla CandidatosExperiencia.

        Realiza el proceso completo de inserción incluyendo:
        - Creación automática de empresa si no existe en catálogo
        - Obtención/creación del puesto en PuestosCategoriasProfesionales
        - Cálculo automático de duración sin solapamientos temporales
        - Conversión de fechas a formato SQL Server compatible

        Args:
            candidato_id (int): ID único del candidato propietario de la experiencia
            exp_data (Dict[str, Any]): Diccionario con datos de la experiencia conteniendo:
                - empresa (str): Nombre de la empresa empleadora
                - puesto (str): Denominación del puesto/cargo desempeñado
                - fecha_inicio (str): Fecha inicio en formato ISO o compatible
                - fecha_fin (str, optional): Fecha fin, None si es empleo actual
                - descripcion (str, optional): Descripción de funciones y logros
            cursor (pyodbc.Cursor): Cursor activo de conexión a SQL Server

        Returns:
            Optional[int]: ID auto-generado de la experiencia insertada, None si falla

        Raises:
            Exception: Si hay errores de conexión DB o datos mal formateados
        """

        try:

            # ? FASE 1: Resolución de entidades relacionadas (empresa y puesto)

            # Obtener o crear la empresa en el catálogo. Si no existe, se crea y se marca para validación
            empresa_id = self._get_or_create_empresa(exp_data.get('empresa', ''), cursor)

            # Obtener o crear el puesto/categoría profesional del catálogo correspondiente
            puesto_categoria_id = self._get_or_create_puesto_categoria_profesional(exp_data.get('puesto', ''), cursor)

            # ? FASE 2: Procesamiento y validación de datos temporales

            # Convertir fechas del JSON a formato SQL Server compatible
            fecha_inicio = format_date_for_sql(exp_data.get('fecha_inicio'))
            fecha_fin = format_date_for_sql(exp_data.get('fecha_fin'))

            # Inicializar duración por defecto
            duracion = 0

            # Calcular duración en meses usando validador especializado, con fallback seguro
            if fecha_inicio:
                try:
                    duracion = ExperienceValidator.calculate_duration(fecha_inicio, fecha_fin)
                    # Si devuelve 0 y fecha_fin es None (empleo actual), recalcular
                    if duracion == 0 and fecha_fin is None:
                        duracion = self._calculate_duration_months(fecha_inicio, fecha_fin)
                except Exception as e:
                    logger.warning(f"Fallo en ExperienceValidator, usando cálculo alternativo: {e}")
                    # Usar nuestro métoodo de cálculo como fallback
                    duracion = self._calculate_duration_months(fecha_inicio, fecha_fin)

            # ? FASE 3: Construcción de la consulta SQL de inserción

            # Consulta INSERT en tabla CandidatosExperiencia con OUTPUT para obtener ID auto-generado
            query = """
                   INSERT INTO dbo.CandidatosExperiencia (
                       IdCandidato,              -- FK al candidato
                       IdEmpresa,                -- FK a catálogo de empresas
                       IdPuesto,                 -- FK a PuestosCategoriasProfesionales
                       FechaInicioPuesto,        -- Fecha inicio experiencia
                       FechaFinPuesto,           -- Fecha fin (NULL si actual)
                       Experiencia,              -- Duración calculada en meses
                       DescripcionExperiencia,   -- Descripción de funciones/logros
                       FechaModificacion,        -- NULL en alta inicial (sin modificaciones)
                       UsuarioModificacion,      -- NULL en alta inicial (sin modificaciones)
                       FechaAlta,                -- Timestamp creación
                       UsuarioAlta               -- Usuario que creó
                   )
                   OUTPUT INSERTED.IdCandidatoExperiencia  -- Retorna ID auto-generado
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, GETDATE(), ?)
               """

            # ? FASE 4: Ejecución de la inserción en base de datos

            values = (
                candidato_id,
                empresa_id,
                puesto_categoria_id,
                fecha_inicio,
                fecha_fin,
                duracion,
                exp_data.get('descripcion'),
                self.default_user_id
            )

            # Ejecutar la inserción y capturar el resultado con ID generado
            cursor.execute(query, values)
            result = cursor.fetchone()

            # ? FASE 5: Validación del resultado y retorno del ID

            # Verificar éxito de la inserción y retornar el ID auto-generado
            if result:
                exp_id = int(result[0])
                logger.debug(f"Experiencia insertada con ID: {exp_id}")
                return exp_id

            # Si no hay resultado, la inserción falló
            return None

        # Capturar cualquier excepción y registrar información detallada para debugging
        except Exception as e:
            logger.error(f"Error insertando experiencia: {e}")
            logger.error(f"Datos: empresa={exp_data.get('empresa')}, puesto={exp_data.get('puesto')}")

            # Retornar None para indicar fallo en la operación
            return None

    # * Convierte prácticas académicas en registros de formación según las reglas de negocio
    def _insert_practica_como_formacion(self, candidato_id: int, exp_data: Dict[str, Any], cursor: pyodbc.Cursor) -> Optional[int]:

        """
        Convierte una práctica/beca académica en registro de formación según reglas de negocio.

        Implementa la regla establecida en Reunión 5: las prácticas académicas no cuentan
        como experiencia profesional sino como formación complementaria. Crea automáticamente
        un título descriptivo combinando puesto y empresa.

        Args:
            candidato_id (int): ID único del candidato que realizó la práctica
            exp_data (Dict[str, Any]): Diccionario con datos de la práctica conteniendo:
                - empresa (str): Entidad donde se realizó la práctica
                - puesto (str): Rol/área de la práctica realizada
                - fecha_inicio (str): Fecha inicio de la práctica
                - fecha_fin (str, optional): Fecha fin de la práctica
            cursor (pyodbc.Cursor): Cursor activo de conexión a SQL Server

        Returns:
            Optional[int]: ID del registro de formación creado, None si falla

        Note:
            - La empresa se convierte en centro educativo en el catálogo
            - Se genera título automático formato: "Prácticas - {puesto} en {empresa}"
            - Requiere catálogos base de especialidades y rangos de estudio
            - El registro se inserta en CandidatosEstudios, no en CandidatosExperiencia
        """

        try:
            # ? FASE 1: Resolución de entidades relacionadas (centro educativo y estudio)

            # Convertir la empresa en centro educativo para el catálogo
            centro_id = self._get_or_create_centro(exp_data.get('empresa', ''), cursor)

            # Extraer datos base para construcción del título
            puesto = exp_data.get('puesto', 'Prácticas')
            empresa = exp_data.get('empresa', '')

            # Generar título descriptivo según disponibilidad de datos
            if empresa and puesto:
                titulo_practica = f"Prácticas - {puesto} en {empresa}"
            elif empresa:
                titulo_practica = f"Prácticas en {empresa}"
            elif puesto:
                titulo_practica = f"Prácticas - {puesto}"
            else:
                titulo_practica = "Prácticas profesionales"

            # Crear o recuperar el estudio con el título generado
            id_estudio = self._get_or_create_estudio(titulo_practica, cursor)

            if not id_estudio:
                logger.warning(f"No se pudo crear el estudio para la práctica: {titulo_practica}")
                return None

            # ? FASE 2: Obtención de catálogos obligatorios para estudios

            # Obtener primer ID disponible de especialidad de estudios
            cursor.execute(
                "SELECT TOP 1 IdEspecialidadEstudio FROM dbo.EspecialidadEstudios ORDER BY IdEspecialidadEstudio")
            result = cursor.fetchone()
            id_especialidad = result[0] if result else 1

            # Obtener primer ID disponible de rango de estudios
            cursor.execute("SELECT TOP 1 IdRangoEstudio FROM dbo.RangoEstudios ORDER BY IdRangoEstudio")
            result = cursor.fetchone()
            id_rango = result[0] if result else 1

            # Validar que los catálogos obligatorios estén disponibles
            if not all([id_especialidad, id_rango]):
                logger.warning("Faltan catálogos obligatorios para estudios")
                return None

            # ? FASE 3: Construcción de la consulta SQL de inserción

            query = """
                INSERT INTO dbo.CandidatosEstudios (
                    IdCandidato,
                    IdEstudio,
                    IdEspecialidad,
                    IdRangoEstudios,
                    IdCentro,
                    FechaInicioEstudio,
                    FechaFinEstudio,
                    FechaModificacion,
                    UsuarioModificacion,
                    FechaAlta,
                    UsuarioAlta
                )
                OUTPUT INSERTED.IdCandidatoEstudios
                VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, GETDATE(), ?)
            """

            # ? FASE 4: Ejecución de la inserción en base de datos

            values = (
                candidato_id,
                id_estudio,
                id_especialidad,
                id_rango,
                centro_id,
                format_date_for_sql(exp_data.get('fecha_inicio')),
                format_date_for_sql(exp_data.get('fecha_fin')),
                self.default_user_id,
                self.default_user_id
            )

            # Ejecutar la inserción y capturar el resultado con ID generado
            cursor.execute(query, values)
            result = cursor.fetchone()

            # ? FASE 5: Validación del resultado y retorno del ID

            # Verificar éxito de la inserción y retornar el ID auto-generado
            if result:
                form_id = int(result[0])
                logger.info(f"Práctica '{titulo_practica}' insertada como formación con ID: {form_id}")
                return form_id

            # Si no hay resultado, la inserción falló
            return None

        # Capturar cualquier excepción y registrar información detallada para debugging
        except Exception as e:
            logger.error(f"Error insertando práctica como formación: {e}")
            logger.error(f"Datos problemáticos: empresa={exp_data.get('empresa')}, puesto={exp_data.get('puesto')}")
            return None

    # * Estructura preparada para insertar proyectos vinculados a experiencias laborales
    def _insert_proyecto(self, experiencia_id: int, proyecto_data: Dict[str, Any], cursor: pyodbc.Cursor) -> Optional[int]:

        """
        Estructura preparada para insertar proyectos específicos vinculados a experiencias laborales.

        Función placeholder diseñada para futuras implementaciones según Reunión 5:
        los proyectos deben registrarse dentro del contexto de experiencias laborales,
        no como entidades independientes.

        Args:
            experiencia_id (int): ID de la experiencia profesional padre
            proyecto_data (Dict[str, Any]): Datos del proyecto a insertar (estructura pendiente)
            cursor (pyodbc.Cursor): Cursor activo de conexión a SQL Server

        Returns:
            Optional[int]: ID del proyecto insertado cuando se implemente

        Toodo:
            - Definir estructura de tabla para proyectos vinculados
            - Implementar lógica de inserción cuando lleguen JSONs con proyectos
            - Validar que no se duplique duración entre proyecto y experiencia padre

        Note:
            Actualmente no funcional - los JSONs procesados vienen con proyectos vacíos.
            La estructura está preparada para desarrollo futuro.
        """

        # TODO: Implementar inserción de proyectos cuando los JSONs contengan datos (actualmente vacíos)
        pass
