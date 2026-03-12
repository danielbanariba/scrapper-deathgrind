#!/usr/bin/env python3
"""
Utilidades compartidas para el scraper de DeathGrind.club
"""

import os
import time
import random
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

            session.get(f"{BASE_URL}/auth/sign-in")
            cookies = session.cookies.get_dict()
            csrf_token = cookies.get('csrfToken', '')

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
