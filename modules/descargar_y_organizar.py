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
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs, urlencode, urlunparse, urljoin

# Configuración
INPUT_FILE = "data/repertorio_con_links.json"
DESTINO_BASE = "/run/media/banar/Entretenimiento/01_edicion_automatizada/01_limpieza_de_impurezas"
TEMP_DIR = "/tmp/deathgrind_downloads"
DESCARGADOS_FILE = "data/descargados.txt"  # Lista de releases ya descargados
FALLIDOS_FILE = "data/fallidos_bandas.txt"  # Bandas con links fallidos
MEGA_PENDIENTES_FILE = "data/mega_pendientes.json"

# Configuración de rate limiting
DELAY_ENTRE_DESCARGAS = 2.0  # Segundos entre cada descarga
DELAY_REINTENTO_DESCARGA = 10.0  # Segundos entre reintentos por descarga parcial
MAX_REINTENTOS_PARCIALES = 5  # 0 = infinito, reintentos si hubo descarga parcial

# Configuración de Mega
MEGA_TIMEOUT_SECONDS = int(os.getenv('MEGA_TIMEOUT_SECONDS', '240'))
MEGA_COOLDOWN_SECONDS = int(os.getenv('MEGA_COOLDOWN_SECONDS', '1200'))
_MEGA_COOLDOWN_UNTIL = 0

# Extensiones de archivos comprimidos
EXTENSIONES_COMPRIMIDAS = {'.zip', '.rar', '.7z', '.tar', '.tar.gz', '.tgz', '.tar.bz2'}

# Extensiones de audio (para verificar extracción exitosa)
EXTENSIONES_AUDIO = {'.mp3', '.flac', '.wav', '.ogg', '.m4a', '.aac', '.wma'}

# User-Agent consistente para evitar bloqueos básicos
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/131.0.0.0 Safari/537.36',
    'Accept': '*/*',
}


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
    except Exception:
        return 0


def cargar_descargados(descargados_file=DESCARGADOS_FILE):
    """Carga la lista de releases ya descargados"""
    descargados = set()
    if os.path.exists(descargados_file):
        with open(descargados_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    descargados.add(line)
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
    """Verifica si un release ya fue descargado"""
    post_id = str(release.get('post_id', ''))
    return post_id in descargados or any(post_id in d for d in descargados)


def cargar_fallidos(fallidos_file=FALLIDOS_FILE):
    """Carga la lista de bandas con fallos previos"""
    fallidos = set()
    if os.path.exists(fallidos_file):
        with open(fallidos_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split('|')
                    if parts and parts[0].isdigit():
                        fallidos.add(parts[0])
    return fallidos


def guardar_fallido(release, fallidos, fallidos_file=FALLIDOS_FILE, motivo="Todos los links fallaron"):
    """Agrega una banda a la lista de fallidos (si no existe)"""
    band_id = str(release.get('band_id', '')).strip()
    if not band_id:
        return

    if band_id in fallidos:
        return

    os.makedirs(os.path.dirname(fallidos_file), exist_ok=True)

    # Si el archivo no existe, crear con encabezado
    if not os.path.exists(fallidos_file):
        with open(fallidos_file, 'w', encoding='utf-8') as f:
            f.write("# Bandas con links fallidos\n")
            f.write("# Formato: band_id|band|post_id|album|fecha|motivo\n")
            f.write("\n")

    band = release.get('band', 'Unknown')
    album = release.get('album', 'Unknown')
    post_id = str(release.get('post_id', ''))
    fecha = time.strftime('%Y-%m-%d')

    with open(fallidos_file, 'a', encoding='utf-8') as f:
        f.write(f"{band_id}|{band}|{post_id}|{album}|{fecha}|{motivo}\n")

    fallidos.add(band_id)


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


def _resolver_playwright_download_url(url, verbose=True, selectors=None, timeout_ms=60000):
    """Intenta resolver un link de descarga usando Playwright (fallback)."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except Exception:
        if verbose:
            print("    ⚠️ Playwright no disponible")
        return None

    selectors = selectors or [
        'a:has-text("Download")',
        'button:has-text("Download")',
        'text=/download/i',
        'a:has-text("Download all")',
        'button:has-text("Download all")',
    ]

    download_url = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=True)
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

            context.close()
            browser.close()
    except Exception as e:
        if verbose:
            print(f"    ⚠️ Playwright error: {e}")
        return None

    return download_url


def _mega_cooldown_activo():
    return _MEGA_COOLDOWN_UNTIL and time.time() < _MEGA_COOLDOWN_UNTIL


def _mega_cooldown_restante():
    if not _mega_cooldown_activo():
        return 0
    return int(_MEGA_COOLDOWN_UNTIL - time.time())


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
    except Exception:
        pass
    return []


def guardar_mega_pendientes(pendientes, pendientes_file=MEGA_PENDIENTES_FILE):
    """Guarda la lista de releases con Mega pendientes."""
    if not pendientes:
        if os.path.exists(pendientes_file):
            try:
                os.remove(pendientes_file)
            except Exception:
                pass
        return

    os.makedirs(os.path.dirname(pendientes_file), exist_ok=True)
    try:
        with open(pendientes_file, 'w', encoding='utf-8') as f:
            json.dump(pendientes, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _guardar_respuesta(response, destino, verbose=True):
    """Guarda un response streaming en destino y retorna (filepath, parcial)"""
    filename = _extraer_nombre_archivo(response.headers, response.url)
    filepath = os.path.join(destino, filename)

    # Descargar con progreso
    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0
    try:
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if verbose and total_size > 0:
                        pct = (downloaded / total_size) * 100
                        print(f"\r    Descargando: {pct:.1f}%", end='', flush=True)

        if verbose and total_size > 0:
            print()  # Nueva línea

    except Exception:
        # Descarga parcial
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass
        return None, downloaded > 0

    # Verificar archivo muy pequeño (probable error)
    if os.path.exists(filepath):
        size = os.path.getsize(filepath)
        if size < 1000:
            os.remove(filepath)
            if verbose:
                print(f"    ⚠️ Archivo muy pequeño ({size} bytes), probablemente error")
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
    except Exception:
        # Si no se puede validar, intentar extraer para no perder archivos válidos
        return True
    return True


def _detectar_extension_audio(filepath):
    """Detecta extensión de audio por firma de archivo"""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(32)
    except Exception:
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
    except Exception:
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
            print(f"    ℹ️ Archivo detectado como audio, renombrado a {os.path.basename(nuevo_path)}")
        return nuevo_path
    except Exception:
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
            print(f"    ℹ️ Archivo detectado como comprimido, renombrado a {os.path.basename(nuevo_path)}")
        return nuevo_path
    except Exception:
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

    return nombre


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
        global _MEGA_COOLDOWN_UNTIL
        if _mega_cooldown_activo():
            if verbose:
                print("    ⏭️ Saltando Mega (cooldown activo)")
            return None, True

        # Asegurar que la URL tenga la clave de encriptación
        # Formato: https://mega.nz/file/ID#KEY o https://mega.nz/#!ID!KEY
        if '#' not in url and '!' not in url:
            if verbose:
                print("    ⚠️ URL de Mega sin clave de encriptación")
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

            # Detectar límite de descarga de Mega
            if 'bandwidth' in error_lower or 'limit' in error_lower or 'quota' in error_lower:
                if verbose:
                    print("    ⚠️ Mega: límite de descarga alcanzado, probando otros servidores...")
                _MEGA_COOLDOWN_UNTIL = time.time() + MEGA_COOLDOWN_SECONDS
                return None, True  # Skip Mega para este release

            if verbose:
                first_line = error_msg.split('\n')[0][:60]
                print(f"    ⚠️ megadl: {first_line}")
            return None, False

    except FileNotFoundError:
        if verbose:
            print("    ⚠️ megadl no instalado")
        return None, False
    except subprocess.TimeoutExpired:
        if verbose:
            print("    ⚠️ Mega: timeout, probando otros servidores...")
        _MEGA_COOLDOWN_UNTIL = time.time() + MEGA_COOLDOWN_SECONDS
        return None, True  # Skip Mega para este release
    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error Mega: {e}")
        return None, False


def descargar_mediafire(url, destino, verbose=True):
    """Descarga un archivo de Mediafire"""
    try:
        # Normalizar a https
        if url.startswith('http://'):
            url = 'https://' + url[len('http://'):]

        # Obtener página de descarga
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
        html = response.text
        patrones = [
            r'id="downloadButton"[^>]*href="([^"]+)"',
            r'aria-label="Download file"[^>]*href="([^"]+)"',
            r'href="(https?://download\d*\.mediafire\.com/[^"]+)"',
            r'"downloadUrl"\s*:\s*"(https:\\/\\/[^\"]+mediafire\.com/[^\"]+)"',
            r'"downloadUrl"\s*:\s*"(https:\\/\\/download[^\"]+)"',
            r'\bdownloadUrl\b\s*=\s*"(https?://[^"]+)"',
        ]
        download_url = _buscar_url_en_html(html, patrones, base_url=url)

        if download_url:
            return descargar_directo(download_url, destino, verbose)

        # Fallback: probar versión no-premium si existe
        if 'file_premium' in url:
            url_alt = url.replace('/file_premium/', '/file/')
            if url_alt != url:
                response = requests.get(url_alt, headers=DEFAULT_HEADERS, timeout=30)
                html_alt = response.text
                download_url = _buscar_url_en_html(html_alt, patrones, base_url=url_alt)
                if download_url:
                    return descargar_directo(download_url, destino, verbose)

        if verbose:
            print("    ⚠️ No se encontró enlace directo en Mediafire")
        return None, False

    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error Mediafire: {e}")
        return None, False


def descargar_vk_doc(url, destino, verbose=True):
    """Descarga un archivo de VK Docs intentando resolver el link directo"""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, stream=True, timeout=30, allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get('content-type', '').lower()
        if 'text/html' not in content_type:
            intentos = 0
            while True:
                intentos += 1
                filepath, parcial = _guardar_respuesta(resp, destino, verbose)
                if filepath:
                    return filepath, False
                if parcial:
                    if verbose:
                        print("    ⚠️ Descarga incompleta, reintentando...")
                    if MAX_REINTENTOS_PARCIALES and intentos >= MAX_REINTENTOS_PARCIALES:
                        return None, True
                    time.sleep(DELAY_REINTENTO_DESCARGA)
                    resp = requests.get(url, headers=DEFAULT_HEADERS, stream=True, timeout=30, allow_redirects=True)
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
            return descargar_directo(download_url, destino, verbose)

        # Intento simple con parámetro de descarga
        dl_url = url + ('&' if '?' in url else '?') + 'dl=1'
        return descargar_directo(dl_url, destino, verbose)

    except requests.exceptions.HTTPError as e:
        if verbose:
            print(f"    ⚠️ HTTP {e.response.status_code}")
        return None, False
    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error VK: {e}")
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


def descargar_google_drive(url, destino, verbose=True):
    """Descarga un archivo público de Google Drive"""
    try:
        file_id = _gdrive_extraer_id(url)
        if not file_id:
            if verbose:
                print("    ⚠️ No se pudo extraer el ID de Google Drive")
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
                timeout=300,
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
                    print("    ⚠️ Google Drive requiere confirmación/cookies (archivo grande o restringido)")
                return None, False

            filepath, parcial = _guardar_respuesta(resp, destino, verbose)
            if filepath:
                return filepath, False
            if parcial:
                if verbose:
                    print("    ⚠️ Descarga incompleta, reintentando...")
                if MAX_REINTENTOS_PARCIALES and intentos >= MAX_REINTENTOS_PARCIALES:
                    return None, True
                time.sleep(DELAY_REINTENTO_DESCARGA)
                continue
            return None, False

    except requests.exceptions.HTTPError as e:
        if verbose:
            print(f"    ⚠️ HTTP {e.response.status_code}")
        return None, False
    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error Google Drive: {e}")
        return None, False


def descargar_yandex_disk(url, destino, verbose=True):
    """Descarga un archivo público de Yandex Disk usando su API pública"""
    try:
        api_url = 'https://cloud-api.yandex.net/v1/disk/public/resources/download'
        resp = requests.get(api_url, params={'public_key': url}, headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        href = data.get('href')
        if not href:
            if verbose:
                print("    ⚠️ No se encontró link directo en Yandex Disk")
            return None, False
        return descargar_directo(href, destino, verbose)
    except requests.exceptions.HTTPError as e:
        if verbose:
            print(f"    ⚠️ HTTP {e.response.status_code}")
        return None, False
    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error Yandex Disk: {e}")
        return None, False


def descargar_pcloud(url, destino, verbose=True):
    """Descarga un archivo público de pCloud"""
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        code = qs.get('code', [None])[0]
        if not code:
            match = re.search(r'code=([A-Za-z0-9]+)', url)
            code = match.group(1) if match else None

        if code:
            api_resp = requests.get(
                'https://api.pcloud.com/getpublinkdownload',
                params={'code': code},
                headers=DEFAULT_HEADERS,
                timeout=30,
            )
            api_resp.raise_for_status()
            data = api_resp.json()
            hosts = data.get('hosts')
            path = data.get('path')
            if hosts and path:
                download_url = f"https://{hosts[0]}{path}"
                return descargar_directo(download_url, destino, verbose)

        # Fallback a URL "download"
        if 'publink/show' in url:
            url = url.replace('/publink/show', '/publink/download')
        if 'download' not in url:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            qs['download'] = ['1']
            url = urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))

        return descargar_directo(url, destino, verbose)
    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error pCloud: {e}")
        return None, False


def descargar_mailru(url, destino, verbose=True):
    """Descarga un archivo público de Mail.ru Cloud"""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()

        content_type = resp.headers.get('content-type', '').lower()
        if 'text/html' in content_type:
            html = resp.text
            match = re.search(r'"downloadUrl":"([^"]+)"', html)
            if not match:
                match = re.search(r'href="(https?://[^"]+mail\.ru/[^"]+/download[^"]*)"', html)
            if match:
                download_url = match.group(1).replace('\\/', '/')
                return descargar_directo(download_url, destino, verbose)

        # Fallback: parámetro download=1
        if 'download=1' not in url:
            sep = '&' if '?' in url else '?'
            url = f"{url}{sep}download=1"
        return descargar_directo(url, destino, verbose)
    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error Mail.ru: {e}")
        return None, False


def _icedrive_extraer_public_id(url):
    parsed = urlparse(url)
    path = parsed.path.strip('/')
    if path.startswith('s/'):
        return path.split('/', 1)[1]
    if path.startswith('0/'):
        return path.split('/', 1)[1]
    return None


def descargar_icedrive(url, destino, verbose=True):
    """Descarga un archivo público de Icedrive resolviendo el link real desde HTML"""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, stream=True, timeout=30, allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get('content-type', '').lower()
        if 'text/html' not in content_type:
            filepath, parcial = _guardar_respuesta(resp, destino, verbose)
            return filepath, parcial

        html = resp.text
        patrones = [
            r'data-download-url="([^"]+)"',
            r'"downloadUrl"\\s*:\\s*"([^"]+)"',
            r'"download_url"\\s*:\\s*"([^"]+)"',
            r'href="([^"]+download[^"]+)"',
            r'(https?://[^"\\s]+icedrive\\.net/[^"\\s]+)',
        ]
        download_url = _buscar_url_en_html(html, patrones, base_url=url)
        if download_url and download_url != url:
            return descargar_directo(download_url, destino, verbose, headers={'Referer': url})

        # Fallback: buscar URLs embebidas con "download"
        candidatos = re.findall(r'(https?:\\\\/\\\\/[^"\\s]+)', html)
        for cand in candidatos:
            cand = _normalizar_url(cand)
            if cand and 'icedrive.net' in cand and 'download' in cand:
                return descargar_directo(cand, destino, verbose, headers={'Referer': url})

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
                archivo, parcial = descargar_directo(candidato, destino, verbose, headers={'Referer': url})
                if archivo:
                    return archivo, parcial

        # Fallback con Playwright si la página requiere JS
        download_url = _resolver_playwright_download_url(url, verbose)
        if download_url:
            return descargar_directo(download_url, destino, verbose, headers={'Referer': url})

        if verbose:
            print("    ⚠️ No se encontró enlace directo en Icedrive")
        return None, False
    except requests.exceptions.HTTPError as e:
        if verbose:
            print(f"    ⚠️ HTTP {e.response.status_code}")
        return None, False
    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error Icedrive: {e}")
        return None, False


def descargar_krakenfiles(url, destino, verbose=True):
    """Descarga un archivo de Krakenfiles resolviendo el link real desde HTML"""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, stream=True, timeout=30, allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get('content-type', '').lower()
        if 'text/html' not in content_type:
            filepath, parcial = _guardar_respuesta(resp, destino, verbose)
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
            archivo, parcial = descargar_directo(candidate, destino, verbose, headers={'Referer': url})
            if archivo:
                return archivo, parcial

        if download_url:
            return descargar_directo(download_url, destino, verbose, headers={'Referer': url})

        if verbose:
            print("    ⚠️ No se encontró enlace directo en Krakenfiles")
        return None, False
    except requests.exceptions.HTTPError as e:
        if verbose:
            print(f"    ⚠️ HTTP {e.response.status_code}")
        return None, False
    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error Krakenfiles: {e}")
        return None, False


def descargar_workupload(url, destino, verbose=True):
    """Descarga un archivo de Workupload resolviendo el link real desde HTML"""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
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
            if verbose:
                print("    ⚠️ No se encontró enlace directo en Workupload")
            return None, False

        return descargar_directo(download_url, destino, verbose)
    except requests.exceptions.HTTPError as e:
        if verbose:
            print(f"    ⚠️ HTTP {e.response.status_code}")
        return None, False
    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error Workupload: {e}")
        return None, False


def descargar_wetransfer(url, destino, verbose=True):
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
        return descargar_directo(download_url, destino, verbose, headers={'Referer': url})
    if verbose:
        print("    ⚠️ WeTransfer requiere navegador/JS (no soportado)")
    return None, False


def descargar_directo(url, destino, verbose=True, headers=None):
    """Descarga un archivo directo por HTTP (funciona con la mayoría de servicios)
    Retorna: (filepath, parcial)
    """
    intentos = 0
    while True:
        intentos += 1
        try:
            req_headers = DEFAULT_HEADERS.copy()
            if headers:
                req_headers.update(headers)
            # Permitir redirecciones
            response = requests.get(url, headers=req_headers, stream=True, timeout=300, allow_redirects=True)
            response.raise_for_status()

            # Verificar que no sea una página HTML (debe ser un archivo)
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' in content_type:
                # Es una página HTML, no un archivo descargable
                if verbose:
                    print(f"    ⚠️ Página HTML (requiere navegador)")
                return None, False

            filepath, parcial = _guardar_respuesta(response, destino, verbose)
            if filepath:
                return filepath, False

            if parcial:
                if verbose:
                    print("    ⚠️ Descarga incompleta, reintentando...")
                if MAX_REINTENTOS_PARCIALES and intentos >= MAX_REINTENTOS_PARCIALES:
                    return None, True
                time.sleep(DELAY_REINTENTO_DESCARGA)
                continue

            return None, False

        except requests.exceptions.HTTPError as e:
            if verbose:
                print(f"    ⚠️ HTTP {e.response.status_code}")
            return None, False
        except Exception as e:
            if verbose:
                error_msg = str(e)[:50]
                print(f"    ⚠️ {error_msg}")
            return None, False


def descargar_link(url, destino, password=None, verbose=True, skip_mega=False):
    """
    Descarga un archivo según el tipo de enlace
    Retorna: (filepath, skip_mega, parcial)
    """
    if not re.match(r'^https?://', url or ''):
        if verbose:
            print("    ⚠️ URL inválida")
        return None, False, False

    tipo = detectar_tipo_link(url)

    os.makedirs(destino, exist_ok=True)

    if tipo == 'mega':
        if skip_mega:
            if verbose:
                print(f"    ⏭️ Saltando Mega (límite/timeout)")
            return None, True, False
        archivo, new_skip_mega = descargar_mega(url, destino, password, verbose)
        return archivo, new_skip_mega, False
    elif tipo == 'mediafire':
        archivo, parcial = descargar_mediafire(url, destino, verbose)
        return archivo, False, parcial
    elif tipo == 'vkdoc':
        archivo, parcial = descargar_vk_doc(url, destino, verbose)
        return archivo, False, parcial
    elif tipo == 'gdrive':
        archivo, parcial = descargar_google_drive(url, destino, verbose)
        return archivo, False, parcial
    elif tipo == 'yandex':
        archivo, parcial = descargar_yandex_disk(url, destino, verbose)
        return archivo, False, parcial
    elif tipo == 'pcloud':
        archivo, parcial = descargar_pcloud(url, destino, verbose)
        return archivo, False, parcial
    elif tipo == 'mailru':
        archivo, parcial = descargar_mailru(url, destino, verbose)
        return archivo, False, parcial
    elif tipo == 'workupload':
        archivo, parcial = descargar_workupload(url, destino, verbose)
        return archivo, False, parcial
    elif tipo == 'icedrive':
        archivo, parcial = descargar_icedrive(url, destino, verbose)
        return archivo, False, parcial
    elif tipo == 'krakenfiles':
        archivo, parcial = descargar_krakenfiles(url, destino, verbose)
        return archivo, False, parcial
    elif tipo == 'wetransfer':
        archivo, parcial = descargar_wetransfer(url, destino, verbose)
        return archivo, False, parcial
    elif tipo == 'dead':
        if verbose:
            print(f"    ⚠️ Servicio cerrado/muerto")
        return None, False, False
    else:
        # Intentar descarga directa para cualquier otro enlace
        archivo, parcial = descargar_directo(url, destino, verbose)
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
                    print(f"    → Usando 7z para ZIP moderno...")
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
                tf.extractall(destino)
            return True

        else:
            if verbose:
                print(f"    ⚠️ Formato no soportado: {ext}")
            return False

    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error extrayendo: {e}")
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
            print("    ⚠️ No se encontraron archivos de audio")
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
        print(f"    ✓ Guardado en: {os.path.basename(destino_real)}")

    return True


def procesar_release(release, destino_base=DESTINO_BASE, temp_dir=TEMP_DIR, verbose=True,
                     descargados=None, fallidos_bandas=None):
    """Procesa un release completo: descarga, extrae y organiza"""
    links = release.get('download_links', [])
    post_id = str(release.get('post_id', ''))
    band = release.get('band', 'Unknown')
    album = release.get('album', 'Unknown')
    band_id = str(release.get('band_id', ''))

    if not links:
        return False, "Sin links", None

    # Banda fallida anteriormente?
    if fallidos_bandas and band_id in fallidos_bandas:
        if verbose:
            print(f"  ⏭️  Banda en fallidos: {band} (id {band_id})")
        return True, "Fallido previo", None

    # Ya descargado anteriormente?
    if descargados and release_ya_descargado(release, descargados):
        if verbose:
            print(f"  ⏭️  Ya descargado: {band} - {album}")
        return True, "Ya descargado", None

    nombre_carpeta = generar_nombre_carpeta(release)
    destino_final = os.path.join(destino_base, nombre_carpeta)

    # Ya existe en disco?
    if os.path.exists(destino_final):
        if verbose:
            print(f"  ⏭️  Ya existe: {nombre_carpeta}")
        return True, "Ya existe", None

    if verbose:
        print(f"\n📥 {band} - {album}")

    # Intentar cada link hasta que uno funcione
    skip_mega = False  # Se activa si Mega tiene límite/timeout

    tuvo_parcial = False
    mega_omitido_por_cooldown = False

    for link_info in links:
        url = link_info.get('url', '')
        password = link_info.get('password', '')

        if not url:
            continue

        tipo = detectar_tipo_link(url)
        if verbose:
            print(f"  → Intentando {tipo}: {url[:60]}...")

        if tipo == 'mega' and _mega_cooldown_activo():
            mega_omitido_por_cooldown = True
            if verbose:
                restante = _mega_cooldown_restante()
                if restante > 0:
                    print(f"    ⏭️ Saltando Mega (cooldown {restante}s)")
                else:
                    print("    ⏭️ Saltando Mega (cooldown activo)")
            continue

        # Crear directorio temporal único
        temp_release = tempfile.mkdtemp(dir=temp_dir)
        temp_download = os.path.join(temp_release, 'download')
        temp_extract = os.path.join(temp_release, 'extract')

        try:
            # 1. Descargar
            archivo, new_skip_mega, parcial = descargar_link(url, temp_download, password, verbose, skip_mega)
            if parcial and not archivo:
                tuvo_parcial = True

            # Actualizar skip_mega si Mega falló por límite/timeout
            if new_skip_mega:
                skip_mega = True
                if tipo == 'mega' and _mega_cooldown_activo():
                    mega_omitido_por_cooldown = True

            if not archivo or not os.path.exists(archivo):
                if verbose and not new_skip_mega and not parcial:
                    print("    ✗ Descarga fallida")
                continue

            if verbose:
                size_mb = os.path.getsize(archivo) / (1024 * 1024)
                print(f"    ✓ Descargado: {size_mb:.1f} MB")

            # Ajustar extensión si el archivo es audio directo
            archivo = _ajustar_extension_audio(archivo, verbose)
            # Ajustar extensión si es comprimido con extensión incorrecta
            archivo = _ajustar_extension_comprimido(archivo, verbose)

            # 2. Extraer si está comprimido
            ext = _ext_compuesta(archivo)

            if ext in EXTENSIONES_COMPRIMIDAS:
                if verbose:
                    print("    Extrayendo...")

                if not _archivo_es_comprimido(archivo, ext):
                    if verbose:
                        print("    ⚠️ Archivo no parece comprimido, se omite extracción")
                    origen = temp_download
                else:
                    if not extraer_archivo(archivo, temp_extract, password, verbose):
                        if verbose:
                            print("    ✗ Extracción fallida")
                        continue
                    origen = temp_extract
            else:
                # No está comprimido, usar directamente
                origen = temp_download

            # 3. Organizar en destino final
            if organizar_carpeta(origen, destino_final, verbose):
                # Retornar info para guardar en lista de descargados
                return True, "OK", {'post_id': post_id, 'band': band, 'album': album}

        except Exception as e:
            if verbose:
                print(f"    ✗ Error: {e}")

        finally:
            # Limpiar temporal
            try:
                shutil.rmtree(temp_release, ignore_errors=True)
            except:
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
    Ejecuta el proceso de descarga y organización

    Args:
        destino_base: Directorio donde guardar los releases
        verbose: Mostrar progreso
        limit: Límite de releases a procesar (None = todos)
    """
    if verbose:
        print("=" * 60)
        print("📦 DESCARGA Y ORGANIZACIÓN DE RELEASES")
        print("=" * 60)

    # Verificar destino
    if not os.path.exists(destino_base):
        print(f"⚠️  El directorio destino no existe: {destino_base}")
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
        print(f"📋 {len(descargados)} releases ya descargados (serán omitidos)")

    # Cargar lista de bandas fallidas
    fallidos_bandas = cargar_fallidos()
    if verbose and fallidos_bandas:
        print(f"🧾 {len(fallidos_bandas)} bandas con links fallidos (serán omitidas)")

    # Cargar cola de Mega pendientes
    mega_pendientes = cargar_mega_pendientes()
    mega_pendientes_ids = set()
    for r in mega_pendientes:
        pid = str(r.get('post_id', '')).strip()
        if pid:
            mega_pendientes_ids.add(pid)
    if verbose and mega_pendientes:
        print(f"⏳ {len(mega_pendientes)} releases con Mega pendientes (reanudarán cuando termine el cooldown)")

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
        print(f"\n📊 {len(con_links)} releases con links de descarga")
        print(f"📁 Destino: {destino_base}")

    if limit:
        con_links = con_links[:limit]
        if verbose:
            print(f"⚠️  Limitado a {limit} releases")

    # Procesar
    exitosos = 0
    fallidos = 0
    omitidos = 0
    pendientes = 0

    def encolar_mega(release_mega):
        nonlocal pendientes
        if not release_mega:
            return
        pid = str(release_mega.get('post_id', '')).strip()
        if pid and pid in mega_pendientes_ids:
            return
        mega_pendientes.append(release_mega)
        if pid:
            mega_pendientes_ids.add(pid)
        pendientes += 1
        if verbose:
            print("  ⏳ Encolado para reintento Mega")

    def procesar_cola_mega():
        nonlocal exitosos, fallidos, omitidos
        # Procesar pendientes solo cuando el cooldown terminó
        while mega_pendientes and not _mega_cooldown_activo():
            release_m = mega_pendientes.pop(0)
            pid = str(release_m.get('post_id', '')).strip()
            if pid and pid in mega_pendientes_ids:
                mega_pendientes_ids.remove(pid)

            if verbose:
                print(f"\n[MEGA] Reintentando: {release_m.get('band', 'Unknown')} - {release_m.get('album', 'Unknown')}")

            exito, mensaje, info = procesar_release(
                release_m, destino_base, TEMP_DIR, verbose, descargados, fallidos_bandas
            )

            if exito:
                if mensaje in ["Ya existe", "Ya descargado", "Fallido previo"]:
                    omitidos += 1
                else:
                    exitosos += 1
                    if info:
                        guardar_descargado(info['post_id'], info['band'], info['album'])
                        descargados.add(info['post_id'])
                continue

            if mensaje == "Mega pendiente":
                # Cooldown volvió a activarse, re-encolar y salir
                encolar_mega(info or release_m)
                break

            fallidos += 1
            if mensaje != "Descarga parcial":
                guardar_fallido(release_m, fallidos_bandas, motivo=mensaje)

        # Si cooldown activo, informar una vez
        if mega_pendientes and _mega_cooldown_activo() and verbose:
            restante = _mega_cooldown_restante()
            if restante > 0:
                print(f"⏳ Mega en cooldown, pendientes: {len(mega_pendientes)} (reanuda en {restante}s)")

    for i, release in enumerate(con_links):
        if verbose:
            print(f"\n[{i+1}/{len(con_links)}]", end='')

        try:
            exito, mensaje, info = procesar_release(
                release, destino_base, TEMP_DIR, verbose, descargados, fallidos_bandas
            )

            if exito:
                if mensaje in ["Ya existe", "Ya descargado", "Fallido previo"]:
                    omitidos += 1
                else:
                    exitosos += 1
                    # Guardar en lista de descargados
                    if info:
                        guardar_descargado(info['post_id'], info['band'], info['album'])
                        descargados.add(info['post_id'])
            else:
                if mensaje == "Mega pendiente":
                    encolar_mega(info)
                else:
                    fallidos += 1
                    # Registrar banda fallida para omitir en futuras ejecuciones
                    if mensaje != "Descarga parcial":
                        guardar_fallido(release, fallidos_bandas, motivo=mensaje)

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrumpido por el usuario")
            guardar_mega_pendientes(mega_pendientes)
            break
        except Exception as e:
            fallidos += 1
            if verbose:
                print(f"  ✗ Error inesperado: {e}")

        # Pausa entre descargas
        time.sleep(DELAY_ENTRE_DESCARGAS)

        # Si Mega está disponible, procesar pendientes
        if mega_pendientes and not _mega_cooldown_activo():
            procesar_cola_mega()

    # Procesar pendientes al final si el cooldown terminó
    if mega_pendientes and not _mega_cooldown_activo():
        procesar_cola_mega()

    # Guardar pendientes restantes en disco
    guardar_mega_pendientes(mega_pendientes)

    # Limpiar temporal
    try:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
    except:
        pass

    # Resumen
    if verbose:
        print("\n" + "=" * 60)
        print("📊 RESUMEN")
        print("=" * 60)
        print(f"✓ Exitosos: {exitosos}")
        print(f"⏭️  Omitidos (ya existían): {omitidos}")
        print(f"✗ Fallidos: {fallidos}")
        if mega_pendientes:
            print(f"⏳ Pendientes Mega: {len(mega_pendientes)} (guardados en {MEGA_PENDIENTES_FILE})")
        print(f"\n📁 Archivos en: {destino_base}")


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
