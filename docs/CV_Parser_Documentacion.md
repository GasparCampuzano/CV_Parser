# Sistema de Procesamiento Automatizado de Currículums

## 📋 Visión General del Proyecto

El proyecto consiste en desarrollar un **sistema automatizado de extracción y clasificación de información** desde currículums vitae, utilizando inteligencia artificial (Azure OpenAI) para transformar documentos CV en formato JSON estructurado y posteriormente almacenar esta información en una base de datos MySQL.

## 🎯 Objetivo Principal

Crear una solución end-to-end que permita:
1. **Procesar currículums masivamente** (hasta 300 documentos por lote)
2. **Extraer información estructurada** mediante IA
3. **Clasificar conocimientos y habilidades** según categorías predefinidas
4. **Validar y almacenar datos** en base de datos evitando duplicados
5. **Proporcionar una interfaz** para que RRHH gestione el proceso

## 🏗️ Arquitectura Técnica

### Stack Tecnológico
- **Backend:** Python
- **IA:** Azure OpenAI Service (GPT-3.5-4K inicialmente)
- **Base de Datos:** MySQL
- **Frontend:** Angular/.NET (interfaz para RRHH)
- **Estructura:** Arquitectura modular con separación clara de responsabilidades

### Flujo de Proceso

```
CV (PDF/Word) → Extracción IA → JSON → Validación → Base de Datos
```

El proceso está **desacoplado en dos fases**:
1. **Fase de Extracción:** CV → IA → JSON
2. **Fase de Inserción:** JSON → Validación → BD

Esta separación permite optimizar costes (no reinvocar IA) y facilitar pruebas.

## 📊 Estructura de Datos Extraídos

### 1. Información del Candidato
- **Datos personales** (nombre, DNI)
- **Datos de contacto** (teléfono, email, dirección)
- **Identificación única** para evitar duplicados

### 2. Experiencia Profesional
- **Empresas y puestos** desempeñados
- **Duración calculada** (en meses, sin duplicar solapamientos)
- **Proyectos** (integrados dentro de cada experiencia, no como elementos independientes)
- **Exclusión** de prácticas/becas/contratos de formación del cómputo profesional

### 3. Formación Académica
- **Centros educativos**
- **Títulos obtenidos**
- **Certificaciones** (se registran como formación, no como skills)

### 4. Conocimientos y Habilidades

Sistema de clasificación en 4 bloques:

| Categoría                    | Descripción                               | Ejemplos                          | Tratamiento                                     |
|------------------------------|-------------------------------------------|-----------------------------------|-------------------------------------------------|
| **Conocimientos Técnicos**   | Lenguajes, BBDD, frameworks, herramientas | Java, Python, React, SQL Server   | Validación contra catálogo - sustitución por ID |
| **Conocimientos de Negocio** | Saberes de dominio/sector                 | Banca, Retail, Seguros, Marketing | Validación contra catálogo - sustitución por ID |
| **Otros Conocimientos**      | Metodologías y habilidades transversales  | Scrum, Agile, DevOps, Lean        | Validación contra catálogo - sustitución por ID |
| **Sin Especificar**          | Términos no clasificables                 | Varios                            | Marcados para revisión manual                   |

### 5. Idiomas
- **Solo idiomas oficiales y cooficiales** del catálogo
- Vinculación estricta con tabla `candidatos_idiomas`
- **Abortar inserción** si el idioma no existe en catálogo

## ✅ Reglas de Validación y Control

### Control de Duplicados
- **Clave primaria:** DNI (preferente)
- **Claves alternativas:** Nombre + Apellidos, Teléfono
- No permitir registro duplicado del mismo candidato

### Estrategia de Inserción en BD

1. **Elementos con validación estricta** (requieren existencia previa):
   - Idiomas → Abortar si no existe
   - Conocimientos técnicos/negocio → Rechazar si no existe en catálogo

2. **Elementos con alta condicional** (solicitar confirmación al usuario):
   - Empresas nuevas
   - Centros educativos nuevos
   - Títulos/certificaciones nuevas
   - Otros conocimientos no catalogados

3. **Orden de grabación:**
   1. Crear ficha básica en tabla `candidatos`
   2. Insertar relaciones 1-N (experiencia, formación, idiomas, habilidades)

## 📈 Gestión de Experiencia Profesional

### Cálculo de Duración
- **Experiencia total por puesto:** Periodo completo sin duplicar proyectos simultáneos
- **Proyectos:** Se registran dentro de la experiencia pero no se suman doblemente
- **Campo consolidado:** Experiencia total por rol/puesto en BD

### Criterios de Exclusión
- ❌ Prácticas universitarias
- ❌ Becas
- ❌ Contratos de formación
- ✅ Solo experiencias con empresa y contrato real

## 🔄 Proceso de Implementación

### Fase Actual
- ✅ Parser desarrollado generando JSON
- ✅ Conexión a BD establecida
- ✅ Primeras inserciones de prueba
- 🔄 Implementación de validaciones y control de duplicados

### Próximas Fases

#### Fase 1: Interfaz RRHH (Angular/.NET)
- Carga de CVs
- Visualización de validaciones
- Confirmación de altas nuevas
- Mensajes de error y confirmación

#### Fase 2: Módulo de Anonimización (Futuro)
- Generación de CVs ciegos
- IDs únicos persistentes
- Sustitución consistente de datos personales

## 💰 Optimización de Costes

### Estrategia de Modelos IA
- **Modelo inicial:** GPT-3.5-4K (mejor relación coste-rendimiento)
- **Escalado:** Solo migrar a GPT-4 si los resultados lo requieren

### Técnicas de Optimización
- **Desacoplamiento:** JSON como interfaz permite reutilizar extracciones
- **Procesamiento batch:** Minimizar llamadas a la API
- **Cache de resultados:** Evitar reprocesamiento de CVs idénticos

### Consideraciones de Región
- **Preferencia:** Europa (cumplimiento GDPR)
- **Alternativa:** West US (mayor disponibilidad de modelos)

## 🎯 Métricas de Éxito

### Métricas Cuantitativas
- **Capacidad:** Procesamiento de 300 CVs por lote
- **Velocidad:** < 5 segundos por CV individual
- **Precisión:** > 85% de extracción correcta
- **Disponibilidad:** 99% uptime del servicio

### Métricas Cualitativas
- **Robustez:** Manejo de múltiples formatos (PDF, Word, idiomas)
- **Integridad:** 0% duplicados en BD
- **Usabilidad:** Interfaz intuitiva para RRHH
- **Mantenibilidad:** Código modular y documentado

## 📁 Estructura del Proyecto

```
procesador_cv/
│
├── config/                         # Configuración del proyecto
│   ├── .env                        # Variables de entorno
│   └── settings.py                 # Configuraciones del sistema
│
├── docs/                           # Documentación
│   ├── architecture.md             # Arquitectura del proyecto
│   └── requirements.txt            # Dependencias
│
├── src/                            # Código fuente principal
│   ├── database/                   # Módulo de base de datos
│   │   ├── db_inserter_dir/        # Módulos de inserción por entidad
│   │   │   ├── candidato.py        # Inserción de candidatos
│   │   │   ├── catalogos.py        # Gestión de catálogos
│   │   │   ├── conocimientos.py    # Inserción de conocimientos
│   │   │   ├── experiencia.py      # Inserción experiencia laboral
│   │   │   ├── formacion.py        # Inserción formación académica
│   │   │   └── idiomas.py          # Inserción de idiomas
│   │   ├── db_config.py            # Configuración de BD
│   │   ├── db_inserter.py          # Orquestador de inserciones
│   │   └── db_validator.py         # Validación de datos
│   ├── app.py                      # Aplicación principal
│   ├── azure_openai_client.py      # Cliente de Azure OpenAI
│   ├── cv_extractor.py             # Extractor de información
│   └── prompt_query.py             # Gestor de prompts
│
├── storage/                        # Almacenamiento JSONs procesados
├── logs/                           # Registro de eventos
└── main.py                         # Punto de entrada

```

## 🔒 Consideraciones de Seguridad y Compliance

### Protección de Datos
- **GDPR Compliance:** Manejo seguro de datos personales
- **Anonimización:** Capacidad de generar CVs ciegos
- **Encriptación:** Datos sensibles encriptados en BD
- **Auditoría:** Log completo de todas las operaciones

### Control de Acceso
- **Autenticación:** Solo usuarios autorizados de RRHH
- **Roles:** Diferentes niveles de acceso según función
- **Trazabilidad:** Registro de quién procesa cada CV

## 📝 Notas de Desarrollo

### Decisiones Técnicas Clave
1. **Separación IA-BD:** Reduce costes y facilita testing
2. **JSON como interfaz:** Permite debugging y reprocesamiento
3. **Validación estricta:** Asegura integridad de datos
4. **Catálogos centralizados:** Mantiene consistencia de clasificación

### Lecciones Aprendidas
- La diversidad de formatos de CV requiere robustez en el parser
- El cálculo de experiencia con solapamientos necesita lógica específica
- La clasificación de conocimientos requiere actualización continua de catálogos
- El balance coste-precisión favorece inicialmente a GPT-3.5

## 📅 Cronograma

### Hitos Completados
- ✅ Prototipo de extracción con IA
- ✅ Estructura de base de datos
- ✅ Conexión Azure OpenAI
- ✅ Primeras pruebas de inserción

### Próximos Hitos
- 🔄 Sistema completo de validaciones
- 📅 Interfaz RRHH funcional
- 📅 Procesamiento batch de 300 CVs
- 📅 Módulo de anonimización

---

**Última actualización:** Octubre 2025  
**Estado del proyecto:** En desarrollo activo  
**Equipo:** Desarrollo Python + RRHH + Infraestructura Azure