"""
Abre, uno por uno, los posts de DeathGrind de los álbumes que ya están en el canal, para
darles like a mano.

El like lo pone la persona con su clic: el script nunca toca la página. Abre cada post en una
pestaña de Brave y mira en la API, con la sesión del scraper (la misma cuenta), si el post ya
tiene el 👍 de la cuenta. Cuando lo tiene, lo anota en data/likes_dados.txt, abre el siguiente
y cierra la pestaña anterior. Cerrar la pestaña del post lo salta sin anotarlo.

El script no se conecta a las pestañas: la verificación de Cloudflare del login no termina si
hay un programa conectado a la página. Brave abre con un perfil propio, y su puerto de
depuración (solo en 127.0.0.1) se usa nada más para abrir, listar y cerrar pestañas.

Los álbumes del canal salen de dos listas de posts: los que bajó el scraper (data/descargados.txt)
y el catálogo de DeathGrind (data/catalogo_posts.txt), con todos los posts de los géneros de
generos_activos.txt, sin filtros. El catálogo encuentra los videos del canal que no vinieron del
scraper. Se arma la primera vez (recorrer DeathGrind tarda unos minutos y no gasta créditos) y
se vuelve a armar con --actualizar-catalogo.

Uso, desde la raíz del repo:
    env/bin/python scripts/likes_a_mano.py [--actualizar-catalogo]

La primera vez hay que iniciar sesión en la ventana con la cuenta del .env: el perfil queda
guardado en ~/.local/share/deathgrind-likes/brave. Cerrar la ventana termina, y la próxima
vez sigue con los que faltan.
"""
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from modules.extraer_bandas import cargar_generos, extraer_todo  # noqa: E402
from modules.utils import (  # noqa: E402
    API_URL, BASE_URL, DATA_DIR, DESCARGADOS_FILE, cargar_env, cargar_publicados,
    crear_sesion_autenticada,
)

LIKES_FILE = RAIZ / "data" / "likes_dados.txt"
CATALOGO_FILE = f"{DATA_DIR}/catalogo_posts.txt"
PERFIL = Path.home() / ".local" / "share" / "deathgrind-likes" / "brave"
BRAVE = "/usr/bin/brave"
PUERTO = 9333
ESPERA_BRAVE_S = 30
PAUSA_CONSULTA_S = 2.5
PAUSA_429_S = 60  # "Too many requests": seguir consultando solo alarga el bloqueo
PAUSA_REINTENTO_S = 0.5  # Brave ocupado tarda en contestar: un pedido que falla se repite una vez
VOLVER_AL_POST_S = 8  # fuera del post (p. ej. después del login), se vuelve a abrir
TITULO_CLOUDFLARE = "Just a moment..."
LIKE = "👍"
CREDITOS_CADA = 10  # likes entre una lectura de los créditos y la siguiente


class BraveCerrado(Exception):
    """La ventana de Brave se cerró."""


def posts_publicados():
    """(post_id, banda, álbum) de los posts descargados o del catálogo que ya están en el canal."""
    registro = cargar_publicados()
    if registro is None:
        sys.exit("No encontré el registro de publicados de click-auto-editor (CLICK_AUTO_EDITOR_DIR)")
    posts, vistos = [], set()
    for archivo in (RAIZ / DESCARGADOS_FILE, RAIZ / CATALOGO_FILE):
        if not archivo.exists():
            continue
        for linea in archivo.read_text(encoding="utf-8", errors="replace").splitlines():
            partes = linea.strip().split("|")
            if len(partes) < 3 or not partes[0].isdigit() or partes[0] in vistos:
                continue
            vistos.add(partes[0])
            banda, album = partes[1], "|".join(partes[2:])
            if registro.buscar(f"{banda} - {album}"):
                posts.append((partes[0], banda, album))
    return posts


def hay_catalogo():
    return (RAIZ / CATALOGO_FILE).exists()


def guardar_catalogo(sesion):
    """Guarda todos los posts de los géneros activos, sin filtros, como post_id|banda|álbum."""
    generos = cargar_generos()
    print(f"Leyendo el catálogo de DeathGrind ({len(generos)} géneros); tarda unos minutos...",
          flush=True)
    releases = extraer_todo(sesion, generos, set(), None, verbose=False)[0]
    archivo = RAIZ / CATALOGO_FILE
    archivo.parent.mkdir(parents=True, exist_ok=True)
    lineas = [f"{r['post_id']}|{r['band']}|{r['album']}" for r in releases]
    archivo.write_text("# Catálogo de DeathGrind para likes_a_mano.py\n# Formato: post_id|band|album\n\n"
                       + "\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Catálogo: {len(lineas)} posts en {CATALOGO_FILE}", flush=True)


def likes_anotados():
    if not LIKES_FILE.exists():
        return set()
    return {
        linea.split("|", 1)[0]
        for linea in LIKES_FILE.read_text(encoding="utf-8").splitlines()
        if linea and not linea.startswith("#")
    }


def anotar_like(post_id, banda, album, origen):
    nuevo = not LIKES_FILE.exists()
    with open(LIKES_FILE, "a", encoding="utf-8") as archivo:
        if nuevo:
            archivo.write("# Posts de DeathGrind con el like de la cuenta\n")
            archivo.write("# Formato: post_id|band|album|origen|fecha (origen: ventana o ya_estaba)\n\n")
        archivo.write(f"{post_id}|{banda}|{album}|{origen}|{datetime.now():%Y-%m-%d %H:%M}\n")


# --- La API del sitio, con la sesión del scraper ---

def usuario_de_la_sesion(sesion):
    html = sesion.get(BASE_URL, headers={"Accept": "text/html"}, timeout=30).text
    hallado = re.search(r'"userId"\s*:\s*(\d+)', html[html.find("__USER_DATA__"):])
    return hallado.group(1) if hallado and hallado.group(1) != "0" else None


def estado_del_post(sesion, post_id):
    """(status, tiene_like): el 👍 de la cuenta según la API del post; status 0 si no hubo respuesta."""
    try:
        respuesta = sesion.get(f"{API_URL}/posts/{post_id}", timeout=30)
    except requests.RequestException:
        return 0, False
    if respuesta.status_code != 200:
        return respuesta.status_code, False
    try:
        datos = respuesta.json()
    except ValueError:
        return 0, False
    if datos.get("isDeleted"):
        return 404, False  # un post borrado responde 200 y su página dice "Post not found"
    mias = (datos.get("post") or {}).get("myReactions") or []
    return 200, LIKE in json.dumps(mias, ensure_ascii=False)


def creditos(sesion, usuario):
    try:
        perfil = sesion.get(f"{API_URL}/users/{usuario}", timeout=30).json().get("profile") or {}
    except (requests.RequestException, ValueError):
        return None
    return perfil.get("downloadCredits")


# --- Las pestañas de Brave, por su puerto de depuración (sin conectarse a ellas) ---

def depuracion(ruta, metodo="GET"):
    pedido = urllib.request.Request(f"http://127.0.0.1:{PUERTO}/json/{ruta}", method=metodo)
    for intento in (1, 2):
        try:
            with urllib.request.urlopen(pedido, timeout=5) as respuesta:
                return respuesta.read().decode("utf-8")
        except (urllib.error.URLError, OSError) as exc:
            # Un solo pedido lento (Brave ocupado) no es una ventana cerrada
            if intento == 2:
                raise BraveCerrado() from exc
            time.sleep(PAUSA_REINTENTO_S)


def pestanas():
    """{id: (url, título)} de las pestañas abiertas."""
    return {t["id"]: (t["url"], t["title"]) for t in json.loads(depuracion("list")) if t["type"] == "page"}


def abrir_pestana(url):
    pestana = json.loads(depuracion(f"new?{url}", metodo="PUT"))["id"]
    depuracion(f"activate/{pestana}")
    return pestana


def cerrar_pestana(pestana):
    if pestana in pestanas():
        depuracion(f"close/{pestana}")


def abrir_brave():
    """Brave con su perfil y el puerto de depuración; espera a que el puerto responda."""
    PERFIL.mkdir(parents=True, exist_ok=True)
    proceso = subprocess.Popen(
        [BRAVE, f"--user-data-dir={PERFIL}", f"--remote-debugging-port={PUERTO}",
         "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check",
         "--new-window", BASE_URL],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    limite = time.monotonic() + ESPERA_BRAVE_S
    while time.monotonic() < limite:
        try:
            depuracion("version")
            return proceso
        except BraveCerrado:
            time.sleep(0.5)
    proceso.terminate()
    sys.exit(f"Brave no abrió su puerto {PUERTO} en {ESPERA_BRAVE_S} s")


def esperar_por_429():
    print(f"   ⏳ DeathGrind pide bajar el ritmo: espero {PAUSA_429_S} s (en la página, Retry después)",
          flush=True)
    time.sleep(PAUSA_429_S)


def esperar_like(sesion, post_id, pestana, url):
    """("like" o "saltado", pestaña del post): espera el 👍 o que se cierre la pestaña."""
    fuera_desde = None
    avisado = False
    while True:
        time.sleep(PAUSA_CONSULTA_S)
        abiertas = pestanas()
        if not abiertas:
            raise BraveCerrado()  # sin ventanas Brave puede seguir vivo: abrir otra pestaña la reabriría
        if pestana not in abiertas:
            return "saltado", None
        status, con_like = estado_del_post(sesion, post_id)
        if con_like:
            return "like", pestana
        if status == 429:
            esperar_por_429()
            continue
        if status not in (0, 200) and not avisado:
            print(f"   ⚠️  La API no deja leer el post (status {status})", flush=True)
            avisado = True
        url_actual, titulo = abiertas[pestana]
        if f"/posts/{post_id}" in url_actual or "/auth/" in url_actual or titulo == TITULO_CLOUDFLARE:
            fuera_desde = None
            continue
        if fuera_desde is None:
            fuera_desde = time.monotonic()
        elif time.monotonic() - fuera_desde > VOLVER_AL_POST_S:
            nueva = abrir_pestana(url)
            cerrar_pestana(pestana)
            pestana, fuera_desde = nueva, None


def main(argv=()):
    parser = argparse.ArgumentParser(
        description="Abre los posts de DeathGrind de los álbumes del canal para darles like.")
    parser.add_argument("--actualizar-catalogo", action="store_true",
                        help="vuelve a recorrer DeathGrind y rehace data/catalogo_posts.txt")
    args = parser.parse_args(argv)
    sesion = None
    if args.actualizar_catalogo or not hay_catalogo():
        cargar_env()
        sesion = crear_sesion_autenticada()
        guardar_catalogo(sesion)
    posts = posts_publicados()
    anotados = likes_anotados()
    faltan = [post for post in posts if post[0] not in anotados]
    print(f"{len(posts)} álbumes del canal tienen post en DeathGrind; faltan {len(faltan)}.", flush=True)
    if not faltan:
        return
    if sesion is None:
        cargar_env()
        sesion = crear_sesion_autenticada()
    usuario = usuario_de_la_sesion(sesion)
    if not usuario:
        sys.exit("La sesión del scraper no tiene usuario: revisa DEATHGRIND_EMAIL y DEATHGRIND_PASSWORD")
    print(f"Créditos de descarga: {creditos(sesion, usuario)}", flush=True)

    brave = abrir_brave()
    print("Si la ventana no tiene la sesión iniciada, iníciala con la cuenta del .env.", flush=True)
    dados = ya_estaban = 0
    actual = None
    try:
        for numero, (post_id, banda, album) in enumerate(faltan, 1):
            status, con_like = estado_del_post(sesion, post_id)
            while status == 429:
                esperar_por_429()
                status, con_like = estado_del_post(sesion, post_id)
            if status == 404:
                print(f"⏭️  {banda} - {album}: el post ya no existe", flush=True)
                continue
            if con_like:
                anotar_like(post_id, banda, album, "ya_estaba")
                ya_estaban += 1
                continue
            url = f"{BASE_URL}/posts/{post_id}"
            nueva = abrir_pestana(url)
            if actual:
                cerrar_pestana(actual)
            print(f"{numero}/{len(faltan)} · {banda} - {album}", flush=True)
            resultado, actual = esperar_like(sesion, post_id, nueva, url)
            if resultado == "saltado":
                print("   ⏭️  saltado", flush=True)
                continue
            anotar_like(post_id, banda, album, "ventana")
            dados += 1
            print(f"   👍 {dados}", flush=True)
            if dados == 1 or dados % CREDITOS_CADA == 0:
                print(f"   Créditos de descarga: {creditos(sesion, usuario)}", flush=True)
        print("✓ No quedan posts por revisar.", flush=True)
    except BraveCerrado:
        print("La ventana de Brave se cerró.", flush=True)
    finally:
        # También con Ctrl+C u otro error: si no, Brave sigue abierto con el puerto y el perfil
        if brave.poll() is None:
            brave.terminate()
    print(f"Likes nuevos: {dados}; ya estaban: {ya_estaban}. Anotados en {LIKES_FILE}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
