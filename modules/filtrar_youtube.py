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
import urllib.parse
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
            "full album", "official album stream", "full album stream",
            "full length", "album stream", "full-album", "album full",
            "full ep", "full ep stream", "ep stream", "official ep", "official full stream"
        ]

    return keywords


def cargar_repertorio(input_file=INPUT_FILE):
    """Carga el repertorio desde JSON"""
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"No existe {input_file}")

    with open(input_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def generar_busqueda_youtube(band, album, year=None):
    """Genera URL de búsqueda en YouTube"""
    if year:
        query = f"{band} {album} {year}"
    else:
        query = f"{band} {album}"

    encoded = urllib.parse.quote(query)
    return f"https://www.youtube.com/results?search_query={encoded}"


class YouTubeFilterParallel:
    def __init__(self, num_workers=5):
        self.playwright = None
        self.browser = None
        self.contexts = []
        self.pages = []
        self.keywords = []
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

    async def verificar_disponibilidad(self, page, url, max_videos=3):
        """Verifica si hay videos con keywords de 'full album' en YouTube"""
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(1.5)

            try:
                await page.wait_for_selector('ytd-video-renderer', timeout=8000)
            except:
                return False, None

            titulos = await page.evaluate('''() => {
                const titles = [];
                const elements = document.querySelectorAll('ytd-video-renderer #video-title');
                for (let i = 0; i < Math.min(elements.length, 5); i++) {
                    const title = elements[i].textContent || elements[i].getAttribute('title') || '';
                    titles.push(title.trim().toLowerCase());
                }
                return titles;
            }''')

            for titulo in titulos[:max_videos]:
                for keyword in self.keywords:
                    if keyword in titulo:
                        return True, titulo

            return False, None

        except Exception:
            return False, None

    async def procesar_release(self, release, page_idx, max_videos=3):
        """Procesa un release usando una página específica"""
        async with self.semaphore:
            page = self.pages[page_idx % self.num_workers]
            band = release.get('band', 'Unknown')
            album = release.get('album', 'Unknown')
            year = release.get('year')

            url = generar_busqueda_youtube(band, album, year)
            es_mainstream, titulo = await self.verificar_disponibilidad(page, url, max_videos)

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
                               max_videos=3, num_workers=5, batch_size=20):
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
    filtro = YouTubeFilterParallel(num_workers=num_workers)
    filtro.keywords = keywords

    if verbose:
        print(f"\n🌐 Iniciando navegador con {num_workers} workers paralelos...")

    await filtro.iniciar_browser(headless=headless)

    if verbose:
        print("✓ Navegador listo\n")

    total = len(repertorio)
    aprobados = []
    rechazados = []
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
        for result in results:
            if isinstance(result, Exception):
                continue

            release, es_mainstream, titulo = result
            procesados += 1

            band = release.get('band', 'Unknown')
            album = release.get('album', 'Unknown')
            year = release.get('year', '')

            if es_mainstream:
                rechazados.append({**release, 'razon': titulo[:50] if titulo else 'keyword'})
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


def run(headless=True, verbose=True, max_videos=3, num_workers=None):
    """
    Ejecuta el filtrado por YouTube (PARALELO)
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
        except:
            import os
            num_workers = min((os.cpu_count() or 4) - 1, 6)

    # Cargar keywords
    keywords = cargar_keywords()
    if verbose:
        print(f"\n✓ {len(keywords)} keywords")

    # Cargar repertorio
    repertorio = cargar_repertorio()
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
    run(headless=False, max_videos=3)
