"""likes_a_mano without a browser: Brave, the site and the registry are all fakes."""

import contextlib
import importlib.util
import io
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import requests

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("likes_a_mano", RAIZ / "scripts" / "likes_a_mano.py")
likes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(likes)


class _Respuesta:
    def __init__(self, status_code, cuerpo=None):
        self.status_code = status_code
        self.cuerpo = cuerpo

    def json(self):
        if self.cuerpo is ValueError:
            raise ValueError("no es JSON")
        return self.cuerpo


class _Sesion:
    """Answers every GET with `respuesta`, or raises it when it is an exception."""

    def __init__(self, respuesta):
        self.respuesta = respuesta

    def get(self, url, **kwargs):
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta


class EstadoDelPost(unittest.TestCase):
    def test_lee_el_status_y_el_like_de_la_cuenta_en_la_api_del_post(self):
        con_like = {"post": {"myReactions": [{"emoji": "👍"}]}}
        casos = (
            ("un post borrado responde 200 pero cuenta como 404, aunque traiga el like",
             _Respuesta(200, {"isDeleted": True, **con_like}), (404, False)),
            ("un 429 no se confunde con un post sin respuesta", _Respuesta(429), (429, False)),
            ("un 404 se devuelve tal cual", _Respuesta(404), (404, False)),
            ("un JSON roto no es un post", _Respuesta(200, ValueError), (0, False)),
            ("sin la API no hay respuesta", requests.ConnectionError("sin red"), (0, False)),
            ("el 👍 en myReactions", _Respuesta(200, con_like), (200, True)),
            ("otra reacción no es el like", _Respuesta(200, {"post": {"myReactions": ["❤️"]}}), (200, False)),
            ("sin reacciones", _Respuesta(200, {"post": {"myReactions": None}}), (200, False)),
        )
        for nombre, respuesta, esperado in casos:
            with self.subTest(nombre):
                self.assertEqual(likes.estado_del_post(_Sesion(respuesta), "77"), esperado)


class _Registro:
    def __init__(self, nombres):
        self.nombres = nombres

    def buscar(self, nombre):
        return nombre in self.nombres


class PostsPublicados(unittest.TestCase):
    def test_solo_los_del_canal_sin_repetidos_ni_lineas_rotas_y_con_el_album_entero(self):
        descargados = "\n".join([
            "# Releases descargados exitosamente",
            "# Formato: post_id|band|album",
            "",
            "10|Banda Uno|Disco Uno",
            "11|Banda Dos|Disco Que No Esta En El Canal",
            "10|Banda Uno|Disco Uno",
            "abc|Banda Tres|Disco Tres",
            "12|Banda Sin Album",
            "13|Banda Pipe|Parte A|Parte B",
        ])
        registro = _Registro({"Banda Uno - Disco Uno", "Banda Tres - Disco Tres", "Banda Pipe - Parte A|Parte B"})
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp) / likes.DESCARGADOS_FILE
            archivo.parent.mkdir(parents=True)
            archivo.write_text(descargados, encoding="utf-8")
            with mock.patch.object(likes, "RAIZ", Path(tmp)), \
                    mock.patch.object(likes, "cargar_publicados", return_value=registro):
                posts = likes.posts_publicados()

        self.assertEqual(posts, [("10", "Banda Uno", "Disco Uno"), ("13", "Banda Pipe", "Parte A|Parte B")])

    def test_suma_los_posts_del_catalogo_que_estan_en_el_canal_sin_repetir_los_descargados(self):
        registro = _Registro({"Banda Uno - Disco Uno", "Banda Vieja - Disco Viejo"})
        with tempfile.TemporaryDirectory() as tmp:
            for nombre, texto in ((likes.DESCARGADOS_FILE, "10|Banda Uno|Disco Uno\n"),
                                  (likes.CATALOGO_FILE, "10|Banda Uno|Disco Uno\n20|Banda Vieja|Disco Viejo\n"
                                                        "21|Banda Ajena|Disco Ajeno\n")):
                archivo = Path(tmp) / nombre
                archivo.parent.mkdir(parents=True, exist_ok=True)
                archivo.write_text(texto, encoding="utf-8")
            with mock.patch.object(likes, "RAIZ", Path(tmp)), \
                    mock.patch.object(likes, "cargar_publicados", return_value=registro):
                posts = likes.posts_publicados()

        self.assertEqual(posts, [("10", "Banda Uno", "Disco Uno"), ("20", "Banda Vieja", "Disco Viejo")])


class Catalogo(unittest.TestCase):
    def test_guarda_todos_los_posts_de_los_generos_sin_filtrar_y_posts_publicados_los_lee(self):
        releases = [{"post_id": 20, "band": "Banda Vieja", "album": "Disco Viejo"},
                    {"post_id": 30, "band": "Uno / Otro", "album": "Split|Raro"}]
        extraer_todo = mock.Mock(return_value=(releases, [], 2, 0, 0, 0, 0))
        registro = _Registro({"Banda Vieja - Disco Viejo", "Uno / Otro - Split|Raro"})
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(likes, "RAIZ", Path(tmp)), \
                mock.patch.object(likes, "cargar_generos", return_value=[(2, "Grind")]), \
                mock.patch.object(likes, "extraer_todo", extraer_todo), \
                mock.patch.object(likes, "cargar_publicados", return_value=registro), \
                contextlib.redirect_stdout(io.StringIO()):
            (Path(tmp) / likes.DESCARGADOS_FILE).parent.mkdir(parents=True)
            (Path(tmp) / likes.DESCARGADOS_FILE).write_text("", encoding="utf-8")
            likes.guardar_catalogo(sesion=object())
            posts = likes.posts_publicados()

        sesion, generos, sellos, tipos = extraer_todo.call_args.args[:4]
        self.assertEqual((generos, sellos, tipos), ([(2, "Grind")], set(), None))
        self.assertEqual(posts, [("20", "Banda Vieja", "Disco Viejo"), ("30", "Uno / Otro", "Split|Raro")])


class _ProcesoBrave:
    def __init__(self):
        self.terminado = False

    def poll(self):
        return None  # sigue abierto

    def terminate(self):
        self.terminado = True


class CierreDeBrave(unittest.TestCase):
    def _main(self, brave, **parches):
        """Runs main() with the site and Brave faked; what it prints stays in self.salida."""
        self.salida = io.StringIO()
        base = {
            "hay_catalogo": mock.Mock(return_value=True),
            "guardar_catalogo": mock.Mock(),
            "posts_publicados": mock.Mock(return_value=[("1", "Banda", "Disco")]),
            "likes_anotados": mock.Mock(return_value=set()),
            "cargar_env": mock.Mock(),
            "crear_sesion_autenticada": mock.Mock(return_value=object()),
            "usuario_de_la_sesion": mock.Mock(return_value="7"),
            "creditos": mock.Mock(return_value=5),
            "abrir_brave": mock.Mock(return_value=brave),
            "estado_del_post": mock.Mock(return_value=(200, False)),
        }
        with contextlib.ExitStack() as pila:
            for nombre, valor in {**base, **parches}.items():
                pila.enter_context(mock.patch.object(likes, nombre, valor))
            pila.enter_context(contextlib.redirect_stdout(self.salida))
            likes.main()

    def test_un_ctrl_c_en_el_bucle_tambien_cierra_brave(self):
        brave = _ProcesoBrave()

        with self.assertRaises(KeyboardInterrupt):
            self._main(brave, estado_del_post=mock.Mock(side_effect=KeyboardInterrupt))

        self.assertTrue(brave.terminado)

    def test_si_se_cierra_la_ventana_termina_con_el_resumen_y_cierra_brave(self):
        brave = _ProcesoBrave()

        self._main(brave, abrir_pestana=mock.Mock(side_effect=likes.BraveCerrado))

        self.assertTrue(brave.terminado)
        self.assertIn("La ventana de Brave se cerró.", self.salida.getvalue())
        self.assertIn("Likes nuevos: 0; ya estaban: 0.", self.salida.getvalue())


class CatalogoEnMain(unittest.TestCase):
    def test_arma_el_catalogo_si_falta_o_si_se_pide_y_si_no_hay_nada_que_hacer_no_inicia_sesion(self):
        casos = (
            ("sin catálogo se arma antes de la lista", False, [], 1, 1),
            ("con catálogo no se vuelve a recorrer DeathGrind", True, [], 0, 0),
            ("--actualizar-catalogo lo vuelve a armar", True, ["--actualizar-catalogo"], 1, 1),
        )
        for nombre, hay, argv, armados, sesiones in casos:
            with self.subTest(nombre), contextlib.ExitStack() as pila:
                guardar = mock.Mock()
                login = mock.Mock(return_value=object())
                parches = {
                    "hay_catalogo": mock.Mock(return_value=hay),
                    "guardar_catalogo": guardar,
                    "posts_publicados": mock.Mock(return_value=[]),
                    "cargar_env": mock.Mock(),
                    "crear_sesion_autenticada": login,
                }
                for atributo, valor in parches.items():
                    pila.enter_context(mock.patch.object(likes, atributo, valor))
                pila.enter_context(contextlib.redirect_stdout(io.StringIO()))
                likes.main(argv)

                self.assertEqual(guardar.call_count, armados)
                self.assertEqual(login.call_count, sesiones)


class _Abierta:
    """What urlopen returns: a context manager with the body."""

    def __init__(self, texto):
        self.texto = texto

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.texto.encode("utf-8")


class Depuracion(unittest.TestCase):
    def test_un_timeout_aislado_no_se_toma_por_un_brave_cerrado(self):
        urlopen = mock.Mock(side_effect=[TimeoutError("timed out"), _Abierta("[]")])

        with mock.patch.object(likes.urllib.request, "urlopen", urlopen), \
                mock.patch.object(likes.time, "sleep"):
            respuesta = likes.depuracion("list")

        self.assertEqual(respuesta, "[]")
        self.assertEqual(urlopen.call_count, 2)

    def test_dos_fallos_seguidos_si_son_un_brave_cerrado(self):
        urlopen = mock.Mock(side_effect=[urllib.error.URLError("rechazado"), urllib.error.URLError("rechazado")])

        with mock.patch.object(likes.urllib.request, "urlopen", urlopen), \
                mock.patch.object(likes.time, "sleep"), \
                self.assertRaises(likes.BraveCerrado):
            likes.depuracion("list")

        self.assertEqual(urlopen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
