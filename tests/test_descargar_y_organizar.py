"""Download failures against a fake server: nothing is downloaded and data/ is not touched."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from modules import descargar_y_organizar as descarga


class _Respuesta:
    """The answer of a host that fails with an HTTP status."""

    def __init__(self, status_code):
        self.status_code = status_code
        self.headers = {}

    def raise_for_status(self):
        raise requests.exceptions.HTTPError(str(self.status_code), response=self)


class _Sesion:
    def __init__(self, status_code):
        self.status_code = status_code

    def get(self, url, **kwargs):
        return _Respuesta(self.status_code)


def _fallidos_tras_descargar(status_code):
    """Runs the download step on one release whose only link answers `status_code`.

    Returns the line the step wrote for that release in the failed list.
    """
    release = {
        "post_id": "123", "band": "Banda", "album": "Disco",
        "download_links": [{"url": "https://files.example.org/disco.zip"}],
    }
    guardar_fallido = descarga.guardar_fallido
    with tempfile.TemporaryDirectory() as tmp:
        fallidos_file = Path(tmp) / "fallidos.txt"
        destino = Path(tmp) / "destino"
        destino.mkdir()

        def guardar_en_tmp(release, fallidos, **kwargs):
            guardar_fallido(release, fallidos, fallidos_file=str(fallidos_file), **kwargs)

        with mock.patch.object(descarga, "cargar_repertorio", return_value=[release]), \
                mock.patch.object(descarga, "cargar_descargados", return_value=set()), \
                mock.patch.object(descarga, "cargar_fallidos", return_value=set()), \
                mock.patch.object(descarga, "cargar_mega_pendientes", return_value=[]), \
                mock.patch.object(descarga, "guardar_mega_pendientes"), \
                mock.patch.object(descarga, "guardar_descargado"), \
                mock.patch.object(descarga, "guardar_fallido", side_effect=guardar_en_tmp), \
                mock.patch.object(descarga, "TEMP_DIR", str(Path(tmp) / "temp")), \
                mock.patch.object(descarga, "_get_session", return_value=_Sesion(status_code)), \
                mock.patch.object(descarga.time, "sleep"):
            descarga.run(destino_base=str(destino), verbose=False)
        lineas = fallidos_file.read_text(encoding="utf-8").splitlines()
        return next(linea for linea in lineas if linea.startswith("123|Banda|Disco|"))


class FallosDeDescargaTest(unittest.TestCase):
    def test_un_429_o_un_5xx_no_marca_el_release_como_definitivo(self):
        for status_code in (429, 502, 504):
            with self.subTest(status_code=status_code):
                self.assertNotIn("[PERM]", _fallidos_tras_descargar(status_code))

    def test_un_404_sigue_marcando_el_release_como_definitivo(self):
        self.assertIn("[PERM]", _fallidos_tras_descargar(404))


if __name__ == "__main__":
    unittest.main()
