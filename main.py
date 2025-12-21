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

# Agregar módulos al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    print()
    print("=" * 60)
    print("🎸 DEATHGRIND.CLUB SCRAPER")
    print("=" * 60)
    print()


def limpiar_archivos_anteriores():
    """Elimina archivos de ejecuciones anteriores"""
    eliminados = 0
    for archivo in ARCHIVOS_LIMPIAR:
        if os.path.exists(archivo):
            os.remove(archivo)
            eliminados += 1

    if eliminados > 0:
        print(f"🗑️  {eliminados} archivo(s) anterior(es) eliminado(s)")


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
        print("⚠️  Archivos requeridos faltantes:")
        for f in faltantes:
            print(f)
        print()
        return False

    # Verificar opcionales
    for archivo, desc in archivos_opcionales:
        if not os.path.exists(archivo):
            print(f"ℹ️  {archivo} no encontrado (opcional)")

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
    print(f"\n⏳ Esperando {segundos}s para evitar rate limiting...")
    time.sleep(segundos)


def ejecutar_pipeline(tipos_permitidos, headless=True):
    """Ejecuta los 3 módulos en secuencia"""

    # Crear directorio data si no existe
    os.makedirs('data', exist_ok=True)

    total_pasos = 3
    paso_actual = 1

    # === MÓDULO 1: BANDAS + REPERTORIO (optimizado) ===
    print("\n" + "=" * 60)
    print(f"📦 PASO {paso_actual}/{total_pasos}: EXTRACCIÓN DE BANDAS Y REPERTORIO")
    print("=" * 60)

    try:
        from modules.extraer_bandas import run as extraer_bandas
        extraer_bandas(tipos_permitidos=tipos_permitidos, verbose=True)
    except Exception as e:
        print(f"\n❌ Error en extracción: {e}")
        return False

    paso_actual += 1
    pausa_entre_modulos(3)

    # === MÓDULO 2: FILTRO YOUTUBE ===
    print("\n" + "=" * 60)
    print(f"📦 PASO {paso_actual}/{total_pasos}: FILTRO YOUTUBE")
    print("=" * 60)

    try:
        from modules.filtrar_youtube import run as filtrar_yt
        # Usar repertorio.json como entrada (ya filtrado por sellos)
        import modules.filtrar_youtube as yt_module
        yt_module.INPUT_FILE = 'data/repertorio.json'
        filtrar_yt(headless=headless, verbose=True)
    except Exception as e:
        print(f"\n❌ Error en filtro YouTube: {e}")
        return False

    paso_actual += 1

    # === MÓDULO 3: LINKS ===
    print("\n" + "=" * 60)
    print(f"📦 PASO {paso_actual}/{total_pasos}: EXTRACCIÓN DE LINKS")
    print("=" * 60)

    try:
        from modules.extraer_links import run as extraer_links
        # Usar repertorio_filtrado.json (después del filtro YouTube)
        import modules.extraer_links as links_module
        links_module.INPUT_FILE = 'data/repertorio_filtrado.json'
        extraer_links(verbose=True)
    except Exception as e:
        print(f"\n❌ Error en extracción de links: {e}")
        return False

    return True


def ejecutar_descarga(verbose=True):
    """Ejecuta el módulo de descarga y organización"""
    print("\n" + "=" * 60)
    print("📦 PASO 4: DESCARGA Y ORGANIZACIÓN")
    print("=" * 60)

    try:
        from modules.descargar_y_organizar import run as descargar, verificar_dependencias

        if not verificar_dependencias():
            print("\n⚠️  Faltan dependencias. Ver README.md")
            return False

        descargar(verbose=verbose)
        return True

    except Exception as e:
        print(f"\n❌ Error en descarga: {e}")
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
        print("Corrige los archivos faltantes y vuelve a ejecutar.")
        sys.exit(1)

    # Limpiar archivos anteriores
    limpiar_archivos_anteriores()

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
    print("-" * 40)

    confirmar = input("\n¿Iniciar extracción? [S/n]: ").strip().lower()
    if confirmar == 'n':
        print("Cancelado.")
        sys.exit(0)

    # Ejecutar pipeline de extracción
    exito = ejecutar_pipeline(
        tipos_permitidos,
        headless=headless
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
