#!/usr/bin/env python3
"""
Utilidades compartidas para optimización automática
"""

import os

def detectar_workers_optimos():
    """
    Detecta automáticamente el número óptimo de workers
    basado en CPU y memoria disponible
    """
    cpu_count = os.cpu_count() or 4

    # Intentar detectar memoria
    try:
        import psutil
        mem_gb = psutil.virtual_memory().total / (1024 ** 3)

        # Más conservador para navegadores (usan mucha RAM)
        if mem_gb >= 32:
            workers_mem = 12
        elif mem_gb >= 16:
            workers_mem = 8
        elif mem_gb >= 8:
            workers_mem = 5
        elif mem_gb >= 4:
            workers_mem = 3
        else:
            workers_mem = 2

    except ImportError:
        # Sin psutil, estimar por CPU
        workers_mem = min(cpu_count, 6)

    # Usar el menor entre CPU y memoria
    workers = min(cpu_count - 1, workers_mem)  # Dejar 1 CPU libre
    workers = max(2, workers)  # Mínimo 2

    return workers


def detectar_workers_api():
    """
    Workers para llamadas API - más conservador para evitar rate limiting
    """
    cpu_count = os.cpu_count() or 4
    # Más conservador para evitar 429
    return min(cpu_count, 10)


def mostrar_recursos():
    """Muestra los recursos detectados"""
    cpu_count = os.cpu_count() or 4

    try:
        import psutil
        mem = psutil.virtual_memory()
        mem_gb = mem.total / (1024 ** 3)
        mem_disp = mem.available / (1024 ** 3)
        print(f"   CPU: {cpu_count} cores")
        print(f"   RAM: {mem_gb:.1f} GB total, {mem_disp:.1f} GB disponible")
    except ImportError:
        print(f"   CPU: {cpu_count} cores")
        print(f"   RAM: (instala psutil para detectar)")

    workers_browser = detectar_workers_optimos()
    workers_api = detectar_workers_api()

    print(f"   Workers browser: {workers_browser}")
    print(f"   Workers API: {workers_api}")

    return workers_browser, workers_api
