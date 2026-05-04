#!/usr/bin/env python3
"""
Módulo: Descarga, extrae y organiza los releases
Entrada: data/repertorio_con_links.json
Salida: Archivos organizados en el directorio destino

Soporta:
  - Mega.nz
  - Mediafire
  - Google Drive
  - Yandex Disk
  - pCloud
  - Mail.ru Cloud
  - Workupload
  - Otros enlaces directos
"""

import os
import json
import time
import re
import shutil
import subprocess
import tempfile
import zipfile
import html as html_lib
import threading
import hashlib
import requests
from requests.utils import requote_uri
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs, urlencode, urlunparse, urljoin

from modules.utils import delay_con_jitter
from modules.logger import setup_logger, log_context

logger = setup_logger(__name__)

# Configuración
INPUT_FILE = "data/repertorio_con_links.json"
DESTINO_BASE = os.getenv('DESTINO_BASE', "/mnt/Entretenimiento/01_edicion_automatizada/01_limpieza_de_impurezas")
TEMP_DIR = "/tmp/deathgrind_downloads"
DESCARGADOS_FILE = "data/descargados.txt"  # Lista de releases ya descargados
FALLIDOS_FILE = "data/fallidos_bandas.txt"  # Bandas con links fallidos
MEGA_PENDIENTES_FILE = "data/mega_pendientes.json"
MEGA_COOLDOWN_FILE = "data/mega_cooldown.txt"

# Configuración de rate limiting
DELAY_ENTRE_DESCARGAS = 2.0  # Segundos entre cada descarga
DELAY_REINTENTO_DESCARGA = 10.0  # Segundos entre reintentos por descarga parcial
MAX_REINTENTOS_PARCIALES = 5  # 0 = infinito, reintentos si hubo descarga parcial

# Configuración de Mega
MEGA_TIMEOUT_SECONDS = int(os.getenv('MEGA_TIMEOUT_SECONDS', '240'))
# Cooldown largo para rate-limit explícito de Mega (bandwidth/quota)
MEGA_COOLDOWN_SECONDS = int(os.getenv('MEGA_COOLDOWN_SECONDS', '1200'))
# Cooldown corto para timeouts: pueden ser red/archivo grande, no rate-limit real
MEGA_TIMEOUT_COOLDOWN_SECONDS = int(os.getenv('MEGA_TIMEOUT_COOLDOWN_SECONDS', '300'))


class MegaCooldownManager:
    """Thread-safe Mega cooldown manager con persistencia a disco"""
    def __init__(self):
        self._lock = threading.Lock()
        self._until = 0
        self._loaded = False

    def _load_from_disk(self):
        """Carga cooldown desde disco (lazy, una sola vez)."""
        if self._loaded:
            return
        self._loaded = True
        try:
            if os.path.exists(MEGA_COOLDOWN_FILE):
                with open(MEGA_COOLDOWN_FILE, 'r') as f:
                    ts = float(f.read().strip())
                if ts > time.time():
                    self._until = ts
                else:
                    # Expirado, limpiar archivo
                    os.remove(MEGA_COOLDOWN_FILE)
        except (ValueError, OSError):
            pass

    def _save_to_disk(self):
        """Guarda timestamp de cooldown a disco."""
        try:
            os.makedirs(os.path.dirname(MEGA_COOLDOWN_FILE), exist_ok=True)
            with open(MEGA_COOLDOWN_FILE, 'w') as f:
                f.write(str(self._until))
        except OSError:
            pass

    def is_active(self):
        with self._lock:
            self._load_from_disk()
            return self._until > 0 and time.time() < self._until

    def remaining(self):
        with self._lock:
            self._load_from_disk()
            if self._until == 0 or time.time() >= self._until:
                return 0
            return int(self._until - time.time())

    def activate(self, seconds=None):
        """Activa cooldown. Si `seconds` es None usa el cooldown largo."""
        duration = seconds if seconds is not None else MEGA_COOLDOWN_SECONDS
        with self._lock:
            # No achicamos un cooldown ya activo: si había uno largo, lo respetamos
            new_until = time.time() + duration
            if new_until > self._until:
                self._until = new_until
                self._save_to_disk()


mega_cooldown = MegaCooldownManager()

# Extensiones de archivos comprimidos
EXTENSIONES_COMPRIMIDAS = {'.zip', '.rar', '.7z', '.tar', '.tar.gz', '.tgz', '.tar.bz2'}

# Extensiones de audio (para verificar extracción exitosa)
EXTENSIONES_AUDIO = {'.mp3', '.flac', '.wav', '.ogg', '.m4a', '.aac', '.wma'}

# Prioridad de links por tipo de servicio (menor = mejor)
LINK_PRIORITY = {
    'direct': 1, 'dropbox': 2, 'mediafire': 2, 'archive': 2, 'vkdoc': 3,
    'gdrive': 3, 'yandex': 3, 'pcloud': 3, 'mailru': 3, 'onedrive': 3,
    'workupload': 4, 'icedrive': 4, 'krakenfiles': 4, 'gofile': 4,
    'wetransfer': 5, 'mega': 6, 'dead': 99,
}

# User-Agent consistente para evitar bloqueos básicos
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/131.0.0.0 Safari/537.36',
    'Accept': '*/*',
}

_thread_local = threading.local()


def _get_session():
    """Sesión HTTP con connection pooling por thread."""
    if not hasattr(_thread_local, 'session'):
        s = requests.Session()
        s.headers.update(DEFAULT_HEADERS)
        _thread_local.session = s
    return _thread_local.session


def _close_session():
    """Cierra la sesión HTTP del thread actual."""
    if hasattr(_thread_local, 'session'):
        _thread_local.session.close()
        del _thread_local.session


def cargar_repertorio(input_file=INPUT_FILE):
    """Carga el repertorio con links"""
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"No existe {input_file}")

    with open(input_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def _parse_year(value):
    """Convierte year a int seguro para ordenar"""
    try:
        if value is None:
            return 0
        if isinstance(value, int):
            return value
        s = str(value).strip()
        if not s:
            return 0
        return int(s[:4])
    except (ValueError, TypeError):
        return 0


def cargar_descargados(descargados_file=DESCARGADOS_FILE):
    """Carga la lista de releases ya descargados (solo post_id)"""
    descargados = set()
    if os.path.exists(descargados_file):
        with open(descargados_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Formato: post_id|band|album
                    parts = line.split('|')
                    if parts:
                        descargados.add(parts[0])
    return descargados


def guardar_descargado(post_id, band, album, descargados_file=DESCARGADOS_FILE):
    """Agrega un release a la lista de descargados"""
    os.makedirs(os.path.dirname(descargados_file), exist_ok=True)

    # Si el archivo no existe, crear con encabezado
    if not os.path.exists(descargados_file):
        with open(descargados_file, 'w', encoding='utf-8') as f:
            f.write("# Releases descargados exitosamente\n")
            f.write("# Formato: post_id|band|album\n")
            f.write("# No editar manualmente\n\n")

    with open(descargados_file, 'a', encoding='utf-8') as f:
        f.write(f"{post_id}|{band}|{album}\n")


def release_ya_descargado(release, descargados):
    """Verifica si un release ya fue descargado (O(1) lookup)"""
    post_id = str(release.get('post_id', ''))
    return post_id in descargados


def cargar_fallidos(fallidos_file=FALLIDOS_FILE):
    """Carga la lista de posts con fallos previos (por post_id, con expiración 30 días)"""
    from datetime import datetime, timedelta
    fallidos = set()
    lineas_vigentes = []
    hay_expirados = False

    if os.path.exists(fallidos_file):
        with open(fallidos_file, 'r', encoding='utf-8') as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith('#'):
                    lineas_vigentes.append(line)
                    continue
                parts = raw.split('|')
                # Formato nuevo: post_id|band|album|fecha|motivo
                # Formato viejo: band_id|band|post_id|album|fecha|motivo
                # Detectar por cantidad de campos y posición de fecha
                fecha_str = None
                post_id = None
                if len(parts) >= 5:
                    # Formato nuevo: parts[3] es fecha
                    if _es_fecha(parts[3]):
                        post_id = parts[0]
                        fecha_str = parts[3]
                    # Formato viejo: parts[4] es fecha
                    elif len(parts) >= 6 and _es_fecha(parts[4]):
                        post_id = parts[2]  # post_id está en posición 2
                        fecha_str = parts[4]
                    else:
                        post_id = parts[0]
                elif len(parts) >= 1 and parts[0].isdigit():
                    post_id = parts[0]

                # Filtrar entradas expiradas (>30 días)
                if fecha_str and post_id:
                    try:
                        fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
                        if datetime.now() - fecha > timedelta(days=30):
                            hay_expirados = True
                            continue
                    except ValueError:
                        pass

                if post_id:
                    fallidos.add(post_id)
                lineas_vigentes.append(line)

        # Reescribir archivo sin entradas expiradas
        if hay_expirados:
            with open(fallidos_file, 'w', encoding='utf-8') as f:
                for line in lineas_vigentes:
                    f.write(line if line.endswith('\n') else line + '\n')

    return fallidos


def _es_fecha(s):
    """Verifica si un string tiene formato YYYY-MM-DD"""
    if len(s) != 10:
        return False
    try:
        from datetime import datetime
        datetime.strptime(s, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def guardar_fallido(release, fallidos, fallidos_file=FALLIDOS_FILE, motivo="Todos los links fallaron"):
    """Agrega un post a la lista de fallidos (por post_id)"""
    post_id = str(release.get('post_id', '')).strip()
    if not post_id:
        return

    if post_id in fallidos:
        return

    os.makedirs(os.path.dirname(fallidos_file), exist_ok=True)

    # Si el archivo no existe, crear con encabezado
    if not os.path.exists(fallidos_file):
        with open(fallidos_file, 'w', encoding='utf-8') as f:
            f.write("# Posts con links fallidos\n")
            f.write("# Formato: post_id|band|album|fecha|motivo\n")
            f.write("\n")

    band = release.get('band', 'Unknown')
    album = release.get('album', 'Unknown')
    fecha = time.strftime('%Y-%m-%d')

    with open(fallidos_file, 'a', encoding='utf-8') as f:
        f.write(f"{post_id}|{band}|{album}|{fecha}|{motivo}\n")

    fallidos.add(post_id)


def limpiar_nombre(nombre):
    """Limpia un nombre para usarlo como nombre de carpeta"""
    # Remover caracteres no válidos para sistemas de archivos
    nombre = re.sub(r'[<>:"/\\|?*]', '', nombre)
    # Remover espacios múltiples
    nombre = re.sub(r'\s+', ' ', nombre)
    # Remover puntos al final (Windows no los permite)
    nombre = nombre.rstrip('.')
    return nombre.strip()


def _extraer_nombre_archivo(headers, final_url):
    """Intenta extraer el nombre de archivo desde headers o URL"""
    filename = None
    if headers and 'content-disposition' in headers:
        cd = headers['content-disposition']
        match = re.search(r'filename[*]?=["\']?(?:UTF-8\'\')?([^"\';]+)', cd)
        if match:
            filename = unquote(match.group(1))

    if not filename:
        parsed = urlparse(final_url)
        filename = os.path.basename(parsed.path)

    if not filename:
        filename = 'download'

    filename = limpiar_nombre(filename)

    # Si no tiene extensión conocida, usar .zip por compatibilidad con el flujo actual
    if not any(filename.lower().endswith(ext) for ext in ['.zip', '.rar', '.7z', '.tar', '.gz', '.mp3', '.flac']):
        filename += '.zip'

    return filename


def _normalizar_url(url):
    """Normaliza URLs escapadas o relativas encontradas en HTML/JSON."""
    if not url:
        return url
    url = url.strip().strip('"').strip("'")
    url = url.replace('\\u002F', '/').replace('\\/', '/')
    url = html_lib.unescape(url)
    if url.startswith('//'):
        url = 'https:' + url
    if url.startswith('http://'):
        url = 'https://' + url[len('http://'):]
    return url


def _preparar_url_http(url):
    """Normaliza y percent-encodea una URL para requests/headers."""
    if not url:
        return url
    try:
        return requote_uri(_normalizar_url(url))
    except Exception:
        return _normalizar_url(url)


def _headers_con_referer(url, extra_headers=None):
    """Construye headers HTTP seguros para URLs con caracteres Unicode."""
    headers = dict(extra_headers or {})
    safe_url = _preparar_url_http(url)
    if safe_url:
        headers['Referer'] = safe_url
    return headers


def _buscar_url_en_html(html_text, patrones, base_url=None):
    """Busca una URL de descarga en HTML usando una lista de patrones."""
    if not html_text:
        return None
    html_text = html_lib.unescape(html_text)
    for patron in patrones:
        match = re.search(patron, html_text, re.IGNORECASE | re.DOTALL)
        if match:
            url = _normalizar_url(match.group(1))
            if base_url and url.startswith('/'):
                url = urljoin(base_url, url)
            return url
    return None


def _respuesta_parece_archivo(response):
    """Heurística para detectar si una respuesta HTTP ya es el archivo."""
    if response is None:
        return False

    content_type = response.headers.get('content-type', '').lower()
    content_disposition = response.headers.get('content-disposition', '').lower()

    if 'attachment' in content_disposition or 'filename=' in content_disposition:
        return True

    if not content_type:
        return bool(getattr(response, 'url', None))

    no_archivo = (
        'text/html',
        'application/json',
        'text/json',
        'application/xml',
        'text/xml',
        'application/javascript',
        'text/javascript',
    )
    return not any(token in content_type for token in no_archivo)


def _guardar_respuesta_con_reintentos(response, destino, verbose=True, show_progress=True, headers=None):
    """Guarda una respuesta streaming y reintenta si quedó parcial."""
    intentos = 0
    request_url = getattr(response, 'url', None)

    while True:
        intentos += 1
        filepath, parcial = _guardar_respuesta(response, destino, verbose, show_progress)
        if filepath:
            return filepath, False
        if not parcial:
            return None, False

        if verbose:
            logger.warning("Descarga incompleta, reintentando...")
        if MAX_REINTENTOS_PARCIALES and intentos >= MAX_REINTENTOS_PARCIALES:
            return None, True

        if not request_url:
            return None, False

        time.sleep(DELAY_REINTENTO_DESCARGA)
        response = _get_session().get(
            request_url,
            headers=headers or None,
            stream=True,
            timeout=(10, 300),
            allow_redirects=True,
        )
        response.raise_for_status()
        if not _respuesta_parece_archivo(response):
            if verbose:
                logger.warning("La respuesta dejó de parecer un archivo")
            return None, False


def _buscar_url_en_json(data, keys):
    """Busca recursivamente una URL en un objeto JSON para claves dadas."""
    if isinstance(data, dict):
        for k, v in data.items():
            if k in keys and isinstance(v, str) and v.startswith('http'):
                return v
            found = _buscar_url_en_json(v, keys)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _buscar_url_en_json(item, keys)
            if found:
                return found
    return None


# Playwright por thread.
# La API sync de Playwright no es thread-safe cuando se comparte browser/context
# entre threads; usar estado local evita greenlet errors.
def _get_playwright_browser():
    """Obtiene o crea un browser Playwright por thread."""
    browser = getattr(_thread_local, 'pw_browser', None)
    if browser is not None:
        return browser

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        _thread_local.pw_playwright = pw
        _thread_local.pw_browser = browser
        return browser
    except Exception:
        # Limpiar parcialmente iniciado
        pw = getattr(_thread_local, 'pw_playwright', None)
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
        if hasattr(_thread_local, 'pw_playwright'):
            del _thread_local.pw_playwright
        if hasattr(_thread_local, 'pw_browser'):
            del _thread_local.pw_browser
        return None


def _cleanup_playwright():
    """Cierra Playwright del thread actual."""
    browser = getattr(_thread_local, 'pw_browser', None)
    if browser:
        try:
            browser.close()
        except Exception:
            pass
        del _thread_local.pw_browser

    pw = getattr(_thread_local, 'pw_playwright', None)
    if pw:
        try:
            pw.stop()
        except Exception:
            pass
        del _thread_local.pw_playwright


def _resolver_playwright_download_url(url, verbose=True, selectors=None, timeout_ms=60000):
    """Intenta resolver un link de descarga usando Playwright (fallback)."""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    except ImportError:
        if verbose:
            logger.warning("Playwright no disponible")
        return None

    selectors = selectors or [
        'a:has-text("Download")',
        'button:has-text("Download")',
        'text=/download/i',
        'a:has-text("Download all")',
        'button:has-text("Download all")',
    ]

    browser = _get_playwright_browser()
    if not browser:
        if verbose:
            logger.warning("Playwright no disponible")
        return None

    download_url = None
    try:
        context = browser.new_context(accept_downloads=True)
        try:
            page = context.new_page()

            def _on_download(download):
                nonlocal download_url
                try:
                    download_url = download.url
                except Exception:
                    pass

            page.on("download", _on_download)
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)

            # Intentar click en botones comunes de descarga
            for sel in selectors:
                if download_url:
                    break
                try:
                    with page.expect_download(timeout=5000) as dl_info:
                        page.click(sel, timeout=5000)
                    dl = dl_info.value
                    download_url = getattr(dl, "url", None)
                except PlaywrightTimeoutError:
                    continue
                except Exception:
                    continue

            # Fallback: buscar hrefs en el DOM
            if not download_url:
                try:
                    hrefs = page.eval_on_selector_all("a", "els => els.map(e => e.href)")
                    for href in hrefs or []:
                        if href and "download" in href.lower():
                            download_url = href
                            break
                except Exception:
                    pass
        finally:
            context.close()
    except (PlaywrightTimeoutError, OSError, RuntimeError) as e:
        if verbose:
            logger.warning(f"Playwright error: {e}")
        return None
    except Exception as e:
        if verbose:
            logger.warning(f"Playwright error: {e}")
        return None

    return download_url


def _acortar_nombre_componente(nombre, max_bytes=220):
    """Acorta un nombre de componente de path para evitar ENAMETOOLONG."""
    if not nombre:
        return nombre

    encoded = nombre.encode('utf-8', errors='ignore')
    if len(encoded) <= max_bytes:
        return nombre

    # Sufijo hash para mantener unicidad del nombre truncado
    digest = hashlib.sha1(encoded).hexdigest()[:8]
    suffix = f"__{digest}"
    suffix_bytes = len(suffix.encode('utf-8'))
    limite_base = max(16, max_bytes - suffix_bytes)

    acumulado = []
    usados = 0
    for ch in nombre:
        ch_bytes = ch.encode('utf-8', errors='ignore')
        if usados + len(ch_bytes) > limite_base:
            break
        acumulado.append(ch)
        usados += len(ch_bytes)

    base = ''.join(acumulado).rstrip(' .')
    if not base:
        base = "release"
    return f"{base}{suffix}"


def _resumir_release_log(band, album, max_chars=72):
    """Resume band+album para usarlo como contexto de log."""
    label = f"{band} - {album}".strip(" -")
    if len(label) <= max_chars:
        return label
    return label[: max_chars - 3].rstrip() + "..."


def _mega_cooldown_activo():
    return mega_cooldown.is_active()


def _mega_cooldown_restante():
    return mega_cooldown.remaining()


def _crear_release_mega(release):
    """Construye un release con solo links de Mega para reintentos."""
    links = release.get('download_links', [])
    mega_links = [li for li in links if detectar_tipo_link(li.get('url', '')) == 'mega']
    if not mega_links:
        return None
    campos = ['post_id', 'band', 'album', 'band_id', 'year', 'type']
    nuevo = {k: release.get(k) for k in campos}
    nuevo['download_links'] = mega_links
    return nuevo


def cargar_mega_pendientes(pendientes_file=MEGA_PENDIENTES_FILE):
    """Carga la lista de releases con Mega pendientes."""
    if not os.path.exists(pendientes_file):
        return []
    try:
        with open(pendientes_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            # Asegurar que solo haya links mega
            limpiados = []
            for r in data:
                if not isinstance(r, dict):
                    continue
                rm = _crear_release_mega(r)
                if rm:
                    limpiados.append(rm)
            return limpiados
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        pass
    return []


def guardar_mega_pendientes(pendientes, pendientes_file=MEGA_PENDIENTES_FILE):
    """Guarda la lista de releases con Mega pendientes."""
    if not pendientes:
        if os.path.exists(pendientes_file):
            try:
                os.remove(pendientes_file)
            except OSError:
                pass
        return

    os.makedirs(os.path.dirname(pendientes_file), exist_ok=True)
    try:
        with open(pendientes_file, 'w', encoding='utf-8') as f:
            json.dump(pendientes, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _guardar_respuesta(response, destino, verbose=True, show_progress=True,
                       append_to=None, offset=0):
    """Guarda un response streaming en destino y retorna (filepath, parcial).

    Args:
        append_to: Si se proporciona, path al archivo parcial para continuar descarga.
        offset: Bytes ya descargados (para mostrar progreso correcto en resume).
    """
    if append_to:
        filepath = append_to
    else:
        filename = _extraer_nombre_archivo(response.headers, response.url)
        filepath = os.path.join(destino, filename)

    # Descargar con progreso
    total_size = int(response.headers.get('content-length', 0))
    if append_to and offset:
        total_size += offset  # content-length en 206 es solo el rango restante
    downloaded = offset
    start_time = time.time()
    try:
        mode = 'ab' if append_to else 'wb'
        with open(filepath, mode) as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if verbose and show_progress and total_size > 0:
                        pct = (downloaded / total_size) * 100
                        print(f"\r    Descargando: {pct:.1f}%", end='', flush=True)

        if verbose and show_progress and total_size > 0:
            print()  # Nueva línea

        # Reportar velocidad en modo paralelo (sin progress bar)
        if verbose and not show_progress and downloaded > 0:
            elapsed = time.time() - start_time
            if elapsed > 0:
                speed_mb = (downloaded / (1024 * 1024)) / elapsed
                logger.info(f"↓ {downloaded / (1024*1024):.1f} MB @ {speed_mb:.1f} MB/s")

    except (OSError, requests.RequestException):
        # Descarga parcial — mantener archivo para posible resume
        return None, downloaded > offset

    # Verificar archivo muy pequeño o página HTML de error
    if os.path.exists(filepath):
        size = os.path.getsize(filepath)
        if size < 5000:
            with open(filepath, 'rb') as f:
                head = f.read(512).lower()
            if b'<!doctype' in head or b'<html' in head or b'<head>' in head:
                os.remove(filepath)
                if verbose:
                    logger.warning(f"Archivo es página HTML de error ({size} bytes)")
                return None, False
            if size < 100:
                os.remove(filepath)
                if verbose:
                    logger.warning(f"Archivo demasiado pequeño ({size} bytes)")
                return None, False

    return filepath, False


def _ext_compuesta(filepath):
    """Obtiene extensión considerando .tar.gz y similares"""
    name = os.path.basename(filepath).lower()
    if name.endswith('.tar.gz'):
        return '.tar.gz'
    if name.endswith('.tar.bz2'):
        return '.tar.bz2'
    if name.endswith('.tgz'):
        return '.tgz'
    return os.path.splitext(name)[1]


def _archivo_es_comprimido(filepath, ext):
    """Valida firma básica para evitar intentar extraer archivos que no son comprimidos"""
    try:
        if ext == '.zip':
            return zipfile.is_zipfile(filepath)
        if ext == '.rar':
            with open(filepath, 'rb') as f:
                sig = f.read(8)
            return sig.startswith(b'Rar!\x1a\x07')
        if ext == '.7z':
            with open(filepath, 'rb') as f:
                sig = f.read(6)
            return sig == b'7z\xbc\xaf\x27\x1c'
        if ext in ['.tar', '.tar.gz', '.tgz', '.tar.bz2']:
            import tarfile
            return tarfile.is_tarfile(filepath)
    except OSError:
        # Si no se puede validar, intentar extraer para no perder archivos válidos
        return True
    return True


def _detectar_extension_audio(filepath):
    """Detecta extensión de audio por firma de archivo"""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(32)
    except OSError:
        return None

    if header.startswith(b'ID3') or header[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'):
        return '.mp3'
    if header.startswith(b'fLaC'):
        return '.flac'
    if header.startswith(b'OggS'):
        return '.ogg'
    if header.startswith(b'RIFF') and header[8:12] == b'WAVE':
        return '.wav'
    if header[:2] in (b'\xff\xf1', b'\xff\xf9'):
        return '.aac'
    if header[4:8] == b'ftyp':
        major = header[8:12]
        if major in (b'M4A ', b'isom', b'mp42', b'MP4 '):
            return '.m4a'
    return None


def _detectar_extension_comprimido(filepath):
    """Detecta extensión de comprimido por firma de archivo"""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(8)
    except OSError:
        return None

    if header.startswith(b'PK\x03\x04') or header.startswith(b'PK\x05\x06') or header.startswith(b'PK\x07\x08'):
        return '.zip'
    if header.startswith(b'Rar!\x1a\x07'):
        return '.rar'
    if header.startswith(b'7z\xbc\xaf\x27\x1c'):
        return '.7z'
    return None


def _ajustar_extension_audio(filepath, verbose=True):
    """Renombra archivo si parece audio y la extensión no coincide"""
    if not os.path.exists(filepath):
        return filepath

    ext_actual = os.path.splitext(filepath)[1].lower()
    ext_audio = _detectar_extension_audio(filepath)
    if not ext_audio:
        return filepath

    if ext_actual == ext_audio:
        return filepath

    nuevo_path = filepath
    if ext_actual:
        nuevo_path = filepath[: -len(ext_actual)] + ext_audio
    else:
        nuevo_path = filepath + ext_audio

    try:
        os.rename(filepath, nuevo_path)
        if verbose:
            logger.info(f"Archivo detectado como audio, renombrado a {os.path.basename(nuevo_path)}")
        return nuevo_path
    except OSError:
        return filepath


def _ajustar_extension_comprimido(filepath, verbose=True):
    """Renombra archivo si parece comprimido y la extensión no coincide"""
    if not os.path.exists(filepath):
        return filepath

    ext_actual = os.path.splitext(filepath)[1].lower()
    ext_comp = _detectar_extension_comprimido(filepath)
    if not ext_comp:
        return filepath

    if ext_actual == ext_comp:
        return filepath

    nuevo_path = filepath
    if ext_actual:
        nuevo_path = filepath[: -len(ext_actual)] + ext_comp
    else:
        nuevo_path = filepath + ext_comp

    try:
        os.rename(filepath, nuevo_path)
        if verbose:
            logger.info(f"Archivo detectado como comprimido, renombrado a {os.path.basename(nuevo_path)}")
        return nuevo_path
    except OSError:
        return filepath


def generar_nombre_carpeta(release):
    """Genera el nombre de carpeta correcto para un release"""
    band = limpiar_nombre(release.get('band', 'Unknown'))
    album = limpiar_nombre(release.get('album', 'Unknown'))
    year = release.get('year', '')
    tipo = release.get('type', '')

    if year:
        nombre = f"{band} - {album} ({year})"
    else:
        nombre = f"{band} - {album}"

    # Agregar tipo si no es Album
    if tipo and tipo.lower() not in ['album', 'álbum']:
        nombre += f" [{tipo}]"

    return _acortar_nombre_componente(nombre)


def _priorizar_links(links):
    """Ordena links por prioridad de servicio (más confiable primero) y calidad"""
    def sort_key(link):
        tipo = detectar_tipo_link(link.get('url', ''))
        # quality puede venir como None en el JSON; tratarlo como 0
        return (LINK_PRIORITY.get(tipo, 50), -(link.get('quality') or 0))
    return sorted(links, key=sort_key)


def detectar_tipo_link(url):
    """Detecta el tipo de enlace de descarga"""
    url_lower = url.lower()

    # Mega requiere herramienta especial (megadl)
    if 'mega.nz' in url_lower or 'mega.co.nz' in url_lower:
        return 'mega'
    # Mediafire requiere resolver el link real
    elif 'mediafire.com' in url_lower:
        return 'mediafire'
    # Google Drive requiere confirmación en archivos grandes
    elif 'drive.google.com' in url_lower or 'docs.google.com' in url_lower:
        return 'gdrive'
    # VK Docs (requiere resolver link real en algunos casos)
    elif 'vk.com/doc' in url_lower or 'vk.com/s/v1/doc' in url_lower:
        return 'vkdoc'
    # Yandex Disk (API pública para obtener link directo)
    elif 'disk.yandex.ru' in url_lower or 'disk.yandex.com' in url_lower or 'yadi.sk' in url_lower:
        return 'yandex'
    # pCloud (link público)
    elif 'u.pcloud.link' in url_lower or 'e.pcloud.link' in url_lower or 'pcloud.com' in url_lower:
        return 'pcloud'
    # Mail.ru cloud (link público)
    elif 'cloud.mail.ru' in url_lower:
        return 'mailru'
    # Icedrive (links públicos)
    elif 'icedrive.net' in url_lower:
        return 'icedrive'
    # Krakenfiles (requiere resolver link real)
    elif 'krakenfiles.com' in url_lower:
        return 'krakenfiles'
    # Workupload (requiere extraer link real del HTML)
    elif 'workupload.com' in url_lower:
        return 'workupload'
    # WeTransfer (enlaces dinámicos)
    elif 'we.tl' in url_lower or 'wetransfer.com' in url_lower:
        return 'wetransfer'
    # Dropbox (descarga directa con ?dl=1)
    elif 'dropbox.com' in url_lower:
        return 'dropbox'
    # OneDrive / SharePoint
    elif '1drv.ms' in url_lower or 'onedrive.live.com' in url_lower or 'sharepoint.com' in url_lower:
        return 'onedrive'
    # Gofile
    elif 'gofile.io' in url_lower:
        return 'gofile'
    # Archive.org
    elif 'archive.org' in url_lower:
        return 'archive'
    # Servicios muertos o con captcha (no intentar)
    elif 'zippyshare.com' in url_lower:
        return 'dead'  # Cerró en 2023
    # Todo lo demás: intentar descarga directa
    else:
        return 'direct'


def descargar_mega(url, destino, password=None, verbose=True):
    """
    Descarga un archivo de Mega.nz usando megadl
    Retorna: (filepath, skip_mega)
        - filepath: ruta al archivo descargado o None si falló
        - skip_mega: True si se debe saltar Mega para este release (límite/timeout)
    """
    try:
        if _mega_cooldown_activo():
            if verbose:
                logger.debug("⏭️ Saltando Mega (cooldown activo)")
            return None, True

        # Asegurar que la URL tenga la clave de encriptación
        # Formato: https://mega.nz/file/ID#KEY o https://mega.nz/#!ID!KEY
        if '#' not in url and '!' not in url:
            if verbose:
                logger.warning("URL de Mega sin clave de encriptación")
            return None, False

        # megadl necesita la URL completa con la clave
        cmd = ['megadl', '--path', destino, '--print-names', url]

        # Timeout configurable - si tarda más, probar otros servidores
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=MEGA_TIMEOUT_SECONDS)

        if result.returncode == 0:
            # megadl con --print-names imprime el nombre del archivo
            filename = result.stdout.strip().split('\n')[-1] if result.stdout else None

            if filename and os.path.exists(os.path.join(destino, filename)):
                return os.path.join(destino, filename), False

            # Fallback: buscar el archivo más reciente en el destino
            for f in os.listdir(destino):
                filepath = os.path.join(destino, f)
                if os.path.isfile(filepath):
                    return filepath, False

            return None, False
        else:
            error_msg = result.stderr.strip() if result.stderr else ""
            error_lower = error_msg.lower()

            # Detectar límite de descarga real de Mega → cooldown largo
            if 'bandwidth' in error_lower or 'limit' in error_lower or 'quota' in error_lower:
                mins = MEGA_COOLDOWN_SECONDS // 60
                if verbose:
                    logger.warning(f"Mega: rate-limit alcanzado, cooldown {mins}m")
                mega_cooldown.activate()
                return None, True  # Skip Mega para este release

            if verbose:
                first_line = error_msg.split('\n')[0][:60]
                logger.warning(f"megadl: {first_line}")
            return None, False

    except FileNotFoundError:
        if verbose:
            logger.warning("megadl no instalado")
        return None, False
    except subprocess.TimeoutExpired:
        # Timeout puede ser red lenta o archivo grande, no necesariamente
        # rate-limit. Cooldown corto para evitar martillar Mega y dar tiempo
        # a que se recupere si era circunstancial.
        mins = MEGA_TIMEOUT_COOLDOWN_SECONDS // 60
        if verbose:
            logger.warning(f"Mega: timeout tras {MEGA_TIMEOUT_SECONDS}s, cooldown {mins}m")
        mega_cooldown.activate(MEGA_TIMEOUT_COOLDOWN_SECONDS)
        return None, True  # Skip Mega para este release
    except (subprocess.SubprocessError, OSError) as e:
        if verbose:
            logger.warning(f"Error Mega: {e}")
        return None, False


def descargar_mediafire(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo de Mediafire"""
    try:
        url = _preparar_url_http(url)

        patrones = [
            r'<a[^>]*id=["\']downloadButton["\'][^>]*href=["\']([^"\']+)["\']',
            r'<a[^>]*href=["\']([^"\']+)["\'][^>]*id=["\']downloadButton["\']',
            r'<a[^>]*aria-label=["\']Download file["\'][^>]*href=["\']([^"\']+)["\']',
            r'href=["\'](https?://download\d*\.mediafire\.com/[^"\']+)["\']',
            r'"downloadUrl"\s*:\s*"(https:\\/\\/[^\"]+mediafire\.com/[^\"]+)"',
            r'"downloadUrl"\s*:\s*"(https:\\/\\/download[^\"]+)"',
            r'\bdownloadUrl\b\s*=\s*"(https?://[^"]+)"',
        ]

        def _resolver_respuesta_mediafire(resp, source_url):
            resp.raise_for_status()

            # Algunos /file_premium/ ya redirigen al ZIP real. No intentes parsear HTML.
            if _respuesta_parece_archivo(resp):
                return _guardar_respuesta_con_reintentos(
                    resp,
                    destino,
                    verbose,
                    show_progress,
                    headers=_headers_con_referer(source_url),
                )

            html = resp.text
            download_url = _buscar_url_en_html(html, patrones, base_url=source_url)
            if download_url:
                return descargar_directo(
                    download_url,
                    destino,
                    verbose,
                    headers=_headers_con_referer(source_url),
                    show_progress=show_progress,
                )
            return None, False

        # Obtener página o archivo directo
        response = _get_session().get(url, stream=True, timeout=(10, 300), allow_redirects=True)
        archivo, parcial = _resolver_respuesta_mediafire(response, url)
        if archivo:
            return archivo, parcial
        if parcial:
            return None, True

        # Fallback: probar versión no-premium si existe
        if 'file_premium' in url:
            url_alt = url.replace('/file_premium/', '/file/')
            if url_alt != url:
                response = _get_session().get(url_alt, stream=True, timeout=(10, 300), allow_redirects=True)
                archivo, parcial = _resolver_respuesta_mediafire(response, url_alt)
                if archivo:
                    return archivo, parcial
                if parcial:
                    return None, True

        # Fallback JS: algunos mirrors de Mediafire generan el link en runtime
        download_url = _resolver_playwright_download_url(url, verbose=False)
        if download_url:
            return descargar_directo(
                download_url,
                destino,
                verbose,
                headers=_headers_con_referer(url),
                show_progress=show_progress,
            )

        if verbose:
            logger.warning("No se encontró enlace directo en Mediafire")
        return None, False

    except Exception as e:
        if verbose:
            logger.warning(f"Error Mediafire: {e}")
        return None, False


def descargar_vk_doc(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo de VK Docs intentando resolver el link directo"""
    try:
        resp = _get_session().get(url, stream=True, timeout=(10, 300), allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get('content-type', '').lower()
        if 'text/html' not in content_type:
            intentos = 0
            while True:
                intentos += 1
                filepath, parcial = _guardar_respuesta(resp, destino, verbose, show_progress)
                if filepath:
                    return filepath, False
                if parcial:
                    if verbose:
                        logger.warning("Descarga incompleta, reintentando...")
                    if MAX_REINTENTOS_PARCIALES and intentos >= MAX_REINTENTOS_PARCIALES:
                        return None, True
                    time.sleep(DELAY_REINTENTO_DESCARGA)
                    resp = _get_session().get(url, stream=True, timeout=(10, 300), allow_redirects=True)
                    resp.raise_for_status()
                    continue
                return None, False

        html = resp.text
        patrones = [
            r'"url":"(https:\\/\\/[^"]+)"',
            r'href="(https://vk\.com/doc[^"]+)"',
            r'href="(https?://[^"]+\.(?:zip|rar|7z|tar|gz|mp3|flac|ogg|wav|m4a|aac))"',
        ]

        download_url = None
        for patron in patrones:
            match = re.search(patron, html)
            if match:
                download_url = match.group(1).replace('\\/', '/')
                break

        if download_url:
            return descargar_directo(download_url, destino, verbose, show_progress=show_progress)

        # Intento simple con parámetro de descarga
        dl_url = url + ('&' if '?' in url else '?') + 'dl=1'
        return descargar_directo(dl_url, destino, verbose, show_progress=show_progress)

    except requests.exceptions.HTTPError as e:
        if verbose:
            logger.warning(f"HTTP {e.response.status_code}")
        return None, False
    except Exception as e:
        if verbose:
            logger.warning(f"Error VK: {e}")
        return None, False


def _gdrive_extraer_id(url):
    """Extrae el ID de un enlace de Google Drive"""
    patrones = [
        r'/file/d/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
        r'/d/([a-zA-Z0-9_-]+)',
    ]
    for patron in patrones:
        match = re.search(patron, url)
        if match:
            return match.group(1)
    return None


def _gdrive_confirm_token(html):
    """Busca el token de confirmación en HTML de Google Drive"""
    match = re.search(r'confirm=([0-9A-Za-z_]+)', html)
    if match:
        return match.group(1)
    match = re.search(r'name="confirm"\s+value="([^"]+)"', html)
    if match:
        return match.group(1)
    return None


def _gdrive_confirm_cookie(cookies):
    for k, v in cookies.items():
        if k.startswith('download_warning'):
            return v
    return None


def descargar_google_drive(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo público de Google Drive"""
    try:
        file_id = _gdrive_extraer_id(url)
        if not file_id:
            if verbose:
                logger.warning("No se pudo extraer el ID de Google Drive")
            return None, False

        session = requests.Session()
        params = {'export': 'download', 'id': file_id}
        intentos = 0
        confirm_token = None
        while True:
            intentos += 1
            resp = session.get(
                'https://drive.google.com/uc',
                params=params,
                headers=DEFAULT_HEADERS,
                stream=True,
                timeout=(10, 300),
                allow_redirects=True,
            )
            resp.raise_for_status()

            content_type = resp.headers.get('content-type', '').lower()
            if 'text/html' in content_type and confirm_token is None:
                confirm_token = _gdrive_confirm_token(resp.text)
                if not confirm_token:
                    confirm_token = _gdrive_confirm_cookie(resp.cookies)
                if confirm_token:
                    params['confirm'] = confirm_token
                    continue

            content_type = resp.headers.get('content-type', '').lower()
            if 'text/html' in content_type and 'content-disposition' not in resp.headers:
                if verbose:
                    logger.warning("Google Drive requiere confirmación/cookies (archivo grande o restringido)")
                return None, False

            filepath, parcial = _guardar_respuesta(resp, destino, verbose, show_progress)
            if filepath:
                return filepath, False
            if parcial:
                if verbose:
                    logger.warning("Descarga incompleta, reintentando...")
                if MAX_REINTENTOS_PARCIALES and intentos >= MAX_REINTENTOS_PARCIALES:
                    return None, True
                time.sleep(DELAY_REINTENTO_DESCARGA)
                continue
            return None, False

    except requests.exceptions.HTTPError as e:
        if verbose:
            logger.warning(f"HTTP {e.response.status_code}")
        return None, False
    except Exception as e:
        if verbose:
            logger.warning(f"Error Google Drive: {e}")
        return None, False


def descargar_yandex_disk(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo público de Yandex Disk usando su API pública"""
    try:
        api_url = 'https://cloud-api.yandex.net/v1/disk/public/resources/download'
        resp = _get_session().get(api_url, params={'public_key': url}, timeout=(10, 30))
        resp.raise_for_status()
        data = resp.json()
        href = data.get('href')
        if not href:
            if verbose:
                logger.warning("No se encontró link directo en Yandex Disk")
            return None, False
        return descargar_directo(href, destino, verbose, show_progress=show_progress)
    except requests.exceptions.HTTPError as e:
        if verbose:
            logger.warning(f"HTTP {e.response.status_code}")
        return None, False
    except Exception as e:
        if verbose:
            logger.warning(f"Error Yandex Disk: {e}")
        return None, False


def descargar_pcloud(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo público de pCloud"""
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        code = qs.get('code', [None])[0]
        if not code:
            match = re.search(r'code=([A-Za-z0-9]+)', url)
            code = match.group(1) if match else None

        if code:
            api_resp = _get_session().get(
                'https://api.pcloud.com/getpublinkdownload',
                params={'code': code},
                timeout=(10, 30),
            )
            api_resp.raise_for_status()
            data = api_resp.json()
            hosts = data.get('hosts')
            path = data.get('path')
            if hosts and path:
                download_url = f"https://{hosts[0]}{path}"
                return descargar_directo(download_url, destino, verbose, show_progress=show_progress)

        # Fallback a URL "download"
        if 'publink/show' in url:
            url = url.replace('/publink/show', '/publink/download')
        if 'download' not in url:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            qs['download'] = ['1']
            url = urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))

        return descargar_directo(url, destino, verbose, show_progress=show_progress)
    except Exception as e:
        if verbose:
            logger.warning(f"Error pCloud: {e}")
        return None, False


def descargar_mailru(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo público de Mail.ru Cloud"""
    try:
        resp = _get_session().get(url, stream=True, timeout=(10, 300), allow_redirects=True)
        resp.raise_for_status()

        if _respuesta_parece_archivo(resp):
            return _guardar_respuesta_con_reintentos(
                resp,
                destino,
                verbose,
                show_progress,
                headers=_headers_con_referer(url),
            )

        content_type = resp.headers.get('content-type', '').lower()
        if 'text/html' in content_type:
            html = resp.text
            match = re.search(r'"downloadUrl":"([^"]+)"', html)
            if not match:
                match = re.search(r'href="(https?://[^"]+mail\.ru/[^"]+/download[^"]*)"', html)
            if match:
                download_url = match.group(1).replace('\\/', '/')
                return descargar_directo(download_url, destino, verbose, show_progress=show_progress)

        # Fallback: parámetro download=1
        if 'download=1' not in url:
            sep = '&' if '?' in url else '?'
            url = f"{url}{sep}download=1"
        return descargar_directo(url, destino, verbose, show_progress=show_progress)
    except Exception as e:
        if verbose:
            logger.warning(f"Error Mail.ru: {e}")
        return None, False


def _icedrive_extraer_public_id(url):
    parsed = urlparse(url)
    path = parsed.path.strip('/')
    if path.startswith('s/'):
        return path.split('/', 1)[1]
    if path.startswith('0/'):
        return path.split('/', 1)[1]
    return None


def descargar_icedrive(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo público de Icedrive resolviendo el link real desde HTML"""
    try:
        resp = _get_session().get(url, stream=True, timeout=(10, 300), allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get('content-type', '').lower()
        if 'text/html' not in content_type:
            filepath, parcial = _guardar_respuesta(resp, destino, verbose, show_progress)
            return filepath, parcial

        html = resp.text
        html_lower = html.lower()
        if 'page not found' in html_lower or 'the page you have requested could not be found' in html_lower:
            if verbose:
                logger.warning("Icedrive devolvió una página inexistente")
            return None, False

        patrones = [
            r'data-download-url="([^"]+)"',
            r'"downloadUrl"\\s*:\\s*"([^"]+)"',
            r'"download_url"\\s*:\\s*"([^"]+)"',
            r'href="([^"]+download[^"]+)"',
            r'(https?://[^"\\s]+icedrive\\.net/[^"\\s]+)',
        ]
        download_url = _buscar_url_en_html(html, patrones, base_url=url)
        if download_url and download_url != url:
            return descargar_directo(download_url, destino, verbose, headers=_headers_con_referer(url), show_progress=show_progress)

        # Fallback: buscar URLs embebidas con "download"
        candidatos = re.findall(r'(https?:\\\\/\\\\/[^"\\s]+)', html)
        for cand in candidatos:
            cand = _normalizar_url(cand)
            if cand and 'icedrive.net' in cand and 'download' in cand:
                return descargar_directo(cand, destino, verbose, headers=_headers_con_referer(url), show_progress=show_progress)

        public_id = _icedrive_extraer_public_id(url)
        if public_id:
            posibles = [
                f"https://icedrive.net/download/{public_id}",
                f"https://icedrive.net/0/{public_id}",
                f"https://icedrive.net/s/{public_id}",
                f"https://icedrive.net/file/{public_id}",
            ]
            for candidato in posibles:
                if candidato == url:
                    continue
                archivo, parcial = descargar_directo(candidato, destino, verbose, headers=_headers_con_referer(url), show_progress=show_progress)
                if archivo:
                    return archivo, parcial

        # Fallback con Playwright si la página requiere JS
        download_url = _resolver_playwright_download_url(url, verbose)
        if download_url:
            return descargar_directo(download_url, destino, verbose, headers=_headers_con_referer(url), show_progress=show_progress)

        if verbose:
            logger.warning("No se encontró enlace directo en Icedrive")
        return None, False
    except requests.exceptions.HTTPError as e:
        if verbose:
            logger.warning(f"HTTP {e.response.status_code}")
        return None, False
    except Exception as e:
        if verbose:
            logger.warning(f"Error Icedrive: {e}")
        return None, False


def descargar_krakenfiles(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo de Krakenfiles resolviendo el link real desde HTML"""
    try:
        resp = _get_session().get(url, stream=True, timeout=(10, 300), allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get('content-type', '').lower()
        if 'text/html' not in content_type:
            filepath, parcial = _guardar_respuesta(resp, destino, verbose, show_progress)
            return filepath, parcial

        html = resp.text
        patrones = [
            r'href="(https?://krakenfiles\\.com/download/[^"]+)"',
            r'action="(/download/[^"]+)"',
            r'data-url="(https?://[^"]+)"',
            r'"download_url"\\s*:\\s*"([^"]+)"',
        ]
        download_url = _buscar_url_en_html(html, patrones, base_url=url)

        # Intento con token si aparece en el HTML
        token = None
        file_hash = None
        match_token = re.search(r'data-token="([^"]+)"', html)
        if match_token:
            token = match_token.group(1)
        match_hash = re.search(r'data-file-hash="([^"]+)"', html)
        if match_hash:
            file_hash = match_hash.group(1)
        if not file_hash:
            match_hash = re.search(r'/view/([A-Za-z0-9]+)/', url)
            if match_hash:
                file_hash = match_hash.group(1)

        if token and file_hash:
            candidate = f"https://krakenfiles.com/download/{file_hash}?token={token}"
            archivo, parcial = descargar_directo(candidate, destino, verbose, headers=_headers_con_referer(url), show_progress=show_progress)
            if archivo:
                return archivo, parcial

        if download_url:
            return descargar_directo(download_url, destino, verbose, headers=_headers_con_referer(url), show_progress=show_progress)

        if verbose:
            logger.warning("No se encontró enlace directo en Krakenfiles")
        return None, False
    except requests.exceptions.HTTPError as e:
        if verbose:
            logger.warning(f"HTTP {e.response.status_code}")
        return None, False
    except Exception as e:
        if verbose:
            logger.warning(f"Error Krakenfiles: {e}")
        return None, False


def descargar_workupload(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo de Workupload resolviendo el link real desde HTML"""
    try:
        resp = _get_session().get(url, timeout=(10, 30))
        resp.raise_for_status()
        html = resp.text

        patrones = [
            r'href="(https?://download\.workupload\.com/[^"]+)"',
            r'href="(https?://workupload\.com/file/[^"]+/download[^"]*)"',
            r'data-url="(https?://[^"]+)"',
            r'data-download-url="(https?://[^"]+)"',
        ]
        download_url = _buscar_url_en_html(html, patrones, base_url=url)

        if not download_url:
            # Fallback: intentar resolver con Playwright (Workupload genera links con JS dinámico)
            download_url = _resolver_playwright_download_url(url, verbose=False)
            if download_url:
                return descargar_directo(download_url, destino, verbose, show_progress=show_progress)
            if verbose:
                logger.warning("No se encontró enlace directo en Workupload")
            return None, False

        return descargar_directo(download_url, destino, verbose, show_progress=show_progress)
    except requests.exceptions.HTTPError as e:
        if verbose:
            logger.warning(f"HTTP {e.response.status_code}")
        return None, False
    except Exception as e:
        if verbose:
            logger.warning(f"Error Workupload: {e}")
        return None, False


def descargar_wetransfer(url, destino, verbose=True, show_progress=True):
    """WeTransfer usa enlaces dinámicos; intentar resolver con Playwright"""
    download_url = _resolver_playwright_download_url(
        url,
        verbose,
        selectors=[
            'button:has-text("Download")',
            'a:has-text("Download")',
            'text=/download/i',
        ],
    )
    if download_url:
        return descargar_directo(download_url, destino, verbose, headers=_headers_con_referer(url), show_progress=show_progress)
    if verbose:
        logger.warning("WeTransfer requiere navegador/JS (no soportado)")
    return None, False


def descargar_onedrive(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo público de OneDrive/SharePoint"""
    try:
        # Convertir share URL a API de descarga directa
        import base64
        encoded = base64.urlsafe_b64encode(url.encode()).decode().rstrip('=')
        share_token = 'u!' + encoded
        api_url = f"https://api.onedrive.com/v1.0/shares/{share_token}/root/content"

        resp = _get_session().get(api_url, stream=True, timeout=(10, 300), allow_redirects=True)

        if resp.status_code == 200:
            content_type = resp.headers.get('content-type', '').lower()
            if 'text/html' not in content_type:
                filepath, parcial = _guardar_respuesta(resp, destino, verbose, show_progress)
                if filepath:
                    return filepath, False

        # Fallback: descarga directa
        return descargar_directo(url, destino, verbose, show_progress=show_progress)
    except Exception as e:
        if verbose:
            logger.warning(f"Error OneDrive: {e}")
        return None, False


def descargar_gofile(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo de Gofile.io usando su API"""
    try:
        # Extraer content ID de la URL
        match = re.search(r'gofile\.io/d/(\w+)', url)
        if not match:
            if verbose:
                logger.warning("No se pudo extraer ID de Gofile")
            return None, False
        content_id = match.group(1)

        # Obtener guest token
        token_resp = _get_session().post(
            'https://api.gofile.io/accounts',
            timeout=(10, 30),
        )
        token_data = token_resp.json()
        guest_token = token_data.get('data', {}).get('token')
        if not guest_token:
            if verbose:
                logger.warning("No se pudo obtener token de Gofile")
            return None, False

        # Obtener info del contenido
        content_resp = _get_session().get(
            f'https://api.gofile.io/contents/{content_id}',
            params={'wt': '4fd6sg89d7s6'},
            headers={'Authorization': f'Bearer {guest_token}'},
            timeout=(10, 30),
        )
        content_data = content_resp.json()
        children = content_data.get('data', {}).get('children', {})

        # Buscar primer archivo descargable
        for child in children.values():
            if child.get('type') == 'file':
                download_url = child.get('link')
                if download_url:
                    return descargar_directo(
                        download_url, destino, verbose,
                        headers={'Cookie': f'accountToken={guest_token}'},
                        show_progress=show_progress
                    )

        if verbose:
            logger.warning("No se encontraron archivos en Gofile")
        return None, False
    except Exception as e:
        if verbose:
            logger.warning(f"Error Gofile: {e}")
        return None, False


def descargar_archive_org(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo de Archive.org"""
    try:
        # Convertir /details/ a /download/
        download_url = url.replace('/details/', '/download/')
        return descargar_directo(download_url, destino, verbose, show_progress=show_progress)
    except Exception as e:
        if verbose:
            logger.warning(f"Error Archive.org: {e}")
        return None, False


def descargar_dropbox(url, destino, verbose=True, show_progress=True):
    """Descarga un archivo de Dropbox convirtiendo a descarga directa con dl=1"""
    if 'dl=0' in url:
        url = url.replace('dl=0', 'dl=1')
    elif 'dl=1' not in url:
        sep = '&' if '?' in url else '?'
        url = f"{url}{sep}dl=1"
    return descargar_directo(url, destino, verbose, show_progress=show_progress)


def descargar_directo(url, destino, verbose=True, headers=None, _pw_fallback=True, show_progress=True):
    """Descarga un archivo directo por HTTP con soporte de resume via Range headers.
    Retorna: (filepath, parcial)
    """
    intentos = 0
    resume_filepath = None
    resume_offset = 0
    safe_url = _preparar_url_http(url)

    while True:
        intentos += 1
        try:
            req_headers = dict(headers) if headers else {}
            if 'Referer' in req_headers:
                req_headers['Referer'] = _preparar_url_http(req_headers['Referer'])

            # Intentar resume si hay archivo parcial de intento anterior
            if resume_filepath and os.path.exists(resume_filepath):
                resume_offset = os.path.getsize(resume_filepath)
                if resume_offset > 0:
                    req_headers['Range'] = f'bytes={resume_offset}-'
                    if verbose:
                        logger.info(f"↻ Resumiendo desde {resume_offset / (1024*1024):.1f} MB...")

            response = _get_session().get(safe_url, headers=req_headers or None, stream=True, timeout=(10, 300), allow_redirects=True)

            # Range resume: 206 = partial content, 200 = servidor no soporta Range
            if response.status_code == 416:
                # Range not satisfiable — archivo puede estar completo
                if resume_filepath and os.path.exists(resume_filepath):
                    return resume_filepath, False
                return None, False

            response.raise_for_status()

            # Verificar que no sea una página HTML (debe ser un archivo)
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' in content_type:
                if _pw_fallback:
                    download_url = _resolver_playwright_download_url(safe_url, verbose=False)
                    if download_url and download_url != safe_url:
                        return descargar_directo(download_url, destino, verbose, headers=headers, _pw_fallback=False, show_progress=show_progress)
                if verbose:
                    logger.warning("Página HTML (requiere navegador)")
                return None, False

            if response.status_code == 206 and resume_filepath:
                # Append al archivo existente
                filepath, parcial = _guardar_respuesta(
                    response, destino, verbose, show_progress,
                    append_to=resume_filepath, offset=resume_offset
                )
            else:
                # Descarga nueva (servidor no soporta Range o primer intento)
                resume_offset = 0
                filepath, parcial = _guardar_respuesta(response, destino, verbose, show_progress)

            if filepath:
                return filepath, False

            if parcial:
                # Determinar path del archivo parcial para resume
                if not resume_filepath:
                    filename = _extraer_nombre_archivo(response.headers, response.url)
                    candidate = os.path.join(destino, filename)
                    if os.path.exists(candidate):
                        resume_filepath = candidate

                if verbose:
                    logger.warning("Descarga incompleta, reintentando...")
                if MAX_REINTENTOS_PARCIALES and intentos >= MAX_REINTENTOS_PARCIALES:
                    # Limpiar archivo parcial en fallo definitivo
                    if resume_filepath and os.path.exists(resume_filepath):
                        try:
                            os.remove(resume_filepath)
                        except OSError:
                            pass
                    return None, True
                time.sleep(DELAY_REINTENTO_DESCARGA)
                continue

            return None, False

        except requests.exceptions.HTTPError as e:
            if verbose:
                logger.warning(f"HTTP {e.response.status_code}")
            return None, False
        except Exception as e:
            if verbose:
                error_msg = str(e)[:50]
                logger.warning(error_msg)
            return None, False


def descargar_link(url, destino, password=None, verbose=True, skip_mega=False, show_progress=True):
    """
    Descarga un archivo según el tipo de enlace
    Retorna: (filepath, skip_mega, parcial)
    """
    if not re.match(r'^https?://', url or ''):
        if verbose:
            logger.warning("URL inválida")
        return None, False, False

    tipo = detectar_tipo_link(url)

    os.makedirs(destino, exist_ok=True)

    if tipo == 'mega':
        if skip_mega:
            if verbose:
                logger.debug("⏭️ Saltando Mega (límite/timeout)")
            return None, True, False
        archivo, new_skip_mega = descargar_mega(url, destino, password, verbose)
        return archivo, new_skip_mega, False
    elif tipo == 'mediafire':
        archivo, parcial = descargar_mediafire(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'vkdoc':
        archivo, parcial = descargar_vk_doc(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'gdrive':
        archivo, parcial = descargar_google_drive(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'yandex':
        archivo, parcial = descargar_yandex_disk(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'pcloud':
        archivo, parcial = descargar_pcloud(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'mailru':
        archivo, parcial = descargar_mailru(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'dropbox':
        archivo, parcial = descargar_dropbox(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'workupload':
        archivo, parcial = descargar_workupload(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'icedrive':
        archivo, parcial = descargar_icedrive(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'krakenfiles':
        archivo, parcial = descargar_krakenfiles(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'wetransfer':
        archivo, parcial = descargar_wetransfer(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'onedrive':
        archivo, parcial = descargar_onedrive(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'gofile':
        archivo, parcial = descargar_gofile(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'archive':
        archivo, parcial = descargar_archive_org(url, destino, verbose, show_progress)
        return archivo, False, parcial
    elif tipo == 'dead':
        if verbose:
            logger.warning("Servicio cerrado/muerto")
        return None, False, False
    else:
        # Intentar descarga directa para cualquier otro enlace
        archivo, parcial = descargar_directo(url, destino, verbose, show_progress=show_progress)
        return archivo, False, parcial


def extraer_archivo(filepath, destino, password=None, verbose=True):
    """Extrae un archivo comprimido"""
    if not os.path.exists(filepath):
        return False

    ext = _ext_compuesta(filepath)
    os.makedirs(destino, exist_ok=True)

    try:
        if ext == '.zip':
            # Intentar con Python primero, si falla usar 7z
            try:
                with zipfile.ZipFile(filepath, 'r') as zf:
                    if password:
                        zf.setpassword(password.encode())
                    zf.extractall(destino)
                return True
            except Exception as zip_error:
                # Fallback a 7z para métodos de compresión no soportados
                if verbose:
                    logger.info("→ Usando 7z para ZIP moderno...")
                cmd = ['7z', 'x', '-y', f'-o{destino}']
                if password:
                    cmd.append(f'-p{password}')
                cmd.append(filepath)
                result = subprocess.run(cmd, capture_output=True, timeout=300)
                return result.returncode == 0

        elif ext == '.rar':
            # Usar unrar
            cmd = ['unrar', 'x', '-y']
            if password:
                cmd.append(f'-p{password}')
            else:
                cmd.append('-p-')  # No password
            cmd.extend([filepath, destino + '/'])

            result = subprocess.run(cmd, capture_output=True, timeout=300)
            return result.returncode == 0

        elif ext == '.7z':
            # Usar 7z
            cmd = ['7z', 'x', '-y', f'-o{destino}']
            if password:
                cmd.append(f'-p{password}')
            cmd.append(filepath)

            result = subprocess.run(cmd, capture_output=True, timeout=300)
            return result.returncode == 0

        elif ext in ['.tar', '.tgz', '.tar.gz', '.tar.bz2']:
            import tarfile
            with tarfile.open(filepath, 'r:*') as tf:
                tf.extractall(destino, filter='data')
            return True

        else:
            if verbose:
                logger.warning(f"Formato no soportado: {ext}")
            return False

    except Exception as e:
        if verbose:
            logger.warning(f"Error extrayendo: {e}")
        return False


def organizar_carpeta(origen, destino_final, verbose=True):
    """Organiza los archivos extraídos en la carpeta destino"""
    if not os.path.exists(origen):
        return False

    # Verificar si hay archivos de audio
    archivos_audio = []
    for root, dirs, files in os.walk(origen):
        for f in files:
            if os.path.splitext(f)[1].lower() in EXTENSIONES_AUDIO:
                archivos_audio.append(os.path.join(root, f))

    if not archivos_audio:
        if verbose:
            logger.warning("No se encontraron archivos de audio")
        return False

    # Crear carpeta destino
    os.makedirs(os.path.dirname(destino_final), exist_ok=True)

    # Si ya existe, agregar sufijo
    destino_real = destino_final
    contador = 1
    while os.path.exists(destino_real):
        destino_real = f"{destino_final} ({contador})"
        contador += 1

    # Mover contenido
    # Si el origen tiene una sola subcarpeta, usarla como base
    items = os.listdir(origen)
    if len(items) == 1 and os.path.isdir(os.path.join(origen, items[0])):
        # Mover la subcarpeta y renombrarla
        shutil.move(os.path.join(origen, items[0]), destino_real)
    else:
        # Mover todo el contenido
        shutil.move(origen, destino_real)

    if verbose:
        logger.info(f"✓ Guardado en: {os.path.basename(destino_real)}")

    return True


def procesar_release(release, destino_base=DESTINO_BASE, temp_dir=TEMP_DIR, verbose=True,
                     descargados=None, fallidos=None, show_progress=True):
    """Procesa un release completo: descarga, extrae y organiza"""
    links = release.get('download_links', [])
    post_id = str(release.get('post_id', ''))
    band = release.get('band', 'Unknown')
    album = release.get('album', 'Unknown')
    log_label = _resumir_release_log(band, album)

    if not links:
        return False, "Sin links", None

    # Post fallido anteriormente?
    if fallidos and post_id in fallidos:
        if verbose:
            with log_context(log_label):
                logger.debug(f"⏭️ Post en fallidos (post {post_id})")
        return True, "Fallido previo", None

    # Ya descargado anteriormente?
    if descargados and release_ya_descargado(release, descargados):
        if verbose:
            with log_context(log_label):
                logger.debug("⏭️ Ya descargado")
        return True, "Ya descargado", None

    nombre_carpeta = generar_nombre_carpeta(release)
    destino_final = os.path.join(destino_base, nombre_carpeta)

    # Ya existe en disco?
    if os.path.exists(destino_final):
        if verbose:
            with log_context(log_label):
                logger.debug(f"⏭️ Ya existe: {nombre_carpeta}")
        return True, "Ya existe", None

    if verbose:
        with log_context(log_label):
            logger.info("📥 Iniciando descarga")

    # Intentar cada link hasta que uno funcione (priorizados por tipo de servicio)
    skip_mega = False  # Se activa si Mega tiene límite/timeout

    tuvo_parcial = False
    mega_omitido_por_cooldown = False

    for link_info in _priorizar_links(links):
        url = link_info.get('url', '')
        password = link_info.get('password', '')

        if not url:
            continue

        tipo = detectar_tipo_link(url)

        # Si Mega está en cooldown, saltamos en silencio: ni "Intentando"
        # ni "Saltando". El release se encolará abajo si todos los links
        # restantes son Mega.
        if tipo == 'mega' and _mega_cooldown_activo():
            mega_omitido_por_cooldown = True
            continue

        with log_context(log_label):
            if verbose:
                logger.info(f"→ Intentando {tipo}: {url[:60]}...")

            # Crear directorio temporal único
            temp_release = tempfile.mkdtemp(dir=temp_dir)
            temp_download = os.path.join(temp_release, 'download')
            temp_extract = os.path.join(temp_release, 'extract')

            try:
                # 1. Descargar
                archivo, new_skip_mega, parcial = descargar_link(url, temp_download, password, verbose, skip_mega, show_progress)
                if parcial and not archivo:
                    tuvo_parcial = True

                # Actualizar skip_mega si Mega falló por límite/timeout
                if new_skip_mega:
                    skip_mega = True
                    if tipo == 'mega' and _mega_cooldown_activo():
                        mega_omitido_por_cooldown = True

                if not archivo or not os.path.exists(archivo):
                    if verbose and not new_skip_mega and not parcial:
                        logger.error("Descarga fallida")
                    continue

                file_size = os.path.getsize(archivo)
                if verbose:
                    size_mb = file_size / (1024 * 1024)
                    logger.info(f"✓ Descargado: {size_mb:.1f} MB")

                # Ajustar extensión si el archivo es audio directo
                archivo = _ajustar_extension_audio(archivo, verbose)
                # Ajustar extensión si es comprimido con extensión incorrecta
                archivo = _ajustar_extension_comprimido(archivo, verbose)

                # 2. Extraer si está comprimido
                ext = _ext_compuesta(archivo)

                if ext in EXTENSIONES_COMPRIMIDAS:
                    if verbose:
                        logger.info("Extrayendo...")

                    if not _archivo_es_comprimido(archivo, ext):
                        if verbose:
                            logger.warning("Archivo no parece comprimido, se omite extracción")
                        origen = temp_download
                    else:
                        if not extraer_archivo(archivo, temp_extract, password, verbose):
                            if verbose:
                                logger.error("Extracción fallida")
                            continue
                        origen = temp_extract
                else:
                    # No está comprimido, usar directamente
                    origen = temp_download

                # 3. Organizar en destino final
                if organizar_carpeta(origen, destino_final, verbose):
                    # Retornar info para guardar en lista de descargados
                    return True, "OK", {'post_id': post_id, 'band': band, 'album': album, 'bytes': file_size}

            except Exception as e:
                if verbose:
                    logger.error(f"Error: {e}")

            finally:
                # Limpiar temporal
                try:
                    shutil.rmtree(temp_release, ignore_errors=True)
                except OSError:
                    pass

        time.sleep(1)  # Pausa entre intentos

    if tuvo_parcial:
        return False, "Descarga parcial", None
    if mega_omitido_por_cooldown:
        mega_release = _crear_release_mega(release)
        if mega_release:
            return False, "Mega pendiente", mega_release
    return False, "Todos los links fallaron", None


def run(destino_base=DESTINO_BASE, verbose=True, limit=None):
    """
    Ejecuta el proceso de descarga y organización.
    Releases con links no-Mega se descargan en paralelo (4 workers).
    Releases solo-Mega se procesan secuencialmente después.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if verbose:
        logger.info("=" * 60)
        logger.info("📦 DESCARGA Y ORGANIZACIÓN DE RELEASES")
        logger.info("=" * 60)

    # Verificar destino
    if not os.path.exists(destino_base):
        logger.warning(f"El directorio destino no existe: {destino_base}")
        crear = input("¿Crearlo? [S/n]: ").strip().lower()
        if crear != 'n':
            os.makedirs(destino_base, exist_ok=True)
        else:
            return

    # Crear directorio temporal
    os.makedirs(TEMP_DIR, exist_ok=True)

    # Cargar lista de releases ya descargados
    descargados = cargar_descargados()
    if verbose and descargados:
        logger.info(f"📋 {len(descargados)} releases ya descargados (serán omitidos)")

    # Cargar lista de posts fallidos
    fallidos = cargar_fallidos()
    if verbose and fallidos:
        logger.info(f"🧾 {len(fallidos)} posts con links fallidos (serán omitidos)")

    # Cargar cola de Mega pendientes
    mega_pendientes = cargar_mega_pendientes()
    mega_pendientes_ids = set()
    for r in mega_pendientes:
        pid = str(r.get('post_id', '')).strip()
        if pid:
            mega_pendientes_ids.add(pid)
    if verbose and mega_pendientes:
        logger.info(f"⏳ {len(mega_pendientes)} releases con Mega pendientes (reanudarán cuando termine el cooldown)")

    # Cargar repertorio
    repertorio = cargar_repertorio()

    # Filtrar solo los que tienen links
    con_links = [r for r in repertorio if r.get('download_links')]

    # Priorizar releases más recientes (year desc)
    con_links.sort(
        key=lambda r: (_parse_year(r.get('year')), r.get('band', ''), r.get('album', '')),
        reverse=True
    )

    if verbose:
        logger.info(f"📊 {len(con_links)} releases con links de descarga")
        logger.info(f"📁 Destino: {destino_base}")

    if limit:
        con_links = con_links[:limit]
        if verbose:
            logger.warning(f"Limitado a {limit} releases")

    # Separar releases: con links no-Mega vs solo-Mega
    releases_no_mega = []
    releases_solo_mega = []
    for r in con_links:
        links = r.get('download_links', [])
        tiene_no_mega = any(detectar_tipo_link(l.get('url', '')) != 'mega' for l in links if l.get('url'))
        if tiene_no_mega:
            releases_no_mega.append(r)
        else:
            releases_solo_mega.append(r)

    if verbose:
        logger.info(f"  → {len(releases_no_mega)} con links no-Mega (paralelo)")
        logger.info(f"  → {len(releases_solo_mega)} solo Mega (secuencial)")

    # Thread-safe counters and locks
    exitosos = 0
    fallidos_count = 0
    omitidos = 0
    pendientes = 0
    total_bytes = 0
    write_lock = threading.Lock()

    def _handle_result(release, exito, mensaje, info):
        nonlocal exitosos, fallidos_count, omitidos, pendientes, total_bytes
        with write_lock:
            if exito:
                if mensaje in ["Ya existe", "Ya descargado", "Fallido previo"]:
                    omitidos += 1
                else:
                    exitosos += 1
                    if info:
                        guardar_descargado(info['post_id'], info['band'], info['album'])
                        descargados.add(info['post_id'])
                        if info.get('bytes'):
                            total_bytes += info['bytes']
            else:
                if mensaje == "Mega pendiente":
                    release_mega = info
                    if release_mega:
                        pid = str(release_mega.get('post_id', '')).strip()
                        if pid and pid not in mega_pendientes_ids:
                            mega_pendientes.append(release_mega)
                            mega_pendientes_ids.add(pid)
                            pendientes += 1
                            if verbose:
                                logger.info("⏳ Encolado para reintento Mega")
                else:
                    fallidos_count += 1
                    if mensaje != "Descarga parcial":
                        guardar_fallido(release, fallidos, motivo=mensaje)

    # === Fase 1: Descargas paralelas (no-Mega) ===
    if releases_no_mega:
        if verbose:
            logger.info(f"🚀 Descargando {len(releases_no_mega)} releases en paralelo (4 workers)...")

        procesados = [0]

        def descargar_worker(release):
            try:
                return release, procesar_release(
                    release, destino_base, TEMP_DIR, verbose, descargados, fallidos,
                    show_progress=False
                )
            finally:
                # Evitar fugas de recursos al reusar threads del pool
                _cleanup_playwright()
                _close_session()

        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(descargar_worker, r): r for r in releases_no_mega}

                for future in as_completed(futures):
                    try:
                        release, (exito, mensaje, info) = future.result()
                        _handle_result(release, exito, mensaje, info)

                        with write_lock:
                            procesados[0] += 1
                            if verbose and procesados[0] % 5 == 0:
                                logger.info(f"📊 Progreso: {procesados[0]}/{len(releases_no_mega)} - "
                                           f"✓{exitosos} ⏭️{omitidos} ✗{fallidos_count}")

                    except Exception as e:
                        with write_lock:
                            fallidos_count += 1
                        if verbose:
                            logger.error(f"Error inesperado: {e}")

        except KeyboardInterrupt:
            logger.warning("Interrumpido por el usuario")
            guardar_mega_pendientes(mega_pendientes)
            _cleanup_playwright()
            return

    # === Fase 2: Descargas secuenciales (solo-Mega + pendientes) ===
    all_mega = releases_solo_mega + mega_pendientes

    # Reseteamos la cola: lo que NO se procese (cooldown, interrupt, fallo
    # con "Mega pendiente") se re-encolará abajo. Los que se procesen con
    # éxito quedan fuera de la cola implícitamente.
    mega_pendientes.clear()
    mega_pendientes_ids.clear()

    def _encolar_pendiente(r):
        """Agrega un release a la cola Mega de forma idempotente."""
        pid = str(r.get('post_id', '')).strip()
        if not pid or pid in mega_pendientes_ids:
            return False
        mr = _crear_release_mega(r)
        if not mr:
            return False
        mega_pendientes.append(mr)
        mega_pendientes_ids.add(pid)
        return True

    if all_mega:
        # Cortocircuito: si Mega ya está en cooldown, no iteramos 675 veces
        # imprimiendo lo mismo. Encolamos todo y salimos limpio.
        if _mega_cooldown_activo():
            restante = _mega_cooldown_restante()
            mins, segs = divmod(restante, 60)
            if verbose:
                logger.info(f"⏸️  Mega en cooldown ({mins}m {segs}s restantes), saltando fase secuencial")
            for r in all_mega:
                _encolar_pendiente(r)
            if verbose:
                logger.info(f"⏳ {len(mega_pendientes)} releases Mega encolados para próxima corrida")
        else:
            if verbose:
                logger.info(f"🔗 Procesando {len(all_mega)} releases Mega secuencialmente...")

            for i, release in enumerate(all_mega):
                # Si el cooldown se activó durante el loop (rate-limit real
                # en plena corrida), encolar el resto y cortar.
                if _mega_cooldown_activo():
                    restante = _mega_cooldown_restante()
                    mins, segs = divmod(restante, 60)
                    pendientes_nuevos = sum(1 for r in all_mega[i:] if _encolar_pendiente(r))
                    if verbose:
                        logger.info(f"⏸️  Mega entró en cooldown ({mins}m {segs}s)")
                        logger.info(f"⏳ Encolados {pendientes_nuevos} releases restantes")
                    break

                if verbose:
                    print(f"\n[MEGA {i+1}/{len(all_mega)}]", end='')

                try:
                    exito, mensaje, info = procesar_release(
                        release, destino_base, TEMP_DIR, verbose, descargados, fallidos
                    )
                    _handle_result(release, exito, mensaje, info)

                except KeyboardInterrupt:
                    logger.warning("Interrumpido por el usuario")
                    for r in all_mega[i+1:]:
                        _encolar_pendiente(r)
                    guardar_mega_pendientes(mega_pendientes)
                    _cleanup_playwright()
                    return
                except Exception as e:
                    fallidos_count += 1
                    if verbose:
                        logger.error(f"Error inesperado: {e}")

                delay_con_jitter(DELAY_ENTRE_DESCARGAS)

    # Guardar pendientes restantes en disco
    guardar_mega_pendientes(mega_pendientes)

    # Cerrar sesión HTTP del thread principal
    _close_session()

    # Limpiar Playwright del thread principal
    _cleanup_playwright()

    # Limpiar temporal
    try:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
    except OSError:
        pass

    # Resumen
    if verbose:
        logger.info("=" * 60)
        logger.info("📊 RESUMEN")
        logger.info("=" * 60)
        logger.info(f"✓ Exitosos: {exitosos}")
        logger.info(f"⏭️ Omitidos (ya existían): {omitidos}")
        logger.info(f"✗ Fallidos: {fallidos_count}")
        if mega_pendientes:
            logger.info(f"⏳ Pendientes Mega: {len(mega_pendientes)} (guardados en {MEGA_PENDIENTES_FILE})")
        if total_bytes > 0:
            if total_bytes >= 1024 * 1024 * 1024:
                logger.info(f"📦 Total descargado: {total_bytes / (1024**3):.1f} GB")
            else:
                logger.info(f"📦 Total descargado: {total_bytes / (1024**2):.1f} MB")
        logger.info(f"📁 Archivos en: {destino_base}")


def verificar_dependencias():
    """Verifica que estén instaladas las herramientas necesarias"""
    dependencias = {
        'unrar': 'unrar (para archivos .rar)',
        '7z': 'p7zip (para archivos .7z)',
        'megadl': 'megatools (para enlaces Mega)'
    }

    faltantes = []
    for cmd, desc in dependencias.items():
        result = subprocess.run(['which', cmd], capture_output=True)
        if result.returncode != 0:
            faltantes.append(f"  - {cmd}: {desc}")

    if faltantes:
        print("⚠️  Dependencias faltantes:")
        for f in faltantes:
            print(f)
        print("\nInstalar con:")
        print("  sudo pacman -S unrar p7zip megatools  # Arch")
        print("  sudo apt install unrar p7zip-full megatools  # Debian/Ubuntu")
        return False

    return True


def limpiar_lista_descargados():
    """Elimina la lista de descargados para empezar de cero"""
    if os.path.exists(DESCARGADOS_FILE):
        os.remove(DESCARGADOS_FILE)
        print(f"✓ Lista de descargados eliminada: {DESCARGADOS_FILE}")
    else:
        print("ℹ️  No existe lista de descargados")


def mostrar_estadisticas_descargados():
    """Muestra estadísticas de la lista de descargados"""
    descargados = cargar_descargados()
    if descargados:
        print(f"📋 Releases descargados: {len(descargados)}")
        print(f"📁 Archivo: {DESCARGADOS_FILE}")
    else:
        print("ℹ️  No hay releases descargados registrados")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Descarga y organiza releases')
    parser.add_argument('--destino', '-d', default=DESTINO_BASE,
                        help='Directorio destino')
    parser.add_argument('--limit', '-l', type=int, default=None,
                        help='Límite de releases a procesar')
    parser.add_argument('--check', '-c', action='store_true',
                        help='Solo verificar dependencias')
    parser.add_argument('--reset', '-r', action='store_true',
                        help='Limpiar lista de descargados y empezar de cero')
    parser.add_argument('--stats', '-s', action='store_true',
                        help='Mostrar estadísticas de descargados')

    args = parser.parse_args()

    if args.check:
        verificar_dependencias()
    elif args.reset:
        limpiar_lista_descargados()
    elif args.stats:
        mostrar_estadisticas_descargados()
    else:
        if verificar_dependencias():
            run(destino_base=args.destino, limit=args.limit)
