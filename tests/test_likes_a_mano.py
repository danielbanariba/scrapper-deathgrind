"""likes_a_mano without a browser: Brave, the site and the registry are all fakes."""

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("likes_a_mano", RAIZ / "scripts" / "likes_a_mano.py")
likes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(likes)


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


if __name__ == "__main__":
    unittest.main()
