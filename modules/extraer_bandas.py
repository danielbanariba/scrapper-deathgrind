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

# Configuración
BASE_URL = "https://deathgrind.club"
API_URL = f"{BASE_URL}/api"
OUTPUT_BANDAS = "data/bandas.json"
OUTPUT_REPERTORIO = "data/repertorio.json"

# Configuración de rate limiting (ajustable)
DELAY_ENTRE_PAGINAS = 1.0      # Segundos entre cada página de resultados
DELAY_ENTRE_GENEROS = 3.0      # Segundos entre cada género
DELAY_BASE_429 = 30            # Segundos base cuando hay rate limit (se multiplica)
MAX_RETRIES_429 = None         # None = infinito, nunca rendirse

# Tipos de disco
TIPOS_DISCO = {
    1: "Album", 2: "EP", 3: "Demo", 4: "Single",
    5: "Split", 6: "Compilation", 7: "Live", 8: "Boxset", 9: "EP"
}


def cargar_env():
    """Carga variables de entorno desde .env"""
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                if '=' in line:
                    key, val = line.strip().split('=', 1)
                    os.environ[key] = val


def crear_sesion_autenticada():
    """Login y retorna sesión autenticada"""
    email = os.environ.get('DEATHGRIND_EMAIL')
    password = os.environ.get('DEATHGRIND_PASSWORD')

    if not email or not password:
        raise ValueError("Faltan credenciales en .env")

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

    raise ConnectionError(f"Error de login: {response.status_code}")


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


def post_en_blacklist(post, sellos_blacklist):
    """Verifica si un post está en un sello problemático"""
    labels = post.get('label', [])
    if isinstance(labels, str):
        labels = [labels]

    for label in labels:
        if str(label).strip().lower() in sellos_blacklist:
            return True, label
    return False, None


def extraer_posts_genero(session, genre_id, genre_name, sellos_blacklist, tipos_permitidos, verbose=True):
    """
    Extrae TODOS los posts de un género, filtrando por sello al vuelo
    """
    releases = []
    bandas_encontradas = {}
    posts_total = 0
    posts_filtrados = 0
    offset = None
    retries_429 = 0
    retries_error = 0
    max_retries_error = 5

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
                wait_time = DELAY_BASE_429 * retries_429
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

                # Filtrar por sello problemático
                en_blacklist, sello = post_en_blacklist(post, sellos_blacklist)
                if en_blacklist:
                    posts_filtrados += 1
                    continue

                # Filtrar por tipo de disco
                type_ids = post.get('type', [])
                if tipos_permitidos:
                    if not any(tid in tipos_permitidos for tid in type_ids):
                        continue

                # Extraer info del post
                post_id = post.get('postId')
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

                # Procesar bandas
                bands = post.get('bands', [])
                for band in bands:
                    if isinstance(band, dict):
                        band_name = band.get('name', '')
                        band_id = band.get('bandId')
                    else:
                        band_name = str(band)
                        band_id = None

                    if band_name and band_name not in bandas_encontradas:
                        bandas_encontradas[band_name] = {
                            'bandId': band_id,
                            'name': band_name,
                            'found_in_genre': genre_name
                        }

                    # Agregar release (uno por cada banda en el post)
                    releases.append({
                        'band': band_name,
                        'band_id': band_id,
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

            time.sleep(DELAY_ENTRE_PAGINAS)

        except Exception as e:
            retries_error += 1
            if retries_error > max_retries_error:
                if verbose:
                    print(f"    ⚠️ Error de conexión persistente: {e}")
                break
            wait_time = retries_error * 5
            if verbose:
                print(f"    ⚠️ Error de conexión, reintentando en {wait_time}s...")
            time.sleep(wait_time)

    return releases, bandas_encontradas, posts_total, posts_filtrados


def extraer_todo(session, generos, sellos_blacklist, tipos_permitidos, verbose=True):
    """
    Extrae todos los posts y bandas, filtrando al vuelo
    """
    todos_releases = []
    todas_bandas = {}
    posts_total = 0
    posts_filtrados_total = 0
    posts_ids_vistos = set()  # Para evitar duplicados entre géneros

    if verbose:
        print(f"\n📦 Scrapeando {len(generos)} géneros...")
        print("=" * 60)

    for i, (genre_id, genre_name) in enumerate(generos):
        if verbose:
            print(f"\n[{i+1}/{len(generos)}] {genre_name} (ID: {genre_id})")

        releases, bandas, posts, filtrados = extraer_posts_genero(
            session, genre_id, genre_name, sellos_blacklist, tipos_permitidos, verbose
        )

        posts_total += posts
        posts_filtrados_total += filtrados

        # Agregar bandas nuevas
        nuevas_bandas = 0
        for nombre, info in bandas.items():
            if nombre not in todas_bandas:
                todas_bandas[nombre] = info
                nuevas_bandas += 1

        # Agregar releases nuevos (evitar duplicados)
        nuevos_releases = 0
        for release in releases:
            post_id = release['post_id']
            if post_id not in posts_ids_vistos:
                posts_ids_vistos.add(post_id)
                todos_releases.append(release)
                nuevos_releases += 1

        if verbose:
            print(f"  → {posts} posts, {filtrados} filtrados, +{nuevas_bandas} bandas, +{nuevos_releases} releases")
            print(f"     Total: {len(todas_bandas)} bandas, {len(todos_releases)} releases")

        # Pausa entre géneros para evitar rate limiting
        if i < len(generos) - 1:
            time.sleep(DELAY_ENTRE_GENEROS)

    return todos_releases, list(todas_bandas.values()), posts_total, posts_filtrados_total


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
    Extrae posts, filtra por sello, y guarda bandas + releases en un solo paso
    """
    if verbose:
        print("=" * 60)
        print("🎸 MÓDULO 1: EXTRACCIÓN DE BANDAS Y REPERTORIO")
        print("   (Optimizado: filtra por sello al extraer)")
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

    if verbose:
        print(f"✓ {len(generos)} géneros")
        print(f"✓ {len(sellos_blacklist)} sellos en blacklist")
        tipos_nombres = [TIPOS_DISCO.get(t, str(t)) for t in tipos_permitidos]
        print(f"✓ Tipos: {', '.join(tipos_nombres)}")

    releases, bandas, posts_total, posts_filtrados = extraer_todo(
        session, generos, sellos_blacklist, tipos_permitidos, verbose
    )

    guardar_datos(bandas, releases, verbose)

    if verbose:
        print("\n" + "=" * 60)
        print("📊 RESULTADO")
        print("=" * 60)
        print(f"Posts procesados: {posts_total:,}")
        print(f"Posts filtrados (sellos problemáticos): {posts_filtrados:,}")
        print(f"Bandas únicas: {len(bandas):,}")
        print(f"Releases válidos: {len(releases):,}")

    return OUTPUT_BANDAS, OUTPUT_REPERTORIO


if __name__ == "__main__":
    run()
