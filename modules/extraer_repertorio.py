#!/usr/bin/env python3
"""
Módulo 2: Extrae el repertorio (discografía) via API (PARALELO)
Entrada: data/bandas.json
Salida: data/repertorio.json
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
INPUT_FILE = "data/bandas.json"
OUTPUT_FILE = "data/repertorio.json"

# Tipos de disco
TIPOS_DISCO = {
    1: "Album", 2: "EP", 3: "Demo", 4: "Single",
    5: "Split", 6: "Compilation", 7: "Live"
}

# Lock para escritura thread-safe
print_lock = threading.Lock()


def cargar_env():
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
                wait = (intento + 1) * 10  # 10s, 20s, 30s
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


def cargar_bandas(input_file=INPUT_FILE):
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"No existe {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def cargar_sellos_blacklist():
    sellos = set()
    if os.path.exists('lista_sello.txt'):
        with open('lista_sello.txt', 'r', encoding='utf-8') as f:
            for line in f:
                sello = line.strip().lower()
                if sello:
                    sellos.add(sello)
    return sellos


def filtrar_por_sello(post, sellos_blacklist):
    labels = post.get('label', [])
    for label in labels:
        label_name = str(label).strip().lower()
        if label_name in sellos_blacklist:
            return True, label
    return False, None


def procesar_banda(args):
    """Procesa una banda (worker thread)"""
    session_data, banda, sellos_blacklist, tipos_permitidos = args

    band_id = banda.get('bandId')
    band_name = banda.get('name', 'Unknown')

    if not band_id:
        return band_name, [], 0, 0

    # Crear sesión para este thread
    session = requests.Session()
    session.headers.update(session_data['headers'])
    for cookie in session_data['cookies']:
        session.cookies.set(cookie['name'], cookie['value'])

    # Obtener discografía de la banda (endpoint correcto)
    posts = []
    offset = 0
    while True:
        try:
            r = session.get(
                f"{API_URL}/bands/{band_id}/discography",
                params={'offset': offset} if offset > 0 else None,
                timeout=30
            )
            if r.status_code != 200:
                break

            data = r.json()
            batch = data.get('posts', [])
            if not batch:
                break

            posts.extend(batch)
            if not data.get('hasMore', False):
                break

            offset = data.get('offset', 0)
            if not offset:
                break
            time.sleep(0.2)
        except:
            break

    # Procesar posts
    releases = []
    filtrados = 0

    for post in posts:
        post_id = post.get('postId')
        album = post.get('album', 'Unknown')
        year = post.get('releaseDate', [None])[0] if post.get('releaseDate') else None
        type_ids = post.get('type', [])

        # Obtener nombre de banda del post (más preciso)
        post_bands = post.get('bands', [])
        post_band_name = post_bands[0].get('name', band_name) if post_bands else band_name
        post_band_id = post_bands[0].get('bandId', band_id) if post_bands else band_id

        # Filtrar por tipo
        if tipos_permitidos:
            if not any(tid in tipos_permitidos for tid in type_ids):
                continue

        # Obtener tipo
        tipo = "Release"
        tipo_id = None
        for tid in type_ids:
            if tid in TIPOS_DISCO:
                tipo = TIPOS_DISCO[tid]
                tipo_id = tid
                break

        # Filtrar por sello
        en_blacklist, _ = filtrar_por_sello(post, sellos_blacklist)
        if en_blacklist:
            filtrados += 1
            continue

        releases.append({
            'band': post_band_name,
            'band_id': post_band_id,
            'album': album,
            'year': year,
            'type': tipo,
            'type_id': tipo_id,
            'post_id': post_id,
            'post_url': f"{BASE_URL}/posts/{post_id}"
        })

    return band_name, releases, len(releases), filtrados


def preparar_session_data(session):
    return {
        'headers': dict(session.headers),
        'cookies': [{'name': k, 'value': v} for k, v in session.cookies.items()]
    }


def extraer_repertorio_paralelo(session, bandas, sellos_blacklist, tipos_permitidos, num_workers=15, verbose=True):
    """Extrae repertorio EN PARALELO"""
    session_data = preparar_session_data(session)
    repertorio = []
    total_filtrados = 0

    # Filtrar bandas sin ID
    bandas_con_id = [b for b in bandas if b.get('bandId')]

    if verbose:
        print(f"\n📀 Procesando {len(bandas_con_id)} bandas con {num_workers} workers...")

    args_list = [
        (session_data, banda, sellos_blacklist, tipos_permitidos)
        for banda in bandas_con_id
    ]

    completados = 0
    total = len(bandas_con_id)

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(procesar_banda, args): args[1]['name'] for args in args_list}

        for future in as_completed(futures):
            completados += 1
            try:
                band_name, releases, num_releases, filtrados = future.result()
                repertorio.extend(releases)
                total_filtrados += filtrados

                if verbose and completados % 50 == 0:
                    pct = (completados / total) * 100
                    print(f"[{completados}/{total}] ({pct:.0f}%) → {len(repertorio)} releases")

            except Exception as e:
                pass

    if verbose:
        print(f"\n✓ {completados} bandas procesadas")
        if total_filtrados > 0:
            print(f"🚫 {total_filtrados} releases excluidos por sello")

    return repertorio


def guardar_repertorio(repertorio, output_file=OUTPUT_FILE):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(repertorio, f, indent=2, ensure_ascii=False)
    return output_file


def run(tipos_permitidos=None, filtrar_sellos=True, verbose=True, num_workers=None):
    """Ejecuta la extracción (PARALELO)"""
    if verbose:
        print("=" * 60)
        print("📀 MÓDULO 2: EXTRACCIÓN DE REPERTORIO (Paralelo)")
        print("=" * 60)

    if tipos_permitidos is None:
        tipos_permitidos = [1, 2, 3, 5, 6, 7]  # Todo excepto Singles

    if num_workers is None:
        try:
            from modules.utils import detectar_workers_api
            num_workers = min(detectar_workers_api(), 10)  # Max 10 para API
        except:
            num_workers = 8

    cargar_env()

    if verbose:
        print("\n🔐 Iniciando sesión...")
    session = crear_sesion_autenticada()
    if verbose:
        print("✓ Sesión iniciada")

    bandas = cargar_bandas()
    if verbose:
        print(f"✓ {len(bandas)} bandas, {num_workers} workers")

    sellos_blacklist = set()
    if filtrar_sellos:
        sellos_blacklist = cargar_sellos_blacklist()
        if verbose:
            print(f"✓ {len(sellos_blacklist)} sellos en blacklist")

    if verbose:
        tipos_nombres = [TIPOS_DISCO.get(t, str(t)) for t in tipos_permitidos]
        print(f"✓ Tipos: {', '.join(tipos_nombres)}")

    repertorio = extraer_repertorio_paralelo(
        session, bandas, sellos_blacklist, tipos_permitidos, num_workers, verbose
    )

    output_file = guardar_repertorio(repertorio)

    if verbose:
        print("\n" + "=" * 60)
        print(f"📊 {len(repertorio)} releases encontrados")

        por_tipo = {}
        for r in repertorio:
            tipo = r['type']
            por_tipo[tipo] = por_tipo.get(tipo, 0) + 1

        for tipo, count in sorted(por_tipo.items(), key=lambda x: -x[1]):
            print(f"   {tipo}: {count}")

        print(f"📁 {output_file}")

    return output_file


if __name__ == "__main__":
    run()
