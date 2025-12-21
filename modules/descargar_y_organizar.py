#!/usr/bin/env python3
"""
Módulo: Descarga, extrae y organiza los releases
Entrada: data/repertorio_con_links.json
Salida: Archivos organizados en el directorio destino

Soporta:
  - Mega.nz
  - Mediafire
  - Google Drive
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
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote

# Configuración
INPUT_FILE = "data/repertorio_con_links.json"
DESTINO_BASE = "/run/media/banar/Entretenimiento/01_edicion_automatizada/01_limpieza_de_impurezas"
TEMP_DIR = "/tmp/deathgrind_downloads"
DESCARGADOS_FILE = "data/descargados.txt"  # Lista de releases ya descargados

# Configuración de rate limiting
DELAY_ENTRE_DESCARGAS = 2.0  # Segundos entre cada descarga

# Extensiones de archivos comprimidos
EXTENSIONES_COMPRIMIDAS = {'.zip', '.rar', '.7z', '.tar', '.tar.gz', '.tgz', '.tar.bz2'}

# Extensiones de audio (para verificar extracción exitosa)
EXTENSIONES_AUDIO = {'.mp3', '.flac', '.wav', '.ogg', '.m4a', '.aac', '.wma'}


def cargar_repertorio(input_file=INPUT_FILE):
    """Carga el repertorio con links"""
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"No existe {input_file}")

    with open(input_file, 'r', encoding='utf-8') as f:
        return json.load(f)


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


def limpiar_nombre(nombre):
    """Limpia un nombre para usarlo como nombre de carpeta"""
    # Remover caracteres no válidos para sistemas de archivos
    nombre = re.sub(r'[<>:"/\\|?*]', '', nombre)
    # Remover espacios múltiples
    nombre = re.sub(r'\s+', ' ', nombre)
    # Remover puntos al final (Windows no los permite)
    nombre = nombre.rstrip('.')
    return nombre.strip()


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

    if 'mega.nz' in url_lower or 'mega.co.nz' in url_lower:
        return 'mega'
    elif 'mediafire.com' in url_lower:
        return 'mediafire'
    elif 'drive.google.com' in url_lower:
        return 'gdrive'
    elif 'cdn2.deathgrind.club' in url_lower or 'cdn.deathgrind.club' in url_lower:
        return 'direct'  # Enlaces directos del CDN
    elif 'zippyshare.com' in url_lower:
        return 'zippyshare'  # Zippyshare cerró en 2023
    elif 'krakenfiles.com' in url_lower:
        return 'krakenfiles'
    elif 'pixeldrain.com' in url_lower:
        return 'pixeldrain'
    elif any(ext in url_lower for ext in ['.zip', '.rar', '.7z']):
        return 'direct'
    else:
        return 'unknown'


def descargar_mega(url, destino, password=None, verbose=True):
    """Descarga un archivo de Mega.nz usando megadl"""
    try:
        # Asegurar que la URL tenga la clave de encriptación
        # Formato: https://mega.nz/file/ID#KEY o https://mega.nz/#!ID!KEY
        if '#' not in url and '!' not in url:
            if verbose:
                print("    ⚠️ URL de Mega sin clave de encriptación")
            return None

        # megadl necesita la URL completa con la clave
        cmd = ['megadl', '--path', destino, '--print-names', url]

        # Timeout más largo para archivos grandes (30 minutos)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

        if result.returncode == 0:
            # megadl con --print-names imprime el nombre del archivo
            filename = result.stdout.strip().split('\n')[-1] if result.stdout else None

            if filename and os.path.exists(os.path.join(destino, filename)):
                return os.path.join(destino, filename)

            # Fallback: buscar el archivo más reciente en el destino
            for f in os.listdir(destino):
                filepath = os.path.join(destino, f)
                if os.path.isfile(filepath):
                    return filepath

            return None
        else:
            error_msg = result.stderr.strip() if result.stderr else "Error desconocido"
            if verbose:
                # Mostrar solo la primera línea del error
                first_line = error_msg.split('\n')[0][:80]
                print(f"    ⚠️ megadl: {first_line}")
            return None

    except FileNotFoundError:
        if verbose:
            print("    ⚠️ megadl no instalado")
        return None
    except subprocess.TimeoutExpired:
        if verbose:
            print("    ⚠️ Timeout (archivo muy grande, intentar manualmente)")
        return None
    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error Mega: {e}")
        return None


def descargar_mediafire(url, destino, verbose=True):
    """Descarga un archivo de Mediafire"""
    try:
        # Obtener página de descarga
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/131.0.0.0 Safari/537.36'
        }

        response = requests.get(url, headers=headers, timeout=30)

        # Buscar el enlace directo de descarga
        # Mediafire tiene un botón con id="downloadButton" y href con el link real
        match = re.search(r'href="(https://download\d*\.mediafire\.com/[^"]+)"', response.text)

        if not match:
            # Intentar otro patrón
            match = re.search(r'aria-label="Download file"\s+href="([^"]+)"', response.text)

        if match:
            download_url = match.group(1)
            return descargar_directo(download_url, destino, verbose)
        else:
            if verbose:
                print("    ⚠️ No se encontró enlace directo en Mediafire")
            return None

    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error Mediafire: {e}")
        return None


def descargar_directo(url, destino, verbose=True):
    """Descarga un archivo directo por HTTP"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/131.0.0.0 Safari/537.36'
        }

        response = requests.get(url, headers=headers, stream=True, timeout=300)
        response.raise_for_status()

        # Obtener nombre del archivo
        if 'content-disposition' in response.headers:
            cd = response.headers['content-disposition']
            match = re.search(r'filename[*]?=["\']?(?:UTF-8\'\')?([^"\';]+)', cd)
            if match:
                filename = unquote(match.group(1))
            else:
                filename = 'download.zip'
        else:
            # Usar el nombre de la URL
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path) or 'download.zip'

        filepath = os.path.join(destino, limpiar_nombre(filename))

        # Descargar con progreso
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

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

        return filepath

    except Exception as e:
        if verbose:
            print(f"    ⚠️ Error descarga directa: {e}")
        return None


def descargar_link(url, destino, password=None, verbose=True):
    """Descarga un archivo según el tipo de enlace"""
    tipo = detectar_tipo_link(url)

    os.makedirs(destino, exist_ok=True)

    if tipo == 'mega':
        return descargar_mega(url, destino, password, verbose)
    elif tipo == 'mediafire':
        return descargar_mediafire(url, destino, verbose)
    elif tipo == 'direct':
        return descargar_directo(url, destino, verbose)
    else:
        if verbose:
            print(f"    ⚠️ Tipo de enlace no soportado: {tipo}")
        return None


def extraer_archivo(filepath, destino, password=None, verbose=True):
    """Extrae un archivo comprimido"""
    if not os.path.exists(filepath):
        return False

    ext = os.path.splitext(filepath)[1].lower()
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


def procesar_release(release, destino_base=DESTINO_BASE, temp_dir=TEMP_DIR, verbose=True, descargados=None):
    """Procesa un release completo: descarga, extrae y organiza"""
    links = release.get('download_links', [])
    post_id = str(release.get('post_id', ''))
    band = release.get('band', 'Unknown')
    album = release.get('album', 'Unknown')

    if not links:
        return False, "Sin links", None

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
    for link_info in links:
        url = link_info.get('url', '')
        password = link_info.get('password', '')

        if not url:
            continue

        tipo = detectar_tipo_link(url)
        if verbose:
            print(f"  → Intentando {tipo}: {url[:60]}...")

        # Crear directorio temporal único
        temp_release = tempfile.mkdtemp(dir=temp_dir)
        temp_download = os.path.join(temp_release, 'download')
        temp_extract = os.path.join(temp_release, 'extract')

        try:
            # 1. Descargar
            archivo = descargar_link(url, temp_download, password, verbose)

            if not archivo or not os.path.exists(archivo):
                if verbose:
                    print("    ✗ Descarga fallida")
                continue

            if verbose:
                size_mb = os.path.getsize(archivo) / (1024 * 1024)
                print(f"    ✓ Descargado: {size_mb:.1f} MB")

            # 2. Extraer si está comprimido
            ext = os.path.splitext(archivo)[1].lower()

            if ext in EXTENSIONES_COMPRIMIDAS:
                if verbose:
                    print("    Extrayendo...")

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

    # Cargar repertorio
    repertorio = cargar_repertorio()

    # Filtrar solo los que tienen links
    con_links = [r for r in repertorio if r.get('download_links')]

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

    for i, release in enumerate(con_links):
        if verbose:
            print(f"\n[{i+1}/{len(con_links)}]", end='')

        try:
            exito, mensaje, info = procesar_release(
                release, destino_base, TEMP_DIR, verbose, descargados
            )

            if exito:
                if mensaje in ["Ya existe", "Ya descargado"]:
                    omitidos += 1
                else:
                    exitosos += 1
                    # Guardar en lista de descargados
                    if info:
                        guardar_descargado(info['post_id'], info['band'], info['album'])
                        descargados.add(info['post_id'])
            else:
                fallidos += 1

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrumpido por el usuario")
            break
        except Exception as e:
            fallidos += 1
            if verbose:
                print(f"  ✗ Error inesperado: {e}")

        # Pausa entre descargas
        time.sleep(DELAY_ENTRE_DESCARGAS)

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
