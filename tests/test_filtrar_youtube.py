"""YouTube filter against fakes: no browser is started and YouTube is never contacted."""

import asyncio
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from playwright.async_api import TimeoutError as TimeoutPlaywright

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


class _Pagina:
    """Fake Playwright page: `goto_falla[i]` says whether the i-th search raises."""

    def __init__(self, goto_falla=(), sin_resultados=False, resultados=()):
        self.goto_falla = goto_falla
        self.sin_resultados = sin_resultados
        self.resultados = list(resultados)
        self.busquedas = 0

    async def goto(self, url, **kwargs):
        i = self.busquedas
        self.busquedas += 1
        if i < len(self.goto_falla) and self.goto_falla[i]:
            raise RuntimeError("net::ERR_CONNECTION_RESET")

    async def wait_for_selector(self, selector, **kwargs):
        if self.sin_resultados:
            raise TimeoutPlaywright("Timeout 20000ms exceeded")

    async def evaluate(self, script, *args):
        return self.resultados


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

    def _correr(self, falso, repertorio, verbose=False, num_workers=2):
        with mock.patch.object(filtrar_youtube, "YouTubeFilterParallel", falso):
            return asyncio.run(filtrar_youtube.filtrar_por_youtube(
                repertorio, ["full album"], verbose=verbose, num_workers=num_workers))

    def _ids_en_checkpoint(self):
        lineas = Path(filtrar_youtube.CHECKPOINT_FILE).read_text(encoding="utf-8").splitlines()
        return [json.loads(linea)["post_id"] for linea in lineas]

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

    def test_un_fallo_o_timeout_no_queda_como_veredicto_y_se_reintenta(self):
        repertorio = [_release(1), _release(2), _release(3), _release(4)]

        async def procesar(release):
            if release["post_id"] == 1:
                raise RuntimeError("chromium murio")
            if release["post_id"] == 2:
                await asyncio.sleep(3600)
            return release["post_id"] == 4, "Banda 4 - Disco 4 (Full Album)"

        with mock.patch.object(filtrar_youtube, "RELEASE_TIMEOUT", 0.05):
            aprobados, rechazados = self._correr(_filtro_falso(procesar), repertorio)

        self.assertEqual(sorted(self._ids_en_checkpoint()), [3, 4])
        self.assertEqual(sorted(r["post_id"] for r in aprobados), [1, 2, 3])
        self.assertEqual([r["post_id"] for r in rechazados], [4])

        verificados = []

        async def reintento(release):
            verificados.append(release["post_id"])
            return False, None

        self._correr(_filtro_falso(reintento), repertorio)
        self.assertEqual(sorted(verificados), [1, 2])

    def test_el_resumen_cuenta_los_releases_sin_verificar_aunque_no_sea_verbose(self):
        async def procesar(release):
            raise RuntimeError("chromium murio")

        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            aprobados, _ = self._correr(_filtro_falso(procesar),
                                        [_release(1), _release(2), _release(3)])

        self.assertEqual(len(aprobados), 3)
        self.assertIn("3 releases sin verificar", salida.getvalue())

    def test_un_release_sin_verificar_no_se_imprime_como_underground(self):
        async def procesar(release):
            if release["post_id"] == 1:
                raise RuntimeError("chromium murio")
            return False, None

        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self._correr(_filtro_falso(procesar), [_release(1), _release(2)], verbose=True)

        lineas = salida.getvalue().splitlines()
        sin_verificar = next(linea for linea in lineas if "Banda 1" in linea)
        verificado = next(linea for linea in lineas if "Banda 2" in linea)
        self.assertIn("sin verificar", sin_verificar)
        self.assertNotIn("Underground", sin_verificar)
        self.assertIn("Underground", verificado)
        self.assertIn("1 releases sin verificar", salida.getvalue())

    def test_las_listas_salen_en_el_orden_del_repertorio(self):
        repertorio = [_release(i) for i in range(1, 6)]
        # 2 and 4 were done before the cut; 5, 3 and 1 finish in reverse order
        self._escribir_checkpoint([_registro(repertorio[3], False), _registro(repertorio[1], True)])
        espera = {5: 0, 3: 0.05, 1: 0.1}

        async def procesar(release):
            await asyncio.sleep(espera[release["post_id"]])
            return release["post_id"] == 3, "Banda 3 - Disco 3 (Full Album)"

        aprobados, rechazados = self._correr(_filtro_falso(procesar), repertorio, num_workers=3)

        # the scenario is real only if the checkpoint kept the completion order
        self.assertEqual(self._ids_en_checkpoint(), [4, 2, 5, 3, 1])
        self.assertEqual([r["post_id"] for r in aprobados], [1, 4, 5])
        self.assertEqual([r["post_id"] for r in rechazados], [2, 3])

        # nothing pending now: the lists rebuilt from the checkpoint keep the order too
        aprobados, rechazados = self._correr(_filtro_falso(_underground), repertorio)
        self.assertEqual([r["post_id"] for r in aprobados], [1, 4, 5])
        self.assertEqual([r["post_id"] for r in rechazados], [2, 3])

    def test_un_checkpoint_cortado_a_medias_no_pierde_el_registro_nuevo(self):
        repertorio = [_release(1), _release(2)]
        completo = json.dumps(_registro(repertorio[0], False), ensure_ascii=False)
        corte = '{"post_id": 2, "mainstream": fal'  # the process died mid-write, no newline
        Path(filtrar_youtube.CHECKPOINT_FILE).write_text(completo + "\n" + corte, encoding="utf-8")

        self._correr(_filtro_falso(_underground), repertorio)

        _, _, procesados = filtrar_youtube._cargar_checkpoint({"1", "2"})
        self.assertEqual(procesados, {"1", "2"})


class VerificarDisponibilidad(unittest.TestCase):
    URLS = ["https://youtube.test/busqueda-1", "https://youtube.test/busqueda-2"]
    COINCIDENCIA = [{"title": "Obscura Flame - Black Tomb (Full Album)", "channel": ""}]

    def _verificar(self, pagina):
        filtro = filtrar_youtube.YouTubeFilterParallel(num_workers=1)
        filtro.keywords = ["full album"]
        filtro.neg_words = set()
        return asyncio.run(filtro.verificar_disponibilidad(
            pagina, self.URLS, "Obscura Flame", "Black Tomb", "Album"))

    def test_una_busqueda_que_falla_sin_coincidencia_levanta_error(self):
        pagina = _Pagina(goto_falla=(True, False), resultados=[])

        with self.assertRaises(Exception):
            self._verificar(pagina)

    def test_una_busqueda_que_falla_con_coincidencia_en_la_otra_sigue_siendo_mainstream(self):
        pagina = _Pagina(goto_falla=(True, False), resultados=self.COINCIDENCIA)

        self.assertEqual(self._verificar(pagina),
                         (True, "Obscura Flame - Black Tomb (Full Album)"))

    def test_sin_resultados_en_youtube_no_cuenta_como_fallo(self):
        pagina = _Pagina(sin_resultados=True)

        self.assertEqual(self._verificar(pagina), (False, None))


if __name__ == "__main__":
    unittest.main()
