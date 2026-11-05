#!/usr/bin/env python3
"""
Módulo de validación para el sistema CV Processor.
Proporciona validadores para duplicados de candidatos y validación contra catálogos.
Compatible con Microsoft SQL Server y la estructura de tablas existente.
CORREGIDO: Usa Usuario ID = 1 en lugar de 0 para todas las inserciones
"""

# Standard library imports
import re
import sys
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any, Union
from datetime import datetime

# Third-party imports
import pyodbc

# Add parent directory to path for relative imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Project imports
from src.database.db_config import DatabaseConfig
from src.database.db_schema import SchemaManager
from config.settings import get_logger, STRICT_VALIDATION, STRICT_CATALOGS

# Logger específico para validación
logger = get_logger(__name__)


class DuplicateValidator:
    """
    Validador de duplicados para candidatos.

    Implementa detección de duplicados en 3 niveles de prioridad:
    1. DNI (si existe y es único)
    2. Email + Nombre completo
    3. Teléfono + Nombre completo

    Según reuniones: evitar duplicados es crítico.
    """

    def __init__(self, db_config: DatabaseConfig = None):
        """
        Inicializa el validador de duplicados.

        Args:
            db_config: Instancia de DatabaseConfig. Si no se proporciona, crea una nueva.
        """
        self.db_config = db_config or DatabaseConfig()
        logger.info("DuplicateValidator inicializado")

    def check_candidate_exists(self, datos_contacto: Dict[str, Any]) -> Optional[int]:
        """
        Verifica si un candidato ya existe en la base de datos.

        Prioridad de verificación:
        1. DNI (más confiable)
        2. Email + Nombre
        3. Teléfono + Nombre

        Args:
            datos_contacto: Diccionario con datos de contacto del candidato
                Estructura esperada:
                - nombre: str
                - apellidos: str
                - email: str
                - telefono: str
                - dni: str (opcional)

        Returns:
            ID del candidato si existe, None si no existe
        """
        try:
            # Extraer y limpiar datos según nueva estructura
            nombre = self._clean_text(datos_contacto.get('nombre', ''))
            apellidos = self._clean_text(datos_contacto.get('apellidos', ''))

            # Construir nombre completo
            nombre_completo = f"{nombre} {apellidos}".strip() if nombre or apellidos else None

            # DNI podría no venir siempre
            dni = self._clean_dni(datos_contacto.get('dni'))

            # Email y teléfono con la estructura actual
            email = self._clean_email(datos_contacto.get('email'))
            telefono = self._clean_phone(datos_contacto.get('telefono'))

            # Prioridad 1: Verificar por DNI (si existe)
            if dni:
                candidate_id = self._check_by_dni(dni)
                if candidate_id:
                    logger.info(f"Candidato duplicado encontrado por DNI: {dni}")
                    return candidate_id

            # Prioridad 2: Verificar por Email + Nombre completo
            if email and nombre_completo:
                candidate_id = self._check_by_email_and_name(email, nombre_completo)
                if candidate_id:
                    logger.info(f"Candidato duplicado encontrado por email+nombre: {email}, {nombre_completo}")
                    return candidate_id

            # Prioridad 3: Verificar por Teléfono + Nombre completo
            if telefono and nombre_completo:
                candidate_id = self._check_by_phone_and_name(telefono, nombre_completo)
                if candidate_id:
                    logger.info(f"Candidato duplicado encontrado por teléfono+nombre: {telefono}, {nombre_completo}")
                    return candidate_id

            logger.debug(f"No se encontraron duplicados para: {nombre_completo or 'Sin nombre'}")
            return None

        except Exception as e:
            logger.error(f"Error verificando duplicados: {e}")
            # En caso de error, mejor ser conservador y no insertar duplicados
            # Podrías considerar re-lanzar la excepción según tu política de errores
            return None

    def _check_by_dni(self, dni: str) -> Optional[int]:
        """
        Busca candidato por DNI (DocumentoIdentidad).

        Args:
            dni: DNI limpio del candidato

        Returns:
            ID del candidato si existe
        """
        query = """
            SELECT IdCandidato 
            FROM dbo.Candidatos 
            WHERE DocumentoIdentidad = ?
        """

        try:
            result = self.db_config.execute_query(query, (dni,))
            if result and result[0]:
                return result[0][0]
        except Exception as e:
            logger.error(f"Error buscando por DNI: {e}")

        return None

    def _check_by_email_and_name(self, email: str, nombre: str) -> Optional[int]:
        """
        Busca candidato por combinación de email y nombre.

        Args:
            email: Email limpio del candidato
            nombre: Nombre completo limpio

        Returns:
            ID del candidato si existe
        """
        # Separar nombre completo en nombre y apellidos
        parts = nombre.split(' ', 1)
        nombre_solo = parts[0] if parts else nombre
        apellidos = parts[1] if len(parts) > 1 else ''

        # Buscar por email y nombre/apellidos
        query = """
            SELECT IdCandidato 
            FROM dbo.Candidatos 
            WHERE LOWER(CorreoElectronico) = LOWER(?)
            AND (LOWER(Nombre) = LOWER(?) OR LOWER(Apellidos) = LOWER(?) 
                 OR LOWER(CONCAT(Nombre, ' ', Apellidos)) = LOWER(?))
        """

        try:
            result = self.db_config.execute_query(
                query,
                (email, nombre_solo, apellidos, nombre)
            )
            if result and result[0]:
                return result[0][0]
        except Exception as e:
            logger.error(f"Error buscando por email+nombre: {e}")

        return None

    def _check_by_phone_and_name(self, telefono: str, nombre: str) -> Optional[int]:
        """
        Busca candidato por combinación de teléfono y nombre.

        Args:
            telefono: Teléfono limpio del candidato
            nombre: Nombre completo limpio

        Returns:
            ID del candidato si existe
        """
        # Separar nombre completo en nombre y apellidos
        parts = nombre.split(' ', 1)
        nombre_solo = parts[0] if parts else nombre
        apellidos = parts[1] if len(parts) > 1 else ''

        query = """
            SELECT IdCandidato 
            FROM dbo.Candidatos 
            WHERE TelefonoContacto = ?
            AND (LOWER(Nombre) = LOWER(?) OR LOWER(Apellidos) = LOWER(?)
                 OR LOWER(CONCAT(Nombre, ' ', Apellidos)) = LOWER(?))
        """

        try:
            result = self.db_config.execute_query(
                query,
                (telefono, nombre_solo, apellidos, nombre)
            )
            if result and result[0]:
                return result[0][0]
        except Exception as e:
            logger.error(f"Error buscando por teléfono+nombre: {e}")

        return None

    @staticmethod
    def _clean_dni(dni: Optional[str]) -> Optional[str]:
        """
        Limpia y normaliza un DNI.

        Args:
            dni: DNI en formato original

        Returns:
            DNI limpio o None
        """
        if not dni:
            return None

        # Eliminar espacios, guiones y puntos, convertir a mayúsculas
        dni_clean = re.sub(r'[\s\-.]', '', str(dni).upper())

        # Validar formato básico (8 números + 1 letra para DNI español)
        # Ajustar según necesidades del país
        if re.match(r'^\d{7,8}[A-Z]$', dni_clean):
            return dni_clean

        # Si no cumple formato estándar pero tiene contenido, devolver limpio
        return dni_clean if dni_clean else None

    @staticmethod
    def _clean_email(email: Optional[str]) -> Optional[str]:
        """
        Limpia y valida un email.

        Args:
            email: Email en formato original

        Returns:
            Email limpio o None
        """
        if not email:
            return None

        email_clean = str(email).strip().lower()

        # Validación básica de formato email
        if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email_clean):
            return email_clean

        return None

    @staticmethod
    def _clean_phone(phone: Optional[str]) -> Optional[str]:
        """
        Limpia y normaliza un número de teléfono.

        Args:
            phone: Teléfono en formato original

        Returns:
            Teléfono limpio o None
        """
        if not phone:
            return None

        # Eliminar todo excepto números y el símbolo +
        phone_clean = re.sub(r'[^\d+]', '', str(phone))

        # Validar longitud mínima
        if len(phone_clean) >= 9:
            return phone_clean

        return None

    @staticmethod
    def _clean_text(text: Optional[str]) -> Optional[str]:
        """
        Limpia texto general.

        Args:
            text: Texto en formato original

        Returns:
            Texto limpio o None
        """
        if not text:
            return None

        text_clean = ' '.join(str(text).split()).strip()
        return text_clean if text_clean else None


class CatalogValidator:
    """
    Validador contra catálogos existentes.

    Implementa las reglas de negocio de las reuniones:
    - Idiomas: solo se aceptan los del catálogo (oficiales/cooficiales)
    - Conocimientos técnicos: solo validados del catálogo
    - Conocimientos de negocio: solo validados del catálogo
    - Otros conocimientos: se pueden agregar nuevos
    - Empresas/Centros: se pueden crear pero marcados para validación
    """

    def __init__(self, db_config: DatabaseConfig = None, schema_manager: SchemaManager = None):
        """
        Inicializa el validador de catálogos.

        Args:
            db_config: Instancia de DatabaseConfig
            schema_manager: Instancia de SchemaManager
        """
        self.db_config = db_config or DatabaseConfig()
        self.schema_manager = schema_manager or SchemaManager(self.db_config)
        self._load_strict_settings()

        # IMPORTANTE: Usar Usuario ID = 1 (existe en BD como "Desarrollo")
        self.default_user_id = 1

        logger.info(f"CatalogValidator inicializado con Usuario ID = {self.default_user_id}")

    def _load_strict_settings(self):
        """Carga configuración de validación estricta desde settings."""
        self.strict_languages = STRICT_CATALOGS.get('idiomas', True)
        self.strict_tech_skills = STRICT_CATALOGS.get('habilidades_tecnicas', True)
        self.strict_business_skills = STRICT_CATALOGS.get('habilidades_negocio', True)
        self.strict_companies = STRICT_CATALOGS.get('empresas', False)
        self.strict_institutions = STRICT_CATALOGS.get('instituciones', False)

    def validate_languages(self, idiomas: List[Dict[str, str]]) -> Tuple[List[Dict], List[str]]:
        """
        Valida idiomas contra el catálogo.

        REGLA: Solo se aceptan idiomas que existen en el catálogo (Reunión 2 y 4).

        Args:
            idiomas: Lista de diccionarios con idioma y nivel

        Returns:
            Tupla (idiomas_válidos, idiomas_rechazados)
        """
        valid_languages = []
        rejected_languages = []

        for idioma_data in idiomas:
            idioma_nombre = self._normalize_language_name(idioma_data.get('idioma', ''))
            nivel = idioma_data.get('nivel', 'Básico')

            if not idioma_nombre:
                continue

            # Buscar idioma en catálogo
            idioma_id = self._find_language_id(idioma_nombre)

            if idioma_id:
                # Buscar nivel si existe, o usar default
                nivel_id = self._find_language_level_id(nivel)

                valid_languages.append({
                    'idioma_id': idioma_id,
                    'idioma_nombre': idioma_nombre,
                    'nivel_id': nivel_id,
                    'nivel_descripcion': nivel
                })
                logger.debug(f"Idioma válido: {idioma_nombre} - Nivel: {nivel}")
            else:
                rejected_languages.append(idioma_nombre)
                logger.warning(f"Idioma rechazado (no está en catálogo): {idioma_nombre}")

        return valid_languages, rejected_languages

    def validate_skills(self, habilidades: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Valida habilidades contra los catálogos correspondientes.

        REGLAS (Reunión 2):
        - Conocimientos técnicos: solo del catálogo
        - Conocimientos de negocio: solo del catálogo
        - Otros conocimientos: se pueden agregar
        - Sin especificar: marcados para revisión

        Args:
            habilidades: Diccionario categorizado de habilidades

        Returns:
            Diccionario con resultados de validación por categoría
        """
        results = {
            'tecnicos': {'encontrados': [], 'no_encontrados': []},
            'negocio': {'encontrados': [], 'no_encontrados': []},
            'otros': {'encontrados': [], 'nuevos': []},
            'sin_especificar': []
        }

        # Procesar conocimientos técnicos
        if 'conocimientos_tecnicos' in habilidades:
            results['tecnicos'] = self._validate_technical_skills(
                habilidades['conocimientos_tecnicos']
            )

        # Procesar conocimientos de negocio
        if 'conocimientos_negocio' in habilidades:
            results['negocio'] = self._validate_business_skills(
                habilidades['conocimientos_negocio']
            )

        # Procesar otros conocimientos
        if 'otros_conocimientos' in habilidades:
            results['otros'] = self._validate_other_skills(
                habilidades['otros_conocimientos']
            )

        # Procesar sin especificar
        if 'sin_especificar' in habilidades:
            results['sin_especificar'] = habilidades['sin_especificar']
            logger.info(f"Habilidades sin especificar para revisión: {len(results['sin_especificar'])}")

        return results

    def validate_company(self, empresa: str) -> Dict[str, Any]:
        """
        Valida una empresa contra el catálogo.

        REGLA: Se pueden crear nuevas pero marcadas para validación (Reunión 2 y 4).

        Args:
            empresa: Nombre de la empresa

        Returns:
            Diccionario con id, nombre y si está validada
        """
        empresa_clean = self._clean_company_name(empresa)

        if not empresa_clean:
            return {'id': None, 'nombre': empresa, 'validada': False}

        # Buscar empresa existente
        empresa_id = self._find_company_id(empresa_clean)

        if empresa_id:
            return {
                'id': empresa_id,
                'nombre': empresa_clean,
                'validada': True
            }

        # Si no existe y no es modo estricto, se puede crear
        if not self.strict_companies:
            # Crear nueva empresa (marcada como no validada)
            empresa_id = self._create_company(empresa_clean)
            if empresa_id:
                logger.info(f"Nueva empresa creada (pendiente validación): {empresa_clean}")
                return {
                    'id': empresa_id,
                    'nombre': empresa_clean,
                    'validada': False
                }

        logger.warning(f"Empresa no encontrada y no se pudo crear: {empresa_clean}")
        return {'id': None, 'nombre': empresa_clean, 'validada': False}

    def validate_institution(self, institucion: str) -> Dict[str, Any]:
        """
        Valida una institución educativa contra el catálogo.

        REGLA: Se pueden crear nuevas pero marcadas para validación (Reunión 2).

        Args:
            institucion: Nombre de la institución

        Returns:
            Diccionario con id, nombre y si está validada
        """
        institucion_clean = self._clean_text(institucion)

        if not institucion_clean:
            return {'id': None, 'nombre': institucion, 'validada': False}

        # Buscar institución existente
        institucion_id = self._find_institution_id(institucion_clean)

        if institucion_id:
            return {
                'id': institucion_id,
                'nombre': institucion_clean,
                'validada': True
            }

        # Si no existe y no es modo estricto, se puede crear
        if not self.strict_institutions:
            # Crear nueva institución (marcada como no validada)
            institucion_id = self._create_institution(institucion_clean)
            if institucion_id:
                logger.info(f"Nueva institución creada (pendiente validación): {institucion_clean}")
                return {
                    'id': institucion_id,
                    'nombre': institucion_clean,
                    'validada': False
                }

        logger.warning(f"Institución no encontrada y no se pudo crear: {institucion_clean}")
        return {'id': None, 'nombre': institucion_clean, 'validada': False}

    def _validate_technical_skills(self, skills: List[str]) -> Dict[str, List]:
        """
        Valida conocimientos técnicos contra catálogo.
        Solo se aceptan los que existen en el catálogo.
        """
        found = []
        not_found = []

        for skill in skills:
            skill_clean = self._clean_text(skill)
            if not skill_clean:
                continue

            skill_id = self._find_technical_skill_id(skill_clean)

            if skill_id:
                found.append({
                    'id': skill_id,
                    'nombre': skill_clean,
                    'categoria': 'tecnico'
                })
            else:
                not_found.append(skill_clean)
                logger.debug(f"Conocimiento técnico no encontrado: {skill_clean}")

        return {'encontrados': found, 'no_encontrados': not_found}

    def _validate_business_skills(self, skills: List[str]) -> Dict[str, List]:
        """
        Valida conocimientos de negocio contra catálogo.
        Solo se aceptan los que existen en el catálogo.
        """
        found = []
        not_found = []

        for skill in skills:
            skill_clean = self._clean_text(skill)
            if not skill_clean:
                continue

            skill_id = self._find_business_skill_id(skill_clean)

            if skill_id:
                found.append({
                    'id': skill_id,
                    'nombre': skill_clean,
                    'categoria': 'negocio'
                })
            else:
                not_found.append(skill_clean)
                logger.debug(f"Conocimiento de negocio no encontrado: {skill_clean}")

        return {'encontrados': found, 'no_encontrados': not_found}

    def _validate_other_skills(self, skills: List[str]) -> Dict[str, List]:
        """
        Valida otros conocimientos.
        Se pueden agregar nuevos si no existen.
        """
        found = []
        new_skills = []

        for skill in skills:
            skill_clean = self._clean_text(skill)
            if not skill_clean:
                continue

            # Buscar si ya existe
            skill_id = self._find_other_skill_id(skill_clean)

            if skill_id:
                found.append({
                    'id': skill_id,
                    'nombre': skill_clean,
                    'categoria': 'otros'
                })
            else:
                # Crear nuevo conocimiento "otros"
                skill_id = self._create_other_skill(skill_clean)
                if skill_id:
                    new_skills.append({
                        'id': skill_id,
                        'nombre': skill_clean,
                        'categoria': 'otros'
                    })
                    logger.info(f"Nuevo conocimiento 'otros' creado: {skill_clean}")

        return {'encontrados': found, 'nuevos': new_skills}

    # ========== Métodos auxiliares de búsqueda ==========

    def _find_language_id(self, idioma: str) -> Optional[int]:
        """Busca ID de idioma en catálogo."""
        query = """
            SELECT IdIdioma 
            FROM dbo.Idiomas 
            WHERE LOWER(Descripcion) = LOWER(?)
        """
        try:
            result = self.db_config.execute_query(query, (idioma,))
            return result[0][0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Error buscando idioma {idioma}: {e}")
            return None

    def _find_language_level_id(self, nivel: str) -> Optional[int]:
        """Busca ID de nivel de idioma."""
        query = """
            SELECT IdNivelIdioma 
            FROM dbo.NivelIdiomas 
            WHERE LOWER(Descripcion) = LOWER(?)
        """
        try:
            result = self.db_config.execute_query(query, (nivel,))
            return result[0][0] if result and result[0] else 1  # Default nivel básico
        except Exception as e:
            logger.error(f"Error buscando nivel {nivel}: {e}")
            return 1

    def _find_technical_skill_id(self, skill: str) -> Optional[int]:
        """Busca ID de conocimiento técnico."""
        query = """
            SELECT IdConocimientoTecnico 
            FROM dbo.ConocimientosTecnicos 
            WHERE LOWER(Descripcion) = LOWER(?)
        """
        try:
            result = self.db_config.execute_query(query, (skill,))
            return result[0][0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Error buscando conocimiento técnico {skill}: {e}")
            return None

    def _find_business_skill_id(self, skill: str) -> Optional[int]:
        """Busca ID de conocimiento de negocio."""
        query = """
            SELECT IdConocimientosNegocio 
            FROM dbo.ConocimientosNegocio 
            WHERE LOWER(Descripcion) = LOWER(?)
        """
        try:
            result = self.db_config.execute_query(query, (skill,))
            return result[0][0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Error buscando conocimiento negocio {skill}: {e}")
            return None

    def _find_other_skill_id(self, skill: str) -> Optional[int]:
        """Busca ID de otros conocimientos."""
        query = """
            SELECT IdConocimientosOtros 
            FROM dbo.ConocimientosOtros 
            WHERE LOWER(Descripcion) = LOWER(?)
        """
        try:
            result = self.db_config.execute_query(query, (skill,))
            return result[0][0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Error buscando otros conocimientos {skill}: {e}")
            return None

    def _find_company_id(self, empresa: str) -> Optional[int]:
        """Busca ID de empresa."""
        query = """
            SELECT IdEmpresa 
            FROM dbo.Empresas 
            WHERE LOWER(Descripcion) = LOWER(?)
        """
        try:
            result = self.db_config.execute_query(query, (empresa,))
            return result[0][0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Error buscando empresa {empresa}: {e}")
            return None

    def _find_institution_id(self, institucion: str) -> Optional[int]:
        """Busca ID de institución educativa."""
        query = """
            SELECT IdCentroEstudios 
            FROM dbo.CentroEstudios 
            WHERE LOWER(Descripcion) = LOWER(?)
        """
        try:
            result = self.db_config.execute_query(query, (institucion,))
            return result[0][0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Error buscando institución {institucion}: {e}")
            return None

    # ========== Métodos de creación (solo donde está permitido) ==========

    def _create_company(self, empresa: str) -> Optional[int]:
        """
        Crea nueva empresa en catálogo.
        CORREGIDO: Usa SCOPE_IDENTITY()
        """
        try:
            existing_id = self._find_company_id(empresa)
            if existing_id:
                return existing_id

            insert_query = """
                INSERT INTO dbo.Empresas 
                (Descripcion, FechaModificacion, UsuarioModificacion, FechaAlta, UsuarioAlta)
                VALUES (?, GETDATE(), ?, GETDATE(), ?);
                SELECT SCOPE_IDENTITY();
            """

            result = self.db_config.execute_query(
                insert_query,
                (empresa, self.default_user_id, self.default_user_id),
                fetch=True,
                commit=True
            )

            if result and result[0] and result[0][0]:
                new_id = int(result[0][0])
                logger.info(f"Nueva empresa creada: {empresa} (ID: {new_id})")
                return new_id

        except pyodbc.IntegrityError:
            logger.debug(f"Empresa ya existe, buscando: {empresa}")
            return self._find_company_id(empresa)
        except Exception as e:
            logger.error(f"Error creando empresa {empresa}: {e}")

        return None

    def _create_institution(self, institucion: str) -> Optional[int]:
        """
        Crea nueva institución en catálogo.
        CORREGIDO: Usa SCOPE_IDENTITY()
        """
        try:
            existing_id = self._find_institution_id(institucion)
            if existing_id:
                return existing_id

            insert_query = """
                INSERT INTO dbo.CentroEstudios 
                (Descripcion, FechaModificacion, UsuarioModificacion, FechaAlta, UsuarioAlta)
                VALUES (?, GETDATE(), ?, GETDATE(), ?);
                SELECT SCOPE_IDENTITY();
            """

            result = self.db_config.execute_query(
                insert_query,
                (institucion, self.default_user_id, self.default_user_id),
                fetch=True,
                commit=True
            )

            if result and result[0] and result[0][0]:
                new_id = int(result[0][0])
                logger.info(f"Nueva institución creada: {institucion} (ID: {new_id})")
                return new_id

        except pyodbc.IntegrityError:
            logger.debug(f"Institución ya existe, buscando: {institucion}")
            return self._find_institution_id(institucion)
        except Exception as e:
            logger.error(f"Error creando institución {institucion}: {e}")

        return None

    def _create_other_skill(self, skill: str) -> Optional[int]:
        """
        Crea nuevo conocimiento en categoría 'otros'.
        CORREGIDO: Usa SCOPE_IDENTITY() en lugar de OUTPUT
        """
        try:
            existing_id = self._find_other_skill_id(skill)
            if existing_id:
                return existing_id

            insert_query = """
                INSERT INTO dbo.ConocimientosOtros 
                (Descripcion, FechaModificacion, UsuarioModificacion, FechaAlta, UsuarioAlta)
                VALUES (?, GETDATE(), ?, GETDATE(), ?)
            """

            result = self.db_config.execute_query(
                insert_query,
                (skill, self.default_user_id, self.default_user_id),
                fetch=False,
                commit=True
            )

            # Obtener el ID con SCOPE_IDENTITY en una query separada
            id_query = "SELECT SCOPE_IDENTITY()"
            result = self.db_config.execute_query(id_query, fetch=True)

            if result and result[0] and result[0][0]:
                new_id = int(result[0][0])
                logger.info(f"Nuevo conocimiento 'otros' creado: {skill} (ID: {new_id})")
                return new_id

        except pyodbc.IntegrityError:
            # Si ya existe por el índice único, buscar el ID
            logger.debug(f"Conocimiento ya existe, buscando: {skill}")
            return self._find_other_skill_id(skill)
        except Exception as e:
            logger.error(f"Error creando otros conocimientos {skill}: {e}")

        return None

    # ========== Métodos de normalización ==========

    @staticmethod
    def _normalize_language_name(idioma: str) -> str:
        """Normaliza nombre de idioma."""
        # Mapeo de variantes comunes
        language_map = {
            'ingles': 'Inglés',
            'inglés': 'Inglés',  # Con tilde
            'english': 'Inglés',
            'español': 'Español',
            'espanol': 'Español',
            'spanish': 'Español',
            'castellano': 'Español',
            'frances': 'Francés',
            'francés': 'Francés',  # Con tilde
            'french': 'Francés',
            'aleman': 'Alemán',
            'alemán': 'Alemán',  # Con tilde
            'german': 'Alemán',
            'italiano': 'Italiano',
            'italian': 'Italiano',
            'portugues': 'Portugués',
            'portugués': 'Portugués',  # Con tilde
            'portuguese': 'Portugués',
            'catalan': 'Catalán',
            'catalán': 'Catalán',  # Con tilde
            'valenciano': 'Valenciano',
            'vasco': 'Euskera',
            'euskera': 'Euskera',
            'gallego': 'Gallego',
            'galego': 'Gallego'
        }

        idioma_lower = idioma.lower().strip()
        # Si está en el mapeo, devolver la forma normalizada
        if idioma_lower in language_map:
            return language_map[idioma_lower]

        # Si no está en el mapeo, devolver el original con primera letra mayúscula
        return idioma.strip().capitalize()

    @staticmethod
    def _clean_company_name(empresa: str) -> str:
        """Limpia nombre de empresa."""
        if not empresa:
            return ""

        # Eliminar sufijos comunes
        empresa_clean = empresa.strip()
        suffixes = ['S.A.', 'S.L.', 'S.L.U.', 'S.A.U.', 'Inc.', 'Ltd.', 'LLC']

        for suffix in suffixes:
            if empresa_clean.endswith(suffix):
                empresa_clean = empresa_clean[:-len(suffix)].strip()

        return empresa_clean

    @staticmethod
    def _clean_text(text: Optional[str]) -> str:
        """Limpia texto general."""
        if not text:
            return ""
        return ' '.join(str(text).split()).strip()


class ExperienceValidator:
    """
    Validador especializado para experiencias profesionales.

    Implementa las reglas de las reuniones:
    - Proyectos dentro de experiencias (no independientes)
    - Prácticas van a formación, no a experiencia
    - Cálculo de duración sin solapamientos
    """

    def __init__(self, db_config: DatabaseConfig = None):
        """
        Inicializa el validador de experiencias.

        Args:
            db_config: Instancia de DatabaseConfig
        """
        self.db_config = db_config or DatabaseConfig()
        logger.info("ExperienceValidator inicializado")

    @staticmethod
    def validate_experience_type(experiencia: Dict[str, Any]) -> str:
        """
        Determina el tipo de experiencia.

        Reglas (Reunión 5):
        - Prácticas/becas/contratos formación → 'formacion'
        - Experiencia con empresa y contrato → 'profesional'

        Args:
            experiencia: Diccionario con datos de experiencia

        Returns:
            'profesional' o 'formacion'
        """
        # Palabras clave que indican prácticas/formación
        keywords_practicas = [
            'práctica', 'practica', 'beca', 'becario',
            'formación', 'formacion', 'trainee', 'intern',
            'aprendiz', 'estudiante', 'universitario'
        ]

        puesto = (experiencia.get('puesto', '') or '').lower()
        descripcion = (experiencia.get('descripcion', '') or '').lower()
        empresa = (experiencia.get('empresa', '') or '').lower()

        # Verificar si es práctica/formación
        for keyword in keywords_practicas:
            if keyword in puesto or keyword in descripcion or keyword in empresa:
                logger.debug(f"Experiencia clasificada como formación/práctica: {puesto}")
                return 'formacion'

        # Si tiene empresa y no es práctica, es profesional
        if experiencia.get('empresa'):
            return 'profesional'

        # Por defecto, si no está claro
        return 'formacion'

    @staticmethod
    def calculate_duration(fecha_inicio: str, fecha_fin: str) -> int:
        """
        Calcula duración en meses entre dos fechas.

        Args:
            fecha_inicio: Fecha en formato YYYY-MM o YYYY-MM-DD
            fecha_fin: Fecha en formato YYYY-MM o YYYY-MM-DD

        Returns:
            Duración en meses
        """
        try:
            # Parsear fechas flexiblemente
            if fecha_inicio and fecha_fin:
                # Intentar formato completo primero
                try:
                    start = datetime.strptime(fecha_inicio, '%Y-%m-%d')
                    end = datetime.strptime(fecha_fin, '%Y-%m-%d')
                except ValueError:
                    # Intentar formato año-mes
                    try:
                        start = datetime.strptime(fecha_inicio, '%Y-%m')
                        end = datetime.strptime(fecha_fin, '%Y-%m')
                    except ValueError:
                        # Intentar solo año
                        start = datetime.strptime(str(fecha_inicio), '%Y')
                        end = datetime.strptime(str(fecha_fin), '%Y')

                # Calcular diferencia en meses
                months = (end.year - start.year) * 12 + (end.month - start.month)

                # Mínimo 1 mes si las fechas son válidas
                return max(1, months)

            return 0

        except Exception as e:
            logger.warning(f"Error calculando duración: {e}")
            return 0

    def validate_projects(self, proyectos: List[Dict], experiencia_id: int) -> List[Dict]:
        """
        Valida proyectos asociados a una experiencia.

        Regla (Reunión 5): Los proyectos siempre van dentro de experiencias.

        Args:
            proyectos: Lista de proyectos
            experiencia_id: ID de la experiencia padre

        Returns:
            Lista de proyectos validados
        """
        validated_projects = []

        for proyecto in proyectos:
            # Limpiar datos básicos
            proyecto_validado = {
                'experiencia_id': experiencia_id,
                'nombre': self._clean_text(proyecto.get('nombre', 'Proyecto sin nombre')),
                'cliente': self._clean_text(proyecto.get('cliente')),
                'tecnologias': ', '.join(proyecto.get('tecnologias', [])) if isinstance(
                    proyecto.get('tecnologias'), list
                ) else proyecto.get('tecnologias'),
                'descripcion': self._clean_text(proyecto.get('descripcion')),
                'fecha_inicio': proyecto.get('fecha_inicio'),
                'fecha_fin': proyecto.get('fecha_fin'),
                'duracion_meses': ExperienceValidator.calculate_duration(
                    proyecto.get('fecha_inicio'),
                    proyecto.get('fecha_fin')
                )
            }

            validated_projects.append(proyecto_validado)
            logger.debug(f"Proyecto validado: {proyecto_validado['nombre']}")

        return validated_projects

    @staticmethod
    def _clean_text(text: Optional[str]) -> Optional[str]:
        """Limpia texto general."""
        if not text:
            return None
        cleaned = ' '.join(str(text).split()).strip()
        return cleaned if cleaned else None


def test_validators():
    """
    Función de prueba para los validadores.
    """
    print("\n" + "=" * 60)
    print("PRUEBA DE VALIDADORES - CV PROCESSOR")
    print("=" * 60)

    try:
        # Inicializar
        db_config = DatabaseConfig()
        schema_manager = SchemaManager(db_config)

        # Test conexión
        print("\n1. Probando conexión...")
        if not db_config.test_connection():
            print("   ❌ Error de conexión")
            return
        print("   ✅ Conexión exitosa")

        # Verificar Usuario ID = 1
        print("\n2. Verificando Usuario para operaciones...")
        result = db_config.execute_query("SELECT Id, Nombre FROM dbo.Usuario WHERE Id = 1")
        if result:
            print(f"   ✅ Usuario sistema encontrado: ID={result[0][0]}, Nombre='{result[0][1]}'")
        else:
            print("   ❌ Usuario ID=1 no encontrado - Las inserciones fallarán")
            return

        # Test DuplicateValidator
        print("\n3. Probando DuplicateValidator...")
        dup_validator = DuplicateValidator(db_config)

        test_contact = {
            'dni': '12345678A',
            'nombre_completo': 'Juan Pérez García',
            'email': 'juan.perez@example.com',
            'telefono': '+34 666 123 456'
        }

        duplicate_id = dup_validator.check_candidate_exists(test_contact)
        if duplicate_id:
            print(f"   ⚠️ Candidato duplicado encontrado: ID #{duplicate_id}")
        else:
            print("   ✅ No se encontraron duplicados")

        # Test CatalogValidator
        print("\n4. Probando CatalogValidator...")
        cat_validator = CatalogValidator(db_config, schema_manager)
        print(f"   Configurado con Usuario ID = {cat_validator.default_user_id}")

        # Test idiomas
        test_languages = [
            {'idioma': 'Español', 'nivel': 'Nativo'},
            {'idioma': 'Inglés', 'nivel': 'C1'},
            {'idioma': 'Klingon', 'nivel': 'Fluido'}  # No existe
        ]

        valid_langs, rejected_langs = cat_validator.validate_languages(test_languages)
        print(f"   Idiomas válidos: {len(valid_langs)}")
        print(f"   Idiomas rechazados: {rejected_langs}")

        # Test habilidades
        test_skills = {
            'conocimientos_tecnicos': ['Python', 'Java', 'Quantum Computing'],
            'conocimientos_negocio': ['Banca', 'Seguros', 'Alquimia'],
            'otros_conocimientos': ['Scrum', 'Agile', 'Meditación'],
            'sin_especificar': ['Algo', 'Otro']
        }

        skills_result = cat_validator.validate_skills(test_skills)
        print(f"   Técnicos encontrados: {len(skills_result['tecnicos']['encontrados'])}")
        print(f"   Técnicos no encontrados: {skills_result['tecnicos']['no_encontrados']}")
        print(f"   Negocio encontrados: {len(skills_result['negocio']['encontrados'])}")
        print(f"   Otros nuevos: {len(skills_result['otros'].get('nuevos', []))}")

        # Test ExperienceValidator
        print("\n5. Probando ExperienceValidator...")
        exp_validator = ExperienceValidator(db_config)

        test_exp = {
            'empresa': 'Empresa Ejemplo S.L.',
            'puesto': 'Becario de desarrollo',
            'descripcion': 'Prácticas universitarias'
        }

        exp_type = ExperienceValidator.validate_experience_type(test_exp)
        print(f"   Tipo de experiencia: {exp_type}")

        duration = ExperienceValidator.calculate_duration('2023-01', '2024-06')
        print(f"   Duración calculada: {duration} meses")

        print("\n" + "=" * 60)
        print("PRUEBAS COMPLETADAS")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error en pruebas: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'db_config' in locals():
            db_config.close()


if __name__ == "__main__":
    test_validators()