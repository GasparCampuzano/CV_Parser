# config/settings.py
"""
Configuración centralizada del sistema CV Processor
Integra todas las configuraciones necesarias para el ecosistema completo.
Actualizado para Microsoft SQL Server.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# Cargar variables de entorno
load_dotenv()

# =============================
# CONFIGURACIÓN BASE
# =============================
BASE_DIR = Path(__file__).parent.parent

# =============================
# CONFIGURACIÓN FLASK
# =============================
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-cambiar-en-produccion')
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
HOST = os.getenv('HOST', '127.0.0.1')
PORT = int(os.getenv('PORT', 5000))

# =============================
# RUTAS DE ALMACENAMIENTO
# =============================
STORAGE_DIR = BASE_DIR / 'storage'
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# =============================
# AZURE OPENAI
# =============================
AZURE_OPENAI_ENDPOINT = os.getenv('AZURE_OPENAI_ENDPOINT')
AZURE_OPENAI_API_KEY = os.getenv('AZURE_OPENAI_API_KEY')
AZURE_OPENAI_API_VERSION = os.getenv('AZURE_OPENAI_API_VERSION', '2023-12-01-preview')
DEPLOYMENT_NAME = os.getenv('DEPLOYMENT_NAME', 'gpt-35-turbo')

# Configuración AI
MAX_TOKENS = int(os.getenv('MAX_TOKENS', 4000))
TEMPERATURE = float(os.getenv('TEMPERATURE', 0.1))
AI_TIMEOUT = int(os.getenv('AI_TIMEOUT', 30))  # segundos
AI_MAX_RETRIES = int(os.getenv('AI_MAX_RETRIES', 3))

# =============================
# CONFIGURACIÓN MICROSOFT SQL SERVER (pyodbc)
# =============================

# Configuración básica de conexión
MSSQL_SERVER = os.getenv('MSSQL_SERVER', 'localhost')
MSSQL_PORT = int(os.getenv('MSSQL_PORT', 1433))
MSSQL_DATABASE = os.getenv('MSSQL_DATABASE', 'cv_database')
MSSQL_USER = os.getenv('MSSQL_USER', '')
MSSQL_PASSWORD = os.getenv('MSSQL_PASSWORD', '')  # Nunca credenciales en el código: van en .env

# Configuración adicional SQL Server
MSSQL_INSTANCE = os.getenv('MSSQL_INSTANCE', '')  # Para instancias nombradas
MSSQL_TRUSTED_CONNECTION = os.getenv('MSSQL_TRUSTED_CONNECTION', 'False').lower() == 'true'
MSSQL_ENCRYPT = os.getenv('MSSQL_ENCRYPT', 'True').lower() == 'true'
MSSQL_TRUST_SERVER_CERTIFICATE = os.getenv('MSSQL_TRUST_SERVER_CERTIFICATE', 'True').lower() == 'true'

# Configuración avanzada
DB_CHARSET = os.getenv('DB_CHARSET', 'UTF-8')
DB_AUTOCOMMIT = os.getenv('DB_AUTOCOMMIT', 'False').lower() == 'true'
DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', 5))
DB_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', 10))
DB_POOL_RECYCLE = int(os.getenv('DB_POOL_RECYCLE', 3600))
DB_POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', 30))
DB_ECHO = os.getenv('DB_ECHO', 'False').lower() == 'true'

# Configuración del driver ODBC para SQL Server
# Opciones comunes:
# - 'ODBC Driver 18 for SQL Server' (Más reciente, recomendado)
# - 'ODBC Driver 17 for SQL Server' (Ampliamente compatible)
# - 'SQL Server Native Client 11.0' (Legacy)
# - 'SQL Server' (Muy antiguo, no recomendado)
ODBC_DRIVER = os.getenv('ODBC_DRIVER', 'ODBC Driver 17 for SQL Server')

# Connection timeouts
DB_CONNECTION_TIMEOUT = int(os.getenv('DB_CONNECTION_TIMEOUT', 30))
DB_QUERY_TIMEOUT = int(os.getenv('DB_QUERY_TIMEOUT', 60))

# Configuración de reintentos para base de datos
DB_MAX_RETRIES = int(os.getenv('DB_MAX_RETRIES', 3))
DB_RETRY_DELAY = int(os.getenv('DB_RETRY_DELAY', 2))  # segundos entre reintentos

# =============================
# CONFIGURACIÓN DE LOGGING
# =============================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# Archivos de log separados por módulo
LOG_FILES = {
    'main': LOG_DIR / 'cv_processor.log',
}

LOG_MAX_SIZE = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# =============================
# CONFIGURACIÓN DE PROCESAMIENTO
# =============================
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt'}
MIN_TEXT_LENGTH = 100  # Mínimo de caracteres para considerar válido un CV
EXTRACTION_TIMEOUT = int(os.getenv('EXTRACTION_TIMEOUT', 60))  # segundos
CV_SHORT_THRESHOLD = int(os.getenv('CV_SHORT_THRESHOLD', 1500))

# =============================
# CONFIGURACIÓN OCR (opcional)
# =============================
USE_OCR = os.getenv('USE_OCR', 'False').lower() == 'true'
TESSERACT_PATH = os.getenv('TESSERACT_PATH', '/usr/bin/tesseract')  # Ajustar según OS
OCR_LANGUAGE = os.getenv('OCR_LANGUAGE', 'spa+eng')

# =============================
# CONFIGURACIÓN DE VALIDACIÓN
# =============================
STRICT_VALIDATION = os.getenv('STRICT_VALIDATION', 'True').lower() == 'true'
AUTO_CREATE_AUXILIARS = os.getenv('AUTO_CREATE_AUXILIARS', 'False').lower() == 'true'

# Validación específica de duplicados
DUPLICATE_CHECK_FIELDS = ['dni', 'email', 'telefono']  # Orden de prioridad
FUZZY_MATCH_THRESHOLD = float(os.getenv('FUZZY_MATCH_THRESHOLD', 0.85))  # Para nombres similares

# =============================
# CONFIGURACIÓN DE CATÁLOGOS
# =============================
# Define qué catálogos requieren validación estricta
STRICT_CATALOGS = {
    'idiomas': True,  # Solo idiomas del catálogo
    'habilidades_tecnicas': True,  # Solo habilidades técnicas validadas
    'habilidades_negocio': True,  # Solo habilidades de negocio validadas
    'empresas': False,  # Se pueden crear nuevas (marcadas como no validadas)
    'instituciones': False  # Se pueden crear nuevas (marcadas como no validadas)
}

# =============================
# CONFIGURACIÓN DE PROCESAMIENTO BATCH
# =============================
BATCH_SIZE = int(os.getenv('BATCH_SIZE', 10))  # CVs por lote
BATCH_COMMIT_FREQUENCY = int(os.getenv('BATCH_COMMIT_FREQUENCY', 5))  # Commit cada N registros
PARALLEL_PROCESSING = os.getenv('PARALLEL_PROCESSING', 'False').lower() == 'true'
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 4))  # Para procesamiento paralelo

# =============================
# CONFIGURACIÓN DE AMBIENTE
# =============================
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')  # development, staging, production
IS_PRODUCTION = ENVIRONMENT == 'production'
IS_DEVELOPMENT = ENVIRONMENT == 'development'

# Ajustes según ambiente
if IS_PRODUCTION:
    DEBUG = False
    DB_ECHO = False
    LOG_LEVEL = 'WARNING'
    STRICT_VALIDATION = True
elif IS_DEVELOPMENT:
    DEBUG = True
    DB_ECHO = True
    LOG_LEVEL = 'INFO'


# =============================
# FUNCIONES DE UTILIDAD
# =============================
def get_db_connection_string():
    """
    Construye la cadena de conexión para SQL Server con pyodbc
    Returns:
        str: Connection string formateada para SQL Server
    """
    # Si usa autenticación de Windows
    if MSSQL_TRUSTED_CONNECTION:
        if MSSQL_INSTANCE:
            server = f"{MSSQL_SERVER}\\{MSSQL_INSTANCE}"
        else:
            server = f"{MSSQL_SERVER},{MSSQL_PORT}"

        connection_string = (
            f"DRIVER={{{ODBC_DRIVER}}};"
            f"SERVER={server};"
            f"DATABASE={MSSQL_DATABASE};"
            f"Trusted_Connection=yes;"
            f"Encrypt={('yes' if MSSQL_ENCRYPT else 'no')};"
            f"TrustServerCertificate={('yes' if MSSQL_TRUST_SERVER_CERTIFICATE else 'no')};"
        )
    else:
        # Autenticación SQL Server
        if MSSQL_INSTANCE:
            server = f"{MSSQL_SERVER}\\{MSSQL_INSTANCE}"
        else:
            server = f"{MSSQL_SERVER},{MSSQL_PORT}"

        connection_string = (
            f"DRIVER={{{ODBC_DRIVER}}};"
            f"SERVER={server};"
            f"DATABASE={MSSQL_DATABASE};"
            f"UID={MSSQL_USER};"
            f"PWD={MSSQL_PASSWORD};"
            f"Encrypt={('yes' if MSSQL_ENCRYPT else 'no')};"
            f"TrustServerCertificate={('yes' if MSSQL_TRUST_SERVER_CERTIFICATE else 'no')};"
        )

    return connection_string


def get_logger(name: str):
    """
    Obtiene un logger configurado con archivo único unificado
    Args:
        name: Nombre del logger
    Returns:
        logging.Logger: Logger configurado
    """
    logger = logging.getLogger(name)

    # Evitar configurar el mismo logger múltiples veces
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL))

    # Evitar propagación de mensajes a loggers padre (previene duplicación)
    logger.propagate = False

    # Handler para archivo - SIEMPRE usa 'main' independiente del parámetro
    try:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            LOG_FILES['main'],  # Siempre usa el archivo unificado
            maxBytes=LOG_MAX_SIZE,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'  # Soporte completo UTF-8 para caracteres especiales
        )
        file_handler.setLevel(getattr(logging, LOG_LEVEL))

        # Formato modificado para incluir el módulo de origen
        unified_format = '%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
        file_handler.setFormatter(
            logging.Formatter(unified_format, datefmt=LOG_DATE_FORMAT)
        )
        logger.addHandler(file_handler)
    except Exception as e:
        # Si falla el archivo, al menos crear console handler
        print(f"Warning: No se pudo crear file handler: {e}")

    # Handler para consola (solo en desarrollo)
    if IS_DEVELOPMENT:
        import sys
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, LOG_LEVEL))

        # Formato más detallado para consola incluyendo módulo
        console_format = '[%(name)s] - %(levelname)s - %(message)s'
        console_handler.setFormatter(
            logging.Formatter(console_format)
        )

        # En Windows, configurar encoding para evitar errores con caracteres especiales
        if hasattr(console_handler.stream, 'reconfigure'):
            try:
                console_handler.stream.reconfigure(encoding='utf-8', errors='replace')
            except:
                pass  # Si falla, continuar sin reconfigurar

        logger.addHandler(console_handler)

    return logger


def validate_config():
    """
    Valida que la configuración crítica esté presente
    Raises:
        ValueError: Si falta configuración crítica
    """
    errors = []

    # Validar Azure OpenAI
    if not AZURE_OPENAI_ENDPOINT:
        errors.append("AZURE_OPENAI_ENDPOINT no configurado")
    if not AZURE_OPENAI_API_KEY:
        errors.append("AZURE_OPENAI_API_KEY no configurado")

    # Validar SQL Server
    if not MSSQL_SERVER:
        errors.append("MSSQL_SERVER no configurado")
    if not MSSQL_USER:
        errors.append("MSSQL_USER no configurado")
    if not MSSQL_PASSWORD and IS_PRODUCTION:
        errors.append("MSSQL_PASSWORD no configurado en producción")
    if not MSSQL_DATABASE:
        errors.append("MSSQL_DATABASE no configurado")

    if errors:
        error_msg = "Errores de configuración:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)

    return True


# =============================
# VALIDACIÓN AL IMPORTAR
# =============================
if __name__ != "__main__":
    # Solo validar cuando se importa, no cuando se ejecuta directamente
    try:
        if IS_PRODUCTION:
            validate_config()
    except ValueError as e:
        # En desarrollo, solo advertir
        if IS_DEVELOPMENT:
            print(f"Advertencia de configuración:\n{e}")
        else:
            raise

# =============================
# TESTING DE CONFIGURACIÓN
# =============================
if __name__ == "__main__":
    print("=" * 60)
    print("CONFIGURACIÓN DEL SISTEMA CV PROCESSOR")
    print("=" * 60)

    print("\n📁 DIRECTORIOS:")
    print(f"  Base: {BASE_DIR}")
    print(f"  Storage: {STORAGE_DIR}")
    print(f"  Logs: {LOG_DIR}")

    print("\n🗄️ SQL SERVER:")
    print(f"  Servidor: {MSSQL_SERVER}:{MSSQL_PORT}")
    print(f"  Base de datos: {MSSQL_DATABASE}")
    print(f"  Usuario: {MSSQL_USER}")
    print(f"  Driver ODBC: {ODBC_DRIVER}")

    print("\n🤖 AZURE OPENAI:")
    print(f"  Endpoint: {AZURE_OPENAI_ENDPOINT or 'NO CONFIGURADO'}")
    print(f"  Modelo: {DEPLOYMENT_NAME}")

    print("\n⚙️ AMBIENTE:")
    print(f"  Entorno: {ENVIRONMENT}")
    print(f"  Debug: {DEBUG}")
    print(f"  Log Level: {LOG_LEVEL}")

    print("\n🔌 CONNECTION STRING:")
    conn_str = get_db_connection_string()
    # Ocultar la contraseña en el output
    safe_conn_str = conn_str.replace(MSSQL_PASSWORD, "***") if MSSQL_PASSWORD else conn_str  # replace("") metería *** entre cada carácter
    print(f"  {safe_conn_str}")

    print("\n" + "=" * 60)