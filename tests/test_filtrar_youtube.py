"""YouTube filter against fakes: no browser is started and YouTube is never contacted."""

import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules import filtrar_youtube


def _release(post_id):
    return {"post_id": post_id, "band": f"Banda {post_id}", "album": f"Disco {post_id}",
            "year": 2024, "type": "Album"}


def _filtro_falso(procesar):
    """Stands in for YouTubeFilterParallel: `procesar(release)` decides each verdict."""

    class Falso:
        creados = []

        def __init__(self, num_workers=5):
            self.num_workers = num_workers
            self.pages = []
            self.cerrado = False
            self.tareas_vivas = None
            Falso.creados.append(self)

        async def iniciar_browser(self, headless=True):
            self.pages = [object() for _ in range(self.num_workers)]

        async def procesar_release(self, release, page, max_videos=10):
            es_mainstream, titulo = await procesar(release)
            return release, es_mainstream, titulo

        async def cerrar(self):
            self.cerrado = True
            actual = asyncio.current_task()
            self.tareas_vivas = [t for t in asyncio.all_tasks() if t is not actual and not t.done()]

    return Falso


async def _underground(release):
    return False, None


def _registro(release, mainstream):
    return {"post_id": release["post_id"], "mainstream": mainstream,
            "razon": "full album" if mainstream else "", "release": release}


class CheckpointDelFiltro(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        cwd = os.getcwd()
        os.chdir(self.tmp)  # the filter reads and writes data/ under the current directory
        self.addCleanup(os.chdir, cwd)
        (self.tmp / "data").mkdir()

    def _escribir_checkpoint(self, registros):
        lineas = [json.dumps(r, ensure_ascii=False) + "\n" for r in registros]
        Path(filtrar_youtube.CHECKPOINT_FILE).write_text("".join(lineas), encoding="utf-8")

    def _correr(self, falso, repertorio, **kwargs):
        with mock.patch.object(filtrar_youtube, "YouTubeFilterParallel", falso):
            return asyncio.run(filtrar_youtube.filtrar_por_youtube(
                repertorio, ["full album"], verbose=False, num_workers=2, **kwargs))

    def test_reanuda_y_verifica_solo_los_pendientes(self):
        repertorio = [_release(1), _release(2), _release(3)]
        self._escribir_checkpoint([_registro(repertorio[0], False), _registro(repertorio[1], True)])
        verificados = []

        async def procesar(release):
            verificados.append(release["post_id"])
            return False, None

        aprobados, rechazados = self._correr(_filtro_falso(procesar), repertorio)

        self.assertEqual(verificados, [3])
        self.assertEqual([r["post_id"] for r in aprobados], [1, 3])
        self.assertEqual([r["post_id"] for r in rechazados], [2])

    def test_sin_pendientes_devuelve_todo_sin_abrir_el_navegador(self):
        repertorio = [_release(1), _release(2)]
        self._escribir_checkpoint([_registro(repertorio[0], False), _registro(repertorio[1], True)])
        falso = _filtro_falso(_underground)

        aprobados, rechazados = self._correr(falso, repertorio)

        self.assertEqual(falso.creados, [])
        self.assertEqual([r["post_id"] for r in aprobados], [1])
        self.assertEqual([r["post_id"] for r in rechazados], [2])

    def test_run_borra_el_checkpoint_al_terminar_bien(self):
        repertorio = [_release(1), _release(2)]
        Path("data/repertorio.json").write_text(json.dumps(repertorio), encoding="utf-8")
        existia_durante_la_corrida = []

        async def procesar(release):
            existia_durante_la_corrida.append(os.path.exists(filtrar_youtube.CHECKPOINT_FILE))
            return False, None

        with mock.patch.object(filtrar_youtube, "YouTubeFilterParallel", _filtro_falso(procesar)):
            filtrar_youtube.run(verbose=False, num_workers=2)

        self.assertEqual(existia_durante_la_corrida, [True, True])
        self.assertFalse(os.path.exists(filtrar_youtube.CHECKPOINT_FILE))
        guardados = json.loads(Path(filtrar_youtube.OUTPUT_FILE).read_text(encoding="utf-8"))
        self.assertEqual([r["post_id"] for r in guardados], [1, 2])


if __name__ == "__main__":
    unittest.main()
