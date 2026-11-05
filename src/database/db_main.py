#!/usr/bin/env python3
"""
Sistema de Procesamiento de CVs - Punto de Entrada Principal
Versión: 1.0.0
Descripción: Aplicación para cargar JSONs de CVs y volcarlos en base de datos SQL Server

Flujo principal:
1. Usuario selecciona archivo JSON
2. Sistema lee y valida el JSON
3. Sistema procesa e inserta datos en BD
4. Sistema muestra resultados

Autor: CV Processor Team
Fecha: 2024
"""

# ============================================================================
# IMPORTS - Organizados por categorías
# ============================================================================

# Standard library imports - Core
import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

# Standard library imports - GUI
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# Third-party imports
import pyodbc

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Project imports - Database modules
from src.database.db_config import DatabaseConfig
from src.database.db_inserter import CVInserter
from src.database.db_schema import SchemaManager

# Project imports - Configuration
from config.settings import (
    get_logger,
    STORAGE_DIR,
    IS_DEVELOPMENT,
    IS_PRODUCTION
)

# ============================================================================
# CONFIGURACIÓN DE LOGGING
# ============================================================================

# Logger principal de la aplicación
logger = get_logger(__name__)

# Configurar nivel de logging según ambiente
if IS_DEVELOPMENT:
    logging.getLogger().setLevel(logging.DEBUG)
else:
    logging.getLogger().setLevel(logging.INFO)

# ============================================================================
# CONSTANTES
# ============================================================================

APP_NAME = "CV Processor - Sistema de Gestión de Candidatos"
APP_VERSION = "1.0.0"
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 700
MIN_WIDTH = 800
MIN_HEIGHT = 600

# Colores de la interfaz
COLOR_BG = "#f0f0f0"
COLOR_HEADER = "#2c3e50"
COLOR_SUCCESS = "#27ae60"
COLOR_ERROR = "#e74c3c"
COLOR_WARNING = "#f39c12"
COLOR_INFO = "#3498db"


# ============================================================================
# CLASE PRINCIPAL DE LA APLICACIÓN
# ============================================================================

class CVProcessorApp:
    """
    Aplicación principal para procesamiento de CVs en formato JSON.

    Gestiona:
    - Interfaz gráfica de usuario
    - Selección y validación de archivos JSON
    - Procesamiento e inserción en base de datos
    - Visualización de resultados y estadísticas
    """

    def __init__(self, root: tk.Tk):
        """
        Inicializa la aplicación.

        Args:
            root: Ventana principal de Tkinter
        """
        self.root = root
        self.db_config = None
        self.cv_inserter = None
        self.schema_manager = None
        self.current_json_path = None
        self.current_json_data = None

        # Configurar ventana principal
        self._setup_window()

        # Inicializar componentes de BD
        self._initialize_database()

        # Crear interfaz
        self._create_interface()

        logger.info(f"{APP_NAME} v{APP_VERSION} iniciado correctamente")

    def _setup_window(self):
        """Configura la ventana principal de la aplicación."""
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)

        # Centrar ventana
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (WINDOW_WIDTH // 2)
        y = (self.root.winfo_screenheight() // 2) - (WINDOW_HEIGHT // 2)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

        # Configurar grid
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # Manejar cierre de ventana
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _initialize_database(self):
        """Inicializa los componentes de base de datos."""
        try:
            # Inicialización diferida - no conectar hasta que sea necesario
            self.db_config = None
            self.cv_inserter = None
            self.schema_manager = None
            logger.info("Componentes de BD pendientes de inicialización diferida")
        except Exception as e:
            logger.error(f"Error en configuración inicial: {e}")

    def _connect_database(self):
        """Conecta con la base de datos cuando sea necesario."""
        if self.db_config is None:
            try:
                self._update_status("Conectando con base de datos...")
                self.db_config = DatabaseConfig()
                self.cv_inserter = CVInserter(self.db_config)
                self.schema_manager = SchemaManager(self.db_config)
                self._log("SUCCESS", "✅ Conexión a BD establecida")
                self._update_status("Conectado a base de datos")
                return True
            except Exception as e:
                self._log("ERROR", f"❌ Error conectando BD: {e}")
                self._update_status("Error de conexión")
                messagebox.showerror(
                    "Error de Conexión",
                    f"No se pudo conectar con la base de datos:\n{str(e)}\n\n"
                    "Verifique la configuración en config/settings.py"
                )
                return False
        return True  # Ya conectado

    def _create_interface(self):
        """Crea la interfaz gráfica completa."""
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)

        # 1. HEADER
        self._create_header(main_frame)

        # 2. CONTROLES
        self._create_controls(main_frame)

        # 3. ÁREA DE INFORMACIÓN
        self._create_info_area(main_frame)

        # 4. ÁREA DE LOG
        self._create_log_area(main_frame)

        # 5. BARRA DE ESTADO
        self._create_status_bar(main_frame)

    # noinspection PyMethodMayBeStatic
    def _create_header(self, parent):
        """Crea el encabezado de la aplicación."""
        header_frame = tk.Frame(parent, bg=COLOR_HEADER, height=80)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_frame.grid_columnconfigure(0, weight=1)

        # Título
        title_label = tk.Label(
            header_frame,
            text=APP_NAME,
            font=("Arial", 18, "bold"),
            bg=COLOR_HEADER,
            fg="white"
        )
        title_label.grid(row=0, column=0, padx=20, pady=(10, 5))

        # Subtítulo
        subtitle_label = tk.Label(
            header_frame,
            text="Sistema de inserción de CVs desde JSON a Base de Datos",
            font=("Arial", 10),
            bg=COLOR_HEADER,
            fg="#ecf0f1"
        )
        subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 10))

    def _create_controls(self, parent):
        """Crea el área de controles principales."""
        control_frame = ttk.LabelFrame(parent, text="Controles", padding="10")
        control_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        control_frame.grid_columnconfigure(1, weight=1)

        # Botón seleccionar archivo
        self.btn_select = ttk.Button(
            control_frame,
            text="📁 Seleccionar JSON",
            command=self._select_json_file,
            width=20
        )
        self.btn_select.grid(row=0, column=0, padx=(0, 10))

        # Label archivo seleccionado
        self.lbl_file = ttk.Label(control_frame, text="No hay archivo seleccionado")
        self.lbl_file.grid(row=0, column=1, sticky="ew")

        # Botón procesar
        self.btn_process = ttk.Button(
            control_frame,
            text="⚙️ Procesar e Insertar",
            command=self._process_json,
            state="disabled",
            width=20
        )
        self.btn_process.grid(row=0, column=2, padx=(10, 0))

        # Separador
        ttk.Separator(control_frame, orient="horizontal").grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=10
        )

        # Botones adicionales
        buttons_frame = ttk.Frame(control_frame)
        buttons_frame.grid(row=2, column=0, columnspan=3)

        ttk.Button(
            buttons_frame,
            text="📊 Ver Estadísticas",
            command=self._show_statistics,
            width=18
        ).pack(side="left", padx=2)

        ttk.Button(
            buttons_frame,
            text="🔍 Verificar Catálogos",
            command=self._verify_catalogs,
            width=18
        ).pack(side="left", padx=2)

        ttk.Button(
            buttons_frame,
            text="🗄️ Probar Conexión BD",
            command=self._test_connection,
            width=18
        ).pack(side="left", padx=2)

        ttk.Button(
            buttons_frame,
            text="🔄 Reiniciar Stats",
            command=self._reset_statistics,
            width=18
        ).pack(side="left", padx=2)

    def _create_info_area(self, parent):
        """Crea el área de información del JSON."""
        self.info_frame = ttk.LabelFrame(parent, text="Información del JSON", padding="10")
        self.info_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        self.info_frame.grid_columnconfigure(0, weight=1)
        self.info_frame.grid_rowconfigure(0, weight=1)

        # Área de texto para mostrar JSON
        self.json_text = scrolledtext.ScrolledText(
            self.info_frame,
            wrap=tk.WORD,
            height=10,
            font=("Consolas", 9)
        )
        self.json_text.grid(row=0, column=0, sticky="nsew")
        self.json_text.config(state="disabled")

    def _create_log_area(self, parent):
        """Crea el área de logs."""
        log_frame = ttk.LabelFrame(parent, text="Registro de Actividad", padding="10")
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 10))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        # Área de texto para logs
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            height=8,
            font=("Consolas", 9),
            bg="#2b2b2b",
            fg="#ffffff"
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        # Tags para colores
        self.log_text.tag_config("SUCCESS", foreground="#27ae60")
        self.log_text.tag_config("ERROR", foreground="#e74c3c")
        self.log_text.tag_config("WARNING", foreground="#f39c12")
        self.log_text.tag_config("INFO", foreground="#3498db")

    def _create_status_bar(self, parent):
        """Crea la barra de estado."""
        self.status_bar = ttk.Label(
            parent,
            text="✅ Sistema listo",
            relief="sunken",
            anchor="w"
        )
        self.status_bar.grid(row=4, column=0, sticky="ew")

    def _select_json_file(self):
        """Permite al usuario seleccionar un archivo JSON."""
        file_path = filedialog.askopenfilename(
            title="Seleccionar archivo JSON de CV",
            filetypes=[
                ("Archivos JSON", "*.json"),
                ("Todos los archivos", "*.*")
            ],
            initialdir=str(STORAGE_DIR) if STORAGE_DIR.exists() else None
        )

        if file_path:
            self._load_json_file(file_path)

    def _load_json_file(self, file_path: str):
        """
        Carga y valida un archivo JSON.

        Args:
            file_path: Ruta del archivo JSON
        """
        try:
            # Leer archivo
            with open(file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            # Validar estructura básica
            if not self._validate_json_structure(json_data):
                return

            # Guardar datos
            self.current_json_path = file_path
            self.current_json_data = json_data

            # Actualizar interfaz
            filename = Path(file_path).name
            self.lbl_file.config(text=f"📄 {filename}")
            self.btn_process.config(state="normal")

            # Mostrar contenido del JSON
            self._display_json_content(json_data)

            # Log
            self._log("SUCCESS", f"✅ JSON cargado: {filename}")
            self._update_status(f"Archivo listo para procesar: {filename}")

        except json.JSONDecodeError as e:
            self._log("ERROR", f"❌ Error de formato JSON: {e}")
            messagebox.showerror("Error JSON", f"El archivo no es un JSON válido:\n{e}")
        except Exception as e:
            self._log("ERROR", f"❌ Error cargando archivo: {e}")
            messagebox.showerror("Error", f"No se pudo cargar el archivo:\n{e}")

    def _validate_json_structure(self, json_data: Dict) -> bool:
        """
        Valida que el JSON tenga la estructura esperada.

        Args:
            json_data: Datos del JSON

        Returns:
            True si la estructura es válida
        """
        recommended_keys = [
            'experiencia_profesional',
            'formacion',
            'idiomas',
            'habilidades'
        ]

        # Verificar clave mínima
        if 'datos_contacto' not in json_data:
            self._log("ERROR", "❌ JSON inválido: falta 'datos_contacto'")
            messagebox.showerror(
                "JSON Inválido",
                "El JSON debe contener al menos 'datos_contacto'"
            )
            return False

        # Advertir sobre claves faltantes
        missing_keys = [k for k in recommended_keys if k not in json_data]
        if missing_keys:
            self._log("WARNING", f"⚠️ Claves recomendadas faltantes: {missing_keys}")

        # Mostrar claves encontradas
        found_keys = list(json_data.keys())
        self._log("INFO", f"📋 Claves encontradas: {found_keys}")

        return True

    def _display_json_content(self, json_data: Dict):
        """
        Muestra el contenido del JSON en el área de información.

        Args:
            json_data: Datos del JSON
        """
        self.json_text.config(state="normal")
        self.json_text.delete(1.0, tk.END)

        # Crear resumen del contenido
        summary = "RESUMEN DEL JSON:\n" + "=" * 50 + "\n\n"

        # Datos de contacto
        if 'datos_contacto' in json_data:
            contacto = json_data['datos_contacto']
            summary += "📝 DATOS DE CONTACTO:\n"
            summary += f"  • Nombre: {contacto.get('nombre_completo', 'N/A')}\n"
            summary += f"  • Email: {contacto.get('email', 'N/A')}\n"
            summary += f"  • Teléfono: {contacto.get('telefono', 'N/A')}\n"
            summary += f"  • DNI: {contacto.get('dni', 'N/A')}\n"

            # Campos adicionales nuevos si existen
            if 'fecha_nacimiento' in contacto:
                summary += f"  • Fecha Nacimiento: {contacto.get('fecha_nacimiento', 'N/A')}\n"
            if 'nacionalidad' in contacto:
                summary += f"  • Nacionalidad: {contacto.get('nacionalidad', 'N/A')}\n"
            if 'provincia' in contacto:
                summary += f"  • Provincia: {contacto.get('provincia', 'N/A')}\n"
            if 'localidad' in contacto:
                summary += f"  • Localidad: {contacto.get('localidad', 'N/A')}\n"
            summary += "\n"

        # Experiencia
        if 'experiencia_profesional' in json_data:
            exp_count = len(json_data['experiencia_profesional'])
            summary += f"💼 EXPERIENCIAS: {exp_count} registros\n"
            for i, exp in enumerate(json_data['experiencia_profesional'][:3], 1):
                summary += f"  {i}. {exp.get('puesto', 'N/A')} en {exp.get('empresa', 'N/A')}\n"
            if exp_count > 3:
                summary += f"  ... y {exp_count - 3} más\n"
            summary += "\n"

        # Formación
        if 'formacion' in json_data:
            form_count = len(json_data['formacion'])
            summary += f"🎓 FORMACIÓN: {form_count} registros\n"
            for i, form in enumerate(json_data['formacion'][:3], 1):
                summary += f"  {i}. {form.get('titulo', 'N/A')} - {form.get('institucion', 'N/A')}\n"
            if form_count > 3:
                summary += f"  ... y {form_count - 3} más\n"
            summary += "\n"

        # Idiomas
        if 'idiomas' in json_data:
            idiomas = json_data['idiomas']
            summary += f"🌐 IDIOMAS: {len(idiomas)} registros\n"
            for idioma in idiomas:
                summary += f"  • {idioma.get('idioma', 'N/A')} - {idioma.get('nivel', 'N/A')}\n"
            summary += "\n"

        # Habilidades
        if 'habilidades' in json_data:
            hab = json_data['habilidades']
            summary += "🔧 HABILIDADES:\n"
            for categoria, items in hab.items():
                if items:
                    summary += f"  • {categoria}: {len(items)} items\n"
                    summary += f"    {', '.join(items[:5])}"
                    if len(items) > 5:
                        summary += f" ... (+{len(items) - 5})"
                    summary += "\n"

        summary += "\n" + "=" * 50 + "\n"
        summary += "JSON completo disponible abajo:\n\n"

        # Agregar JSON formateado
        json_formatted = json.dumps(json_data, indent=2, ensure_ascii=False)

        self.json_text.insert(1.0, summary + json_formatted)
        self.json_text.config(state="disabled")

    def _process_json(self):
        """Procesa el JSON seleccionado e inserta en BD."""
        if not self.current_json_data:
            messagebox.showwarning("Sin archivo", "Por favor selecciona un archivo JSON primero")
            return

        # Conectar si no está conectado
        if not self._connect_database():
            return

        # Confirmar acción
        response = messagebox.askyesno(
            "Confirmar Procesamiento",
            "¿Deseas procesar e insertar este CV en la base de datos?"
        )

        if not response:
            return

        # Deshabilitar botones durante procesamiento
        self.btn_process.config(state="disabled")
        self.btn_select.config(state="disabled")
        self._update_status("Procesando...")

        try:
            # Procesar con el insertor
            self._log("INFO", "Iniciando procesamiento del CV...")

            filename = Path(self.current_json_path).name
            result = self.cv_inserter.insert_cv_data(
                self.current_json_data,
                filename
            )

            # Procesar resultado
            if result['status'] == 'exitoso':
                self._handle_success(result)
            elif result['status'] == 'duplicado':
                self._handle_duplicate(result)
            else:
                self._handle_error(result)

        except Exception as e:
            logger.error(f"Error procesando JSON: {e}")
            self._log("ERROR", f"❌ Error inesperado: {e}")
            messagebox.showerror("Error", f"Error procesando el archivo:\n{e}")

        finally:
            # Rehabilitar botones
            self.btn_process.config(state="normal")
            self.btn_select.config(state="normal")

    def _handle_success(self, result: Dict):
        """Maneja el resultado exitoso."""
        candidato_id = result['candidato_id']
        warnings = result.get('warnings', [])

        self._log("SUCCESS", f"✅ CV insertado exitosamente - ID: {candidato_id}")

        # Mostrar warnings si hay
        if warnings:
            self._log("WARNING", "⚠️ Advertencias durante el procesamiento:")
            for warning in warnings:
                self._log("WARNING", f"  • {warning}")

        # Mensaje de éxito
        msg = f"CV procesado exitosamente!\n\n"
        msg += f"ID del candidato: {candidato_id}\n"
        if warnings:
            msg += f"\nAdvertencias:\n"
            for w in warnings:
                msg += f"• {w}\n"

        messagebox.showinfo("Éxito", msg)
        self._update_status(f"CV insertado correctamente - ID: {candidato_id}")

    def _handle_duplicate(self, result: Dict):
        """Maneja el caso de duplicado."""
        candidato_id = result['candidato_id']

        self._log("WARNING", f"⚠️ Candidato duplicado detectado - ID existente: {candidato_id}")

        messagebox.showwarning(
            "Candidato Duplicado",
            f"El candidato ya existe en la base de datos.\n\nID existente: {candidato_id}"
        )

        self._update_status(f"Candidato duplicado - ID: {candidato_id}")

    def _handle_error(self, result: Dict):
        """Maneja errores en el procesamiento."""
        error = result.get('error', 'Error desconocido')

        self._log("ERROR", f"❌ Error al procesar CV: {error}")

        messagebox.showerror(
            "Error de Procesamiento",
            f"No se pudo procesar el CV:\n\n{error}"
        )

        self._update_status("Error en el procesamiento")

    def _show_statistics(self):
        """Muestra estadísticas del procesamiento."""
        if not self._connect_database():
            return

        stats = self.cv_inserter.get_stats()

        msg = "📊 ESTADÍSTICAS DE PROCESAMIENTO\n"
        msg += "=" * 40 + "\n\n"
        msg += f"✅ Candidatos insertados: {stats['candidatos_insertados']}\n"
        msg += f"⚠️ Duplicados detectados: {stats['duplicados_detectados']}\n"
        msg += f"❌ Errores: {stats['errores']}\n"

        if stats['warnings']:
            msg += f"\n📝 Últimas advertencias:\n"
            for warning in stats['warnings'][-5:]:  # Últimas 5
                msg += f"  • {warning}\n"

        messagebox.showinfo("Estadísticas", msg)
        self._log("INFO", "Estadísticas mostradas")

    def _reset_statistics(self):
        """Reinicia las estadísticas."""
        if not self._connect_database():
            return

        response = messagebox.askyesno(
            "Reiniciar Estadísticas",
            "¿Deseas reiniciar todas las estadísticas?"
        )

        if response:
            self.cv_inserter.reset_stats()
            self._log("INFO", "📊 Estadísticas reiniciadas")
            self._update_status("Estadísticas reiniciadas")

    def _verify_catalogs(self):
        """Verifica el estado de los catálogos."""
        self._log("INFO", "Verificando catálogos...")

        if not self._connect_database():
            return

        catalog_stats = self.schema_manager.get_catalog_stats()

        msg = "🔍 ESTADO DE CATÁLOGOS\n"
        msg += "=" * 40 + "\n\n"

        for catalog, count in catalog_stats.items():
            if count >= 0:
                status = "✅" if count > 0 else "⚠️"
                msg += f"{status} {catalog}: {count} registros\n"
            else:
                msg += f"❌ {catalog}: No existe\n"

        messagebox.showinfo("Estado de Catálogos", msg)
        self._log("INFO", "Verificación de catálogos completada")

    def _test_connection(self):
        """Prueba la conexión a la base de datos."""
        self._log("INFO", "Probando conexión a BD...")

        if not self._connect_database():
            return

        if self.db_config.test_connection():
            server_info = self.db_config.get_server_info()

            msg = "✅ CONEXIÓN EXITOSA\n"
            msg += "=" * 40 + "\n\n"
            msg += f"Servidor: {server_info.get('server_name', 'N/A')}\n"
            msg += f"Base de datos: {server_info.get('database', 'N/A')}\n"
            msg += f"Usuario: {server_info.get('user', 'N/A')}\n"

            messagebox.showinfo("Conexión BD", msg)
            self._log("SUCCESS", "✅ Conexión a BD verificada")
        else:
            messagebox.showerror(
                "Error de Conexión",
                "No se pudo conectar con la base de datos"
            )
            self._log("ERROR", "❌ Error de conexión a BD")

    def _log(self, level: str, message: str):
        """
        Agrega un mensaje al área de log.

        Args:
            level: Nivel del mensaje (INFO, SUCCESS, WARNING, ERROR)
            message: Mensaje a mostrar
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"

        self.log_text.insert(tk.END, log_entry, level)
        self.log_text.see(tk.END)

        # También al logger de Python
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)

    def _update_status(self, message: str):
        """Actualiza la barra de estado."""
        self.status_bar.config(text=f"📍 {message}")

    def _on_closing(self):
        """Maneja el cierre de la aplicación."""
        if messagebox.askokcancel("Salir", "¿Deseas cerrar la aplicación?"):
            try:
                if self.db_config:
                    self.db_config.close()
                logger.info("Aplicación cerrada correctamente")
            except:
                pass
            finally:
                self.root.destroy()


# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================

def main():
    """Función principal de la aplicación."""
    print(f"\n{'=' * 60}")
    print(f"{APP_NAME}")
    print(f"Versión: {APP_VERSION}")
    print(f"{'=' * 60}\n")

    try:
        # Crear ventana principal
        root = tk.Tk()

        # Estilo para widgets ttk
        style = ttk.Style()
        style.theme_use('clam')  # O 'vista', 'xpnative' en Windows

        # Crear aplicación
        CVProcessorApp(root)

        # Iniciar loop principal
        root.mainloop()

    except Exception as e:
        logger.error(f"Error fatal en la aplicación: {e}")
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    main()