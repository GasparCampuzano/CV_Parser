#!/usr/bin/env python3
"""
Mixin para inserción de conocimientos/habilidades del candidato.
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

# * Mixin especializado en la inserción de conocimientos y habilidades categorizadas por tipo
class ConocimientosInserter:

    """
    Mixin especializado en la inserción de conocimientos y habilidades categorizadas.

    Este mixin implementa la lógica de negocio para insertar diferentes categorías de
    conocimientos según las reglas establecidas en las reuniones, con políticas
    diferenciadas por tipo de conocimiento y validación contra catálogos existentes.

    Categorías de conocimientos soportadas:
        - Conocimientos técnicos: lenguajes, frameworks, BBDD (solo catálogo)
        - Conocimientos de negocio: sectores, dominios (solo catálogo)
        - Otros conocimientos: metodologías, habilidades transversales (creación permitida)
        - Sin especificar: términos que requieren clasificación manual

    Políticas de inserción:
        - Técnicos y negocio: política estricta, solo del catálogo existente
        - Otros: política permisiva, se pueden crear nuevos automáticamente
        - Sin especificar: solo registro para revisión manual posterior

    Notas:
        - Implementa las reglas de las reuniones 2, 8 y 9
        - Requiere CatalogValidator para validación previa
        - Maneja relaciones N:M entre candidatos y conocimientos
        - Previene duplicados mediante constraints de BD
    """

    def _get_or_create_conocimiento_tecnico(self, nombre: str, cursor: pyodbc.Cursor) -> Optional[int]:
        """
        Obtiene el ID de un conocimiento técnico existente o lo crea si no existe.

        Args:
            nombre (str): Nombre del conocimiento técnico
            cursor (pyodbc.Cursor): Cursor activo de conexión

        Returns:
            Optional[int]: ID del conocimiento técnico o None si falla
        """
        try:
            # Primero intentar obtener si existe
            query_select = """
                SELECT IdConocimientoTecnico 
                FROM dbo.ConocimientosTecnicos 
                WHERE Descripcion = ?
            """
            cursor.execute(query_select, (nombre,))
            result = cursor.fetchone()

            if result:
                return result[0]

            # Si no existe, crear nuevo
            query_insert = """
                INSERT INTO dbo.ConocimientosTecnicos (
                    Descripcion,
                    FechaAlta,
                    UsuarioAlta,
                    FechaModificacion,
                    UsuarioModificacion
                )
                OUTPUT INSERTED.IdConocimientoTecnico
                VALUES (?, GETDATE(), ?, GETDATE(), ?)
            """
            cursor.execute(query_insert, (nombre, self.default_user_id, self.default_user_id))
            result = cursor.fetchone()

            if result:
                logger.info(f"Creado nuevo conocimiento técnico: {nombre} (ID: {result[0]})")
                return result[0]

        except Exception as e:
            logger.error(f"Error creando conocimiento técnico '{nombre}': {e}")

        return None

    def _get_or_create_conocimiento_negocio(self, nombre: str, cursor: pyodbc.Cursor) -> Optional[int]:
        """
        Obtiene el ID de un conocimiento de negocio existente o lo crea si no existe.

        Args:
            nombre (str): Nombre del conocimiento de negocio
            cursor (pyodbc.Cursor): Cursor activo de conexión

        Returns:
            Optional[int]: ID del conocimiento de negocio o None si falla
        """
        try:
            # Primero intentar obtener si existe
            query_select = """
                SELECT IdConocimientosNegocio 
                FROM dbo.ConocimientosNegocio 
                WHERE Descripcion = ?
            """
            cursor.execute(query_select, (nombre,))
            result = cursor.fetchone()

            if result:
                return result[0]

            # Si no existe, crear nuevo
            query_insert = """
                INSERT INTO dbo.ConocimientosNegocio (
                    Descripcion,
                    FechaAlta,
                    UsuarioAlta,
                    FechaModificacion,
                    UsuarioModificacion
                )
                OUTPUT INSERTED.IdConocimientosNegocio
                VALUES (?, GETDATE(), ?, GETDATE(), ?)
            """
            cursor.execute(query_insert, (nombre, self.default_user_id, self.default_user_id))
            result = cursor.fetchone()

            if result:
                logger.info(f"Creado nuevo conocimiento de negocio: {nombre} (ID: {result[0]})")
                return result[0]

        except Exception as e:
            logger.error(f"Error creando conocimiento de negocio '{nombre}': {e}")

        return None

    # * Procesa e inserta todos los conocimientos del candidato según políticas por categoría
    def _insert_conocimientos(self, candidato_id: int, habilidades: Dict[str, List[str]], cursor: pyodbc.Cursor) -> Dict[str, Any]:

        """
        Inserta conocimientos del candidato aplicando políticas diferenciadas por categoría.

        Implementa un sistema de procesamiento por fases que valida contra catálogos
        existentes y aplica reglas específicas según el tipo de conocimiento:
        - Técnicos/Negocio: solo insertar si existe en catálogo
        - Otros: insertar existentes y crear nuevos automáticamente
        - Sin especificar: registrar para revisión manual

        Args:
            candidato_id (int): ID único del candidato propietario de los conocimientos
            habilidades (Dict[str, List[str]]): Diccionario de habilidades por categoría:
                - 'Conocimientos Tecnicos': Lista de tecnologías, lenguajes, frameworks
                - 'Conocimientos Negocio': Lista de sectores, dominios de negocio
                - 'Otros Conocimientos': Lista de metodologías, soft skills
                - 'Conocimientos Sin Especificar': Lista para clasificación manual
            cursor (pyodbc.Cursor): Cursor activo de conexión a SQL Server

        Returns:
            Dict[str, Any]: Diccionario con estadísticas detalladas de la operación:
                - tecnicos_insertados (int): Cantidad insertada exitosamente
                - tecnicos_rechazados (List[str]): Técnicos no encontrados en catálogo
                - negocio_insertados (int): Cantidad insertada exitosamente
                - negocio_rechazados (List[str]): Negocio no encontrados en catálogo
                - otros_insertados (int): Cantidad total insertada (existentes + nuevos)
                - otros_nuevos (List[str]): Otros conocimientos creados automáticamente
                - sin_especificar (List[str]): Habilidades que requieren revisión manual

        Note:
            - Utiliza CatalogValidator para validación previa masiva
            - Maneja duplicados mediante constraints de BD (IntegrityError)
            - Los rechazados se reportan pero no bloquean otros conocimientos
        """

        # * FASE 1: Inicialización de estructuras de seguimiento y normalización de datos

        # Inicializar estructura de resultados para tracking detallado de inserciones
        results = {
            'tecnicos_insertados': 0,
            'tecnicos_rechazados': [],
            'tecnicos_nuevos': [],
            'negocio_insertados': 0,
            'negocio_rechazados': [],
            'negocio_nuevos': [],
            'otros_insertados': 0,
            'otros_nuevos': [],
            'sin_especificar': []
        }

        try:

            # Definir mapeo de nombres de categorías del JSON a nombres internos normalizados
            categoria_map = {
                'Conocimientos Tecnicos': 'conocimientos_tecnicos',
                'Conocimientos Negocio': 'conocimientos_negocio',
                'Otros Conocimientos': 'otros_conocimientos',
                'Conocimientos Sin Especificar': 'sin_especificar'
            }

            # Normalizar todas las categorías usando el mapeo definido
            habilidades_norm = {}

            # Si la key existe en el mapeo, usar el valor mapeado; sino, normalizar manualmente
            for key, value in habilidades.items():
                normalized_key = categoria_map.get(key, key.lower().replace(' ', '_'))
                habilidades_norm[normalized_key] = value

            # ? FASE 2: Validación masiva contra catálogos mediante validador especializado

            # Validar todas las habilidades contra sus catálogos respectivos de una vez
            validation_result = self.cat_validator.validate_skills(habilidades_norm)

            # ? FASE 3: Procesamiento de conocimientos técnicos (política estricta)

            # Insertar solo los conocimientos técnicos encontrados en el catálogo
            if 'tecnicos' in validation_result:
                for skill_data in validation_result['tecnicos']['encontrados']:
                    if self._insert_conocimiento_tecnico(candidato_id, skill_data['id'], cursor):
                        results['tecnicos_insertados'] += 1

                # Crear e insertar los no encontrados
                for skill_name in validation_result['tecnicos']['no_encontrados']:
                    skill_id = self._get_or_create_conocimiento_tecnico(skill_name, cursor)
                    if skill_id:
                        if self._insert_conocimiento_tecnico(candidato_id, skill_id, cursor):
                            results['tecnicos_insertados'] += 1
                            results['tecnicos_nuevos'].append(skill_name)
                        else:
                            logger.warning(f"No se pudo insertar conocimiento técnico creado: {skill_name}")

            # ? FASE 4: Procesamiento de conocimientos de negocio (política estricta)

            # Insertar solo los conocimientos de negocio encontrados en el catálogo
            if 'negocio' in validation_result:
                for skill_data in validation_result['negocio']['encontrados']:
                    if self._insert_conocimiento_negocio(candidato_id, skill_data['id'], cursor):
                        results['negocio_insertados'] += 1

                # Crear e insertar los no encontrados
                for skill_name in validation_result['negocio']['no_encontrados']:
                    skill_id = self._get_or_create_conocimiento_negocio(skill_name, cursor)
                    if skill_id:
                        if self._insert_conocimiento_negocio(candidato_id, skill_id, cursor):
                            results['negocio_insertados'] += 1
                            results['negocio_nuevos'].append(skill_name)
                        else:
                            logger.warning(f"No se pudo insertar conocimiento de negocio creado: {skill_name}")

            # ? FASE 5: Procesamiento de otros conocimientos (política permisiva)

            # Insertar los que ya existían en el catálogo
            if 'otros' in validation_result:
                for skill_data in validation_result['otros']['encontrados']:
                    if self._insert_conocimiento_otros(candidato_id, skill_data['id'], cursor):
                        results['otros_insertados'] += 1

                # Procesar los nuevos creados automáticamente por el validador (política permisiva)
                for skill_data in validation_result['otros'].get('nuevos', []):
                    skill_id = self._get_or_create_otros_conocimientos(skill_data['nombre'], cursor)
                    if skill_id:
                        if self._insert_conocimiento_otros(candidato_id, skill_id, cursor):
                            results['otros_insertados'] += 1
                            results['otros_nuevos'].append(skill_data['nombre'])

            # ? FASE 6: Registro de conocimientos sin especificar para revisión manual

            # Registrar términos que requieren intervención humana para clasificación
            results['sin_especificar'] = validation_result.get('sin_especificar', [])

            # Registrar resumen de la operación completa en logs
            logger.info(f"Conocimientos insertados - Técnicos: {results['tecnicos_insertados']}, "
                        f"Negocio: {results['negocio_insertados']}, Otros: {results['otros_insertados']}")

        # Capturar cualquier excepción y registrar información detallada para debugging
        except Exception as e:
            logger.error(f"Error insertando conocimientos: {e}")

        # Retornar estructura completa de resultados para análisis posterior
        return results

    # * Inserta relación candidato-conocimiento técnico con manejo de duplicados
    def _insert_conocimiento_tecnico(self, candidato_id: int, conocimiento_id: int, cursor: pyodbc.Cursor) -> bool:

        """
        Inserta una relación candidato-conocimiento técnico en tabla N:M.

        Maneja la inserción de conocimientos técnicos (lenguajes, frameworks, BBDD)
        en la tabla relacional CandidatosConocimientosTecnicos, con manejo automático
        de duplicados mediante constraints de base de datos.

        Args:
            candidato_id (int): ID único del candidato propietario
            conocimiento_id (int): ID del conocimiento técnico del catálogo validado
            cursor (pyodbc.Cursor): Cursor activo de conexión a SQL Server

        Returns:
            bool: True si inserción exitosa, False si ya existía o falló

        Note:
            - Maneja IntegrityError para duplicados (constraint UNIQUE)
            - Usa self.default_user_id para auditoría de cambios
            - No incluye descripción adicional (campo NULL)
        """

        try:
            # Consulta INSERT para tabla relacional candidato-conocimiento técnico
            query = """
               INSERT INTO dbo.CandidatosConocimientosTecnicos (
                   IdCandidato,                        -- FK al candidato
                   IdConocimientoTecnico,              -- FK al conocimiento técnico del catálogo
                   DescripcionConocimientoTecnico,     -- Descripción adicional (opcional)
                   FechaModificacion,                  -- Timestamp de última modificación
                   UsuarioModificacion,                -- ID del usuario que modificó
                   FechaAlta,                          -- Timestamp de creación
                   UsuarioAlta                         -- ID del usuario que creó
               )
               VALUES (?, ?, ?, GETDATE(), ?, GETDATE(), ?)
           """

            # Ejecutar inserción con descripción NULL y usuario por defecto
            cursor.execute(query, (candidato_id, conocimiento_id, None, self.default_user_id, self.default_user_id))
            return True

        # Error de integridad: relación candidato-conocimiento ya existe (no crítico)
        except pyodbc.IntegrityError:
            logger.debug(f"Conocimiento técnico ya existe: {conocimiento_id}")
            return False

        # Cualquier otro error SQL o de conexión
        except Exception as e:
            logger.error(f"Error insertando conocimiento técnico: {e}")
            return False

    # * Inserta relación candidato-conocimiento de negocio con manejo de duplicados
    def _insert_conocimiento_negocio(self, candidato_id: int, conocimiento_id: int, cursor: pyodbc.Cursor) -> bool:

        """
        Inserta una relación candidato-conocimiento de negocio en tabla N:M.

        Maneja la inserción de conocimientos de negocio (sectores, dominios)
        en la tabla relacional CandidatosConocimientosNegocio, con manejo automático
        de duplicados mediante constraints de base de datos.

        Args:
            candidato_id (int): ID único del candidato propietario
            conocimiento_id (int): ID del conocimiento de negocio del catálogo validado
            cursor (pyodbc.Cursor): Cursor activo de conexión a SQL Server

        Returns:
            bool: True si inserción exitosa, False si ya existía o falló

        Note:
            - Maneja IntegrityError para duplicados (constraint UNIQUE)
            - Usa self.default_user_id para auditoría de cambios
            - No incluye descripción adicional (campo NULL)
        """

        try:
            # Consulta INSERT para tabla relacional candidato-conocimiento de negocio
            query = """
               INSERT INTO dbo.CandidatosConocimientosNegocio (
                   IdCandidato,                        -- FK al candidato
                   IdConocimientosNegocio,             -- FK al conocimiento de negocio
                   DescripcionConocimientoNegocio,     -- Descripción adicional (opcional)
                   FechaModificacion,                  -- Timestamp de última modificación
                   UsuarioModificacion,                -- Usuario que modificó
                   FechaAlta,                          -- Timestamp de creación
                   UsuarioAlta                         -- Usuario que creó
               )
               VALUES (?, ?, ?, NULL, NULL, GETDATE(), ?)
           """

            # Ejecutar inserción con descripción NULL y usuario por defecto
            cursor.execute(query, (candidato_id, conocimiento_id, None, self.default_user_id))
            return True

        # Error de integridad: relación ya existe (constraint UNIQUE, no crítico)
        except pyodbc.IntegrityError:
            logger.debug(f"Conocimiento negocio ya existe: {conocimiento_id}")
            return False

        # Cualquier otro error no controlado
        except Exception as e:
            logger.error(f"Error insertando conocimiento negocio: {e}")
            return False

    # * Inserta relación candidato-otros conocimientos con manejo de duplicados
    def _insert_conocimiento_otros(self, candidato_id: int, conocimiento_id: int, cursor: pyodbc.Cursor) -> bool:

        """
        Inserta una relación candidato-otros conocimientos en tabla N:M.

        Maneja la inserción de otros conocimientos (metodologías, soft skills)
        en la tabla relacional CandidatosConocimientosOtros, con manejo automático
        de duplicados mediante constraints de base de datos.

        Args:
            candidato_id (int): ID único del candidato propietario
            conocimiento_id (int): ID del conocimiento del catálogo (existente o recién creado)
            cursor (pyodbc.Cursor): Cursor activo de conexión a SQL Server

        Returns:
            bool: True si inserción exitosa, False si ya existía o falló

        Note:
            - Soporta tanto conocimientos existentes como recién creados
            - Maneja IntegrityError para duplicados (constraint UNIQUE)
            - Usa self.default_user_id para auditoría de cambios
            - No incluye descripción adicional (campo NULL)
        """

        try:
            # Consulta INSERT para tabla relacional candidato-otros conocimientos
            query = """
               INSERT INTO dbo.CandidatosConocimientosOtros (
                   IdCandidato,                       -- FK: ID del candidato
                   IdConocimientosOtros,              -- FK: ID del conocimiento específico
                   DescripcionConocimientosOtros,     -- Descripción adicional (NULL por defecto)
                   FechaModificacion,                 -- Timestamp de última modificación
                   UsuarioModificacion,               -- ID del usuario que modificó
                   FechaAlta,                         -- Timestamp de creación del registro
                   UsuarioAlta                        -- ID del usuario que creó el registro
               )
               VALUES (?, ?, ?, GETDATE(), ?, GETDATE(), ?)
           """

            # Ejecutar inserción con descripción NULL y usuario por defecto
            cursor.execute(query, (candidato_id, conocimiento_id, None, self.default_user_id, self.default_user_id))
            return True

        # Error de integridad: combinación candidato-conocimiento ya existe (no crítico)
        except pyodbc.IntegrityError:
            logger.debug(f"Otros conocimientos ya existe: {conocimiento_id}")
            return False

        # Cualquier otro error (conexión, SQL malformado, etc.)
        except Exception as e:
            logger.error(f"Error insertando otros conocimientos: {e}")
            return False
