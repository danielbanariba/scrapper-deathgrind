#!/usr/bin/env python3
"""
DeathGrind.club Scraper - Programa Principal

Ejecuta el pipeline completo:
1. Extraer bandas + repertorio (API) - filtra por sellos al extraer
2. Filtrar por YouTube (solo underground)
3. Extraer links de descarga (API)

Uso:
    python main.py
"""

import os
import sys
import importlib.util

# Agregar módulos al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.logger import setup_logger

logger = setup_logger(__name__)

# Tipos de disco disponibles
TIPOS_DISCO = {
    1: "Album",
    2: "EP",
    3: "Demo",
    4: "Single",
    5: "Split",
    6: "Compilation",
    7: "Live"
}

# Archivos a limpiar antes de cada ejecución
ARCHIVOS_LIMPIAR = [
    'data/bandas.json',
    'data/repertorio.json',
    'data/repertorio_filtrado.json',
    'data/releases_mainstream.txt',
    'data/repertorio_con_links.json',
    'data/links_descarga.txt',
    'data/discografia_detalle.txt'
]


def mostrar_banner():
    logger.info("")
    logger.info("=" * 60)
    logger.info("🎸 DEATHGRIND.CLUB SCRAPER")
    logger.info("=" * 60)
    logger.info("")


def hay_archivos_anteriores():
    """Verifica si existen archivos de una ejecución anterior"""
    for archivo in ARCHIVOS_LIMPIAR:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 2:
            return True
    return False


def limpiar_archivos_anteriores():
    """Elimina archivos de ejecuciones anteriores"""
    eliminados = 0
    for archivo in ARCHIVOS_LIMPIAR:
        if os.path.exists(archivo):
            os.remove(archivo)
            eliminados += 1

    if eliminados > 0:
        logger.info(f"🗑️  {eliminados} archivo(s) anterior(es) eliminado(s)")


def menu_reanudar_o_limpiar():
    """Muestra menú interactivo cuando hay datos de una ejecución anterior.
    Returns: 'limpiar', 'reanudar', o 'cancelar'
    """
    print("\n📋 Se encontraron datos de una ejecución anterior:")
    archivos_existentes = []
    for archivo in ARCHIVOS_LIMPIAR:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 2:
            size = os.path.getsize(archivo)
            if size > 1024:
                size_str = f"{size/1024:.1f} KB"
            else:
                size_str = f"{size} bytes"
            archivos_existentes.append(f"   {archivo} ({size_str})")
    for a in archivos_existentes:
        print(a)

    print("\n  l) Limpiar y empezar de cero")
    print("  r) Reanudar desde donde se quedó")
    print("  c) Cancelar")

    opcion = input("\nOpción [r]: ").strip().lower() or 'r'
    if opcion == 'l':
        return 'limpiar'
    elif opcion == 'c':
        return 'cancelar'
    return 'reanudar'


def _paso_completado(archivo_output):
    """Verifica si un paso ya fue completado (archivo de salida existe y tiene contenido)"""
    return os.path.exists(archivo_output) and os.path.getsize(archivo_output) > 2


def verificar_dependencias():
    """Verifica que existan los archivos necesarios"""
    archivos_requeridos = [
        ('generos_activos.txt', 'Lista de géneros'),
        ('.env', 'Credenciales')
    ]

    archivos_opcionales = [
        ('lista_sello.txt', 'Lista de sellos (blacklist)'),
        ('keywords_album.txt', 'Keywords para filtro YouTube'),
        ('keywords_ep.txt', 'Keywords para filtro YouTube')
    ]

    faltantes = []
    for archivo, desc in archivos_requeridos:
        if not os.path.exists(archivo):
            faltantes.append(f"  ❌ {archivo}: {desc}")

    if faltantes:
        logger.warning("Archivos requeridos faltantes:")
        for f in faltantes:
            logger.warning(f)
        logger.info("")
        return False

    # Verificar opcionales
    for archivo, desc in archivos_opcionales:
        if not os.path.exists(archivo):
            logger.info(f"ℹ️  {archivo} no encontrado (opcional)")

    # Verificar dependencias de Python necesarias para el pipeline
    faltantes_py = []
    for modulo in ("requests", "playwright"):
        if importlib.util.find_spec(modulo) is None:
            faltantes_py.append(modulo)

    if faltantes_py:
        logger.warning("Dependencias de Python faltantes:")
        for mod in faltantes_py:
            logger.error(f"  {mod}")
        logger.info("\nInstala con:")
        logger.info("  pip install -r requirements.txt")
        logger.info("  playwright install chromium")
        return False

    return True


def seleccionar_tipos_disco():
    """Menú interactivo para seleccionar tipos de disco"""
    print("📀 ¿Qué tipos de disco quieres extraer?")
    print()
    print("  a) Albums + EPs (recomendado)")
    print("  b) Solo Albums")
    print("  c) Solo EPs")
    print("  d) Todo excepto Singles")
    print("  e) Todo")
    print("  f) Selección personalizada")
    print()

    opcion = input("Opción [a]: ").strip().lower() or 'a'

    if opcion == 'a':
        return [1, 2]
    elif opcion == 'b':
        return [1]
    elif opcion == 'c':
        return [2]
    elif opcion == 'd':
        return [1, 2, 3, 5, 6, 7]
    elif opcion == 'e':
        return list(TIPOS_DISCO.keys())
    elif opcion == 'f':
        print("\nTipos disponibles:")
        for id, nombre in TIPOS_DISCO.items():
            print(f"  {id}. {nombre}")
        ids = input("IDs separados por coma (ej: 1,2,3): ").strip()
        return [int(x.strip()) for x in ids.split(',') if x.strip().isdigit()]

    return [1, 2]


def preguntar_headless():
    """Pregunta si ejecutar navegador sin ventana"""
    print("\n🌐 ¿Ejecutar navegador en modo invisible?")
    print("  s) Sí, en segundo plano")
    print("  n) No, quiero ver el navegador")

    opcion = input("Opción [s]: ").strip().lower() or 's'
    return opcion == 's'


def detectar_recursos():
    """Detecta recursos del sistema automáticamente"""
    try:
        from modules.utils import mostrar_recursos, detectar_workers_optimos, detectar_workers_api
        print("\n⚡ Detectando recursos del sistema...")
        workers_browser, workers_api = mostrar_recursos()
        return workers_browser, workers_api
    except Exception as e:
        # Fallback
        import os
        cpu = os.cpu_count() or 4
        return min(cpu - 1, 6), min(cpu * 2, 15)


import time

def pausa_entre_modulos(segundos=5):
    """Pausa para evitar rate limiting"""
    logger.info(f"\n⏳ Esperando {segundos}s para evitar rate limiting...")
    time.sleep(segundos)


def ejecutar_pipeline(tipos_permitidos, headless=True, reanudar=False):
    """Ejecuta los 3 módulos en secuencia. Si reanudar=True, salta pasos completados."""

    # Crear directorio data si no existe
    os.makedirs('data', exist_ok=True)

    total_pasos = 3
    paso_actual = 1

    # === MÓDULO 1: BANDAS + REPERTORIO (optimizado) ===
    if reanudar and _paso_completado('data/repertorio.json'):
        logger.info(f"\n⏭️  PASO {paso_actual}/{total_pasos}: EXTRACCIÓN — ya completado, saltando")
    else:
        logger.info("\n" + "=" * 60)
        logger.info(f"📦 PASO {paso_actual}/{total_pasos}: EXTRACCIÓN DE BANDAS Y REPERTORIO")
        logger.info("=" * 60)

        try:
            from modules.extraer_bandas import run as extraer_bandas
            extraer_bandas(tipos_permitidos=tipos_permitidos, verbose=True)
        except Exception as e:
            logger.error(f"Error en extracción: {e}")
            return False

        pausa_entre_modulos(3)

    paso_actual += 1

    # === MÓDULO 2: FILTRO YOUTUBE ===
    if reanudar and _paso_completado('data/repertorio_filtrado.json'):
        logger.info(f"\n⏭️  PASO {paso_actual}/{total_pasos}: FILTRO YOUTUBE — ya completado, saltando")
    else:
        logger.info("\n" + "=" * 60)
        logger.info(f"📦 PASO {paso_actual}/{total_pasos}: FILTRO YOUTUBE")
        logger.info("=" * 60)

        try:
            from modules.filtrar_youtube import run as filtrar_yt
            filtrar_yt(headless=headless, verbose=True, input_file='data/repertorio.json')
        except Exception as e:
            logger.error(f"Error en filtro YouTube: {e}")
            return False

    paso_actual += 1

    # === MÓDULO 3: LINKS ===
    if reanudar and _paso_completado('data/repertorio_con_links.json'):
        logger.info(f"\n⏭️  PASO {paso_actual}/{total_pasos}: EXTRACCIÓN DE LINKS — ya completado, saltando")
    else:
        logger.info("\n" + "=" * 60)
        logger.info(f"📦 PASO {paso_actual}/{total_pasos}: EXTRACCIÓN DE LINKS")
        logger.info("=" * 60)

        try:
            from modules.extraer_links import run as extraer_links
            extraer_links(verbose=True, input_file='data/repertorio_filtrado.json')
        except Exception as e:
            logger.error(f"Error en extracción de links: {e}")
            return False

    return True


def ejecutar_descarga(verbose=True):
    """Ejecuta el módulo de descarga y organización"""
    logger.info("\n" + "=" * 60)
    logger.info("📦 PASO 4: DESCARGA Y ORGANIZACIÓN")
    logger.info("=" * 60)

    try:
        from modules.descargar_y_organizar import run as descargar, verificar_dependencias

        if not verificar_dependencias():
            logger.warning("Faltan dependencias. Ver README.md")
            return False

        descargar(verbose=verbose)
        return True

    except Exception as e:
        logger.error(f"Error en descarga: {e}")
        return False


def mostrar_resumen():
    """Muestra resumen final"""
    import json

    print("\n" + "=" * 60)
    print("✅ EXTRACCIÓN COMPLETADA")
    print("=" * 60)

    # Estadísticas
    if os.path.exists('data/repertorio_con_links.json'):
        with open('data/repertorio_con_links.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        total = len(data)
        con_links = sum(1 for r in data if r.get('download_links'))
        total_links = sum(len(r.get('download_links', [])) for r in data)

        print(f"\n📊 Estadísticas:")
        print(f"   Releases procesados: {total}")
        print(f"   Releases con links: {con_links}")
        print(f"   Total links extraídos: {total_links}")

    # Filtro YouTube
    if os.path.exists('data/releases_mainstream.txt'):
        with open('data/releases_mainstream.txt', 'r') as f:
            lineas = [l for l in f if not l.startswith('#') and l.strip()]
        mainstream = len(lineas) // 2  # Cada release son 2 líneas
        print(f"   Excluidos por YouTube: {mainstream}")

    # Archivos generados
    print(f"\n📁 Archivos generados:")

    archivo_principal = 'data/links_descarga.txt'
    if os.path.exists(archivo_principal):
        with open(archivo_principal, 'r') as f:
            num_links = len(f.readlines())
        print(f"   ★ {archivo_principal} ({num_links} links)")

    otros = ['data/discografia_detalle.txt', 'data/repertorio_con_links.json']
    for archivo in otros:
        if os.path.exists(archivo):
            size = os.path.getsize(archivo)
            if size > 1024:
                size_str = f"{size/1024:.1f} KB"
            else:
                size_str = f"{size} bytes"
            print(f"     {archivo} ({size_str})")


def main():
    mostrar_banner()

    # Verificar dependencias
    if not verificar_dependencias():
        logger.error("Corrige los archivos faltantes y vuelve a ejecutar.")
        sys.exit(1)

    # Detectar datos anteriores y preguntar
    reanudar = False
    if hay_archivos_anteriores():
        opcion = menu_reanudar_o_limpiar()
        if opcion == 'cancelar':
            print("Cancelado.")
            sys.exit(0)
        elif opcion == 'limpiar':
            limpiar_archivos_anteriores()
        else:
            reanudar = True
            logger.info("📂 Reanudando desde ejecución anterior")

    # Seleccionar tipos
    tipos_permitidos = seleccionar_tipos_disco()
    tipos_nombres = [TIPOS_DISCO.get(t, str(t)) for t in tipos_permitidos]
    print(f"\n✓ Tipos seleccionados: {', '.join(tipos_nombres)}")

    # Preguntar modo headless
    headless = preguntar_headless()

    # Detectar recursos automáticamente
    workers_browser, workers_api = detectar_recursos()

    # Resumen de configuración
    print("\n" + "-" * 40)
    print("📋 CONFIGURACIÓN:")
    print(f"   Tipos: {', '.join(tipos_nombres)}")
    print(f"   Modo: {'Invisible' if headless else 'Visible'}")
    if reanudar:
        print(f"   Modo: REANUDAR (saltará pasos completados)")
    print("-" * 40)

    confirmar = input("\n¿Iniciar extracción? [S/n]: ").strip().lower()
    if confirmar == 'n':
        print("Cancelado.")
        sys.exit(0)

    # Ejecutar pipeline de extracción
    exito = ejecutar_pipeline(
        tipos_permitidos,
        headless=headless,
        reanudar=reanudar
    )

    if exito:
        mostrar_resumen()

        # Ejecutar descarga automáticamente
        ejecutar_descarga(verbose=True)

        print("\n🎸 ¡Proceso completado!")
    else:
        print("\n⚠️  El proceso terminó con errores.")
        sys.exit(1)


if __name__ == "__main__":
    main()
