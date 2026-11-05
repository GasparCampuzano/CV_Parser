# Arquitectura del Proyecto: procesador_cv

```
│
├── config/                         # Configuración del proyecto
│   ├── .env                        # Variables de entorno
│   ├── __init__.py                 # Módulo de inicialización
│   └── settings.py                 # Configuraciones del sistema
│
├── docs/                           # Documentación
│   ├── architecture.txt            # Plantilla de la arquitectura del proyecto
│   └── CV_Parser_Documentacion.md  # Documentación completa del sistema
│
├── logs/                           # Registro de eventos
│
├── src/                            # Código fuente principal
│   ├── database/                   # Módulo de base de datos
│   │   ├── db_inserter_dir/        # Módulos de inserción por entidad
│   │   │   ├── __init__.py
│   │   │   ├── candidato.py        # Inserción de datos del candidato
│   │   │   ├── catalogos.py        # Gestión de catálogos
│   │   │   ├── conocimientos.py    # Inserción de conocimientos/skills
│   │   │   ├── direcciones.py      # Gestión de direcciones
│   │   │   ├── experiencia.py      # Inserción de experiencia laboral
│   │   │   ├── formacion.py        # Inserción de formación académica
│   │   │   ├── idiomas.py          # Inserción de idiomas
│   │   │   └── utils.py            # Utilidades comunes
│   │   ├── __init__.py
│   │   ├── db_config.py            # Configuración de base de datos
│   │   ├── db_inserter.py          # Orquestador de inserciones
│   │   ├── db_main.py              # Punto de entrada del módulo DB
│   │   ├── db_schema.py            # Definición de esquemas
│   │   └── db_validator.py         # Validación de datos
│   ├── __init__.py
│   ├── app.py                      # Aplicación principal
│   ├── azure_openai_client.py      # Cliente de Azure OpenAI
│   ├── cv_extractor.py             # Extractor de información de CVs
│   └── prompt_query.py             # Gestor de prompts y queries
│
├── storage/                        # Almacenamiento de datos procesados
│
├── .gitignore                      # Archivos y carpetas excluidos de Git
├── requirements.txt                # Dependencias del proyecto
├── .env.example                    # Plantilla de variables de entorno
└── main.py                         # Punto de entrada de la aplicación
```

## Descripción de Componentes

**Módulos Principales:**
- `config/`: Gestión centralizada de configuraciones y variables de entorno
- `src/`: Lógica de negocio y procesamiento de CVs con integración a Azure OpenAI
- `storage/`: Persistencia de CVs procesados en formato JSON
- `logs/`: Trazabilidad de operacions del sistema

**Archivos Clave:**
- `main.py`: Entry point de la aplicación
- `cv_extractor.py`: Core del procesamiento de documentos
- `azure_openai_client.py`: Integración con servicios de IAe
