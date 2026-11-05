#!/usr/bin/env python3
"""
Utilidades y funciones auxiliares para el módulo de inserción de CVs.
"""

# Importación de librerías estándar y utilidades de tipado
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

# Añade el directorio raíz del proyecto al PYTHONPATH
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Importa el logger desde la configuración del proyecto
from config.settings import get_logger
logger = get_logger(__name__)


# * Función que convierte distintas representaciones de fecha a un formato estándar SQL (YYYY-MM-DD)
def format_date_for_sql(date_str: Optional[str]) -> Optional[str]:

    """
    Normaliza y convierte diferentes representaciones de fecha a un formato
    estándar compatible con SQL Server (YYYY-MM-DD).

    Args:
        date_str (Optional[str]): Cadena de texto que representa una fecha
            en diversos formatos.

    Returns:
        Optional[str]: Fecha en formato "YYYY-MM-DD" si se puede interpretar,
        en caso contrario devuelve None.
    """

    # Verifica casos de valores nulos o representaciones textuales de null
    if not date_str or date_str == 'None' or date_str == 'null':
        return None

    # Convierte el valor a cadena, elimina espacios y asigna None si queda vacío
    date_str = str(date_str).strip() or None

    # ---------------------------------------------------------------------------------------------------------------- #

    # ? Normaliza formatos parciales de fecha (YYYY-MM-DD, YYYY-MM, YYYY) completándolos con día/mes cuando faltan

    # Caso: fecha completa ya en formato ISO "YYYY-MM-DD"
    if len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-':
        return date_str

    # Caso: año y mes "YYYY-MM" → se completa con "-01"
    if len(date_str) == 7 and date_str[4] == '-':
        return f"{date_str}-01"

    # Caso: solo año "YYYY" → se completa con "-01-01"
    if len(date_str) == 4 and date_str.isdigit():
        return f"{date_str}-01-01"

    # Caso: formato "YYYY-MM" o "MM-YYYY" → se completa con la fecha "Año-Mes" o "Mes-Año"
    try:

        # Normaliza separadores y divide en partes
        if '/' in date_str or '-' in date_str:
            parts = date_str.replace('/', '-').split('-')

            # Interpreta si la cadena está en formato Año-Mes o Mes-Año y construye la fecha correspondiente
            if len(parts) == 2:
                if len(parts[0]) == 4:  # Año primero
                    return f"{parts[0]}-{parts[1].zfill(2)}-01"
                else:
                    return f"{parts[1]}-{parts[0].zfill(2)}-01"

    # Ignora errores y permite continuar
    except Exception:
        pass

    # ---------------------------------------------------------------------------------------------------------------- #

    # Palabras clave que indican actualidad → tratadas como NULL
    if date_str.lower() in ['presente', 'actual', 'actualidad', 'present', 'current']:
        return None

    # Si ninguna condición se cumple, registra advertencia y devuelve None
    logger.warning(f"No se pudo convertir fecha: {date_str}")
    return None


def insertar_texto_cv(json_data: Dict, id_candidato: int, conn) -> bool:
    """
    Inserta el texto parseado del CV en la tabla dbo.CandidatosCv

    Args:
        json_data: El JSON completo del CV
        id_candidato: ID del candidato
        conn: Conexión activa a la base de datos

    Returns:
        bool: True si se insertó correctamente, False si hubo error
    """
    try:
        cursor = conn.cursor()

        # Extraer el texto del metadata
        texto_cv = json_data.get("_metadata", {}).get("Original Text", "")
        archivo = json_data.get("_metadata", {}).get("archivo_original", "")

        if not texto_cv:
            logger.error(f"No se encontró texto para candidato {id_candidato}")
            return False

        # Verificar si ya existe
        cursor.execute("""
            SELECT IdCandidatoCv FROM dbo.CandidatosCv 
            WHERE IdCandidato = ?
        """, id_candidato)

        existe = cursor.fetchone()
        fecha_actual = datetime.now()

        if existe:
            # Actualizar
            cursor.execute("""
                UPDATE dbo.CandidatosCv
                SET TextoCv = ?,
                    Archivo = ?,
                    Observaciones = ?,
                    FechaModificacion = ?
                WHERE IdCandidato = ?
            """, texto_cv, archivo, "Pendiente de revisión", fecha_actual, id_candidato)

        else:
            # Insertar nuevo
            cursor.execute("""
                INSERT INTO dbo.CandidatosCv 
                (IdCandidato, FechaCv, Archivo, TextoCv, Observaciones, 
                 FechaModificacion, UsuarioModificacion, FechaAlta, UsuarioAlta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, id_candidato, fecha_actual, archivo, texto_cv,
                           "Pendiente de revisión", fecha_actual, 1, fecha_actual, 1)

        conn.commit()
        logger.info(f"Texto CV insertado/actualizado para candidato {id_candidato}")
        return True

    except Exception as e:
        logger.error(f"Error insertando texto CV: {str(e)}")
        conn.rollback()
        return False
