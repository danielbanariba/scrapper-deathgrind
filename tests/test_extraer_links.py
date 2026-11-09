"""Link extraction against fakes: the site is never contacted and no credit is spent."""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules import extraer_links, utils


class _Respuesta:
    def __init__(self, status_code, cuerpo):
        self.status_code = status_code
        self._cuerpo = cuerpo

    def json(self):
        return self._cuerpo


class _SesionLinks:
    """Gives one link per post until `con_creditos` posts were asked, then 403 like the site."""

    def __init__(self, con_creditos):
        self.con_creditos = con_creditos
        self.pedidos = []

    def get(self, url, **kwargs):
        self.pedidos.append(url)
        if len(self.pedidos) > self.con_creditos:
            return _Respuesta(403, {"error": "", "errorCode": "DOWNLOAD_CREDITS_EXHAUSTED"})
        post_id = url.rstrip("/").split("/")[-2]
        return _Respuesta(200, {"links": [{"href": f"https://mega.nz/file/{post_id}"}]})


class _SesionLogin:
    headers = {}
    cookies = {}


def _release(post_id, band, album):
    return {"post_id": post_id, "band": band, "album": album, "year": 2024,
            "type": "Album", "post_url": f"https://deathgrind.club/posts/{post_id}"}


# Same contract as click-auto-editor's registro_publicados.py: leer(ruta) -> objeto con buscar(nombre)
REGISTRO_FALSO = """
from pathlib import Path


class _Registro:
    def __init__(self, nombres):
        self.nombres = nombres

    def buscar(self, nombre):
        return nombre.lower() in self.nombres


def leer(ruta):
    ruta = Path(ruta)
    lineas = ruta.read_text(encoding="utf-8").splitlines() if ruta.exists() else []
    return _Registro({linea.split("\\t")[0] for linea in lineas if linea})
"""


class ExtraerLinks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        cwd = os.getcwd()
        os.chdir(self.tmp)  # run() writes to data/ under the current directory
        self.addCleanup(os.chdir, cwd)
        for objetivo, valor in (
            ("crear_sesion_autenticada", lambda: _SesionLogin()),
            ("cargar_env", lambda: None),
            ("delay_con_jitter", lambda *a, **k: None),
        ):
            parche = mock.patch.object(extraer_links, objetivo, valor)
            parche.start()
            self.addCleanup(parche.stop)
        parche = mock.patch.object(extraer_links.time, "sleep", lambda s: None)
        parche.start()
        self.addCleanup(parche.stop)
        # No click-auto-editor next to the tests unless a test puts one there.
        parche = mock.patch.dict(os.environ, {"CLICK_AUTO_EDITOR_DIR": str(self.tmp / "sin-editor")})
        parche.start()
        self.addCleanup(parche.stop)

    def _correr(self, repertorio, sesion, verbose=False):
        """Runs the step; what it prints stays in self.salida."""
        entrada = self.tmp / "repertorio_filtrado.json"
        entrada.write_text(json.dumps(repertorio), encoding="utf-8")
        self.salida = io.StringIO()
        with mock.patch.object(extraer_links, "_get_thread_session", return_value=sesion), \
                contextlib.redirect_stdout(self.salida):
            extraer_links.run(verbose=verbose, num_workers=1, input_file=str(entrada))
        salida = self.tmp / utils.REPERTORIO_CON_LINKS_FILE
        return json.loads(salida.read_text(encoding="utf-8"))

    def _poner_registro(self, codigo, filas=()):
        """A click-auto-editor folder whose registro_publicados.py is `codigo`; returns it."""
        editor = self.tmp / "editor"
        (editor / "data" / "agente").mkdir(parents=True, exist_ok=True)
        (editor / "registro_publicados.py").write_text(codigo, encoding="utf-8")
        (editor / "data" / "agente" / "ya_publicados.tsv").write_text(
            "".join(f"{fila}\n" for fila in filas), encoding="utf-8")
        return editor

    def test_sin_creditos_deja_de_pedir_links_y_no_marca_lo_que_no_pidio(self):
        repertorio = [_release(i, f"Banda {i}", f"Disco {i}") for i in range(1, 6)]
        sesion = _SesionLinks(con_creditos=1)

        resultado = self._correr(repertorio, sesion)

        self.assertEqual(len(sesion.pedidos), 2)
        self.assertEqual(resultado[0]["download_links"][0]["url"], "https://mega.nz/file/1")
        self.assertEqual([r.get("download_links") for r in resultado[1:]], [None] * 4)

    def test_con_la_cuenta_sin_creditos_los_que_quedan_en_cola_no_esperan_su_pausa(self):
        repertorio = [_release(i, f"Banda {i}", f"Disco {i}") for i in range(1, 6)]

        with mock.patch.object(extraer_links, "delay_con_jitter") as pausa:
            self._correr(repertorio, _SesionLinks(con_creditos=1))

        self.assertEqual(pausa.call_count, 2)

    def test_el_resumen_no_cuenta_los_releases_que_no_se_pidieron(self):
        repertorio = [_release(i, f"Banda {i}", f"Disco {i}") for i in range(1, 6)]

        self._correr(repertorio, _SesionLinks(con_creditos=1), verbose=True)

        self.assertIn("✓ 1 releases procesados", self.salida.getvalue())

    def test_no_pide_links_de_lo_ya_publicado_con_un_registro_falso(self):
        editor = self._poner_registro(REGISTRO_FALSO, filas=["pigto - the collector\tsubir\tabc123"])
        repertorio = [_release(7, "PIGTO", "The Collector"), _release(8, "Otra Banda", "Disco")]
        sesion = _SesionLinks(con_creditos=10)

        with mock.patch.dict(os.environ, {"CLICK_AUTO_EDITOR_DIR": str(editor)}):
            resultado = self._correr(repertorio, sesion)

        self.assertEqual(sesion.pedidos, [f"{utils.API_URL}/posts/8/links"])
        self.assertEqual([r["post_id"] for r in resultado], [8])

    def test_un_registro_que_no_carga_frena_el_paso_sin_pedir_links(self):
        for causa, codigo in (
            ("SyntaxError", "def leer(:\n"),
            ("ModuleNotFoundError", "import modulo_que_solo_existe_en_otro_entorno\n"),
            ("AttributeError", "x = 1\n"),
            ("OSError", "def leer(ruta):\n    raise OSError('disco ilegible')\n"),
        ):
            with self.subTest(causa=causa):
                editor = self._poner_registro(codigo)
                repertorio = [_release(i, f"Banda {i}", f"Disco {i}") for i in range(1, 4)]
                sesion = _SesionLinks(con_creditos=10)

                with mock.patch.dict(os.environ, {"CLICK_AUTO_EDITOR_DIR": str(editor)}), \
                        self.assertRaises(SystemExit) as parada:
                    self._correr(repertorio, sesion)

                # A text exit code is printed as one line, without a traceback
                self.assertIsInstance(parada.exception.code, str)
                self.assertIn(str(editor / "registro_publicados.py"), parada.exception.code)
                self.assertIn(causa, parada.exception.code)
                self.assertEqual(sesion.pedidos, [])

    def test_no_pide_links_de_lo_ya_publicado(self):
        origen = Path(os.environ.get("CLICK_AUTO_EDITOR_REAL", utils.DIR_CLICK_AUTO_EDITOR))
        codigo = origen.expanduser() / "registro_publicados.py"
        if not codigo.is_file():
            self.skipTest(f"no está {codigo}")
        editor = self.tmp / "editor"
        editor.mkdir()
        shutil.copy(codigo, editor / "registro_publicados.py")
        spec = importlib.util.spec_from_file_location("registro_de_prueba", editor / "registro_publicados.py")
        registro = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(registro)
        registro.anotar(editor / "data" / "agente" / "ya_publicados.tsv",
                        [("Pigto - The Collector", "subir", "abc123")])
        repertorio = [_release(7, "PIGTO", "The Collector"), _release(8, "Otra Banda", "Disco")]
        sesion = _SesionLinks(con_creditos=10)

        with mock.patch.dict(os.environ, {"CLICK_AUTO_EDITOR_DIR": str(editor)}):
            resultado = self._correr(repertorio, sesion)

        self.assertEqual(sesion.pedidos, [f"{utils.API_URL}/posts/8/links"])
        self.assertEqual([r["post_id"] for r in resultado], [8])


if __name__ == "__main__":
    unittest.main()
