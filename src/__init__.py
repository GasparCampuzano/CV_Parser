"""
CV Processor - Módulo Principal

Este módulo contiene todas las funcionalidades principales para el procesamiento
automatizado de currículums vitae, incluyendo extracción de texto, procesamiento
con IA y gestión de datos.

Componentes principales:
- azure_openai_client: Cliente para Azure OpenAI API
- cv_extractor: Extractor de texto de múltiples formatos de archivo
- database: Operaciones de base de datos MySQL
- utils: Utilidades y funciones auxiliares
"""

import logging
import sys
from pathlib import Path

# Agregar el directorio padre al path para poder importar config
sys.path.insert(0, str(Path(__file__).parent.parent))

# Importar configuración centralizada
try:
    from config import settings
    settings_available = True
except ImportError:
    settings = None
    settings_available = False
    print("[WARN] Warning: Could not import settings module")

# Configurar logging
if settings_available:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(settings.LOG_FILE) if hasattr(settings, 'LOG_FILE') else logging.NullHandler(),
            logging.StreamHandler()
        ]
    )
else:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# Información del módulo
__version__ = "1.0.0"
__author__ = "Gaspar Campuzano"
__description__ = "CV Processor - Automated Resume Processing System"

# Log de inicio
logger.info(f"Inicializando CV Processor v{__version__}")

# Importaciones principales con logging detallado
try:
    from .azure_openai_client import (
        check_azure_openai_status,
        send_to_azure_openai,
        parse_azure_openai_response,
    )
    azure_openai_available = True
    logger.debug("[OK] Módulo azure_openai_client cargado correctamente")
except ImportError as e:
    check_azure_openai_status = None
    send_to_azure_openai = None
    parse_azure_openai_response = None
    create_extraction_prompt = None
    azure_openai_available = False
    logger.warning(f"[WARN] Módulo azure_openai_client no disponible: {e}")

try:
    from .cv_extractor import (
        extract_text_from_file,
        clean_and_normalize_text
    )
    cv_extractor_available = True
    logger.debug("[OK] Módulo cv_extractor cargado correctamente")
except ImportError as e:
    extract_text_from_file = None
    clean_and_normalize_text = None
    cv_extractor_available = False
    logger.warning(f"[WARN] Módulo cv_extractor no disponible: {e}")

try:
    from . import database
    database_available = True
    logger.debug("[OK] Módulo database cargado correctamente")
except ImportError as e:
    database_available = False
    logger.warning(f"[WARN] Módulo database no disponible: {e}")

try:
    from . import app
    app_available = True
    logger.debug("[OK] Módulo app cargado correctamente")
except ImportError as e:
    app_available = False
    logger.warning(f"[WARN] Módulo app no disponible: {e}")

# Configuración de disponibilidad de módulos
AVAILABLE_MODULES = {
    'settings': settings_available,
    'app': app_available,
    'azure_openai': azure_openai_available,
    'cv_extractor': cv_extractor_available,
    'database': database_available,
}

# Usar configuración desde settings si está disponible
if settings_available:
    SUPPORTED_EXTENSIONS = settings.ALLOWED_EXTENSIONS
    DEFAULT_CONFIG = {
        'max_file_size': settings.MAX_CONTENT_LENGTH,
        'supported_languages': ['es', 'en'],
        'ai_provider': 'azure_openai',
        'max_retries': settings.AI_MAX_RETRIES,
        'timeout': settings.AI_TIMEOUT
    }
else:
    # Valores por defecto si settings no está disponible
    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt'}
    DEFAULT_CONFIG = {
        'max_file_size': 16 * 1024 * 1024,
        'supported_languages': ['es', 'en'],
        'ai_provider': 'azure_openai',
        'max_retries': 3,
        'timeout': 30
    }

def get_module_info():
    """
    Retorna información sobre el estado de los módulos disponibles.

    Returns:
        dict: Información de módulos y configuración
    """
    return {
        'version': __version__,
        'available_modules': AVAILABLE_MODULES,
        'supported_extensions': list(SUPPORTED_EXTENSIONS),
        'default_config': DEFAULT_CONFIG,
        'settings_loaded': settings_available
    }

def check_dependencies():
    """
    Verifica que las dependencias críticas estén disponibles.

    Returns:
        dict: Estado de dependencias críticas
    """
    critical_modules = ['settings', 'cv_extractor']
    ai_modules = ['azure_openai']

    syst = {
        'critical_ok': all(AVAILABLE_MODULES.get(mod, False) for mod in critical_modules),
        'ai_available': any(AVAILABLE_MODULES.get(mod, False) for mod in ai_modules),
        'database_ready': AVAILABLE_MODULES.get('database', False),
        'app_ready': AVAILABLE_MODULES.get('app', False),
        'ready_for_production': False
    }

    # El sistema está listo si tiene módulos críticos, IA, app y settings
    syst['ready_for_production'] = (
            syst['critical_ok'] and
            syst['ai_available'] and
            syst['app_ready']
    )

    # Log del estado
    if syst['ready_for_production']:
        logger.info("[OK] Sistema listo para producción")
    else:
        missing = [mod for mod, available in AVAILABLE_MODULES.items() if not available]
        logger.warning(f"[WARN] Sistema no listo. Módulos faltantes: {missing}")

    return syst

def system_status():
    """
    Función de conveniencia que combina información del módulo y dependencias.

    Returns:
        dict: Estado completo del sistema
    """
    sys_status = {
        **get_module_info(),
        'dependencies': check_dependencies()
    }

    # Log resumen del estado
    logger.info(f"Estado del sistema: {len([v for v in AVAILABLE_MODULES.values() if v])}/{len(AVAILABLE_MODULES)} módulos disponibles")

    return sys_status

# Verificar estado al importar
status = check_dependencies()
if not status['critical_ok']:
    logger.error("[ERROR] Módulos críticos no disponibles. El sistema puede no funcionar correctamente.")

# Exportar las funciones principales disponibles
__all__ = [
    # Información del módulo
    '__version__',
    '__author__',
    '__description__',

    # Funciones de utilidad
    'get_module_info',
    'check_dependencies',
    'system_status',

    # Configuración
    'SUPPORTED_EXTENSIONS',
    'DEFAULT_CONFIG',
    'AVAILABLE_MODULES',
]

# Agregar funciones disponibles a __all__ dinámicamente
if azure_openai_available:
    __all__.extend([
        'check_azure_openai_status',
        'send_to_azure_openai',
        'parse_azure_openai_response',
        'create_extraction_prompt'
    ])

if cv_extractor_available:
    __all__.extend([
        'extract_text_from_file',
        'clean_and_normalize_text'
    ])

# Log final
logger.info(f"CV Processor v{__version__} inicializado - {len(__all__)} funciones exportadas")