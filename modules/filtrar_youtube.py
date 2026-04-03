#!/usr/bin/env python3
"""
Módulo 4: Filtra releases verificando disponibilidad en YouTube
Entrada: data/repertorio.json
Salida: data/repertorio_filtrado.json

Lógica: Si un release tiene "full album" fácilmente en YouTube,
se considera mainstream y se EXCLUYE. Solo se mantienen los underground.
"""

import asyncio
import os
import json
import re
import urllib.parse
import unicodedata
from playwright.async_api import async_playwright

try:
    from playwright_stealth.stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

# Configuración
INPUT_FILE = "data/repertorio.json"
OUTPUT_FILE = "data/repertorio_filtrado.json"
OUTPUT_RECHAZADOS = "data/releases_mainstream.txt"

# Keywords que indican que el album está disponible (mainstream)
KEYWORDS_MAINSTREAM = []

# Palabras que suelen indicar resultados irrelevantes
NEGATIVE_KEYWORDS = [
    "cover", "reaction", "react", "guitar cover", "drum cover",
    "bass cover", "vocal cover", "karaoke", "lesson", "tutorial",
    "review", "track by track", "interview", "teaser", "trailer",
    "playthrough", "unboxing", "ranking", "top 10",
    "first time listening", "breakdown", "analysis",
    "drum cam", "guitar playthrough", "bass playthrough",
]

# Stopwords para tokenización simple
STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "to", "in", "for", "from",
    "on", "at", "by", "with", "vol", "vol.", "volume", "pt", "part",
    "disc", "cd", "lp", "ep", "demo", "single"
}


def _build_neg_words():
    """Pre-normaliza NEGATIVE_KEYWORDS a un set de palabras individuales"""
    words = set()
    for neg in NEGATIVE_KEYWORDS:
        words.update(_normalizar_texto(neg).split())
    return words


def cargar_keywords():
    """Carga keywords desde archivos"""
    keywords = []

    # Keywords de album
    if os.path.exists('keywords_album.txt'):
        with open('keywords_album.txt', 'r', encoding='utf-8') as f:
            for line in f:
                kw = line.strip().lower()
                if kw:
                    keywords.append(kw)

    # Keywords de EP
    if os.path.exists('keywords_ep.txt'):
        with open('keywords_ep.txt', 'r', encoding='utf-8') as f:
            for line in f:
                kw = line.strip().lower()
                if kw:
                    keywords.append(kw)

    # Si no hay archivos, usar defaults
    if not keywords:
        keywords = [
            "full album", "official album stream", "full album stream", "full length",
            "album stream", "full-album", "album full", "official full stream",
            "álbum completo", "album completo", "disco completo",
            "full stream", "full release", "complete album",
            "entire album", "album premiere",
        ]

    # Normalizar keywords para comparación estable
    keywords = [_normalizar_texto(k) for k in keywords if k]

    return keywords


def _normalizar_texto(texto):
    """Normaliza texto para comparación (minúsculas + sin acentos + sin símbolos)"""
    texto = texto.lower()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r'[_]+', ' ', texto)
    texto = re.sub(r'[^\w\s]', ' ', texto, flags=re.UNICODE)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


def _tokenizar(texto):
    """Tokeniza y elimina stopwords"""
    normal = _normalizar_texto(texto)
    tokens = [t for t in normal.split() if len(t) >= 2 and t not in STOPWORDS]
    return tokens


def _contar_coincidencias(tokens, texto_normalizado):
    """Cuenta cuántos tokens aparecen en el texto"""
    if not tokens:
        return 0
    hay = f" {texto_normalizado} "
    hits = 0
    for t in tokens:
        if f" {t} " in hay:
            hits += 1
    return hits


def cargar_repertorio(input_file=INPUT_FILE):
    """Carga el repertorio desde JSON"""
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"No existe {input_file}")

    with open(input_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def generar_urls_busqueda(band, album, year=None, es_split=False):
    """Genera 2 URLs de búsqueda en YouTube (doble búsqueda)"""
    # Query 1: banda + album + año
    if year:
        q1 = f"{band} {album} {year}"
    else:
        q1 = f"{band} {album}"

    # Query 2: variante con "full album"
    if es_split and " / " in band:
        # Para splits, la segunda query usa solo la primera banda
        primera_banda = band.split(" / ")[0].strip()
        q2 = f"{primera_banda} {album} full album"
    else:
        q2 = f"{band} {album} full album"

    return [
        f"https://www.youtube.com/results?search_query={urllib.parse.quote(q1)}",
        f"https://www.youtube.com/results?search_query={urllib.parse.quote(q2)}",
    ]


class YouTubeFilterParallel:
    def __init__(self, num_workers=5):
        self.playwright = None
        self.browser = None
        self.contexts = []
        self.pages = []
        self.keywords = []
        self.neg_words = set()
        self.num_workers = num_workers
        self.semaphore = None

    async def iniciar_browser(self, headless=True):
        """Inicializa Playwright con múltiples páginas"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=headless)
        self.semaphore = asyncio.Semaphore(self.num_workers)

        # Crear múltiples contextos y páginas
        for i in range(self.num_workers):
            context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent=f'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.{i}.0 Safari/537.36'
            )
            page = await context.new_page()

            if HAS_STEALTH:
                stealth = Stealth()
                await stealth.apply_stealth_async(page)

            self.contexts.append(context)
            self.pages.append(page)

    async def verificar_disponibilidad(self, page, urls, band, album, tipo, max_videos=10):
        """
        Verifica si hay videos con 'full album' en YouTube.
        Recibe lista de URLs (doble búsqueda). Si la primera detecta mainstream,
        retorna inmediatamente sin visitar la segunda (fast path).
        """
        tipo_norm = str(tipo or '').lower()
        band_tokens = _tokenizar(band)
        album_tokens = _tokenizar(album)
        band_req = 1 if len(band_tokens) <= 2 else 2
        album_req = 1 if len(album_tokens) <= 2 else 2

        for url in urls:
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)

                try:
                    await page.wait_for_selector('ytd-video-renderer', timeout=20000)
                except (asyncio.TimeoutError, Exception):
                    continue

                resultados = await page.evaluate('''() => {
                    const items = [];
                    const elements = Array.from(document.querySelectorAll('ytd-video-renderer')).slice(0, 10);
                    for (const el of elements) {
                        const titleEl = el.querySelector('#video-title');
                        const title = titleEl ? (titleEl.textContent || titleEl.getAttribute('title') || '').trim() : '';
                        const chEl = el.querySelector('ytd-channel-name #text a');
                        const channel = chEl ? (chEl.textContent || '').trim() : '';
                        items.push({title, channel});
                    }
                    return items;
                }''')

                for item in resultados:
                    titulo = (item.get('title') or '')
                    canal = (item.get('channel') or '')

                    titulo_norm = _normalizar_texto(titulo)
                    canal_norm = _normalizar_texto(canal)

                    # Evitar falsos positivos comunes (excepto si el release es Live)
                    if tipo_norm != "live":
                        titulo_words = set(titulo_norm.split())
                        if self.neg_words & titulo_words:
                            continue

                    band_hits = max(
                        _contar_coincidencias(band_tokens, titulo_norm),
                        _contar_coincidencias(band_tokens, canal_norm)
                    )
                    album_hits = _contar_coincidencias(album_tokens, titulo_norm)

                    # Si no hay tokens de álbum (títulos muy cortos), solo usar banda + keyword
                    if album_tokens:
                        if band_hits < band_req or album_hits < album_req:
                            continue
                    else:
                        if band_hits < band_req:
                            continue

                    # Solo keywords determinan si es mainstream
                    has_keyword = any(kw in titulo_norm for kw in self.keywords)

                    if has_keyword:
                        return True, titulo

            except Exception:
                continue

        return False, None

    async def procesar_release(self, release, page_idx, max_videos=10):
        """Procesa un release usando una página específica"""
        async with self.semaphore:
            page = self.pages[page_idx % self.num_workers]
            band = release.get('band', 'Unknown')
            album = release.get('album', 'Unknown')
            year = release.get('year')
            tipo = release.get('type', '')

            es_split = " / " in band
            es_self_titled = _normalizar_texto(band) == _normalizar_texto(album)

            # Generar URLs de búsqueda
            urls = generar_urls_busqueda(band, album, year, es_split=es_split)

            # Self-titled: agregar "self titled" a la primera query
            if es_self_titled:
                if year:
                    q_st = f"{band} {album} self titled {year}"
                else:
                    q_st = f"{band} {album} self titled"
                urls[0] = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q_st)}"

            es_mainstream, titulo = await self.verificar_disponibilidad(
                page, urls, band, album, tipo, max_videos
            )

            return release, es_mainstream, titulo

    async def cerrar(self):
        """Cierra el navegador"""
        for context in self.contexts:
            await context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


async def filtrar_por_youtube(repertorio, keywords, headless=True, verbose=True,
                               max_videos=10, num_workers=5, batch_size=20):
    """
    Filtra releases verificando disponibilidad en YouTube (PARALELO)

    Args:
        repertorio: Lista de releases
        keywords: Lista de keywords que indican mainstream
        headless: Ejecutar sin ventana
        verbose: Mostrar progreso
        max_videos: Cuántos videos analizar por búsqueda
        num_workers: Número de páginas paralelas
        batch_size: Tamaño del lote para procesar

    Returns:
        tuple: (releases_aprobados, releases_rechazados)
    """
    aprobados = []
    rechazados = []
    if verbose:
        print("🔄 Sin caché: se verificarán todos los releases del repertorio actual")

    filtro = YouTubeFilterParallel(num_workers=num_workers)
    filtro.keywords = keywords
    filtro.neg_words = _build_neg_words()

    if verbose:
        print(f"\n🌐 Iniciando navegador con {num_workers} workers paralelos...")

    await filtro.iniciar_browser(headless=headless)

    if verbose:
        print("✓ Navegador listo\n")

    total = len(repertorio)
    procesados = 0

    # Procesar en lotes
    for batch_start in range(0, total, batch_size):
        batch = repertorio[batch_start:batch_start + batch_size]

        # Crear tareas para el lote
        tasks = []
        for idx, release in enumerate(batch):
            task = filtro.procesar_release(release, batch_start + idx, max_videos)
            tasks.append(task)

        # Ejecutar lote en paralelo
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Procesar resultados
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                release = batch[i]
                aprobados.append(release)  # Asumir underground en error
                procesados += 1
                continue

            release, es_mainstream, titulo = result
            procesados += 1

            band = release.get('band', 'Unknown')
            album = release.get('album', 'Unknown')
            year = release.get('year', '')
            razon = titulo[:50] if titulo else 'keyword'

            if es_mainstream:
                rechazados.append({**release, 'razon': razon})
                if verbose:
                    year_str = f"({year})" if year else ""
                    print(f"[{procesados}/{total}] {band} - {album} {year_str} ❌ Mainstream")
            else:
                aprobados.append(release)
                if verbose:
                    year_str = f"({year})" if year else ""
                    print(f"[{procesados}/{total}] {band} - {album} {year_str} ✓ Underground")

        # Mostrar progreso del lote
        if verbose:
            pct = (procesados / total) * 100
            print(f"\n📊 Progreso: {procesados}/{total} ({pct:.1f}%) - Underground: {len(aprobados)}, Mainstream: {len(rechazados)}\n")

    await filtro.cerrar()

    return aprobados, rechazados


def guardar_resultados(aprobados, rechazados, output_file=OUTPUT_FILE,
                       output_rechazados=OUTPUT_RECHAZADOS, verbose=True):
    """Guarda los resultados"""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Guardar aprobados (underground)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(aprobados, f, indent=2, ensure_ascii=False)

    # Guardar rechazados (mainstream) para referencia
    with open(output_rechazados, 'w', encoding='utf-8') as f:
        f.write("# Releases excluidos por estar disponibles en YouTube\n")
        f.write("# (encontrados con keywords de 'full album')\n\n")
        for r in rechazados:
            year_str = f"({r.get('year')})" if r.get('year') else ""
            f.write(f"{r['band']} - {r['album']} {year_str}\n")
            f.write(f"  Razón: {r.get('razon', 'N/A')}\n\n")

    if verbose:
        print(f"\n📁 Guardado: {output_file} ({len(aprobados)} releases)")
        print(f"📁 Guardado: {output_rechazados} ({len(rechazados)} excluidos)")


def run(headless=True, verbose=True, max_videos=10, num_workers=None,
        input_file=None):
    """
    Ejecuta el filtrado por YouTube (PARALELO)

    Args:
        headless: Ejecutar sin ventana
        verbose: Mostrar progreso
        max_videos: Cuántos videos analizar por búsqueda
        num_workers: Número de páginas paralelas
        input_file: Archivo de entrada (default: INPUT_FILE)
    """
    if verbose:
        print("=" * 60)
        print("🎬 MÓDULO 3: FILTRO YOUTUBE (Paralelo)")
        print("=" * 60)

    # Auto-detectar workers
    if num_workers is None:
        try:
            from modules.utils import detectar_workers_optimos
            num_workers = detectar_workers_optimos()
        except ImportError:
            num_workers = min((os.cpu_count() or 4) - 1, 6)

    # Cargar keywords
    keywords = cargar_keywords()
    if verbose:
        print(f"\n✓ {len(keywords)} keywords")

    # Cargar repertorio
    repertorio = cargar_repertorio(input_file or INPUT_FILE)
    if verbose:
        print(f"✓ {len(repertorio)} releases, {num_workers} workers")

    # Filtrar
    aprobados, rechazados = asyncio.run(
        filtrar_por_youtube(
            repertorio,
            keywords,
            headless=headless,
            verbose=verbose,
            max_videos=max_videos,
            num_workers=num_workers
        )
    )

    # Guardar
    guardar_resultados(aprobados, rechazados, verbose=verbose)

    # Estadísticas
    if verbose:
        print("\n" + "=" * 60)
        print("📊 RESULTADO")
        print("=" * 60)
        print(f"Total verificados: {len(repertorio)}")
        print(f"Underground (aprobados): {len(aprobados)}")
        print(f"Mainstream (excluidos): {len(rechazados)}")

        if repertorio:
            pct = (len(aprobados) / len(repertorio)) * 100
            print(f"Tasa de aprobación: {pct:.1f}%")

    return OUTPUT_FILE


if __name__ == "__main__":
    run(headless=False, max_videos=10)
