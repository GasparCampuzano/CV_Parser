#!/usr/bin/env python3
"""
Mixin para inserción de candidatos en la base de datos.
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

# * Mixin que proporciona funcionalidad para insertar candidatos en la base de datos con validación completa
class CandidatoInserter:

    """
    Mixin que proporciona funcionalidad especializada para la inserción de candidatos.

    Esta clase implementa el patrón Mixin para añadir capacidades de inserción de candidatos
    a otras clases. Maneja la inserción completa en la tabla principal 'Candidatos' con todos
    los campos requeridos, incluyendo validación de datos, manejo de valores por defecto y
    logging detallado de operaciones.

    La clase asume que la clase que la herede tiene definido el atributo 'default_user_id'
    para el control de auditoría.

    Attributes:
        Heredados de la clase padre (debe tener default_user_id definido)

    Methods:
        _insert_candidato: Inserta un candidato completo en la base de datos
    """

    # * Realiza la inserción completa de un candidato en la tabla principal con manejo de errores y logging
    def _insert_candidato(self, datos_contacto: Dict[str, Any], cursor: pyodbc.Cursor) -> Optional[int]:

        """
        Inserta un registro completo de candidato en la tabla principal de la base de datos.

        Esta función maneja la inserción de un candidato con todos sus campos, incluyendo
        la separación automática del nombre completo, inferencia de datos opcionales,
        y manejo de valores por defecto según el esquema de la base de datos.

        Utiliza una consulta SQL con OUTPUT INSERTED para obtener el ID auto-generado
        de forma atómica, garantizando la integridad de la operación.

        Args:
            datos_contacto (Dict[str, Any]): Diccionario con los datos del candidato.
                Debe incluir al menos 'nombre_completo'. Campos opcionales incluyen:
                'telefono', 'email', 'dni', 'nacionalidad', 'fecha_nacimiento',
                'direccion', 'provincia', 'localidad', 'codigo_postal', 'linkedin',
                'duracion_experiencia_total', etc.
            cursor (pyodbc.Cursor): Cursor activo de la conexión a la base de datos
                con permisos de escritura en la tabla Candidatos.

        Returns:
            Optional[int]: ID del candidato recién insertado si la operación es exitosa,
                None si ocurre algún error durante la inserción.

        Raises:
            Exception: Propaga cualquier excepción de base de datos o de validación,
                después de loggear el error con contexto detallado.
        """

        try:

            # ? FASE 1: Extracción del nombre

            # Extraer el nombre completo del diccionario de datos de contacto
            nombre = datos_contacto.get('nombre', '')
            apellidos = datos_contacto.get('apellidos', '')

            # ? FASE 2: Extracción del seoxo

            # Inferir sexo basándose en el nombre
            sexo = datos_contacto.get('sexo', None)

            # ? FASE 2.5: Procesar dirección para obtener IDs
            # Extraer datos de dirección
            direccion_dict = datos_contacto.get('direccion', {})

            # Obtener ID de localidad
            localidad_id = None
            localidad = direccion_dict.get('localidad')
            if localidad:
                localidad_id = self._get_localidad_id(localidad, cursor)

            # Obtener ID de provincia
            provincia_id = None
            provincia = direccion_dict.get('provincia')
            if provincia:
                provincia_id = self._get_provincia_id(provincia, cursor)
            # Si no se encontró pero tenemos localidad, obtener provincia desde la localidad
            elif localidad_id:
                provincia_id = self._get_provincia_from_localidad(localidad_id, cursor)

            # Código postal con valor por defecto 0 si no existe
            codigo_postal = direccion_dict.get('codigo_postal')
            if not codigo_postal or codigo_postal == '' or codigo_postal is None:
                codigo_postal = 0
            else:
                # Asegurarse de que es un número
                try:
                    codigo_postal = int(codigo_postal)
                except (ValueError, TypeError):
                    codigo_postal = 0

            logger.debug(f"IDs de ubicación: Localidad={localidad_id}, Provincia={provincia_id}")

            # ? FASE 3: Definir consulta SQL INSERT con cláusula OUTPUT para retornar el ID auto-generado

            query = """ 
            INSERT INTO dbo.Candidatos (
                IdEmpleado,                -- 1. FK a tabla Empleado (NULL si no es empleado interno)
                FechaAltaEmpleado,         -- 2. Fecha cuando se dio de alta como empleado
                Nombre,                    -- 3. Nombre del candidato
                Apellidos,                 -- 4. Apellidos del candidato
                Sexo,                      -- 5. Sexo (H/M/NULL)
                TelefonoContacto,          -- 6. Número de teléfono
                CorreoElectronico,         -- 7. Email de contacto
                IdEstadoCandidato,         -- 8. FK a EstadoCandidato (9 = Nuevo)
                FechaEstado,               -- 9. Fecha del cambio de estado actual
                Revisado,                  -- 10. Flag: 0=No revisado, 1=Revisado por RRHH
                FechaRevisionInicial,      -- 11. Fecha de primera revisión (NULL hasta revisión)
                IdPuesto,                  -- 12. FK a Puestos (puesto al que aplica)
                FechaNacimiento,           -- 13. Fecha de nacimiento
                Nacionalidad,              -- 14. Nacionalidad del candidato
                DocumentoIdentidad,        -- 15. DNI/Pasaporte
                DireccionActual,           -- 16. Dirección postal
                Provincia,                 -- 17. Provincia de residencia
                Localidad,                 -- 18. Ciudad/localidad
                CodigoPostal,              -- 19. Código postal
                IdOrigenCv,                -- 20. FK a OrigenCV (de dónde viene el CV)
                Linkedin,                  -- 21. URL del perfil LinkedIn
                Foto,                      -- 22. Ruta a foto del candidato
                Titulado,                  -- 23. Flag: tiene titulación universitaria
                Homologado,                -- 24. Flag: títulos homologados en España
                Rgdp,                      -- 25. Flag: aceptación del RGPD
                FechaRgdp,                 -- 26. Fecha de aceptación RGPD
                DuracionExperiencia,       -- 27. Experiencia total en meses
                FechaModificacion,         -- 28. Timestamp de última modificación (NULL para altas)
                UsuarioModificacion,       -- 29. ID del usuario que modificó (NULL para altas)
                FechaAlta,                 -- 30. Timestamp de creación
                UsuarioAlta                -- 31. ID del usuario que creó el registro
            )
            OUTPUT INSERTED.IdCandidato    -- Retorna el ID auto-generado
            VALUES (
                ?,                  -- 1. IdEmpleado
                NULL,               -- 2. FechaAltaEmpleado
                ?,                  -- 3. Nombre
                ?,                  -- 4. Apellidos
                ?,                  -- 5. Sexo (H/M/NULL)
                ?,                  -- 6. TelefonoContacto
                ?,                  -- 7. CorreoElectronico
                ?,                  -- 8. IdEstadoCandidato (9 = Nuevo)
                GETDATE(),          -- 9. FechaEstado (momento actual)
                ?,                  -- 10. Revisado (0 = no revisado)
                NULL,               -- 11. FechaRevisionInicial (NULL hasta primera revisión)
                ?,                  -- 12. IdPuesto
                ?,                  -- 13. FechaNacimiento
                ?,                  -- 14. Nacionalidad
                ?,                  -- 15. DocumentoIdentidad
                ?,                  -- 16. DireccionActual
                ?,                  -- 17. Provincia
                ?,                  -- 18. Localidad
                ?,                  -- 19. CodigoPostal
                ?,                  -- 20. IdOrigenCv
                ?,                  -- 21. Linkedin
                ?,                  -- 22. Foto
                ?,                  -- 23. Titulado
                ?,                  -- 24. Homologado
                ?,                  -- 25. Rgdp
                NULL,               -- 26. FechaRgdp (momento actual si acepta)
                ?,                  -- 27. DuracionExperiencia
                NULL,               -- 28. FechaModificacion (NULL para altas nuevas)
                NULL,               -- 29. UsuarioModificacion (NULL para altas nuevas)
                GETDATE(),          -- 30. FechaAlta (momento actual)
                ?                   -- 31. UsuarioAlta
            )
            """

            # ? Mapear datos del candidato a tupla de parámetros SQL con valores por defecto y validaciones aplicadas
            values = (
                # 1. IdEmpleado
                datos_contacto.get('id_empleado', None),

                # 3-4. Datos básicos
                nombre or 'Sin nombre',
                apellidos or 'Sin apellidos',

                # 5. Sexo inferido
                sexo,

                # 6-7. Contacto
                datos_contacto.get('telefono'),
                datos_contacto.get('email'),

                # 8. Estado (9 = Nuevo base de datos)
                9,

                # 10. Revisado
                0,

                # 12. IdPuesto (por ahora NULL, pendiente implementar mapeo)
                datos_contacto.get('id_puesto', None),

                # 13. Fecha nacimiento
                format_date_for_sql(datos_contacto.get('fecha_nacimiento')),

                # 14-15. Identidad
                datos_contacto.get('nacionalidad'),
                datos_contacto.get('dni'),

                # 16-19. Dirección (usando IDs de catálogo)
                direccion_dict.get('calle'),  # DireccionActual (solo la calle)
                provincia_id,  # Provincia (ahora usando el ID)
                localidad_id,  # Localidad (usando el ID)
                codigo_postal,  # CodigoPostal (ya validado, nunca será NULL)

                # 20-21. Origen y LinkedIn
                datos_contacto.get('id_origen_cv', None),
                datos_contacto.get('linkedin'),

                # 22. Foto
                datos_contacto.get('foto', None),

                # 23-25. Flags
                datos_contacto.get('titulado', 0),
                datos_contacto.get('homologado', 0),
                datos_contacto.get('rgdp', 0),

                # 27. Duración experiencia total
                datos_contacto.get('duracion_experiencia_total', 0),

                # 31. UsuarioAlta
                self.default_user_id
            )

            # ? Ejecutar inserción SQL y recuperar el ID auto-generado del candidato recién creadoReintentar

            # Ejecutar la consulta SQL con los valores preparados
            cursor.execute(query, values)

            # Obtener el resultado del OUTPUT INSERTED.IdCandidato
            result = cursor.fetchone()

            # Verificar que la inserción fue exitosa y retornar el ID
            if result:
                candidato_id = result[0]
                logger.info(f"Candidato insertado con ID: {candidato_id}")
                return candidato_id

            # Retornar None si la inserción falló o no se pudo obtener el ID generado
            return None

        # Capturar, loggear errores de inserción con contexto de depuración y re-propagar la excepción
        except Exception as e:
            logger.error(f"Error insertando candidato: {e}")
            logger.error(f"Valores problemáticos: {values[:5]}...")
            raise
