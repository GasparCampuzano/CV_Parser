#!/usr/bin/env python3
"""
Mixin para gestión de direcciones y localidades en la base de datos.
"""

import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import pyodbc

# Añade el directorio raíz del proyecto al PYTHONPATH
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import get_logger

logger = get_logger(__name__)


class DireccionesManager:
    """
    Mixin que proporciona funcionalidad para parsear direcciones
    y obtener IDs de localidades y provincias.
    """

    def _get_provincia_id(self, provincia_nombre: str, cursor: pyodbc.Cursor) -> Optional[int]:
        """
        Busca el ID de una provincia en la tabla dbo.Provincias.

        Args:
            provincia_nombre: Nombre de la provincia a buscar
            cursor: Cursor de la BD

        Returns:
            ID de la provincia o None si no se encuentra
        """
        if not provincia_nombre:
            return None

        try:
            # Búsqueda exacta primero
            query = """
            SELECT IdProvincia 
            FROM dbo.Provincias 
            WHERE LOWER(Descripcion) = LOWER(?)
            """
            cursor.execute(query, (provincia_nombre,))
            result = cursor.fetchone()

            if result:
                logger.info(f"Provincia '{provincia_nombre}' encontrada exacta con ID: {result[0]}")
                return result[0]

            # Buscar si la provincia está contenida en la descripción
            query_contains = """
            SELECT TOP 1 IdProvincia, Descripcion 
            FROM dbo.Provincias 
            WHERE LOWER(Descripcion) LIKE LOWER(?)
            ORDER BY CASE 
                WHEN LOWER(Descripcion) = LOWER(?) THEN 1
                WHEN LOWER(Descripcion) LIKE LOWER(?) THEN 2
                ELSE 3
            END, LEN(Descripcion)
            """
            cursor.execute(query_contains,
                           (f'{provincia_nombre}%',
                            provincia_nombre,
                            f'{provincia_nombre}%'))
            result_like = cursor.fetchone()

            if result_like:
                logger.info(
                    f"Provincia '{provincia_nombre}' encontrada parcial: '{result_like[1]}' (ID: {result_like[0]})")
                return result_like[0]

            logger.warning(f"Provincia '{provincia_nombre}' no encontrada en el catálogo")

        except Exception as e:
            logger.error(f"Error buscando provincia '{provincia_nombre}': {e}")

        return None

    def _get_provincia_from_localidad(self, localidad_id: int, cursor: pyodbc.Cursor) -> Optional[int]:
        """
        Obtiene la provincia de una localidad específica.

        Args:
            localidad_id: ID de la localidad
            cursor: Cursor de la BD

        Returns:
            ID de la provincia o None si no se encuentra
        """
        if not localidad_id:
            return None

        try:
            query = """
            SELECT IdProvincia 
            FROM dbo.Localidades 
            WHERE IdLocalidad = ?
            """
            cursor.execute(query, (localidad_id,))
            result = cursor.fetchone()

            if result:
                logger.info(f"Provincia obtenida desde localidad {localidad_id}: ID {result[0]}")
                return result[0]

        except Exception as e:
            logger.error(f"Error obteniendo provincia desde localidad {localidad_id}: {e}")

        return None

    def _parse_direccion(self, direccion_completa: str) -> Dict[str, Optional[str]]:
        """
        Parsea una dirección completa para extraer localidad, provincia y código postal.
        """
        if not direccion_completa:
            return {'localidad': None, 'provincia': None, 'codigo_postal': None}

        resultado = {
            'localidad': None,
            'provincia': None,
            'codigo_postal': None,
            'direccion_sin_localidad': direccion_completa
        }

        try:
            # Buscar código postal (5 dígitos)
            cp_pattern = r'\b(\d{5})\b'
            cp_match = re.search(cp_pattern, direccion_completa)
            if cp_match:
                resultado['codigo_postal'] = cp_match.group(1)
                direccion_completa = direccion_completa.replace(cp_match.group(1), '').strip()

            # Lista de provincias españolas para detección
            provincias_conocidas = [
                'Madrid', 'Barcelona', 'Valencia', 'Sevilla', 'Alicante',
                'Málaga', 'Murcia', 'Cádiz', 'Vizcaya', 'Baleares',
                'Coruña', 'Las Palmas', 'Asturias', 'Zaragoza', 'Pontevedra',
                'Granada', 'Tarragona', 'Córdoba', 'Gerona', 'Guipúzcoa',
                'Toledo', 'Badajoz', 'Navarra', 'Jaén', 'Cantabria',
                'Castellón', 'Huelva', 'Valladolid', 'Ciudad Real', 'León',
                'Lérida', 'Cáceres', 'Albacete', 'Burgos', 'Salamanca',
                'Almería', 'Lugo', 'Ávila', 'Orense', 'La Rioja',
                'Guadalajara', 'Huesca', 'Cuenca', 'Zamora', 'Palencia',
                'Segovia', 'Teruel', 'Soria', 'Melilla', 'Ceuta'
            ]

            # Separar por comas
            partes = [p.strip() for p in direccion_completa.split(',')]

            if len(partes) >= 2:
                # El último elemento suele ser la localidad
                posible_localidad = partes[-1].strip()

                # Verificar si la localidad es también una provincia (ej: Madrid, Barcelona)
                localidad_lower = posible_localidad.lower()
                for provincia in provincias_conocidas:
                    if provincia.lower() == localidad_lower:
                        resultado['provincia'] = provincia
                        break

                resultado['direccion_sin_localidad'] = ', '.join(partes[:-1])
                resultado['localidad'] = posible_localidad

                # Si hay más de 2 partes, la penúltima podría ser la provincia
                if len(partes) >= 3 and not resultado['provincia']:
                    posible_provincia = partes[-2].strip()
                    for provincia in provincias_conocidas:
                        if provincia.lower() in posible_provincia.lower():
                            resultado['provincia'] = provincia
                            resultado['direccion_sin_localidad'] = ', '.join(partes[:-2])
                            break

            elif len(partes) == 1:
                resultado['localidad'] = self._extraer_localidad_de_texto(partes[0])

            logger.debug(f"Dirección parseada: {resultado}")

        except Exception as e:
            logger.error(f"Error parseando dirección '{direccion_completa}': {e}")

        return resultado

    def _extraer_localidad_de_texto(self, texto: str) -> Optional[str]:
        """
        Intenta extraer la localidad de un texto usando patrones comunes.
        """
        # Lista de ciudades principales de España para detección
        ciudades_conocidas = [
            'Madrid', 'Barcelona', 'Valencia', 'Sevilla', 'Zaragoza',
            'Málaga', 'Murcia', 'Palma', 'Las Palmas', 'Bilbao',
            'Alicante', 'Córdoba', 'Valladolid', 'Vigo', 'Gijón',
            'Toledo', 'Badajoz', 'Marbella', 'Segovia', 'Ávila'
        ]

        texto_lower = texto.lower()
        for ciudad in ciudades_conocidas:
            if ciudad.lower() in texto_lower:
                return ciudad

        return None

    def _get_localidad_id(self, localidad_nombre: str, cursor: pyodbc.Cursor) -> Optional[int]:
        """
        Busca el ID de una localidad en la tabla dbo.Localidades.

        Args:
            localidad_nombre: Nombre de la localidad a buscar
            cursor: Cursor de la BD

        Returns:
            ID de la localidad o None si no se encuentra
        """
        if not localidad_nombre:
            return None

        try:
            # Búsqueda exacta primero
            query = """
            SELECT IdLocalidad 
            FROM dbo.Localidades 
            WHERE LOWER(Descripcion) = LOWER(?)
            """
            cursor.execute(query, (localidad_nombre,))
            result = cursor.fetchone()

            if result:
                logger.info(f"Localidad '{localidad_nombre}' encontrada con ID: {result[0]}")
                return result[0]

            # Si no hay coincidencia exacta, buscar coincidencia parcial
            query_like = """
            SELECT TOP 1 IdLocalidad, Descripcion 
            FROM dbo.Localidades 
            WHERE Descripcion LIKE ?
            ORDER BY LEN(Descripcion)
            """
            cursor.execute(query_like, (f'%{localidad_nombre}%',))
            result_like = cursor.fetchone()

            if result_like:
                logger.warning(
                    f"Localidad '{localidad_nombre}' no encontrada exacta, usando '{result_like[1]}' (ID: {result_like[0]})")
                return result_like[0]

            logger.warning(f"Localidad '{localidad_nombre}' no encontrada en el catálogo")

        except Exception as e:
            logger.error(f"Error buscando localidad '{localidad_nombre}': {e}")

        return None