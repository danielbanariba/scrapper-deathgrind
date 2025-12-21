#!/usr/bin/env python3
"""
Módulo 4: Extrae links de descarga via API (PARALELO)
Entrada: data/repertorio_filtrado.json
Salida: data/links_descarga.txt, data/repertorio_con_links.json

NOTA: Usa el endpoint /api/posts/{post_id}/links para obtener los links directamente
"""

import requests
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Configuración
BASE_URL = "https://deathgrind.club"
API_URL = f"{BASE_URL}/api"
INPUT_FILE = "data/repertorio_filtrado.json"
OUTPUT_JSON = "data/repertorio_con_links.json"
OUTPUT_TXT = "data/links_descarga.txt"
OUTPUT_DETALLE = "data/discografia_detalle.txt"

# Configuración de rate limiting (ajustable)
DELAY_ENTRE_REQUESTS = 0.5     # Segundos entre cada request
DELAY_BASE_429 = 30            # Segundos base cuando hay rate limit

# Lock para thread safety
print_lock = threading.Lock()


def cargar_env():
    """Carga variables de entorno desde .env"""
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                if '=' in line:
                    key, val = line.strip().split('=', 1)
                    os.environ[key] = val


def crear_sesion_autenticada(max_retries=3):
    """Login con retry para manejar rate limiting"""
    email = os.environ.get('DEATHGRIND_EMAIL')
    password = os.environ.get('DEATHGRIND_PASSWORD')

    if not email or not password:
        raise ValueError("Faltan credenciales en .env")

    for intento in range(max_retries):
        try:
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'application/json',
            })

            session.get(f"{BASE_URL}/auth/sign-in")
            cookies = session.cookies.get_dict()
            csrf_token = cookies.get('csrfToken', '')

            login_data = {"login": email, "password": password}
            headers = {'x-csrf-token': csrf_token, 'x-uuid': '12345'}
            response = session.post(f"{API_URL}/auth/login", json=login_data, headers=headers)

            if response.status_code in [200, 202]:
                cookies = session.cookies.get_dict()
                csrf_token = cookies.get('csrfToken', '')
                session.headers.update({'x-csrf-token': csrf_token, 'x-uuid': '12345'})
                return session

            if response.status_code == 429:
                wait = (intento + 1) * 10
                print(f"   ⚠️ Rate limited, esperando {wait}s...")
                time.sleep(wait)
                continue

            raise ConnectionError(f"Error de login: {response.status_code}")

        except requests.exceptions.RequestException as e:
            if intento < max_retries - 1:
                time.sleep(5)
                continue
            raise

    raise ConnectionError("No se pudo conectar después de varios intentos")


def cargar_repertorio(input_file=INPUT_FILE):
    """Carga el repertorio desde JSON"""
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"No existe {input_file}")

    with open(input_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def preparar_session_data(session):
    """Prepara datos de sesión para workers"""
    return {
        'headers': dict(session.headers),
        'cookies': [{'name': k, 'value': v} for k, v in session.cookies.items()]
    }


def extraer_links_post(session_data, release, max_retries=10):
    """
    Extrae links de descarga de un post via API

    Args:
        session_data: Datos de sesión para crear la conexión
        release: Diccionario con datos del release
        max_retries: Número de reintentos en caso de error

    Returns:
        tuple: (release_actualizado, num_links)
    """
    post_id = release.get('post_id')

    # Crear sesión para este request
    session = requests.Session()
    session.headers.update(session_data['headers'])
    for cookie in session_data['cookies']:
        session.cookies.set(cookie['name'], cookie['value'])

    retries_429 = 0
    retries_error = 0

    while retries_error < max_retries:
        try:
            # Pequeña pausa para no saturar
            time.sleep(DELAY_ENTRE_REQUESTS)

            # Obtener links via API
            response = session.get(
                f"{API_URL}/posts/{post_id}/links",
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                links = data.get('links', [])

                # Convertir al formato esperado
                download_links = []
                for link in links:
                    download_links.append({
                        'url': link.get('href', ''),
                        'text': link.get('text', 'Download'),
                        'quality': link.get('quality', 0),
                        'password': link.get('password', '')
                    })

                release['download_links'] = download_links
                return release, len(download_links)

            elif response.status_code == 429:
                # Rate limiting - esperar y reintentar indefinidamente
                retries_429 += 1
                wait = DELAY_BASE_429 * retries_429
                with print_lock:
                    print(f"    ⏳ Rate limited en links, esperando {wait}s...")
                time.sleep(wait)
                continue

            elif response.status_code == 404:
                # No hay links para este post
                release['download_links'] = []
                return release, 0

            else:
                retries_error += 1
                time.sleep(5)
                continue

        except requests.exceptions.RequestException:
            retries_error += 1
            time.sleep(5)
            continue

    release['download_links'] = []
    return release, 0


def extraer_links_paralelo(session, repertorio, num_workers=10, verbose=True):
    """
    Extrae links de descarga para todos los releases (PARALELO via API)

    Args:
        session: Sesión autenticada
        repertorio: Lista de releases
        num_workers: Número de workers paralelos
        verbose: Mostrar progreso

    Returns:
        list: Repertorio con links agregados
    """
    session_data = preparar_session_data(session)

    total = len(repertorio)
    procesados = 0
    con_links = 0

    if verbose:
        print(f"\n🔗 Extrayendo links con {num_workers} workers...")

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Crear tareas
        futures = {
            executor.submit(extraer_links_post, session_data, release): idx
            for idx, release in enumerate(repertorio)
        }

        for future in as_completed(futures):
            procesados += 1
            try:
                release, num_links = future.result()

                # Actualizar repertorio
                idx = futures[future]
                repertorio[idx] = release

                if num_links > 0:
                    con_links += 1
                    if verbose:
                        band = release.get('band', 'Unknown')
                        album = release.get('album', 'Unknown')
                        year = release.get('year', '')
                        year_str = f"({year})" if year else ""
                        with print_lock:
                            print(f"[{procesados}/{total}] {band} - {album} {year_str} ✓ {num_links} link(s)")
                else:
                    if verbose and procesados % 20 == 0:
                        with print_lock:
                            pct = (procesados / total) * 100
                            print(f"[{procesados}/{total}] ({pct:.0f}%) - {con_links} con links")

            except Exception as e:
                pass

    if verbose:
        print(f"\n✓ {procesados} releases procesados")

    return repertorio


def guardar_resultados(repertorio, output_json=OUTPUT_JSON, output_txt=OUTPUT_TXT,
                       output_detalle=OUTPUT_DETALLE, verbose=True):
    """Guarda los resultados en múltiples formatos"""
    os.makedirs(os.path.dirname(output_json), exist_ok=True)

    # JSON completo
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(repertorio, f, indent=2, ensure_ascii=False)

    # TXT solo links (para descarga masiva)
    with open(output_txt, 'w', encoding='utf-8') as f:
        for release in repertorio:
            for link in release.get('download_links', []):
                url = link.get('url', '')
                if url:
                    f.write(f"{url}\n")

    # TXT detallado
    with open(output_detalle, 'w', encoding='utf-8') as f:
        for release in repertorio:
            links = release.get('download_links', [])
            if links:
                year = f"({release['year']})" if release.get('year') else ""
                tipo = f"[{release['type']}]" if release.get('type') else ""

                f.write(f"\n{'=' * 60}\n")
                f.write(f"{release['band']} - {release['album']} {year} {tipo}\n")
                f.write(f"URL: {release['post_url']}\n")
                f.write(f"\nLINKS DE DESCARGA:\n")

                for link in links:
                    quality = link.get('quality', 0)
                    quality_str = f"[Q:{quality}]" if quality else ""
                    password = link.get('password', '')
                    pwd_str = f" (pwd: {password})" if password else ""
                    f.write(f"  → {link.get('url', '')} {quality_str}{pwd_str}\n")

    if verbose:
        total_links = sum(len(r.get('download_links', [])) for r in repertorio)
        print(f"\n📁 Guardado: {output_json}")
        print(f"📁 Guardado: {output_txt} ({total_links} links)")
        print(f"📁 Guardado: {output_detalle}")


def run(verbose=True, num_workers=None):
    """
    Ejecuta la extracción de links (PARALELO via API)
    """
    if verbose:
        print("=" * 60)
        print("🔗 MÓDULO 3: EXTRACCIÓN DE LINKS (API)")
        print("=" * 60)

    # Auto-detectar workers (conservador para evitar rate limiting)
    if num_workers is None:
        try:
            from modules.utils import detectar_workers_api
            num_workers = min(detectar_workers_api(), 5)  # Máximo 5 para ser conservador
        except:
            num_workers = 3  # Muy conservador por defecto

    cargar_env()

    if verbose:
        print("\n🔐 Iniciando sesión...")
    session = crear_sesion_autenticada()
    if verbose:
        print("✓ Sesión iniciada")

    repertorio = cargar_repertorio()
    if verbose:
        print(f"✓ {len(repertorio)} releases, {num_workers} workers")

    # Extraer links via API
    repertorio_con_links = extraer_links_paralelo(
        session,
        repertorio,
        num_workers=num_workers,
        verbose=verbose
    )

    # Guardar
    guardar_resultados(repertorio_con_links, verbose=verbose)

    # Estadísticas
    if verbose:
        con_links = sum(1 for r in repertorio_con_links if r.get('download_links'))
        total_links = sum(len(r.get('download_links', [])) for r in repertorio_con_links)

        print("\n" + "=" * 60)
        print("📊 RESULTADO")
        print("=" * 60)
        print(f"Releases procesados: {len(repertorio_con_links)}")
        print(f"Releases con links: {con_links}")
        print(f"Total links extraídos: {total_links}")

    return OUTPUT_TXT


if __name__ == "__main__":
    run(num_workers=10)
