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
