"""Link extraction against fakes: the site is never contacted and no credit is spent."""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import threading
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


class _RespuestaHtml(_Respuesta):
    """A page that is not JSON, like the one Cloudflare puts in front of the site."""

    def json(self):
        raise ValueError("no es JSON")


class _SesionLinks:
    """Gives one link per post until `con_creditos` posts were asked, then 403 like the site.

    `latencia` makes each answer wait, so several workers overlap as they do on the network.
    """

    def __init__(self, con_creditos, latencia=0):
        self.con_creditos = con_creditos
        self.latencia = latencia
        self.pedidos = []

    def get(self, url, **kwargs):
        self.pedidos.append(url)
        if self.latencia:
            threading.Event().wait(self.latencia)
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


def clave(nombre):
    return nombre.split(" (")[0].lower()
"""


# What registro_publicados.clave promises: "banda|album" with no case, accents or signs,
# and None when either half is empty
REGISTRO_CON_CLAVE = REGISTRO_FALSO + '''
import unicodedata


def _compacto(texto):
    texto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in texto if c.isalnum())


def clave(nombre):
    if " - " not in nombre:
        return None
    banda, album = (_compacto(parte) for parte in nombre.split(" - ", 1))
    return f"{banda}|{album}" if banda and album else None
'''


def _config_falsa(album, renderizando, otras):
    """A click-auto-editor config.py whose queue folders are the given paths."""
    return (
        "from pathlib import Path\n"
        f"DIRS_ORIGEN_RENDER = (Path({str(otras / 'limpieza')!r}), Path({str(album)!r}), "
        f"Path({str(otras / 'EP')!r}))\n"
        f"DIR_RENDERIZANDO = Path({str(renderizando)!r})\n"
        f"DIR_UPLOAD = Path({str(otras / 'upload_video')!r})\n"
        f"DIR_CENSURA = Path({str(otras / 'Censura')!r})\n"
    )


class SinCreditos(unittest.TestCase):
    def test_solo_un_403_con_el_error_de_creditos_corta_la_corrida(self):
        casos = (
            ("una pagina HTML con 403", _RespuestaHtml(403, None), False),
            ("un 403 con otro errorCode", _Respuesta(403, {"errorCode": "FORBIDDEN"}), False),
            ("un 403 sin creditos", _Respuesta(403, {"errorCode": "DOWNLOAD_CREDITS_EXHAUSTED"}), True),
        )
        for nombre, respuesta, esperado in casos:
            with self.subTest(nombre):
                self.assertIs(extraer_links._sin_creditos(respuesta), esperado)


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

    def _correr(self, repertorio, sesion, num_workers=1, verbose=False):
        """Runs the step; what it prints stays in self.salida."""
        entrada = self.tmp / "repertorio_filtrado.json"
        entrada.write_text(json.dumps(repertorio), encoding="utf-8")
        self.salida = io.StringIO()
        with mock.patch.object(extraer_links, "_get_thread_session", return_value=sesion), \
                contextlib.redirect_stdout(self.salida):
            extraer_links.run(verbose=verbose, num_workers=num_workers, input_file=str(entrada))
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
        # The newest post goes first
        self.assertEqual(resultado[0]["download_links"][0]["url"], "https://mega.nz/file/5")
        self.assertEqual([r.get("download_links") for r in resultado[1:]], [None] * 4)

    def test_sin_creditos_avisa_con_varios_workers_y_no_pide_todos_los_releases(self):
        repertorio = [_release(i, f"Banda {i}", f"Disco {i}") for i in range(1, 21)]
        sesion = _SesionLinks(con_creditos=2, latencia=0.01)

        self._correr(repertorio, sesion, num_workers=5)

        self.assertIn("❌", self.salida.getvalue())
        self.assertIn("sin créditos", self.salida.getvalue())
        self.assertLess(len(sesion.pedidos), len(repertorio))

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

    def _poner_cola(self, codigo_registro, config=None):
        """A click-auto-editor with a queue: Album/ and Renderizando/ under self.tmp."""
        editor = self._poner_registro(codigo_registro)
        self.album, self.renderizando = self.tmp / "cola" / "Album", self.tmp / "ssd" / "Renderizando"
        self.album.mkdir(parents=True)
        self.renderizando.mkdir(parents=True)
        texto = config if config is not None else _config_falsa(self.album, self.renderizando, self.tmp / "cola")
        (editor / "config.py").write_text(texto, encoding="utf-8")
        return editor

    def test_no_pide_links_de_lo_que_ya_esta_en_una_carpeta_de_la_cola(self):
        codigo = Path(os.environ.get("CLICK_AUTO_EDITOR_REAL", utils.DIR_CLICK_AUTO_EDITOR)).expanduser()
        codigo = codigo / "registro_publicados.py"
        if not codigo.is_file():
            self.skipTest(f"no está {codigo}")
        editor = self._poner_cola(codigo.read_text(encoding="utf-8"))
        # Folder names as the queue keeps them: year, type tag and the __N suffix
        (self.album / "PIGTO - The Collector (2020) [EP]").mkdir()
        (self.renderizando / "Otra Banda - Disco (2008)__2").mkdir()
        repertorio = [_release(7, "Pigto", "The Collector"), _release(8, "Otra Banda", "Disco"),
                      _release(9, "Tercera", "Nuevo")]
        sesion = _SesionLinks(con_creditos=10)

        with mock.patch.dict(os.environ, {"CLICK_AUTO_EDITOR_DIR": str(editor)}):
            resultado = self._correr(repertorio, sesion, verbose=True)

        self.assertEqual(sesion.pedidos, [f"{utils.API_URL}/posts/9/links"])
        self.assertEqual([r["post_id"] for r in resultado], [9])
        self.assertIn("2 releases ya están en la cola", self.salida.getvalue())

    def test_una_config_que_no_carga_frena_el_paso_sin_pedir_links(self):
        for causa, config in (("SyntaxError", "DIR_EP = (\n"), ("AttributeError", "DIRS_ORIGEN_RENDER = ()\n")):
            with self.subTest(causa=causa):
                editor = self._poner_cola(REGISTRO_FALSO, config=config)
                sesion = _SesionLinks(con_creditos=10)

                with mock.patch.dict(os.environ, {"CLICK_AUTO_EDITOR_DIR": str(editor)}), \
                        self.assertRaises(SystemExit) as parada:
                    self._correr([_release(1, "Banda", "Disco")], sesion)

                self.assertIsInstance(parada.exception.code, str)
                self.assertIn(str(editor / "config.py"), parada.exception.code)
                self.assertIn(causa, parada.exception.code)
                self.assertEqual(sesion.pedidos, [])
                shutil.rmtree(self.tmp / "cola")
                shutil.rmtree(self.tmp / "ssd")

    def test_pide_primero_los_posts_mas_nuevos_y_sin_creditos_quedan_los_viejos(self):
        repertorio = [_release(10, "Vieja", "Uno"), _release(950, "Nueva", "Dos"),
                      _release(300, "Media", "Tres"), _release(42, "Otra", "Cuatro")]
        sesion = _SesionLinks(con_creditos=2)

        resultado = self._correr(repertorio, sesion)

        self.assertEqual(sesion.pedidos[:2], [f"{utils.API_URL}/posts/950/links",
                                              f"{utils.API_URL}/posts/300/links"])
        sin_pedir = sorted(r["post_id"] for r in resultado if "download_links" not in r)
        self.assertEqual(sin_pedir, [10, 42])

    def test_una_carpeta_de_la_cola_que_no_esta_se_avisa_y_las_demas_cuentan(self):
        editor = self._poner_cola(REGISTRO_FALSO)
        (self.album / "Banda - Disco (2020)").mkdir()
        shutil.rmtree(self.renderizando)  # the SSD is not mounted
        sesion = _SesionLinks(con_creditos=10)

        with mock.patch.dict(os.environ, {"CLICK_AUTO_EDITOR_DIR": str(editor)}):
            self._correr([_release(1, "Banda", "Disco"), _release(2, "Otra", "Cosa")], sesion)

        self.assertEqual(sesion.pedidos, [f"{utils.API_URL}/posts/2/links"])
        self.assertIn(f"⚠️ No pude leer {self.renderizando}", self.salida.getvalue())

    def _correr_con_lista_negra(self, lista, repertorio, codigo=REGISTRO_CON_CLAVE, verbose=False):
        """Runs the step with a click-auto-editor whose band blacklist holds `lista`.

        Returns what the fake site was asked and the releases that were saved.
        """
        editor = self._poner_registro(codigo)
        if lista is not None:
            (editor / "lista_negra_bandas.txt").write_text(lista, encoding="utf-8")
        sesion = _SesionLinks(con_creditos=100)
        with mock.patch.dict(os.environ, {"CLICK_AUTO_EDITOR_DIR": str(editor)}):
            resultado = self._correr(repertorio, sesion, verbose=verbose)
        return editor, sesion, resultado

    def test_no_pide_links_de_una_banda_de_la_lista_negra(self):
        # "# Otra Banda" is a commented-out line: that band stays allowed
        repertorio = [_release(7, "Prophecy", "Cold Winds"), _release(8, "Otra Banda", "Disco")]

        _, sesion, resultado = self._correr_con_lista_negra(
            "# Otra Banda\n\nProphecy\n", repertorio, verbose=True)

        self.assertEqual(sesion.pedidos, [f"{utils.API_URL}/posts/8/links"])
        self.assertEqual([r["post_id"] for r in resultado], [8])
        self.assertIn("1 releases de bandas en la lista negra", self.salida.getvalue())
        self.assertIn("Prophecy - Cold Winds", self.salida.getvalue())

    def test_la_lista_negra_ignora_mayusculas_tildes_y_espacios(self):
        repertorio = [_release(1, "PROPHECY", "Uno"), _release(2, "Próphecy", "Dos"),
                      _release(3, "  dark   FUNERAL ", "Tres"), _release(4, "Otra Banda", "Cuatro")]

        _, sesion, _ = self._correr_con_lista_negra("Prophecy\nDark Funeral\n", repertorio)

        self.assertEqual(sesion.pedidos, [f"{utils.API_URL}/posts/4/links"])

    def test_la_lista_negra_con_el_registro_real_ignora_mayusculas_y_tildes(self):
        origen = Path(os.environ.get("CLICK_AUTO_EDITOR_REAL", utils.DIR_CLICK_AUTO_EDITOR)).expanduser()
        codigo = origen / "registro_publicados.py"
        if not codigo.is_file():
            self.skipTest(f"no está {codigo}")
        repertorio = [_release(1, "PROPHECY", "Uno"), _release(2, "Próphecy", "Dos"),
                      _release(3, "Otra Banda", "Tres")]

        _, sesion, _ = self._correr_con_lista_negra(
            "Prophecy\n", repertorio, codigo=codigo.read_text(encoding="utf-8"))

        self.assertEqual(sesion.pedidos, [f"{utils.API_URL}/posts/3/links"])

    def test_una_banda_que_no_esta_en_la_lista_negra_se_sigue_pidiendo(self):
        # Names that only contain or start like a blocked one are other bands
        repertorio = [_release(1, "Prophecy of Doom", "Uno"), _release(2, "Proph", "Dos"),
                      _release(3, "Otra Banda", "Tres")]

        _, sesion, resultado = self._correr_con_lista_negra("Prophecy\n", repertorio)

        self.assertEqual(len(sesion.pedidos), 3)
        self.assertEqual(sorted(r["post_id"] for r in resultado), [1, 2, 3])

    def test_un_nombre_sin_letras_en_la_lista_negra_no_bloquea_a_otros_sin_letras(self):
        # Both names have an empty key: they must not match each other
        repertorio = [_release(1, "???", "Uno"), _release(2, "Otra Banda", "Dos")]

        _, sesion, _ = self._correr_con_lista_negra("†††\n", repertorio)

        self.assertEqual(len(sesion.pedidos), 2)

    def test_la_lista_negra_muestra_diez_nombres_y_cuenta_el_resto(self):
        bandas = [f"Banda{letra}" for letra in "ABCDEFGHIJKL"]
        repertorio = [_release(i, banda, "Disco") for i, banda in enumerate(bandas, start=1)]

        _, sesion, _ = self._correr_con_lista_negra("\n".join(bandas), repertorio, verbose=True)

        self.assertEqual(sesion.pedidos, [])
        salida = self.salida.getvalue()
        self.assertIn("12 releases de bandas en la lista negra", salida)
        self.assertEqual(salida.count("   • Banda"), 10)
        self.assertIn("… y 2 más", salida)

    def test_sin_archivo_de_lista_negra_no_se_bloquea_nada(self):
        repertorio = [_release(1, "Prophecy", "Uno"), _release(2, "Otra Banda", "Dos")]

        _, sesion, _ = self._correr_con_lista_negra(None, repertorio, verbose=True)

        self.assertEqual(len(sesion.pedidos), 2)
        self.assertNotIn("lista_negra_bandas", self.salida.getvalue())

    def test_sin_el_codigo_de_click_auto_editor_avisa_y_no_bloquea_nada(self):
        # setUp points CLICK_AUTO_EDITOR_DIR at a folder that does not exist
        sesion = _SesionLinks(con_creditos=100)

        self._correr([_release(1, "Prophecy", "Uno"), _release(2, "Otra Banda", "Dos")], sesion)

        self.assertEqual(len(sesion.pedidos), 2)
        self.assertIn("lista_negra_bandas.txt", self.salida.getvalue())

    def test_un_registro_sin_clave_frena_el_paso_sin_pedir_links(self):
        # leer works (so the published step goes on) but there is no clave to normalize with
        codigo = REGISTRO_FALSO.replace("def clave(", "def otra_cosa(")
        editor = self._poner_registro(codigo)
        (editor / "lista_negra_bandas.txt").write_text("Prophecy\n", encoding="utf-8")
        sesion = _SesionLinks(con_creditos=10)

        with mock.patch.dict(os.environ, {"CLICK_AUTO_EDITOR_DIR": str(editor)}), \
                self.assertRaises(SystemExit) as parada:
            self._correr([_release(1, "Prophecy", "Uno")], sesion)

        self.assertIsInstance(parada.exception.code, str)
        self.assertIn(str(editor / "registro_publicados.py"), parada.exception.code)
        self.assertIn("AttributeError", parada.exception.code)
        self.assertEqual(sesion.pedidos, [])

    def test_una_lista_negra_ilegible_frena_el_paso_sin_pedir_links(self):
        editor = self._poner_registro(REGISTRO_CON_CLAVE)
        # Saved as latin-1 by mistake: "Próphecy" is not valid UTF-8
        (editor / "lista_negra_bandas.txt").write_bytes("Próphecy\n".encode("latin-1"))
        sesion = _SesionLinks(con_creditos=10)

        with mock.patch.dict(os.environ, {"CLICK_AUTO_EDITOR_DIR": str(editor)}), \
                self.assertRaises(SystemExit) as parada:
            self._correr([_release(1, "Prophecy", "Uno")], sesion)

        self.assertIsInstance(parada.exception.code, str)
        self.assertIn(str(editor / "lista_negra_bandas.txt"), parada.exception.code)
        self.assertIn("UnicodeDecodeError", parada.exception.code)
        self.assertEqual(sesion.pedidos, [])


if __name__ == "__main__":
    unittest.main()
