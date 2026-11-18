#!/usr/bin/env python3
"""
Utilidades compartidas para el scraper de DeathGrind.club
"""

import importlib.util
import os
import re
import sys
import time
import random
from pathlib import Path

import requests

from modules.logger import setup_logger

logger = setup_logger(__name__)

# =============================================================================
# Constantes centralizadas
# =============================================================================

# URLs
BASE_URL = "https://deathgrind.club"
API_URL = f"{BASE_URL}/api"

# Paths de datos
DATA_DIR = "data"
BANDAS_FILE = f"{DATA_DIR}/bandas.json"
REPERTORIO_FILE = f"{DATA_DIR}/repertorio.json"
REPERTORIO_FILTRADO_FILE = f"{DATA_DIR}/repertorio_filtrado.json"
REPERTORIO_CON_LINKS_FILE = f"{DATA_DIR}/repertorio_con_links.json"
LINKS_FILE = f"{DATA_DIR}/links_descarga.txt"
DETALLE_FILE = f"{DATA_DIR}/discografia_detalle.txt"
MAINSTREAM_FILE = f"{DATA_DIR}/releases_mainstream.txt"
DESCARGADOS_FILE = f"{DATA_DIR}/descargados.txt"
FALLIDOS_FILE = f"{DATA_DIR}/fallidos_bandas.txt"
MEGA_PENDIENTES_FILE = f"{DATA_DIR}/mega_pendientes.json"

# Rate limiting
DELAY_BASE_429 = 30
MAX_BACKOFF_429 = 300

# HTTP
DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) Chrome/131.0.0.0 Safari/537.36"
DEFAULT_UUID = "12345"

# El login valida el token impreso en la página de sign-in, no el de la cookie (si no, 419)
P_CSRF_DE_LA_PAGINA = re.compile(r'"csrfToken"\s*:\s*"([^"]+)"')

# click-auto-editor guarda el registro de los álbumes ya publicados en el canal
DIR_CLICK_AUTO_EDITOR = Path.home() / "Desktop" / "click-auto-editor"
# ... y la lista de bandas que no quiere ver más: una por línea, sin las vacías ni las que empiezan con #
LISTA_NEGRA_BANDAS = "lista_negra_bandas.txt"


# =============================================================================
# Funciones compartidas
# =============================================================================

def cargar_env():
    """Carga variables de entorno desde .env"""
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                # Ignorar vacías y comentarios
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip()
                    # Quitar comillas envolventes
                    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                        val = val[1:-1]
                    os.environ[key] = val


def token_csrf_de_la_pagina(session, html):
    """El token de window.__USER_DATA__ en la página; el de la cookie si no está."""
    coincidencia = P_CSRF_DE_LA_PAGINA.search(html or "")
    return coincidencia.group(1) if coincidencia else session.cookies.get_dict().get("csrfToken", "")


def crear_sesion_autenticada(max_retries=3):
    """Login con retry y retorna sesión autenticada"""
    email = os.environ.get('DEATHGRIND_EMAIL')
    password = os.environ.get('DEATHGRIND_PASSWORD')

    if not email or not password:
        raise ValueError("Faltan credenciales en .env")

    for intento in range(max_retries):
        try:
            session = requests.Session()
            session.headers.update({
                'User-Agent': DEFAULT_USER_AGENT,
                'Accept': 'application/json',
            })

            pagina = session.get(f"{BASE_URL}/auth/sign-in")
            csrf_token = token_csrf_de_la_pagina(session, pagina.text)

            login_data = {"login": email, "password": password}
            headers = {'x-csrf-token': csrf_token, 'x-uuid': DEFAULT_UUID}
            response = session.post(f"{API_URL}/auth/login", json=login_data, headers=headers)

            if response.status_code in [200, 202]:
                cookies = session.cookies.get_dict()
                csrf_token = cookies.get('csrfToken', '')
                session.headers.update({'x-csrf-token': csrf_token, 'x-uuid': DEFAULT_UUID})
                return session

            if response.status_code == 429:
                wait = (intento + 1) * 10
                print(f"   ⚠️ Rate limited, esperando {wait}s...")
                time.sleep(wait)
                continue

            raise ConnectionError(f"Error de login: {response.status_code}")

        except requests.exceptions.RequestException:
            if intento < max_retries - 1:
                time.sleep(5)
                continue
            raise

    raise ConnectionError("No se pudo conectar después de varios intentos")


def cargar_sellos_blacklist():
    """Carga lista de sellos problemáticos"""
    sellos = set()
    if os.path.exists('lista_sello.txt'):
        with open('lista_sello.txt', 'r', encoding='utf-8') as f:
            for line in f:
                sello = line.strip().lower()
                if sello:
                    sellos.add(sello)
    return sellos


def cargar_publicados():
    """El registro de álbumes ya publicados de click-auto-editor, o None si no está su código.

    Usa su propio registro_publicados.py para que la clave "banda|álbum" sea la misma.
    La carpeta sale de CLICK_AUTO_EDITOR_DIR (por defecto ~/Desktop/click-auto-editor).

    Si ese código está pero no carga, frena con un solo mensaje (sin traceback): devolver None
    haría pedir los links de todo, también de lo ya publicado, y eso gasta créditos de descarga.
    """
    base = _dir_click_auto_editor()
    codigo = base / "registro_publicados.py"
    if not codigo.is_file():
        return None
    try:
        return _cargar_modulo(codigo, "registro_publicados").leer(base / "data" / "agente" / "ya_publicados.tsv")
    except (SyntaxError, ImportError, AttributeError, OSError) as exc:
        sys.exit(f"❌ No se pudo cargar {codigo} ({type(exc).__name__}: {exc}). "
                 "Se frena el paso de links para no gastar créditos de descarga en lo ya "
                 "publicado; arregla ese archivo y vuelve a correr.")


def cargar_cola():
    """Busca un release en las carpetas que click-auto-editor tiene en cola, o None si no está su código.

    Devuelve una función: nombre "Banda - Álbum" -> la carpeta de la cola con ese álbum, o None.
    Las carpetas son las de origen del render (01_limpieza_de_impurezas, Album/, EP/),
    Renderizando/, upload_video/ y Censura/, como las define su config.py, y la clave
    "banda|álbum" es la de su registro_publicados.py: la misma que usa el servicio.

    Una carpeta que no se puede leer (el SSD sin montar) se avisa y no cuenta. Si ese código
    está pero no carga, frena con un solo mensaje, igual que cargar_publicados.
    """
    base = _dir_click_auto_editor()
    config_py, registro_py = base / "config.py", base / "registro_publicados.py"
    if not (config_py.is_file() and registro_py.is_file()):
        return None
    codigo = config_py
    try:
        config = _cargar_modulo(config_py, "config_click_auto_editor")
        carpetas = [*config.DIRS_ORIGEN_RENDER, config.DIR_RENDERIZANDO, config.DIR_UPLOAD, config.DIR_CENSURA]
        codigo = registro_py
        clave = _cargar_modulo(registro_py, "registro_publicados").clave
    except (SyntaxError, ImportError, AttributeError, OSError) as exc:
        sys.exit(f"❌ No se pudo cargar {codigo} ({type(exc).__name__}: {exc}). "
                 "Se frena el paso de links para no gastar créditos de descarga en lo que ya "
                 "está en la cola; arregla ese archivo y vuelve a correr.")
    en_cola = {}
    for carpeta in carpetas:
        try:
            albumes = sorted(c for c in Path(carpeta).iterdir() if c.is_dir())
        except OSError as exc:
            print(f"⚠️ No pude leer {carpeta} ({type(exc).__name__}): lo que esté ahí no se saltea")
            continue
        for album in albumes:
            k = clave(album.name)
            if k:
                en_cola.setdefault(k, album)
    return lambda nombre: en_cola.get(clave(nombre))


def cargar_bandas_bloqueadas():
    """Las bandas que click-auto-editor no quiere ver más, o None si no está su código.

    Devuelve una función: nombre de banda -> True si está en su lista_negra_bandas.txt. El archivo
    se lee en cada corrida: sin él no se bloquea nada. Es una comparación por nombre de banda, no
    por banda real: una banda homónima se bloquea también.

    La clave es la banda de la "banda|álbum" de su registro_publicados.clave, la misma que usa el
    servicio, así "PROPHECY", "Prophecy" y "Próphecy" son la misma línea. Un nombre sin letras ni
    números no tiene clave: no se bloquea ni bloquea a otro.

    Si el código está pero no carga, o la lista está pero no se puede leer (por ejemplo, guardada
    en latin-1), frena con un solo mensaje (sin traceback), igual que cargar_publicados: seguir
    gastaría créditos de descarga en bandas que no se quieren.
    """
    base = _dir_click_auto_editor()
    registro_py = base / "registro_publicados.py"
    if not registro_py.is_file():
        return None
    lista = base / LISTA_NEGRA_BANDAS
    codigo = registro_py
    try:
        clave = _cargar_modulo(registro_py, "registro_publicados").clave

        def clave_de_banda(nombre):
            completa = clave(f"{nombre or ''} - x")
            return completa.split("|")[0] if completa else None

        bloqueadas = set()
        if lista.is_file():
            codigo = lista
            for linea in lista.read_text(encoding="utf-8").splitlines():
                linea = linea.strip()
                if linea and not linea.startswith("#"):
                    bloqueadas.add(clave_de_banda(linea))
            bloqueadas.discard(None)
    except (SyntaxError, ImportError, AttributeError, OSError, UnicodeDecodeError) as exc:
        sys.exit(f"❌ No se pudo cargar {codigo} ({type(exc).__name__}: {exc}). "
                 "Se frena para no pedir links ni bajar bandas de la lista negra de "
                 "click-auto-editor; arregla ese archivo y vuelve a correr.")
    return lambda nombre: clave_de_banda(nombre) in bloqueadas


def _dir_click_auto_editor():
    """La carpeta de click-auto-editor: CLICK_AUTO_EDITOR_DIR, o ~/Desktop/click-auto-editor."""
    return Path(os.environ.get("CLICK_AUTO_EDITOR_DIR") or DIR_CLICK_AUTO_EDITOR).expanduser()


def _cargar_modulo(codigo, nombre):
    spec = importlib.util.spec_from_file_location(nombre, codigo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def delay_con_jitter(base, factor=0.3):
    """Delay con variación aleatoria para evitar detección de bots"""
    jitter = base * random.uniform(-factor, factor)
    time.sleep(base + jitter)


# =============================================================================
# Detección de recursos del sistema
# =============================================================================

def detectar_workers_optimos():
    """
    Detecta automáticamente el número óptimo de workers
    basado en CPU y memoria disponible
    """
    cpu_count = os.cpu_count() or 4

    # Intentar detectar memoria
    try:
        import psutil
        mem_gb = psutil.virtual_memory().total / (1024 ** 3)

        # Más conservador para navegadores (usan mucha RAM)
        if mem_gb >= 32:
            workers_mem = 12
        elif mem_gb >= 16:
            workers_mem = 8
        elif mem_gb >= 8:
            workers_mem = 5
        elif mem_gb >= 4:
            workers_mem = 3
        else:
            workers_mem = 2

    except ImportError:
        # Sin psutil, estimar por CPU
        workers_mem = min(cpu_count, 6)

    # Usar el menor entre CPU y memoria
    workers = min(cpu_count - 1, workers_mem)  # Dejar 1 CPU libre
    workers = max(2, workers)  # Mínimo 2

    return workers


def detectar_workers_api():
    """
    Workers para llamadas API - más conservador para evitar rate limiting
    """
    cpu_count = os.cpu_count() or 4
    # Más conservador para evitar 429
    return min(cpu_count, 10)


def mostrar_recursos():
    """Muestra los recursos detectados"""
    cpu_count = os.cpu_count() or 4

    try:
        import psutil
        mem = psutil.virtual_memory()
        mem_gb = mem.total / (1024 ** 3)
        mem_disp = mem.available / (1024 ** 3)
        logger.info(f"   CPU: {cpu_count} cores")
        logger.info(f"   RAM: {mem_gb:.1f} GB total, {mem_disp:.1f} GB disponible")
    except ImportError:
        logger.info(f"   CPU: {cpu_count} cores")
        logger.info(f"   RAM: (instala psutil para detectar)")

    workers_browser = detectar_workers_optimos()
    workers_api = detectar_workers_api()

    logger.info(f"   Workers browser: {workers_browser}")
    logger.info(f"   Workers API: {workers_api}")

    return workers_browser, workers_api
