#!/usr/bin/env python3
"""
Módulo 1: Extrae posts/releases y bandas de DeathGrind.club via API
Filtra por sello problemático al momento de extraer (optimizado)

Salida:
  - data/bandas.json (bandas únicas)
  - data/repertorio.json (releases filtrados)
"""

import requests
import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from modules.utils import (
    BASE_URL, API_URL, DELAY_BASE_429, MAX_BACKOFF_429,
    BANDAS_FILE, REPERTORIO_FILE, FALLIDOS_FILE,
    cargar_env, crear_sesion_autenticada, cargar_sellos_blacklist,
    delay_con_jitter,
)

# Thread-local storage para sesiones HTTP
_thread_local = threading.local()


def _get_thread_session(session_data):
    """Obtiene o crea una sesión HTTP para el thread actual"""
    if not hasattr(_thread_local, 'session'):
        session = requests.Session()
        session.headers.update(session_data['headers'])
        for cookie in session_data['cookies']:
            session.cookies.set(cookie['name'], cookie['value'])
        _thread_local.session = session
    return _thread_local.session


def _preparar_session_data(session):
    """Prepara datos de sesión para crear copias thread-local"""
    return {
        'headers': dict(session.headers),
        'cookies': [{'name': k, 'value': v} for k, v in session.cookies.items()]
    }

# Configuración
OUTPUT_BANDAS = BANDAS_FILE
OUTPUT_REPERTORIO = REPERTORIO_FILE

# Configuración de rate limiting (ajustable)
DELAY_ENTRE_PAGINAS = 1.0      # Segundos entre cada página de resultados
MAX_RETRIES_429 = None         # None = infinito, nunca rendirse

# Tipos de disco
# Nota: La API usa ID 9 como alias de EP (mismo tipo que ID 2)
TIPOS_DISCO = {
    1: "Album", 2: "EP", 3: "Demo", 4: "Single",
    5: "Split", 6: "Compilation", 7: "Live", 8: "Boxset", 9: "EP"
}


def cargar_generos():
    """Carga géneros desde archivo"""
    generos = []
    if os.path.exists('generos_activos.txt'):
        with open('generos_activos.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()[1:]
            for line in lines:
                parts = line.strip().split('\t')
                if len(parts) >= 3:
                    generos.append((int(parts[0]), parts[2]))
    return generos


def cargar_descargados():
    """Carga lista de releases ya descargados (por post_id)"""
    descargados = set()
    descargados_file = 'data/descargados.txt'
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


def cargar_fallidos():
    """Carga lista de posts con links fallidos (por post_id, con expiración 30 días)"""
    from datetime import datetime, timedelta
    fallidos = set()
    lineas_vigentes = []
    hay_expirados = False

    if os.path.exists(FALLIDOS_FILE):
        with open(FALLIDOS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith('#'):
                    lineas_vigentes.append(line)
                    continue
                parts = raw.split('|')
                # Formato nuevo: post_id|band|album|fecha|motivo
                # Formato viejo: band_id|band|post_id|album|fecha|motivo
                fecha_str = None
                post_id = None
                if len(parts) >= 5:
                    if _es_fecha(parts[3]):
                        post_id = parts[0]
                        fecha_str = parts[3]
                    elif len(parts) >= 6 and _es_fecha(parts[4]):
                        post_id = parts[2]
                        fecha_str = parts[4]
                    else:
                        post_id = parts[0]
                elif len(parts) >= 1 and parts[0].isdigit():
                    post_id = parts[0]

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

        if hay_expirados:
            with open(FALLIDOS_FILE, 'w', encoding='utf-8') as f:
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


def post_en_blacklist(post, sellos_blacklist):
    """Verifica si un post está en un sello problemático"""
    labels = post.get('label', [])
    if isinstance(labels, str):
        labels = [labels]

    for label in labels:
        if str(label).strip().lower() in sellos_blacklist:
            return True, label
    return False, None


def extraer_posts_genero(session_data, genre_id, genre_name, sellos_blacklist, tipos_permitidos,
                         descargados=None, fallidos_posts=None, verbose=True):
    """
    Extrae TODOS los posts de un género, filtrando por sello y descargados al vuelo
    """
    session = _get_thread_session(session_data)
    releases = []
    bandas_encontradas = {}
    posts_total = 0
    posts_filtrados_sello = 0
    posts_filtrados_descargados = 0
    posts_filtrados_fallidos = 0
    offset = None
    retries_429 = 0
    retries_error = 0
    max_retries_error = 5

    if descargados is None:
        descargados = set()
    if fallidos_posts is None:
        fallidos_posts = set()

    while True:
        try:
            params = {'genres': genre_id}
            if offset is not None:
                params['offset'] = offset

            r = session.get(
                f"{API_URL}/posts/filter",
                params=params,
                timeout=30
            )

            # Manejar rate limiting - NUNCA rendirse
            if r.status_code == 429:
                retries_429 += 1
                wait_time = min(DELAY_BASE_429 * retries_429, MAX_BACKOFF_429)
                if verbose:
                    print(f"    ⏳ Rate limited (intento {retries_429}), esperando {wait_time}s...")
                time.sleep(wait_time)
                continue

            if r.status_code != 200:
                retries_error += 1
                if retries_error > max_retries_error:
                    if verbose:
                        print(f"    ⚠️ Error {r.status_code} persistente, continuando...")
                    break
                time.sleep(5)
                continue

            # Reset contadores en éxito
            retries_429 = 0
            retries_error = 0
            data = r.json()
            posts = data.get('posts', [])

            if not posts:
                break

            for post in posts:
                posts_total += 1
                post_id = post.get('postId')

                # Filtrar por ya descargados
                if str(post_id) in descargados:
                    posts_filtrados_descargados += 1
                    continue

                # Filtrar por posts fallidos
                if str(post_id) in fallidos_posts:
                    posts_filtrados_fallidos += 1
                    continue

                # Filtrar por sello problemático
                en_blacklist, sello = post_en_blacklist(post, sellos_blacklist)
                if en_blacklist:
                    posts_filtrados_sello += 1
                    continue

                # Filtrar por tipo de disco
                type_ids = post.get('type', [])
                if tipos_permitidos:
                    if not any(tid in tipos_permitidos for tid in type_ids):
                        continue
                album = post.get('album', 'Unknown')
                year = post.get('releaseDate', [None])[0] if post.get('releaseDate') else None

                # Obtener tipo
                tipo = "Release"
                tipo_id = None
                for tid in type_ids:
                    if tid in TIPOS_DISCO:
                        tipo = TIPOS_DISCO[tid]
                        tipo_id = tid
                        break

                # Procesar bandas - recolectar todas del post
                bands = post.get('bands', [])
                band_names = []
                band_ids = []
                for band in bands:
                    if isinstance(band, dict):
                        band_name = band.get('name', '')
                        band_id = band.get('bandId')
                    else:
                        band_name = str(band)
                        band_id = None

                    if band_name:
                        band_names.append(band_name)
                    if band_id is not None:
                        band_ids.append(band_id)

                    if band_name and band_name not in bandas_encontradas:
                        bandas_encontradas[band_name] = {
                            'bandId': band_id,
                            'name': band_name,
                            'found_in_genre': genre_name
                        }

                # Un solo release por post con todas las bandas
                releases.append({
                    'band': ' / '.join(band_names) if band_names else 'Unknown',
                    'band_id': band_ids[0] if band_ids else None,
                    'band_ids': band_ids,
                    'album': album,
                    'year': year,
                    'type': tipo,
                    'type_id': tipo_id,
                    'post_id': post_id,
                    'post_url': f"{BASE_URL}/posts/{post_id}"
                })

            # Verificar si hay más páginas
            if not data.get('hasMore', False):
                break

            offset = data.get('offset')
            if offset is None:
                break

            delay_con_jitter(DELAY_ENTRE_PAGINAS)

        except (requests.RequestException, TimeoutError, json.JSONDecodeError, KeyError) as e:
            retries_error += 1
            if retries_error > max_retries_error:
                if verbose:
                    print(f"    ⚠️ Error de conexión persistente: {e}")
                break
            wait_time = retries_error * 5
            if verbose:
                print(f"    ⚠️ Error de conexión, reintentando en {wait_time}s...")
            time.sleep(wait_time)

    return (releases, bandas_encontradas, posts_total, posts_filtrados_sello,
            posts_filtrados_descargados, posts_filtrados_fallidos)


def extraer_todo(session, generos, sellos_blacklist, tipos_permitidos,
                 descargados=None, fallidos_posts=None, verbose=True):
    """
    Extrae todos los posts y bandas, filtrando al vuelo (3 géneros en paralelo)
    """
    session_data = _preparar_session_data(session)

    todos_releases = []
    todas_bandas = {}
    posts_total = 0
    posts_filtrados_sello = 0
    posts_filtrados_descargados = 0
    posts_filtrados_fallidos = 0
    posts_ids_vistos = set()  # Para evitar duplicados entre géneros
    lock = threading.Lock()

    if descargados is None:
        descargados = set()
    if fallidos_posts is None:
        fallidos_posts = set()

    if verbose:
        print(f"\n📦 Scrapeando {len(generos)} géneros (3 workers paralelos)...")
        if descargados:
            print(f"📋 {len(descargados)} releases ya descargados (serán omitidos)")
        print("=" * 60)

    completados = [0]  # Mutable para acceso desde closure

    def procesar_genero(args):
        idx, genre_id, genre_name = args
        releases, bandas, posts, filtrados_sello, filtrados_desc, filtrados_fallidos = extraer_posts_genero(
            session_data, genre_id, genre_name, sellos_blacklist, tipos_permitidos, descargados, fallidos_posts, verbose
        )
        return (idx, genre_name, releases, bandas, posts, filtrados_sello, filtrados_desc, filtrados_fallidos)

    tareas = [(i, gid, gname) for i, (gid, gname) in enumerate(generos)]

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(procesar_genero, t): t for t in tareas}

        for future in as_completed(futures):
            idx, genre_name, releases, bandas, posts, filtrados_sello, filtrados_desc, filtrados_fallidos = future.result()

            with lock:
                posts_total += posts
                posts_filtrados_sello += filtrados_sello
                posts_filtrados_descargados += filtrados_desc
                posts_filtrados_fallidos += filtrados_fallidos

                nuevas_bandas = 0
                for nombre, info in bandas.items():
                    if nombre not in todas_bandas:
                        todas_bandas[nombre] = info
                        nuevas_bandas += 1

                nuevos_releases = 0
                for release in releases:
                    post_id = release['post_id']
                    if post_id not in posts_ids_vistos:
                        posts_ids_vistos.add(post_id)
                        todos_releases.append(release)
                        nuevos_releases += 1

                completados[0] += 1

                if verbose:
                    filtrados_total = filtrados_sello + filtrados_desc + filtrados_fallidos
                    print(f"\n[{completados[0]}/{len(generos)}] {genre_name}")
                    print(f"  → {posts} posts, {filtrados_total} filtrados, +{nuevas_bandas} bandas, +{nuevos_releases} releases")
                    print(f"     Total: {len(todas_bandas)} bandas, {len(todos_releases)} releases")

    return (todos_releases, list(todas_bandas.values()), posts_total,
            posts_filtrados_sello, posts_filtrados_descargados, posts_filtrados_fallidos)


def guardar_datos(bandas, releases, verbose=True):
    """Guarda bandas y releases en archivos JSON"""
    os.makedirs('data', exist_ok=True)

    with open(OUTPUT_BANDAS, 'w', encoding='utf-8') as f:
        json.dump(bandas, f, indent=2, ensure_ascii=False)

    with open(OUTPUT_REPERTORIO, 'w', encoding='utf-8') as f:
        json.dump(releases, f, indent=2, ensure_ascii=False)

    if verbose:
        print(f"\n📁 {OUTPUT_BANDAS} ({len(bandas)} bandas)")
        print(f"📁 {OUTPUT_REPERTORIO} ({len(releases)} releases)")


def run(tipos_permitidos=None, verbose=True):
    """
    Ejecuta la extracción optimizada
    Extrae posts, filtra por sello/descargados/fallidos, guarda bandas + releases
    """
    if verbose:
        print("=" * 60)
        print("🎸 MÓDULO 1: EXTRACCIÓN DE BANDAS Y REPERTORIO")
        print("   (Optimizado: filtra por sello, descargados y fallidos al extraer)")
        print("=" * 60)

    if tipos_permitidos is None:
        tipos_permitidos = [1, 2]  # Albums y EPs por defecto

    cargar_env()

    if verbose:
        print("\n🔐 Iniciando sesión...")
    session = crear_sesion_autenticada()
    if verbose:
        print("✓ Sesión iniciada")

    generos = cargar_generos()
    if not generos:
        raise FileNotFoundError("No se encontró generos_activos.txt")

    sellos_blacklist = cargar_sellos_blacklist()
    descargados = cargar_descargados()
    fallidos_posts = cargar_fallidos()

    if verbose:
        print(f"✓ {len(generos)} géneros")
        print(f"✓ {len(sellos_blacklist)} sellos en blacklist")
        print(f"✓ {len(descargados)} releases ya descargados")
        print(f"✓ {len(fallidos_posts)} posts con links fallidos")
        tipos_nombres = [TIPOS_DISCO.get(t, str(t)) for t in tipos_permitidos]
        print(f"✓ Tipos: {', '.join(tipos_nombres)}")

    releases, bandas, posts_total, posts_filtrados_sello, posts_filtrados_desc, posts_filtrados_fallidos = extraer_todo(
        session, generos, sellos_blacklist, tipos_permitidos, descargados, fallidos_posts, verbose
    )

    guardar_datos(bandas, releases, verbose)

    if verbose:
        print("\n" + "=" * 60)
        print("📊 RESULTADO")
        print("=" * 60)
        print(f"Posts procesados: {posts_total:,}")
        print(f"Filtrados (sellos): {posts_filtrados_sello:,}")
        print(f"Filtrados (ya descargados): {posts_filtrados_desc:,}")
        print(f"Filtrados (bandas fallidas): {posts_filtrados_fallidos:,}")
        print(f"Bandas únicas: {len(bandas):,}")
        print(f"Releases nuevos: {len(releases):,}")

    return OUTPUT_BANDAS, OUTPUT_REPERTORIO


if __name__ == "__main__":
    run()
