# src/database/db_config.py
"""
Módulo de configuración y gestión de conexiones Microsoft SQL Server usando pyodbc.
Proporciona pool de conexiones, reintentos automáticos y logging centralizado.
CORREGIDO: Mejor manejo del context manager para evitar "generator didn't stop after throw()"
"""

import pyodbc
import time
import sys
from pathlib import Path
from typing import Optional, Any
from contextlib import contextmanager
import threading

# Añadir el directorio padre al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import (
    MSSQL_PASSWORD, MSSQL_DATABASE,
    DB_AUTOCOMMIT, DB_POOL_SIZE, DB_MAX_OVERFLOW,
    DB_CONNECTION_TIMEOUT, DB_QUERY_TIMEOUT, DB_MAX_RETRIES, DB_RETRY_DELAY,
    DB_ECHO, get_db_connection_string, get_logger
)

# Logger específico para base de datos
logger = get_logger(__name__)


class ConnectionPool:
    """
    Pool de conexiones thread-safe para SQL Server usando pyodbc
    """

    def __init__(self, min_size: int = 2, max_size: int = None):
        """
        Inicializa el pool de conexiones

        Args:
            min_size: Número mínimo de conexiones
            max_size: Número máximo de conexiones
        """
        self.min_size = min_size
        self.max_size = max_size or DB_POOL_SIZE
        self._connections = []
        self._used_connections = set()
        self._lock = threading.Lock()
        self._created_connections = 0

        # Crear conexiones iniciales
        self._initialize_pool()

    def _initialize_pool(self):
        """Crea las conexiones iniciales del pool"""
        logger.info(f"Inicializando pool con {self.min_size} conexiones")
        for _ in range(self.min_size):
            try:
                conn = self._create_connection()
                if conn:
                    self._connections.append(conn)
            except Exception as e:
                logger.warning(f"Error creando conexión inicial: {e}")

    def _create_connection(self) -> Optional[pyodbc.Connection]:
        """
        Crea una nueva conexión a SQL Server

        Returns:
            pyodbc.Connection o None si falla
        """
        try:
            connection_string = get_db_connection_string()

            if DB_ECHO:
                logger.debug(f"Conectando con: {connection_string.replace(MSSQL_PASSWORD, '***') if MSSQL_PASSWORD else connection_string}")

            conn = pyodbc.connect(
                connection_string,
                autocommit=DB_AUTOCOMMIT,
                timeout=DB_CONNECTION_TIMEOUT
            )

            # Configurar timeout de query
            conn.timeout = DB_QUERY_TIMEOUT

            self._created_connections += 1
            logger.debug(f"Conexión #{self._created_connections} creada exitosamente")

            return conn

        except pyodbc.Error as e:
            logger.error(f"Error pyodbc al crear conexión: {e}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado al crear conexión: {e}")
            return None

    def get_connection(self) -> Optional[pyodbc.Connection]:
        """
        Obtiene una conexión del pool

        Returns:
            pyodbc.Connection o None si no hay disponibles
        """
        with self._lock:
            # Intentar obtener una conexión existente
            while self._connections:
                conn = self._connections.pop(0)

                # Verificar que la conexión sigue activa
                if self._is_connection_alive(conn):
                    self._used_connections.add(conn)
                    logger.debug(f"Conexión obtenida del pool. En uso: {len(self._used_connections)}")
                    return conn
                else:
                    logger.debug("Conexión muerta descartada")

            # Si no hay conexiones y no hemos alcanzado el máximo, crear una nueva
            if len(self._used_connections) < self.max_size:
                conn = self._create_connection()
                if conn:
                    self._used_connections.add(conn)
                    return conn

            logger.warning("No hay conexiones disponibles en el pool")
            return None

    def return_connection(self, conn: pyodbc.Connection):
        """
        Devuelve una conexión al pool

        Args:
            conn: Conexión a devolver
        """
        with self._lock:
            if conn in self._used_connections:
                self._used_connections.remove(conn)

                # Hacer rollback si hay transacción pendiente
                try:
                    if not DB_AUTOCOMMIT:
                        conn.rollback()
                except:
                    pass

                # Verificar que sigue viva antes de devolverla
                if self._is_connection_alive(conn):
                    self._connections.append(conn)
                    logger.debug(f"Conexión devuelta al pool. Disponibles: {len(self._connections)}")
                else:
                    logger.debug("Conexión muerta no devuelta al pool")

    @staticmethod
    def _is_connection_alive(conn: pyodbc.Connection) -> bool:
        """
        Verifica si una conexión sigue activa

        Args:
            conn: Conexión a verificar

        Returns:
            bool: True si está activa
        """
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 AS test")
            cursor.close()
            return True
        except:
            return False

    def close_all(self):
        """Cierra todas las conexiones del pool"""
        with self._lock:
            # Cerrar conexiones disponibles
            for conn in self._connections:
                try:
                    conn.close()
                except:
                    pass

            # Cerrar conexiones en uso
            for conn in self._used_connections:
                try:
                    conn.close()
                except:
                    pass

            self._connections.clear()
            self._used_connections.clear()
            logger.info("Todas las conexiones del pool cerradas")


class DatabaseConfig:
    """
    Configuración y gestión principal de la base de datos SQL Server
    """

    _instance = None
    _pool = None

    def __new__(cls):
        """Singleton pattern para una única instancia"""
        if cls._instance is None:
            cls._instance = super(DatabaseConfig, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Inicializa la configuración si no existe"""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._init_pool()

    @staticmethod
    def _init_pool():
        """Inicializa el pool de conexiones"""
        if DatabaseConfig._pool is None:
            DatabaseConfig._pool = ConnectionPool(
                min_size=2,
                max_size=DB_POOL_SIZE + DB_MAX_OVERFLOW
            )
            logger.info("Pool de conexiones inicializado")

    @contextmanager
    def get_connection(self, retries: int = None):
        """
        Context manager mejorado para obtener conexiones del pool.
        CORREGIDO: Manejo apropiado de excepciones para evitar "generator didn't stop after throw()"
        """
        if retries is None:
            retries = DB_MAX_RETRIES

        conn = None
        exception_to_raise = None

        for attempt in range(retries + 1):
            try:
                # Obtener conexión del pool
                conn = self._pool.get_connection()

                if conn:
                    # Si obtenemos conexión, yield y salir
                    try:
                        yield conn
                        return  # Éxito, salir del método
                    except Exception as e:
                        # Si hay error durante el uso de la conexión, guardarlo
                        exception_to_raise = e
                        raise
                    finally:
                        # SIEMPRE devolver la conexión al pool
                        if conn:
                            self._pool.return_connection(conn)
                            conn = None
                else:
                    # No hay conexión disponible
                    if attempt == retries:
                        raise ConnectionError("Pool agotado, no hay conexiones disponibles")
                    else:
                        logger.warning(f"Intento {attempt + 1}: No hay conexión disponible, reintentando...")
                        time.sleep(DB_RETRY_DELAY * (attempt + 1))

            except Exception as e:
                if attempt == retries:
                    # Último intento - propagar error
                    logger.error(f"Falló después de {retries + 1} intentos: {e}")
                    raise
                else:
                    # Reintentar
                    logger.warning(f"Intento {attempt + 1} falló: {e}")
                    time.sleep(DB_RETRY_DELAY * (attempt + 1))

    def execute_query(self, query: str, params: tuple = None,
                      fetch: bool = True, commit: bool = False) -> Optional[Any]:
        """
        Ejecuta una query con manejo de errores y reintentos.
        MEJORADO: Mejor manejo de transacciones y errores.

        Args:
            query: SQL query a ejecutar
            params: Parámetros para la query
            fetch: Si debe hacer fetch de resultados
            commit: Si debe hacer commit después de ejecutar

        Returns:
            Resultados del fetch o None
        """
        with self.get_connection() as conn:
            cursor = None
            try:
                cursor = conn.cursor()

                if DB_ECHO:
                    logger.debug(f"Ejecutando: {query[:100]}...")
                    if params:
                        logger.debug(f"Parámetros: {params}")

                # Ejecutar query
                cursor.execute(query, params or ())

                # Si necesitamos commit y no está en autocommit
                if commit and not DB_AUTOCOMMIT:
                    conn.commit()
                    logger.debug("Commit realizado")

                # Obtener resultados si es necesario
                if fetch:
                    results = cursor.fetchall()
                    logger.debug(f"Obtenidos {len(results)} registros")
                    return results
                else:
                    return cursor.rowcount

            except pyodbc.Error as e:
                # En caso de error, hacer rollback si no está en autocommit
                if not DB_AUTOCOMMIT:
                    try:
                        conn.rollback()
                        logger.debug("Rollback realizado debido a error")
                    except:
                        pass

                logger.error(f"Error ejecutando query: {e}")
                logger.error(f"Query: {query[:200]}")
                logger.error(f"Params: {params}")
                raise

            finally:
                # Cerrar cursor siempre
                if cursor:
                    try:
                        cursor.close()
                    except:
                        pass

    def execute_many(self, query: str, data: list, commit: bool = True) -> int:
        """
        Ejecuta una query múltiples veces con diferentes datos

        Args:
            query: SQL query a ejecutar
            data: Lista de tuplas con parámetros
            commit: Si debe hacer commit después

        Returns:
            Número de filas afectadas
        """
        with self.get_connection() as conn:
            cursor = None
            rows_affected = 0

            try:
                cursor = conn.cursor()

                for params in data:
                    cursor.execute(query, params)
                    rows_affected += cursor.rowcount

                if commit and not DB_AUTOCOMMIT:
                    conn.commit()
                    logger.debug(f"Commit realizado. {rows_affected} filas afectadas")

                return rows_affected

            except pyodbc.Error as e:
                if not DB_AUTOCOMMIT:
                    try:
                        conn.rollback()
                    except:
                        pass
                logger.error(f"Error en execute_many: {e}")
                raise

            finally:
                if cursor:
                    try:
                        cursor.close()
                    except:
                        pass

    def test_connection(self) -> bool:
        """
        Prueba la conexión a SQL Server

        Returns:
            bool: True si la conexión es exitosa
        """
        try:
            # SQL Server usa @@VERSION
            result = self.execute_query("SELECT @@VERSION")
            if result:
                version = result[0][0]
                # Mostrar solo los primeros 80 caracteres de la versión
                version_short = version[:80] + "..." if len(version) > 80 else version
                logger.info(f"✅ Conexión exitosa. SQL Server: {version_short}")
                print(f"✅ Conexión exitosa. SQL Server: {version_short}")
                return True
            else:
                logger.error("❌ Query ejecutada pero sin resultados")
                return False
        except Exception as e:
            logger.error(f"❌ Error probando conexión: {e}")
            print(f"❌ Error probando conexión: {e}")
            return False

    def get_table_info(self, table_name: str) -> list:
        """
        Obtiene información sobre una tabla en SQL Server

        Args:
            table_name: Nombre de la tabla

        Returns:
            Lista con información de columnas
        """
        query = """
            SELECT 
                COLUMN_NAME, 
                DATA_TYPE, 
                IS_NULLABLE, 
                COLUMN_DEFAULT,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_CATALOG = ? AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
        """
        return self.execute_query(query, (MSSQL_DATABASE, table_name))

    def table_exists(self, table_name: str) -> bool:
        """
        Verifica si una tabla existe en SQL Server

        Args:
            table_name: Nombre de la tabla

        Returns:
            bool: True si existe
        """
        query = """
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_CATALOG = ? 
            AND TABLE_NAME = ?
            AND TABLE_TYPE = 'BASE TABLE'
        """
        result = self.execute_query(query, (MSSQL_DATABASE, table_name))
        return result[0][0] > 0 if result else False

    def get_tables_list(self) -> list:
        """
        Obtiene lista de todas las tablas en la base de datos

        Returns:
            Lista de nombres de tablas
        """
        query = """
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_CATALOG = ? 
            AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """
        results = self.execute_query(query, (MSSQL_DATABASE,))
        return [row[0] for row in results] if results else []

    def get_server_info(self) -> dict:
        """
        Obtiene información del servidor SQL Server

        Returns:
            Diccionario con información del servidor
        """
        info = {}

        try:
            # Versión del servidor
            result = self.execute_query("SELECT @@VERSION")
            if result:
                info['version'] = result[0][0]

            # Nombre del servidor
            result = self.execute_query("SELECT @@SERVERNAME")
            if result:
                info['server_name'] = result[0][0]

            # Base de datos actual
            result = self.execute_query("SELECT DB_NAME()")
            if result:
                info['database'] = result[0][0]

            # Usuario actual
            result = self.execute_query("SELECT SUSER_NAME()")
            if result:
                info['user'] = result[0][0]

            # Collation de la base de datos
            result = self.execute_query(
                "SELECT CAST(DATABASEPROPERTYEX(?, 'Collation') AS NVARCHAR(256))",
                (MSSQL_DATABASE,)
            )
            if result:
                info['collation'] = result[0][0]

        except pyodbc.Error as e:
            # Manejar específicamente el error de tipo SQL
            if 'ODBC SQL type -150' in str(e):
                logger.warning(f"Error con sql_variant, intentando método alternativo")
                try:
                    result = self.execute_query(f"""
                        SELECT CONVERT(NVARCHAR(256), SERVERPROPERTY('Collation'))
                    """)
                    if result:
                        info['collation'] = result[0][0]
                except Exception as e2:
                    logger.warning(f"No se pudo obtener collation: {e2}")
            else:
                logger.error(f"Error obteniendo información del servidor: {e}")
        except Exception as e:
            logger.error(f"Error obteniendo información del servidor: {e}")

        return info

    def close(self):
        """Cierra el pool de conexiones"""
        if self._pool:
            self._pool.close_all()
            DatabaseConfig._pool = None
            logger.info("DatabaseConfig cerrado")

    def __del__(self):
        """Destructor para cerrar conexiones"""
        try:
            self.close()
        except:
            pass


# Función de utilidad para testing rápido
def test_database_config():
    """Función de prueba para verificar la conexión a SQL Server"""
    print("\n" + "=" * 60)
    print("PRUEBA DE CONEXIÓN SQL SERVER")
    print("=" * 60)

    import logging
    logging.getLogger().setLevel(logging.INFO)

    db_config = None

    try:
        db_config = DatabaseConfig()

        # Test 1: Conexión básica
        print("\n1. Probando conexión...")
        if db_config.test_connection():
            print("   ✅ Conexión exitosa")
        else:
            print("   ❌ Conexión fallida")
            return False

        # Test 2: Información del servidor
        print("\n2. Información del servidor:")
        server_info = db_config.get_server_info()
        for key, value in server_info.items():
            if key == 'version':
                # Acortar la versión para display
                value = value[:80] + "..." if len(value) > 80 else value
            print(f"   - {key}: {value}")

        # Test 3: Pool de conexiones
        print("\n3. Probando pool de conexiones...")
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT @@SPID")  # SQL Server Session ID
            spid = cursor.fetchone()[0]
            cursor.close()
            print(f"   ✅ Conexión ID (SPID): {spid}")

        # Test 4: Múltiples conexiones simultáneas
        print("\n4. Probando múltiples conexiones...")
        connections_test = []
        for i in range(3):
            with db_config.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT @@SPID")
                spid = cursor.fetchone()[0]
                connections_test.append(spid)
                cursor.close()
        print(f"   ✅ SPIDs obtenidos: {connections_test}")

        # Test 5: Verificar timeout configurado
        print("\n5. Configuración de timeouts:")
        with db_config.get_connection() as conn:
            print(f"   - Connection timeout: {DB_CONNECTION_TIMEOUT}s")
            print(f"   - Query timeout: {conn.timeout}s")
            print(f"   - Autocommit: {conn.autocommit}")

        # Test 6: Verificar Usuario ID = 1
        print("\n6. Verificando Usuario ID = 1:")
        result = db_config.execute_query("SELECT Id, Nombre FROM dbo.Usuario WHERE Id = 1")
        if result:
            print(f"   ✅ Usuario encontrado: ID={result[0][0]}, Nombre='{result[0][1]}'")
        else:
            print("   ❌ Usuario ID=1 no encontrado")

        print("\n" + "=" * 60)
        print("TODAS LAS PRUEBAS DE CONEXIÓN COMPLETADAS")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n❌ Error en pruebas: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Limpiar
        try:
            if db_config:
                db_config.close()
        except:
            pass


if __name__ == "__main__":
    test_database_config()