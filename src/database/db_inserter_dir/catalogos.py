#!/usr/bin/env python3
"""
Mixin para gestión de catálogos en la base de datos.
Maneja la creación y búsqueda de elementos en catálogos maestros.
"""

# Importación de librerías estándar y utilidades de tipado
import sys
from pathlib import Path
from typing import Optional
import pyodbc

# Añade el directorio raíz del proyecto al PYTHONPATH
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Importa el logger desde la configuración del proyecto
from config.settings import get_logger
logger = get_logger(__name__)

# * Gestor de catálogos maestros con patrón get-or-create para entidades de CV (empresas, centros, estudios, puestos)
class CatalogosManager:

    """
    Mixin para gestión automatizada de catálogos maestros en el sistema de procesamiento de CVs.

    Esta clase implementa el patrón "get_or_create" para entidades de catálogo, permitiendo
    la creación automática de registros cuando no existen en la base de datos. Está diseñada
    para ser utilizada como mixin en clases que requieran acceso a catálogos maestros.

    Funcionalidades principales:
    - Búsqueda de elementos existentes en catálogos mediante coincidencia exacta
    - Creación automática de nuevos registros cuando no se encuentran
    - Manejo de campos de auditoría (fechas y usuarios de alta/modificación)
    - Gestión de errores de concurrencia y violaciones de integridad
    - Logging detallado de operaciones para trazabilidad

    Catálogos soportados:
    - Empresas (dbo.Empresas)
    - Centros de estudios (dbo.CentroEstudios)
    - Estudios/títulos (dbo.Estudios)
    - Puestos y categorías profesionales (dbo.PuestosCategoriasProfesionales)
    - Otros conocimientos (dbo.ConocimientosOtros)

    Requisitos:
    - La clase que herede este mixin debe definir 'default_user_id' para auditoría
    - Requiere cursor de pyodbc activo para operaciones de base de datos
    - Asume esquema de base de datos SQL Server con campos de auditoría estándar

    Comportamiento ante errores:
    - Retorna None si no puede crear o encontrar el elemento solicitado
    - Maneja race conditions mediante re-intentos de búsqueda
    - Registra errores detallados en logs para debugging
    """

    # * Busca o crea un puesto/categoría profesional en el catálogo, retornando su ID único
    def _get_or_create_puesto_categoria_profesional(self, descripcion_puesto: str, cursor: pyodbc.Cursor) -> Optional[int]:

        """
        Obtiene o crea un registro puesto profesional.

        Args:
            descripcion_puesto: Descripción del puesto
            cursor: Cursor de la conexión

        Returns:
            ID del puesto existente o creado
        """

        # Validar que el nombre del puesto no está vacío o nulo
        if not descripcion_puesto:
            return None

        try:
            # ? FASE 1: Buscar si el puesto ya existe en el catálogo

            # Buscar si ya existe
            query = """
                SELECT IdPuestoCategoriaProfesional 
                FROM dbo.PuestosCategoriasProfesionales 
                WHERE LOWER(Descripcion) = LOWER(?)
            """
            cursor.execute(query, (descripcion_puesto,))
            result = cursor.fetchone()

            # Si encontramos el puesto, devolver su ID
            if result:
                return result[0]

            # ? FASE 2: El puesto no existe, proceder a crearlo

            # Insertar nuevo registro con campos de auditoría requeridos
            insert_query = """
                INSERT INTO dbo.PuestosCategoriasProfesionales 
                (Descripcion, FechaModificacion, UsuarioModificacion, FechaAlta, UsuarioAlta)
                VALUES (?, GETDATE(), ?, GETDATE(), ?)
            """

            # Ejecutar INSERT con descripción y usuario de auditoría
            cursor.execute(insert_query, (descripcion_puesto, self.default_user_id, self.default_user_id))

            # ? FASE 3: Recuperar el ID del registro recién creado

            # Nueva consulta SELECT para obtener el ID generado
            select_query = """
                SELECT IdPuestoCategoriaProfesional 
                FROM dbo.PuestosCategoriasProfesionales 
                WHERE LOWER(Descripcion) = LOWER(?)
            """
            cursor.execute(select_query, (descripcion_puesto,))
            result = cursor.fetchone()

            # Verificar que se recuperó correctamente el nuevo registro. Y de ser así, retornar el ID
            if result:
                new_id = int(result[0])
                logger.info(f"Nuevo puesto-categoría creado: {descripcion_puesto} (ID: {new_id})")
                return new_id

        # Log detallado del error para debugging
        except Exception as e:
            logger.error(f"Error en _get_or_create_puesto_categoria_profesional: {e}")

        # Si llegamos aquí, algo falló en el proceso
        return None

    # * Busca o crea una empresa en el catálogo maestro, retornando su ID único
    def _get_or_create_empresa(self, empresa_nombre: str, cursor: pyodbc.Cursor) -> Optional[int]:

        """
        Obtiene o crea una empresa.

        Args:
            empresa_nombre: Nombre de la empresa
            cursor: Cursor de la conexión

        Returns:
            ID de la empresa existente o creada
        """

        # Validar que el nombre de empresa no esté vacío
        if not empresa_nombre:
            return None

        # ? FASE 1: BÚSQUEDA - Verificar si la empresa ya existe en la BD
        try:
            # Consulta simple para buscar empresa por descripción exacta
            query = "SELECT IdEmpresa FROM dbo.Empresas WHERE Descripcion = ?"
            cursor.execute(query, (empresa_nombre,))
            result = cursor.fetchone()

            # Si encontramos la empresa, devolver su ID
            if result:
                return result[0]

        # Error en búsqueda - continuar intentando crear
        except Exception as e:
            logger.debug(f"Error buscando empresa: {e}")

        # ? FASE 2: CREACIÓN - La empresa no existe, intentar crearla
        try:
            # Query INSERT con OUTPUT para obtener el ID auto-generado
            query = """
                INSERT INTO dbo.Empresas 
                (Descripcion, FechaModificacion, UsuarioModificacion, FechaAlta, UsuarioAlta)
                OUTPUT INSERTED.IdEmpresa
                VALUES (?, GETDATE(), ?, GETDATE(), ?)
            """

            # Ejecutar inserción con: nombre, usuario_modificacion, usuario_alta
            cursor.execute(query, (empresa_nombre, self.default_user_id, self.default_user_id))
            result = cursor.fetchone()

            # Verificar que la inserción fue exitosa. Y si lo fue, devolver el ID generado
            if result:
                empresa_id = int(result[0])
                logger.info(f"Nueva empresa creada: {empresa_nombre}")
                return empresa_id

        # ! CASO ESPECIAL: Error de duplicado (Otro proceso la creó mientras la buscábamos)
        except pyodbc.IntegrityError:
            # Intentar buscar de nuevo la empresa recién creada
            query = "SELECT IdEmpresa FROM dbo.Empresas WHERE Descripcion = ?"
            cursor.execute(query, (empresa_nombre,))
            result = cursor.fetchone()

            # Si la encontramos, devolver el ID de la empresa creada por otro proceso
            if result:
                return result[0]

        # Error general en creación - log para debugging
        except Exception as e:
            logger.error(f"Error creando empresa {empresa_nombre}: {e}")

        # ? Si llegamos aquí, falló tanto la búsqueda como la creación
        return None

    # * Busca o crea un centro de estudios en el catálogo, retornando su ID único
    def _get_or_create_centro(self, centro_nombre: str, cursor: pyodbc.Cursor) -> Optional[int]:

        """
        Obtiene o crea un centro de estudios.

        Args:
            centro_nombre: Nombre del centro
            cursor: Cursor de la conexión

        Returns:
            ID del centro existente o creado
        """

        # Validar que el nombre del centro no esté vacío
        if not centro_nombre:
            return None

        # ? PASO 1: Buscar si el centro ya existe en la base de datos

        # Consulta simple para buscar el centro de estudios por descripción exacta
        query = "SELECT IdCentroEstudios FROM dbo.CentroEstudios WHERE LOWER(Descripcion) = LOWER(?)"
        cursor.execute(query, (centro_nombre,))
        result = cursor.fetchone()

        # Si encuentra el centro, retornar su ID
        if result:
            return result[0]

        # ? PASO 2: El centro no existe, intentar crearlo

        try:
            # Definir INSERT con OUTPUT para obtener el ID auto-generado
            query = """
                INSERT INTO dbo.CentroEstudios (
                    Descripcion,
                    FechaModificacion,
                    UsuarioModificacion,
                    FechaAlta,
                    UsuarioAlta
                )
                OUTPUT INSERTED.IdCentroEstudios
                VALUES (?, GETDATE(), ?, GETDATE(), ?)
            """

            # Ejecutar INSERT con los valores: nombre, usuario_modificacion, usuario_alta
            cursor.execute(query, (centro_nombre, self.default_user_id, self.default_user_id))
            result = cursor.fetchone()

            # Verificar que la inserción fue exitosa. De ser asi, retornar el ID creado
            if result:
                centro_id = int(result[0])
                logger.info(f"Nuevo centro creado: {centro_nombre}")
                return centro_id

        # Capturar cualquier error durante la inserción (violaciones de integridad, etc.)
        except Exception as e:
            logger.error(f"Error creando centro {centro_nombre}: {e}")

        # ? Si llegamos aquí, algo falló en la creación
        return None

    # * Busca o crea un estudio/título académico en el catálogo, retornando su ID único
    def _get_or_create_estudio(self, titulo: str, cursor: pyodbc.Cursor) -> Optional[int]:

        """
        Obtiene o crea un estudio/título.

        Args:
            titulo: Título del estudio
            cursor: Cursor de la conexión

        Returns:
            ID del estudio existente o creado
        """

        # Verificar si se proporcionó un título
        if not titulo:

            # Si no hay título, buscar cualquier estudio existente como fallback
            query = "SELECT TOP 1 IdEstudio FROM dbo.Estudios ORDER BY IdEstudio"
            cursor.execute(query)
            result = cursor.fetchone()

            # Retornar primer ID disponible o None
            return result[0] if result else None

        # ? PASO 1: Buscar si el estudio ya existe en la base de datos

        query = "SELECT IdEstudio FROM dbo.Estudios WHERE LOWER(Descripcion) = LOWER(?)"
        cursor.execute(query, (titulo,))
        result = cursor.fetchone()

        # Si encontramos el estudio, retornar su ID
        if result:
            return result[0]

        # ? PASO 2: El estudio no existe, necesitamos crearlo

        # Obtenemos un IdRangoEstudio válido
        query = "SELECT TOP 1 IdRangoEstudio FROM dbo.RangoEstudios ORDER BY IdRangoEstudio"
        cursor.execute(query)
        rango_result = cursor.fetchone()

        # Usar el primer rango disponible, o 1 como fallback
        id_rango = rango_result[0] if rango_result else 1

        # ? PASO 3: Crear nuevo estudio en la base de datos
        try:
            # Query INSERT con OUTPUT para obtener el ID auto-generado
            query = """
               INSERT INTO dbo.Estudios (
                   Descripcion,           -- Nombre/descripción del estudio
                   IdRangoEstudio,        -- FK obligatorio a RangoEstudios
                   FechaModificacion,     -- Timestamp de modificación
                   UsuarioModificacion,   -- ID del usuario que modifica
                   FechaAlta,             -- Timestamp de creación
                   UsuarioAlta            -- ID del usuario que crea
               )
               OUTPUT INSERTED.IdEstudio  -- Retornar el ID auto-generado
               VALUES (?, ?, GETDATE(), ?, GETDATE(), ?)
           """

            # Ejecutar INSERT con los valores: título, rango, user_id, user_id
            cursor.execute(query, (titulo, id_rango, self.default_user_id, self.default_user_id))
            result = cursor.fetchone()

            # Verificar que la inserción fue exitosa y retonar el ID del estudio introducido
            if result:
                estudio_id = int(result[0])
                logger.info(f"Nuevo estudio creado: {titulo}")
                return estudio_id

        # Si falla la creación
        except Exception as e:
            # Loggear el error
            logger.error(f"Error creando estudio {titulo}: {e}")

            # FALLBACK: Buscar cualquier estudio existente para no fallar completamente
            query = "SELECT TOP 1 IdEstudio FROM dbo.Estudios ORDER BY IdEstudio"
            cursor.execute(query)
            result = cursor.fetchone()

            # Retornar primer estudio disponible
            return result[0] if result else None

        # ? Si llegamos aquí, algo falló y no pudimos crear ni encontrar
        return None

    # * Busca o crea un conocimiento en la categoría "Otros", retornando su ID único
    def _get_or_create_otros_conocimientos(self, conocimiento: str, cursor: pyodbc.Cursor) -> Optional[int]:

        """
        Obtiene o crea un conocimiento en la categoría 'otros'.

        Args:
            conocimiento: Descripción del conocimiento
            cursor: Cursor de la conexión

        Returns:
            ID del conocimiento existente o creado
        """

        # Rechazar conocimientos vacíos o nulos
        if not conocimiento:
            return None

        try:

            # ? FASE 1: Buscar conocimiento existente por descripción (case-insensitive)

            query = """
                SELECT IdConocimientosOtros 
                FROM dbo.ConocimientosOtros 
                WHERE LOWER(Descripcion) = LOWER(?)
            """
            cursor.execute(query, (conocimiento,))
            result = cursor.fetchone()

            # Retornar ID si encontramos coincidencia exacta
            if result:
                return result[0]

            # ? FASE 2: Insertar nuevo conocimiento con campos de auditoría

            insert_query = """
                INSERT INTO dbo.ConocimientosOtros 
                (Descripcion, FechaModificacion, UsuarioModificacion, FechaAlta, UsuarioAlta)
                VALUES (?, GETDATE(), ?, GETDATE(), ?)
            """
            cursor.execute(insert_query, (conocimiento, self.default_user_id, self.default_user_id))

            # Recuperar ID auto-generado del registro recién insertado
            cursor.execute("SELECT SCOPE_IDENTITY()")
            result = cursor.fetchone()

            # ? FASE 3: Validar inserción exitosa y retornar nuevo ID

            if result and result[0]:
                new_id = int(result[0])
                logger.info(f"Nuevo conocimiento 'otros' creado: {conocimiento} (ID: {new_id})")
                return new_id

        # Manejar conflictos de concurrencia (otro proceso ya lo creó)
        except pyodbc.IntegrityError:
            cursor.execute(query, (conocimiento,))
            result = cursor.fetchone()
            if result:
                return result[0]

        # Capturar errores generales de base de datos
        except Exception as e:
            logger.error(f"Error en _get_or_create_otros_conocimientos: {e}")

        # ? Falló tanto búsqueda como creación
        return None
