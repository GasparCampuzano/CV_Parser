#!/usr/bin/env python3
"""
Módulo de gestión de esquema y datos iniciales para el sistema CV Processor.
NO crea tablas (responsabilidad del equipo de BD), solo gestiona datos iniciales en catálogos.
Actualizado para SQL Server con campos FechaAlta y UsuarioAlta requeridos.
"""

import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Añadir el directorio padre al path para imports relativos
sys.path.insert(0, str(Path(__file__).parent.parent))

# Imports del proyecto
from src.database.db_config import DatabaseConfig
from config.settings import get_logger

# Logger específico para schema
logger = get_logger(__name__)


class SchemaManager:
    """
    Gestor de esquema y datos iniciales de catálogos.
    IMPORTANTE: No crea tablas, solo verifica y carga datos iniciales.
    """

    def __init__(self, db_config: DatabaseConfig = None):
        """
        Inicializa el gestor de esquema.

        Args:
            db_config: Instancia de DatabaseConfig. Si no se proporciona, crea una nueva.
        """
        self.db_config = db_config or DatabaseConfig()
        self.initialized_catalogs = set()
        self.default_user_id = 1  # Usuario 1 existe en la BD (Usuario sistema)

    def verify_schema(self) -> Dict[str, bool]:
        """
        Verifica que las tablas necesarias existan en la BD.

        Returns:
            Diccionario con el estado de cada tabla crítica
        """
        required_tables = [
            'Candidatos',
            'CandidatosExperiencia',
            'CandidatosEstudios',
            'CandidatosIdiomas',
            'CandidatosCertificaciones',
            'CandidatosConocimientosTecnicos',
            'CandidatosConocimientosNegocio',
            'CandidatosConocimientosOtros',
            'Empresas',
            'Puestos',
            'Idiomas',
            'NivelIdiomas',
            'ConocimientosTecnicos',
            'ConocimientosNegocio',
            'ConocimientosOtros',
            'CentroEstudios',
            'Certificaciones'
        ]

        schema_status = {}
        logger.info("Verificando esquema de base de datos...")

        for table in required_tables:
            exists = self.db_config.table_exists(table)
            schema_status[table] = exists

            if not exists:
                logger.warning(f"⚠️ Tabla no encontrada: dbo.{table}")
            else:
                logger.debug(f"✓ Tabla verificada: dbo.{table}")

        # Resumen
        tables_ok = sum(1 for v in schema_status.values() if v)
        logger.info(f"Esquema verificado: {tables_ok}/{len(required_tables)} tablas encontradas")

        return schema_status

    def initialize_catalogs(self, force: bool = False) -> Dict[str, int]:
        """
        Inicializa todos los catálogos con datos básicos.

        Args:
            force: Si True, reinicializa aunque ya tengan datos

        Returns:
            Diccionario con el número de registros insertados por catálogo
        """
        results = {}

        logger.info("Inicializando catálogos con datos básicos...")

        # Orden de inicialización (respetando dependencias)
        catalogs_init_order = [
            ('Idiomas', self._init_idiomas),
            ('NivelIdiomas', self._init_niveles_idioma),
            ('ConocimientosTecnicos', self._init_conocimientos_tecnicos),
            ('ConocimientosNegocio', self._init_conocimientos_negocio),
            ('ConocimientosOtros', self._init_conocimientos_otros)
        ]

        for catalog_name, init_method in catalogs_init_order:
            try:
                if not self.db_config.table_exists(catalog_name):
                    logger.warning(f"Tabla {catalog_name} no existe, saltando inicialización")
                    results[catalog_name] = 0
                    continue

                # Verificar si ya tiene datos
                count_query = f"SELECT COUNT(*) FROM dbo.{catalog_name}"
                result = self.db_config.execute_query(count_query)
                existing_count = result[0][0] if result else 0

                if existing_count > 0 and not force:
                    logger.info(f"Catálogo {catalog_name} ya contiene {existing_count} registros, saltando")
                    results[catalog_name] = 0
                    continue

                # Inicializar catálogo
                inserted = init_method()
                results[catalog_name] = inserted
                logger.info(f"✓ {catalog_name}: {inserted} registros insertados")

            except Exception as e:
                logger.error(f"Error inicializando {catalog_name}: {e}")
                results[catalog_name] = -1

        return results

    def _init_idiomas(self) -> int:
        """
        Inicializa el catálogo de idiomas con idiomas oficiales y cooficiales.
        Según reuniones: solo idiomas oficiales/cooficiales permitidos.
        """
        idiomas_data = [
            'Español',
            'Inglés',
            'Francés',
            'Alemán',
            'Italiano',
            'Portugués',
            'Catalán',
            'Euskera',
            'Gallego',
            'Valenciano',
            'Chino Mandarín',
            'Árabe',
            'Ruso',
            'Japonés',
            'Holandés'
        ]

        inserted = 0
        for idioma in idiomas_data:
            try:
                # Verificar si ya existe
                check_query = "SELECT IdIdioma FROM dbo.Idiomas WHERE Descripcion = ?"
                result = self.db_config.execute_query(check_query, (idioma,))

                if not result:
                    # Incluir FechaAlta y UsuarioAlta
                    insert_query = """
                        INSERT INTO dbo.Idiomas 
                        (Descripcion, FechaModificacion, UsuarioModificacion, FechaAlta, UsuarioAlta)
                        VALUES (?, GETDATE(), ?, GETDATE(), ?)
                    """
                    self.db_config.execute_query(
                        insert_query,
                        (idioma, self.default_user_id, self.default_user_id),
                        fetch=False,
                        commit=True
                    )
                    inserted += 1
                    logger.debug(f"Idioma insertado: {idioma}")

            except Exception as e:
                logger.error(f"Error insertando idioma {idioma}: {e}")

        return inserted

    def _init_niveles_idioma(self) -> int:
        """
        Inicializa los niveles de idioma estándar.
        """
        niveles_data = [
            'A1',
            'A2',
            'B1',
            'B2',
            'C1',
            'C2',
            'Básico',
            'Intermedio',
            'Avanzado',
            'Nativo'
        ]

        inserted = 0
        for nivel in niveles_data:
            try:
                check_query = "SELECT IdNivelIdioma FROM dbo.NivelIdiomas WHERE Descripcion = ?"
                result = self.db_config.execute_query(check_query, (nivel,))

                if not result:
                    # Incluir FechaAlta y UsuarioAlta
                    insert_query = """
                        INSERT INTO dbo.NivelIdiomas 
                        (Descripcion, FechaModificacion, UsuarioModificacion, FechaAlta, UsuarioAlta)
                        VALUES (?, GETDATE(), ?, GETDATE(), ?)
                    """
                    self.db_config.execute_query(
                        insert_query,
                        (nivel, self.default_user_id, self.default_user_id),
                        fetch=False,
                        commit=True
                    )
                    inserted += 1
                    logger.debug(f"Nivel idioma insertado: {nivel}")

            except Exception as e:
                logger.error(f"Error insertando nivel idioma {nivel}: {e}")

        return inserted

    def _init_conocimientos_tecnicos(self) -> int:
        """
        Inicializa conocimientos técnicos básicos.
        Basado en reunión 2: lenguajes, BBDD, frameworks y herramientas concretas.
        """
        conocimientos = [
            # Lenguajes de programación
            'Python', 'Java', 'JavaScript', 'TypeScript', 'C++', 'C#', 'C',
            'Go', 'Rust', 'Ruby', 'PHP', 'Swift', 'Kotlin', 'Scala', 'R',
            'MATLAB', 'Perl', 'Objective-C', 'Visual Basic', 'COBOL', 'Fortran',

            # Frameworks Frontend
            'React', 'Angular', 'Vue.js', 'Next.js', 'Nuxt.js', 'Svelte',
            'jQuery', 'Bootstrap', 'Tailwind CSS', 'Material-UI',

            # Frameworks Backend
            'Django', 'Flask', 'FastAPI', 'Spring', 'Spring Boot', 'Express.js',
            'Node.js', 'ASP.NET', 'Ruby on Rails', 'Laravel', 'Symfony',

            # Bases de datos
            'MySQL', 'PostgreSQL', 'MongoDB', 'Oracle', 'SQL Server', 'SQLite',
            'Redis', 'Cassandra', 'Elasticsearch', 'DynamoDB', 'MariaDB',
            'Neo4j', 'CouchDB', 'Firebase', 'Supabase', 'SQL'

            # Cloud y DevOps
            'AWS', 'Azure', 'Google Cloud', 'Docker', 'Kubernetes', 'Jenkins',
            'GitLab CI', 'GitHub Actions', 'Terraform', 'Ansible', 'Vagrant',

            # Herramientas
            'Git', 'SVN', 'Mercurial', 'JIRA', 'Confluence', 'Slack',
            'Visual Studio', 'IntelliJ IDEA', 'Eclipse', 'VS Code',

            # Tecnologías específicas
            'REST API', 'GraphQL', 'SOAP', 'Microservicios', 'WebSockets',
            'JWT', 'OAuth', 'SAML', 'Machine Learning', 'Deep Learning',
            'TensorFlow', 'PyTorch', 'Scikit-learn', 'Pandas', 'NumPy'
        ]

        return self._insert_conocimientos('ConocimientosTecnicos', conocimientos, 'IdConocimientoTecnico')

    def _init_conocimientos_negocio(self) -> int:
        """
        Inicializa conocimientos de negocio/sector.
        Basado en reunión 2: saberes de dominio o sector.
        """
        conocimientos = [
            # Sectores principales
            'Banca', 'Seguros', 'Retail', 'Logística', 'Telecomunicaciones',
            'Energía', 'Utilities', 'Farmacéutica', 'Salud', 'Educación',
            'Administración Pública', 'Defensa', 'Aeronáutica', 'Automoción',
            'Construcción', 'Inmobiliario', 'Turismo', 'Hostelería',
            'Alimentación', 'Distribución', 'Transporte', 'Media',

            # Áreas funcionales
            'Marketing Digital', 'E-commerce', 'CRM', 'ERP', 'Supply Chain',
            'Recursos Humanos', 'Finanzas', 'Contabilidad', 'Auditoría',
            'Compliance', 'Risk Management', 'Trading', 'Investment Banking',
            'Asset Management', 'Venture Capital', 'Private Equity',

            # Conocimientos específicos de negocio
            'GDPR', 'SOX', 'Basel III', 'MiFID II', 'PSD2', 'KYC', 'AML',
            'Business Intelligence', 'Data Analytics', 'Customer Experience',
            'Digital Transformation', 'Innovation Management', 'Change Management',

            # Productos y servicios financieros
            'Préstamos', 'Hipotecas', 'Tarjetas de Crédito', 'Seguros de Vida',
            'Seguros de Hogar', 'Planes de Pensiones', 'Fondos de Inversión',
            'Derivados Financieros', 'Renta Fija', 'Renta Variable'
        ]

        # Nota: ConocimientosNegocio usa IdConocimientosNegocio (con 's')
        return self._insert_conocimientos('ConocimientosNegocio', conocimientos, 'IdConocimientosNegocio')

    def _init_conocimientos_otros(self) -> int:
        """
        Inicializa otros conocimientos (metodologías y habilidades transversales).
        Basado en reunión 2: metodologías y habilidades transversales.
        """
        conocimientos = [
            # Metodologías ágiles
            'Scrum', 'Agile', 'Kanban', 'Lean', 'XP', 'SAFe', 'DevOps',
            'CI/CD', 'TDD', 'BDD', 'DDD', 'Pair Programming',

            # Gestión de proyectos
            'PMP', 'PRINCE2', 'ITIL', 'COBIT', 'Six Sigma', 'Waterfall',
            'Project Management', 'Product Management', 'Product Owner',
            'Scrum Master', 'Agile Coach',

            # Arquitectura y diseño
            'Arquitectura de Software', 'Diseño de Sistemas', 'UML',
            'Design Patterns', 'SOLID', 'Clean Code', 'Refactoring',
            'Domain-Driven Design', 'Event-Driven Architecture',
            'CQRS', 'Event Sourcing',

            # Soft Skills relevantes
            'Liderazgo', 'Trabajo en Equipo', 'Comunicación', 'Negociación',
            'Resolución de Problemas', 'Pensamiento Analítico', 'Creatividad',
            'Gestión del Tiempo', 'Orientación a Resultados', 'Adaptabilidad',

            # Certificaciones y estándares
            'ISO 9001', 'ISO 27001', 'ISO 20000', 'CMMI', 'PMI', 'ISTQB',
            'AWS Certified', 'Azure Certified', 'Google Cloud Certified',
            'Certified Kubernetes', 'Red Hat Certified'
        ]

        return self._insert_conocimientos('ConocimientosOtros', conocimientos, 'IdConocimientosOtros')

    def _insert_conocimientos(self, tabla: str, conocimientos: List[str], id_column: str) -> int:
        """
        Helper para insertar conocimientos en cualquiera de las tres tablas.

        Args:
            tabla: Nombre de la tabla (sin dbo.)
            conocimientos: Lista de conocimientos a insertar
            id_column: Nombre exacto de la columna ID

        Returns:
            Número de registros insertados
        """
        inserted = 0

        for conocimiento in conocimientos:
            try:
                # Verificar si ya existe
                check_query = f"SELECT {id_column} FROM dbo.{tabla} WHERE Descripcion = ?"
                result = self.db_config.execute_query(check_query, (conocimiento,))

                if not result:
                    # Incluir FechaAlta y UsuarioAlta (requeridos en SQL Server)
                    insert_query = f"""
                        INSERT INTO dbo.{tabla} 
                        (Descripcion, FechaModificacion, UsuarioModificacion, FechaAlta, UsuarioAlta)
                        VALUES (?, GETDATE(), ?, GETDATE(), ?)
                    """
                    self.db_config.execute_query(
                        insert_query,
                        (conocimiento, self.default_user_id, self.default_user_id),
                        fetch=False,  # No hacer fetch
                        commit=True
                    )
                    inserted += 1
                    logger.debug(f"Insertado en {tabla}: {conocimiento}")

            except Exception as e:
                logger.error(f"Error insertando {conocimiento} en {tabla}: {e}")

        return inserted

    def get_catalog_stats(self) -> Dict[str, int]:
        """
        Obtiene estadísticas de los catálogos.

        Returns:
            Diccionario con el conteo de registros por catálogo
        """
        catalogs = [
            'Idiomas', 'NivelIdiomas', 'ConocimientosTecnicos',
            'ConocimientosNegocio', 'ConocimientosOtros',
            'Empresas', 'Puestos', 'CentroEstudios', 'Certificaciones'
        ]

        stats = {}
        for catalog in catalogs:
            try:
                if self.db_config.table_exists(catalog):
                    query = f"SELECT COUNT(*) FROM dbo.{catalog}"
                    result = self.db_config.execute_query(query)
                    stats[catalog] = result[0][0] if result else 0
                else:
                    stats[catalog] = -1  # Tabla no existe
            except Exception as e:
                logger.error(f"Error obteniendo stats de {catalog}: {e}")
                stats[catalog] = -1

        return stats

    def find_or_create_catalog_item(self, catalog_table: str, description: str,
                                    id_column: str = None) -> Optional[int]:
        """
        Busca un elemento en un catálogo y lo crea si no existe.
        ACTUALIZADO: Incluye FechaAlta y UsuarioAlta requeridos.

        Args:
            catalog_table: Nombre de la tabla catálogo (sin dbo.)
            description: Descripción del elemento a buscar/crear
            id_column: Nombre de la columna ID (si None, se infiere)

        Returns:
            ID del elemento encontrado o creado, None si hay error
        """
        if id_column is None:
            # Inferir nombre de columna ID - manejo especial para ConocimientosNegocio
            if catalog_table == 'ConocimientosNegocio':
                id_column = 'IdConocimientosNegocio'
            elif catalog_table == 'ConocimientosOtros':
                id_column = 'IdConocimientosOtros'
            else:
                id_column = f"Id{catalog_table[:-1] if catalog_table.endswith('s') else catalog_table}"

        try:
            # Buscar existente
            select_query = f"""
                SELECT {id_column} 
                FROM dbo.{catalog_table} 
                WHERE Descripcion = ?
            """
            result = self.db_config.execute_query(select_query, (description,))

            if result and result[0]:
                return result[0][0]

            # No existe, crear nuevo con FechaAlta y UsuarioAlta
            insert_query = f"""
                INSERT INTO dbo.{catalog_table} 
                (Descripcion, FechaModificacion, UsuarioModificacion, FechaAlta, UsuarioAlta)
                VALUES (?, GETDATE(), ?, GETDATE(), ?)
            """
            self.db_config.execute_query(
                insert_query,
                (description, self.default_user_id, self.default_user_id),
                fetch=False,
                commit=True
            )

            # Después del INSERT, recuperar el ID con un SELECT
            select_query = f"SELECT {id_column} FROM dbo.{catalog_table} WHERE Descripcion = ?"
            result = self.db_config.execute_query(select_query, (description,))

            if result and result[0]:
                logger.info(f"Creado nuevo elemento en {catalog_table}: {description}")
                return result[0][0]

        except Exception as e:
            logger.error(f"Error en find_or_create para {catalog_table}/{description}: {e}")

        return None

    def validate_catalog_items(self, catalog_table: str,
                               items: List[str]) -> Tuple[List[Tuple[int, str]], List[str]]:
        """
        Valida una lista de elementos contra un catálogo.

        Args:
            catalog_table: Nombre de la tabla catálogo
            items: Lista de descripciones a validar

        Returns:
            Tupla con (encontrados[(id, descripcion)], no_encontrados[descripcion])
        """
        found = []
        not_found = []

        # Determinar nombre correcto de columna ID
        if catalog_table == 'ConocimientosNegocio':
            id_column = 'IdConocimientosNegocio'
        elif catalog_table == 'ConocimientosOtros':
            id_column = 'IdConocimientosOtros'
        else:
            id_column = f"Id{catalog_table[:-1] if catalog_table.endswith('s') else catalog_table}"

        for item in items:
            try:
                query = f"""
                    SELECT {id_column}, Descripcion 
                    FROM dbo.{catalog_table} 
                    WHERE LOWER(Descripcion) = LOWER(?)
                """
                result = self.db_config.execute_query(query, (item,))

                if result and result[0]:
                    found.append((result[0][0], result[0][1]))
                else:
                    not_found.append(item)

            except Exception as e:
                logger.error(f"Error validando {item} en {catalog_table}: {e}")
                not_found.append(item)

        return found, not_found

    def get_catalog_id(self, catalog_table: str, description: str) -> Optional[int]:
        """
        Obtiene el ID de un elemento específico del catálogo.

        Args:
            catalog_table: Nombre de la tabla catálogo
            description: Descripción del elemento

        Returns:
            ID del elemento o None si no existe
        """
        # Determinar nombre correcto de columna ID
        if catalog_table == 'ConocimientosTecnicos':
            id_column = 'IdConocimientoTecnico'  # SIN 's' en Tecnico
        elif catalog_table == 'ConocimientosNegocio':
            id_column = 'IdConocimientosNegocio'
        elif catalog_table == 'ConocimientosOtros':
            id_column = 'IdConocimientosOtros'
        else:
            id_column = f"Id{catalog_table[:-1] if catalog_table.endswith('s') else catalog_table}"

        try:
            query = f"""
                SELECT {id_column} 
                FROM dbo.{catalog_table} 
                WHERE LOWER(Descripcion) = LOWER(?)
            """
            result = self.db_config.execute_query(query, (description,))

            if result and result[0]:
                return result[0][0]

        except Exception as e:
            logger.error(f"Error obteniendo ID de {description} en {catalog_table}: {e}")

        return None


def main():
    """
    Función principal para testing y setup inicial.
    """
    print("\n" + "=" * 60)
    print("GESTIÓN DE ESQUEMA Y CATÁLOGOS - CV PROCESSOR")
    print("=" * 60)

    try:
        # Inicializar
        db_config = DatabaseConfig()
        schema_mgr = SchemaManager(db_config)

        # Test de conexión
        print("\n1. Probando conexión...")
        if not db_config.test_connection():
            print("   ❌ Error de conexión")
            return

        # Verificar esquema
        print("\n2. Verificando esquema...")
        schema_status = schema_mgr.verify_schema()

        missing_tables = [t for t, exists in schema_status.items() if not exists]
        if missing_tables:
            print(f"   ⚠️ Tablas faltantes: {', '.join(missing_tables)}")
            print("   Contacte al equipo de BD para crear las tablas necesarias.")
        else:
            print("   ✓ Todas las tablas necesarias existen")

        # Estadísticas y contenido actual
        print("\n3. CONTENIDO ACTUAL DE CATÁLOGOS:")
        print("-" * 60)

        # Función helper para mostrar registros
        def show_catalog_content(catalog_name, id_column=None, desc_column="Descripcion", max_show=10):
            try:
                # Si no se especifica columna ID, intentar detectarla
                if id_column is None:
                    # Manejo especial para tablas conocidas
                    if catalog_name == 'ConocimientosNegocio':
                        id_column = 'IdConocimientosNegocio'
                    elif catalog_name == 'ConocimientosOtros':
                        id_column = 'IdConocimientosOtros'
                    else:
                        # Obtener información de columnas para detectar el nombre correcto
                        columns_info = db_config.get_table_info(catalog_name)
                        # Buscar columna que empiece con 'Id'
                        for col_info in columns_info:
                            col_name = col_info[0]  # COLUMN_NAME es el primer elemento
                            if col_name.startswith('Id') and col_name != 'IdMigracion':
                                id_column = col_name
                                break

                    if not id_column:
                        print(f"   ⚠️ No se pudo detectar columna ID para {catalog_name}")
                        return

                # Obtener total
                count_query = f"SELECT COUNT(*) FROM dbo.{catalog_name}"
                result = db_config.execute_query(count_query)
                total = result[0][0] if result else 0

                print(f"\n📁 {catalog_name}: {total} registros")

                if total > 0:
                    # Obtener muestra de registros - usando columna detectada
                    sample_query = f"""
                        SELECT TOP {max_show} {id_column}, {desc_column}
                        FROM dbo.{catalog_name}
                        ORDER BY {id_column}
                    """
                    results = db_config.execute_query(sample_query)

                    if results:
                        for row in results[:5]:  # Mostrar máximo 5 en pantalla
                            print(f"   [{row[0]:3d}] {row[1]}")

                        if total > 5:
                            print(f"   ... y {total - 5} registros más")
                else:
                    print("   (Vacío)")

            except Exception as e:
                print(f"   ❌ Error leyendo {catalog_name}: {str(e)[:100]}")

        # Mostrar contenido de cada catálogo
        catalogs_to_show = [
            ('Idiomas', 'IdIdioma'),
            ('NivelIdiomas', 'IdNivelIdioma'),
            ('Empresas', 'IdEmpresa'),
            ('Puestos', 'IdPuesto'),
            ('CentroEstudios', 'IdCentroEstudios'),
            ('Certificaciones', 'IdCertificacion'),
            ('ConocimientosTecnicos', 'IdConocimientoTecnico'),
            ('ConocimientosNegocio', 'IdConocimientosNegocio'),
            ('ConocimientosOtros', 'IdConocimientosOtros')
        ]

        for catalog_info in catalogs_to_show:
            catalog, id_col = catalog_info
            show_catalog_content(catalog, id_col)

        print("\n" + "-" * 60)

        # Preguntar sobre inicialización con mensaje más claro
        print("\n4. OPCIONES DISPONIBLES:")
        print("   a) Añadir datos faltantes a los catálogos")
        print("   b) Ver qué datos se añadirían (sin modificar)")
        print("   c) Salir sin hacer cambios")

        response = input("\nSeleccione una opción (a/b/c): ").lower()

        if response == 'a':
            print("\n5. Añadiendo datos faltantes a catálogos...")
            results = schema_mgr.initialize_catalogs(force=False)

            for catalog, inserted in results.items():
                if inserted > 0:
                    print(f"   ✓ {catalog}: {inserted} nuevos registros añadidos")
                elif inserted == 0:
                    print(f"   - {catalog}: No se añadieron registros (ya existían)")
                else:
                    print(f"   ❌ {catalog}: Error al procesar")

        elif response == 'b':
            print("\n5. DATOS QUE SE AÑADIRÍAN (sin modificar BD):")
            print("-" * 60)

            # Simular qué se añadiría - versión simplificada
            print("\nVerificando qué elementos faltan en los catálogos principales...")

            # Solo verificar algunos elementos clave
            checks = [
                ('Idiomas', ['Español', 'Inglés', 'Francés', 'Alemán']),
                ('ConocimientosTecnicos', ['Python', 'Java', 'JavaScript']),
                ('ConocimientosNegocio', ['Banca', 'Seguros']),
                ('ConocimientosOtros', ['Scrum', 'Agile'])
            ]

            for catalog, samples in checks:
                print(f"\n{catalog}:")
                nuevos = 0
                existentes = 0

                for item in samples:
                    try:
                        id_found = schema_mgr.get_catalog_id(catalog, item)

                        if id_found:
                            print(f"   ✓ '{item}' - Ya existe (ID: {id_found})")
                            existentes += 1
                        else:
                            print(f"   + '{item}' - Se añadiría")
                            nuevos += 1
                    except:
                        print(f"   ? '{item}' - No se pudo verificar")

                if nuevos > 0:
                    print(f"   → Se añadirían aproximadamente {nuevos * 10} elementos nuevos")

        else:
            print("\n✓ Saliendo sin realizar cambios")

        print("\n" + "=" * 60)
        print("PROCESO COMPLETADO")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cerrar conexión
        if 'db_config' in locals():
            db_config.close()


if __name__ == "__main__":
    main()