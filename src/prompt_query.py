
# ============================================
# PROMPTS MODULARES PARA EXTRACCIÓN DE CV
# ============================================

def create_contacto_prompt(cv_text: str, current_date: str) -> str:

    """Prompt específico para extraer datos de contacto."""

    return f"""
Extrae ÚNICAMENTE los datos de contacto del siguiente CV y devuelve un JSON válido.

FECHA ACTUAL: {current_date}

**INSTRUCCIONES:**
- Extraer información de contacto del CV completo
- Si un dato no existe, usar null
- No inventar ni inferir datos
- Buscar en TODO el texto, no solo al principio

**REGLAS ESPECÍFICAS:**
- nombre: Primera letra en mayúscula de cada parte
- apellidos: Todos los apellidos juntos, primera letra en mayúscula
- email: En minúsculas, validar formato básico
- telefono: Formato internacional (+34...), sin espacios ni guiones
- direccion: Desglosar en campos separados (calle, localidad, codigo_postal, provincia, pais)
- linkedin: Solo URL válida de LinkedIn
- otras_redes: Lista de otras redes sociales profesionales (NO incluir LinkedIn aquí)
- sexo: "H" o "M" solo si es explícito o muy claro por el nombre, sino null

**FORMATO DE SALIDA:**
{{
    "datos_contacto": {{
        "nombre": "string o null",
        "apellidos": "string o null", 
        "email": "string o null",
        "telefono": "string o null",
        "direccion": {{
            "calle": "string o null",
            "localidad": "string o null",
            "codigo_postal": "string o null",
            "provincia": "string o null",
            "pais": "string o null"
        }},
        "linkedin": "string o null",
        "otras_redes": [],
        "sexo": "H/M o null"
    }}
}}

**TEXTO DEL CV:**
{cv_text}

**RESPUESTA (solo JSON, sin explicaciones):**
"""


def create_experiencia_prompt(cv_text: str, current_date: str) -> str:
    """Prompt específico para extraer experiencia profesional."""

    return f"""
Extrae ÚNICAMENTE la experiencia profesional del siguiente CV y devuelve un JSON válido.

FECHA ACTUAL PARA CÁLCULOS: {current_date}

**INSTRUCCIONES:**
- Extraer SOLO experiencias laborales remuneradas (NO prácticas, NO becas)
- Ordenar cronológicamente inverso (más reciente primero)
- Calcular duración en meses para cada experiencia
- No inventar datos

**REGLAS PARA CADA EXPERIENCIA:**
- empresa: Nombre exacto como aparece en el CV
- puesto: Cargo exacto sin modificaciones
- fecha_inicio/fecha_fin: Formato YYYY-MM-DD
  * Solo año → YYYY-01-01
  * Solo mes/año → YYYY-MM-01
  * "actualidad/presente" → fecha_fin: null
- duracion: Calcular meses entre inicio y fin (string)
- descripcion: Texto completo de responsabilidades, concatenar viñetas con ". "
- ubicacion: Ciudad/país si aparece, sino null
- es_practica: false (las prácticas NO van aquí)
- proyectos: Lista de proyectos si se mencionan específicamente

**FORMATO DE PROYECTO:**
{{
    "nombre": "string",
    "cliente": "string o null",
    "tecnologias": "string con tecnologías separadas por comas",
    "descripcion": "string",
    "fecha_inicio": "YYYY-MM-DD o null",
    "fecha_fin": "YYYY-MM-DD o null",
    "duracion_meses": "string o null"
}}

**FORMATO DE SALIDA:**
{{
    "experiencia_profesional": [
        {{
            "empresa": "string",
            "puesto": "string",
            "fecha_inicio": "YYYY-MM-DD",
            "fecha_fin": "YYYY-MM-DD o null",
            "duracion": "string (número de meses)",
            "descripcion": "string",
            "ubicacion": "string o null",
            "es_practica": false,
            "proyectos": []
        }}
    ]
}}

**TEXTO DEL CV:**
{cv_text}

**RESPUESTA (solo JSON, sin explicaciones):**
"""


def create_formacion_prompt(cv_text: str, current_date: str) -> str:
    """Prompt específico para extraer formación."""

    return f"""
Extrae ÚNICAMENTE la formación, educación y certificaciones del siguiente CV y devuelve un JSON válido.

FECHA ACTUAL: {current_date}

**INSTRUCCIONES:**
- Incluir: estudios académicos, cursos, certificaciones, prácticas formativas, becas
- Ordenar cronológicamente inverso
- No inventar datos

**CLASIFICACIÓN DE TIPO:**
- "academica": Estudios reglados (grados, máster, FP, bootcamps, cursos)
- "certificacion": Certificaciones profesionales (AWS, Cisco, PMI, ITIL, etc.)
- "practica": Prácticas, internships, contratos en prácticas
- "beca": Becas, scholarships

**CLASIFICACIÓN DE RANGO (solo para tipo "academica"):**
- doctorado
- master_universitario
- grado_universitario
- tecnico_superior
- fp_superior
- fp_medio
- fp_basica
- bachillerato
- eso
- primaria
- sin_estudios (si no se puede determinar)

**REGLAS:**
- institucion: Nombre exacto del centro
- titulo: Nombre exacto del título/curso
- fecha_inicio/fecha_fin: Formato YYYY-MM-DD
- descripcion: Detalles adicionales (horas, modalidad, nota) si existen
- proyectos: Solo si menciona TFG, TFM o proyectos académicos específicos

**FORMATO DE SALIDA:**
{{
    "formacion": [
        {{
            "institucion": "string",
            "titulo": "string",
            "fecha_inicio": "YYYY-MM-DD",
            "fecha_fin": "YYYY-MM-DD o null",
            "descripcion": "string o null",
            "tipo": "academica|certificacion|practica|beca",
            "rango": "string (solo si tipo es 'academica')",
            "proyectos": []
        }}
    ]
}}

**TEXTO DEL CV:**
{cv_text}

**RESPUESTA (solo JSON, sin explicaciones):**
"""


def create_idiomas_prompt(cv_text: str, current_date: str) -> str:
    """Prompt específico para extraer idiomas."""

    return f"""
Extrae ÚNICAMENTE los idiomas del siguiente CV y devuelve un JSON válido.

**INSTRUCCIONES:**
- Extraer todos los idiomas mencionados con sus niveles
- No inventar idiomas ni niveles

**NIVELES VÁLIDOS (USAR SOLO ESTOS):**
- Certificaciones oficiales: "A1", "A2", "B1", "B2", "C1", "C2"
- Descriptivos: "Bajo", "Bajo-Medio", "Medio", "Medio-Alto", "Alto"
- Si no indica nivel: null

**MAPEO OBLIGATORIO:**
- básico/elemental/principiante → "Bajo"
- pre-intermedio/intermedio-bajo → "Bajo-Medio"
- intermedio → "Medio"
- intermedio-alto/bueno → "Medio-Alto"
- avanzado/fluido/proficiente → "Alto"
- nativo/lengua materna/bilingüe → "C2"
- First/FCE → "B2"
- Advanced/CAE → "C1"
- Proficiency/CPE → "C2"
- PET → "B1"
- KET → "A2"

**FORMATO DE SALIDA:**
{{
    "idiomas": [
        {{
            "idioma": "string (primera letra mayúscula)",
            "nivel": "string o null (solo valores válidos)"
        }}
    ]
}}

**TEXTO DEL CV:**
{cv_text}

**RESPUESTA (solo JSON, sin explicaciones):**
"""


def create_habilidades_prompt(cv_text: str, current_date: str) -> str:
    """Prompt específico para extraer habilidades y conocimientos."""

    return f"""
Extrae ÚNICAMENTE las habilidades técnicas y conocimientos del siguiente CV y clasifícalas correctamente.

**INSTRUCCIONES:**
- Buscar en TODO el CV: experiencias, proyectos, formación, habilidades
- NO incluir soft skills (trabajo en equipo, liderazgo, comunicación, etc.)
- NO inventar habilidades esperables del puesto
- Separar elementos unidos por "/" o "&" o comas
- Mantener unidas expresiones estándar: "TCP/IP", "CI/CD", "UI/UX"

**CLASIFICACIÓN OBLIGATORIA:**

1. CONOCIMIENTOS TÉCNICOS (herramientas para CREAR/CONSTRUIR):
- Lenguajes: Python, Java, JavaScript, C#, Go, etc.
- Frameworks/Librerías: React, Angular, Django, pandas, NumPy, etc.
- Bases de datos: MySQL, PostgreSQL, MongoDB, Redis, etc.
- DevOps: Docker, Kubernetes, Jenkins, Git, etc.
- Cloud técnico: AWS, Azure, GCP (para desarrollo/despliegue)
- BI/Analytics técnico: Power BI, Tableau (cuando se use para desarrollo)
- IDEs: Visual Studio, IntelliJ, VSCode

2. CONOCIMIENTOS DE NEGOCIO (contextos y sectores):
- Sectores: Banca, Seguros, Retail, Telecomunicaciones
- Dominios: E-commerce, Facturación, Trading
- Normativas: GDPR, PCI-DSS, ISO 27001
- Áreas funcionales: Finanzas, Marketing, RRHH

3. OTROS CONOCIMIENTOS (metodologías y productividad):
- Ofimática: Excel, Word, PowerPoint, Access
- Metodologías: Scrum, Agile, Kanban
- Gestión: JIRA, Confluence, Trello
- Colaboración: Teams, Slack, Zoom
- Certificaciones de gestión: PMP, Scrum Master

4. SIN ESPECIFICAR:
- Solo si no encaja claramente en ninguna categoría anterior

**FORMATO DE SALIDA:**
{{
    "habilidades": {{
        "conocimientos_tecnicos": ["array de strings"],
        "conocimientos_negocio": ["array de strings"],
        "otros_conocimientos": ["array de strings"],
        "conocimientos_sin_especificar": ["array de strings"]
    }}
}}

**TEXTO DEL CV:**
{cv_text}

**RESPUESTA (solo JSON, sin explicaciones):**
"""
