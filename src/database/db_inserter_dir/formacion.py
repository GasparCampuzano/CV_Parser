#!/usr/bin/env python3
"""
Mixin para inserción de formación académica.
"""

# Importación de librerías estándar y utilidades de tipado
import sys
from pathlib import Path
from typing import Dict, Any, Optional
import pyodbc
from .utils import format_date_for_sql

# Añade el directorio raíz del proyecto al PYTHONPATH
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Importa el logger desde la configuración del proyecto
from config.settings import get_logger
logger = get_logger(__name__)

# * Mixin especializado en la inserción de formación académica y estudios reglados
class FormacionInserter:

    """
    Mixin especializado en la inserción de formación académica y estudios reglados.

    Este mixin maneja la lógica de negocio para insertar diferentes tipos de formación
    académica en la base de datos, incluyendo la creación automática de centros educativos
    y estudios no catalogados, con valores por defecto para especialidades y rangos.

    Funcionalidades principales:
        - Inserción de formación académica (grados, másteres, certificaciones)
        - Creación automática de centros educativos no catalogados
        - Creación automática de tipos de estudio no catalogados
        - Asignación de valores por defecto para especialidades y rangos

    Notas:
        - Los registros se insertan en la tabla CandidatosEstudios
        - Especialidades y rangos usan valores por defecto (ID=1) temporalmente
        - Requiere conexión activa a base de datos SQL Server
        - Compatible con el formato de fechas del JSON de entrada
    """

    # * Inserta formación académica completa con creación automática de entidades relacionadas
    def _insert_formacion(self, candidato_id: int, form_data: Dict[str, Any], cursor: pyodbc.Cursor) -> Optional[int]:

        """
        Inserta una formación académica completa en la tabla CandidatosEstudios.

        Args:
            candidato_id (int): ID único del candidato propietario de la formación
            form_data (Dict[str, Any]): Diccionario con datos de la formación conteniendo:
                - institucion (str): Nombre del centro educativo donde se realizó
                - titulo (str): Denominación del título o certificación obtenida
                - fecha_inicio (str): Fecha inicio de los estudios en formato ISO
                - fecha_fin (str, optional): Fecha fin, None si estudios en curso
            cursor (pyodbc.Cursor): Cursor activo de conexión a SQL Server

        Returns:
            Optional[int]: ID auto-generado de la formación insertada, None si falla
        """

        try:

            # ? FASE 1: Resolución de entidades relacionadas (centro educativo y estudio)

            # Obtener o crear el centro educativo basado en la institución proporcionada
            centro_id = self._get_or_create_centro(form_data.get('institucion', ''), cursor)

            # Buscar o crear el registro de estudio basado en el título académico
            id_estudio = self._get_or_create_estudio(form_data.get('titulo', ''), cursor)

            # ? FASE 2: Asignación de catálogos obligatorios con valores por defecto

            # TODO: Por ahora asigna valores por defecto para campos obligatorios FK. En un futuro mapeará las especialidades
            id_especialidad = 1

            # Obtener rango directamente del form_data
            rango_raw = form_data.get("rango")
            rango_value = rango_raw.strip() if rango_raw is not None else None
            id_rango = self._get_rango_id(rango_value, cursor)

            # Convertir fechas del JSON a formato SQL Server compatible
            fecha_inicio = format_date_for_sql(form_data.get('fecha_inicio'))
            fecha_fin = format_date_for_sql(form_data.get('fecha_fin'))

            # * FASE 3: Construcción de la consulta SQL de inserción

            query = """
               INSERT INTO dbo.CandidatosEstudios (
                   IdCandidato,            -- FK al candidato propietario
                   IdEstudio,              -- FK al tipo de estudio (ej: "Licenciatura")
                   IdEspecialidad,         -- FK a especialidad (ej: "Informática")
                   IdRangoEstudios,        -- FK a rango educativo (ej: "Universitario")
                   IdCentro,               -- FK al centro educativo
                   FechaInicioEstudio,     -- Fecha de inicio de los estudios
                   FechaFinEstudio,        -- Fecha de fin (NULL si en curso)
                   FechaModificacion,      -- Timestamp de última modificación
                   UsuarioModificacion,    -- Usuario que modificó el registro
                   FechaAlta,              -- Timestamp de creación
                   UsuarioAlta             -- Usuario que creó el registro
               )
               OUTPUT INSERTED.IdCandidatoEstudios  -- Retorna el ID del registro creado
               VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, GETDATE(), ?)
           """

            # * FASE 4: Ejecución de la inserción en base de datos

            values = (
                candidato_id,
                id_estudio,
                id_especialidad,
                id_rango,
                centro_id,
                fecha_inicio,
                fecha_fin,
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
                logger.debug(f"Formación insertada con ID: {form_id}")
                return form_id

            # Si no hay resultado, la inserción falló
            return None

        # Capturar cualquier excepción y registrar información detallada para debugging
        except Exception as e:
            logger.error(f"Error insertando formación: {e}")
            logger.error(
                f"Datos problemáticos - fecha_inicio: {form_data.get('fecha_inicio')}, fecha_fin: {form_data.get('fecha_fin')}")

            # Retornar None para indicar fallo en la operación
            return None

    def _get_rango_id(self, rango_value: str, cursor: pyodbc.Cursor) -> int:
        """
        Mapea el valor del rango del JSON al ID correspondiente en dbo.RangoEstudios.
        """

        rango_mapping = {
            'doctorado': 'Doctorado',
            'master_universitario': 'Máster Universitario',
            'grado_universitario': 'Grado Universitario',
            'tecnico_superior': 'Técnico Superior',
            'fp_superior': 'FP Grado Superior',
            'fp_medio': 'FP Grado Medio',
            'fp_basica': 'FP Básica',
            'bachillerato': 'Bachillerato',
            'eso': 'ESO',
            'primaria': 'Educación Primaria',
            'sin_estudios': 'Sin estudios'
        }

        if not rango_value or rango_value not in rango_mapping:
            logger.warning(f"Rango '{rango_value}' no reconocido, usando valor por defecto")
            return 2

        descripcion_rango = rango_mapping[rango_value]

        # Query para solicitar el rango de estudio
        query = """
            SELECT IdRangoEstudio  
            FROM dbo.RangoEstudios 
            WHERE Descripcion = ?
        """

        try:
            cursor.execute(query, (descripcion_rango,))
            result = cursor.fetchone()

            if result:
                return int(result[0])
            else:
                logger.error(f"No se encontró el rango '{descripcion_rango}' en la BD")
                return 1

        except Exception as e:
            logger.error(f"Error obteniendo ID de rango: {e}")
            return 1

    def _es_estudio_universitario(self, titulo: str) -> bool:
        """
        Determina si un estudio es de nivel universitario.
        """
        palabras_universitarias = [
            'grado', 'licenciatura', 'licenciado', 'ingeniería', 'ingeniero',
            'máster', 'master', 'doctorado', 'doctor', 'phd',
            'diplomatura', 'diplomado', 'arquitectura', 'arquitecto',
            'medicina', 'médico', 'derecho', 'abogado', 'ade',
            'universitario', 'universidad', 'bachelor', 'degree'
        ]

        titulo_lower = titulo.lower()
        return any(palabra in titulo_lower for palabra in palabras_universitarias)

    def procesar_formacion_y_titulacion(self, candidato_id: int, formacion_list: list, cursor) -> dict:
        """
        Procesa formación y actualiza campo Titulado si detecta estudios universitarios.
        """
        formaciones_insertadas = 0
        es_titulado = False

        for formacion in formacion_list:
            # Usar _insert_formacion
            form_id = self._insert_formacion(candidato_id, formacion, cursor)

            if form_id:
                formaciones_insertadas += 1

                # Verificar si es universitario
                if not es_titulado and self._es_estudio_universitario(formacion.get('titulo', '')):
                    es_titulado = True

                    # Actualizar el campo Titulado directamente aquí
                    try:
                        query = """
                            UPDATE dbo.Candidatos 
                            SET Titulado = 1,
                                FechaModificacion = GETDATE(),
                                UsuarioModificacion = ?
                            WHERE IdCandidato = ?
                        """
                        cursor.execute(query, (self.default_user_id, candidato_id))
                        logger.info(f"Candidato {candidato_id} marcado como Titulado")
                    except Exception as e:
                        logger.error(f"Error actualizando Titulado: {e}")

        return {
            'formaciones_insertadas': formaciones_insertadas,
            'es_titulado': es_titulado
        }
