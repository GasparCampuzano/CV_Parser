#!/usr/bin/env python3
"""
Mixins para inserción de CVs en base de datos.
"""

# Este __init__.py puede estar vacío
# O si quieres, puedes exportar solo los mixins para uso directo:

from .candidato import CandidatoInserter
from .catalogos import CatalogosManager
from .conocimientos import ConocimientosInserter
from .experiencia import ExperienciaInserter
from .formacion import FormacionInserter
from .idiomas import IdiomasInserter
from .utils import format_date_for_sql

__all__ = [
    'CandidatoInserter',
    'CatalogosManager',
    'ConocimientosInserter',
    'ExperienciaInserter',
    'FormacionInserter',
    'IdiomasInserter',
    'format_date_for_sql',
]

# Información del módulo
__version__ = '2.0.0'
__author__ = 'Sistema de Procesamiento de CVs'
__description__ = 'Mixins para inserción de datos de CVs en SQL Server'