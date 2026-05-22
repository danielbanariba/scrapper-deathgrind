#!/usr/bin/env python3
"""
Daemon que drena data/mega_pendientes.json.

Procesa releases Mega uno por uno, persiste el JSON después de cada
release (si lo matás, no perdés progreso), respeta el cooldown de Mega
(duerme y reintenta en vez de morir como hace main.py). Termina solo
cuando la cola queda vacía.

Uso típico (tmux):
    tmux new -s dg-mega
    source env/bin/activate
    python procesar_mega_pendientes.py
    # Ctrl+b d  → detach (sigue corriendo)
    # tmux attach -t dg-mega  → volver a verlo

Logs además a data/mega_daemon.log.
"""

import logging
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importar módulos primero para que sus loggers se inicialicen,
# después les enchufamos un FileHandler para volcar todo al log.
from modules import descargar_y_organizar as dy
from modules.descargar_y_organizar import (
    DESTINO_BASE,
    TEMP_DIR,
    _cleanup_playwright,
    _close_session,
    _mega_cooldown_activo,
    _mega_cooldown_restante,
    cargar_descargados,
    cargar_fallidos,
    cargar_mega_pendientes,
    guardar_descargado,
    guardar_fallido,
    guardar_mega_pendientes,
    procesar_release,
    verificar_dependencias,
)
from modules.logger import setup_logger

LOG_FILE = "data/mega_daemon.log"
PAUSA_ENTRE_RELEASES = 2.0
CHUNK_SLEEP_COOLDOWN = 10  # despertarse cada N segs para chequear SIGINT


def _attach_file_handler(path):
    """Agrega un FileHandler a todos los loggers ya configurados.
    Los loggers de los módulos tienen propagate=False, así que no
    podemos confiar en el root."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    ))
    fh.setLevel(logging.DEBUG)
    for name in list(logging.Logger.manager.loggerDict.keys()):
        lg = logging.getLogger(name)
        if isinstance(lg, logging.Logger) and lg.handlers:
            lg.addHandler(fh)


log = setup_logger("mega_daemon")

_stop = False


def _signal_handler(signum, _frame):
    global _stop
    log.warning(f"⚠️  Señal {signum} recibida; saliendo al terminar el release actual")
    _stop = True


def _post_id(release):
    return str(release.get("post_id", "")).strip()


def _quitar_de_cola(post_id):
    """Recarga el JSON, quita el release indicado, persiste."""
    cola = cargar_mega_pendientes()
    cola = [r for r in cola if _post_id(r) != post_id]
    guardar_mega_pendientes(cola)


def _dormir_cooldown():
    """Duerme hasta que el cooldown expire, en chunks para responder a SIGINT."""
    restante = _mega_cooldown_restante()
    if restante <= 0:
        return
    mins, segs = divmod(restante, 60)
    log.info(f"⏸️  Mega en cooldown ({mins}m {segs}s). Durmiendo…")
    total = restante + 5  # margen
    dormido = 0
    while dormido < total and not _stop:
        time.sleep(min(CHUNK_SLEEP_COOLDOWN, total - dormido))
        dormido += CHUNK_SLEEP_COOLDOWN
    log.info("⏯️  Reanudando")


def main():
    _attach_file_handler(LOG_FILE)

    log.info("=" * 60)
    log.info("🌙 MEGA DAEMON iniciado")
    log.info(f"   destino: {DESTINO_BASE}")
    log.info(f"   log:     {LOG_FILE}")
    log.info("=" * 60)

    if not verificar_dependencias():
        log.error("Faltan dependencias del sistema (unrar/7z/megatools).")
        return 1

    # Fail loudly si el destino no está montado: bajo systemd, Restart=on-failure
    # va a reintentar hasta que el mount aparezca.
    if not os.path.isdir(DESTINO_BASE):
        log.error(f"❌ Destino no accesible: {DESTINO_BASE} (¿mount caído?)")
        return 2

    os.makedirs(TEMP_DIR, exist_ok=True)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    descargados = cargar_descargados()
    fallidos = cargar_fallidos()
    log.info(f"📋 {len(descargados)} ya descargados | {len(fallidos)} fallidos previos")

    exitosos = 0
    omitidos = 0
    fallidos_run = 0
    total_bytes = 0

    while not _stop:
        cola = cargar_mega_pendientes()
        if not cola:
            log.info("✅ Cola Mega vacía, trabajo terminado")
            break

        if _mega_cooldown_activo():
            _dormir_cooldown()
            continue

        release = cola[0]
        pid = _post_id(release)
        band = release.get("band", "?")
        album = release.get("album", "?")
        log.info(f"[{len(cola)} pendientes] 🎵 {band} — {album} (post {pid})")

        try:
            exito, mensaje, info = procesar_release(
                release,
                DESTINO_BASE,
                TEMP_DIR,
                verbose=True,
                descargados=descargados,
                fallidos=fallidos,
                show_progress=False,
            )
        except Exception as e:
            log.error(f"❌ Excepción procesando release: {e}")
            exito, mensaje, info = False, f"Excepción: {e}", None

        if exito:
            if mensaje in ("Ya existe", "Ya descargado", "Fallido previo"):
                omitidos += 1
                log.info(f"⏭️  {mensaje}")
            else:
                exitosos += 1
                if info:
                    guardar_descargado(info["post_id"], info["band"], info["album"])
                    descargados.add(info["post_id"])
                    total_bytes += info.get("bytes", 0) or 0
                log.info(f"✓ Descargado OK ({mensaje})")
            _quitar_de_cola(pid)

        elif mensaje == "Mega pendiente":
            # Mega volvió a cooldown durante el intento. NO sacamos de la cola;
            # el próximo loop detectará el cooldown y dormirá.
            log.info("⏸️  Mega entró en cooldown durante el intento; queda en cola")

        else:
            fallidos_run += 1
            es_perm = "definitivo" in mensaje.lower()
            es_transitorio = (
                mensaje == "Descarga parcial"
                or "temporalmente caído" in mensaje.lower()
            )
            if not es_transitorio:
                guardar_fallido(release, fallidos, motivo=mensaje, permanente=es_perm)
            log.warning(f"✗ Fallido: {mensaje}{' [PERM]' if es_perm else ''}")
            # Lo sacamos igual: si es transitorio el próximo run del pipeline
            # lo va a reencolar; si es definitivo ya quedó en fallidos.
            _quitar_de_cola(pid)

        # Pausa anti rate-limit entre releases
        if not _stop:
            time.sleep(PAUSA_ENTRE_RELEASES)

    _close_session()
    _cleanup_playwright()

    log.info("=" * 60)
    log.info("📊 RESUMEN DEL RUN")
    log.info(f"✓ Exitosos:  {exitosos}")
    log.info(f"⏭️ Omitidos: {omitidos}")
    log.info(f"✗ Fallidos:  {fallidos_run}")
    if total_bytes >= 1024 ** 3:
        log.info(f"📦 Total:    {total_bytes / 1024 ** 3:.2f} GB")
    elif total_bytes > 0:
        log.info(f"📦 Total:    {total_bytes / 1024 ** 2:.1f} MB")
    cola = cargar_mega_pendientes()
    log.info(f"📋 Quedan en cola: {len(cola)}")
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
