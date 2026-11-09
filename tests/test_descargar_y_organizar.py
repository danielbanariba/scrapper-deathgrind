"""Download step against fake hosts: nothing is downloaded and data/ is not touched."""

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import requests

from modules import descargar_y_organizar as descarga

PAGINA_YANDEX = "https://disk.yandex.ru/d/disco123"
API_WEB_YANDEX = "https://disk.yandex.ru/public/api/download-url"
DESCARGA_YANDEX = "https://downloader.disk.yandex.ru/disk/disco123"


class _Respuesta:
    def __init__(self, status_code, url="", text="", cuerpo=None, contenido=b"", headers=None):
        self.status_code = status_code
        self.url = url
        self.text = text
        self.cuerpo = cuerpo
        self.contenido = contenido
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(str(self.status_code), response=self)

    def json(self):
        return self.cuerpo

    def iter_content(self, chunk_size):
        yield self.contenido


class _Sesion:
    """Answers the URLs in `rutas`; every other URL gets `status_code`."""

    def __init__(self, status_code, rutas=None):
        self.status_code = status_code
        self.rutas = rutas or {}
        self.posts = []

    def get(self, url, **kwargs):
        return self.rutas.get(url) or _Respuesta(self.status_code, url)

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.rutas.get(url) or _Respuesta(self.status_code, url)


def _zip_con_un_tema():
    contenido = io.BytesIO()
    with zipfile.ZipFile(contenido, "w") as archivo:
        archivo.writestr("Banda - Disco/01 - Tema.mp3", b"\xff\xfb" + b"\x00" * 4000)
    return contenido.getvalue()


def _pagina_yandex(recurso):
    datos = {"rootResourceId": "raiz", "environment": {"sk": "clave-sk"}, "resources": {"raiz": recurso}}
    return (f'<html><script type="application/json" id="store-prefetch">{json.dumps(datos)}'
            '</script></html>')


def _descargar(sesion, url):
    """Runs the download step on one release whose only link is `url`.

    Returns the release's line in the failed list (None if there is none), whether it
    was saved as downloaded, and the files left in the destination.
    """
    release = {"post_id": "123", "band": "Banda", "album": "Disco", "download_links": [{"url": url}]}
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
                mock.patch.object(descarga, "guardar_descargado") as guardar_descargado, \
                mock.patch.object(descarga, "guardar_fallido", side_effect=guardar_en_tmp), \
                mock.patch.object(descarga, "TEMP_DIR", str(Path(tmp) / "temp")), \
                mock.patch.object(descarga, "_get_session", return_value=sesion), \
                mock.patch.object(descarga.time, "sleep"):
            descarga.run(destino_base=str(destino), verbose=False)
        lineas = fallidos_file.read_text(encoding="utf-8").splitlines() if fallidos_file.exists() else []
        return SimpleNamespace(
            fallido=next((linea for linea in lineas if linea.startswith("123|Banda|Disco|")), None),
            descargado=guardar_descargado.call_args_list == [mock.call("123", "Banda", "Disco")],
            archivos=sorted(str(p.relative_to(destino)) for p in destino.rglob("*") if p.is_file()),
        )


class FallosDeDescargaTest(unittest.TestCase):
    def test_un_429_o_un_5xx_no_marca_el_release_como_definitivo(self):
        for status_code in (429, 502, 504):
            with self.subTest(status_code=status_code):
                fallido = _descargar(_Sesion(status_code), "https://files.example.org/disco.zip").fallido
                self.assertNotIn("[PERM]", fallido)

    def test_un_404_sigue_marcando_el_release_como_definitivo(self):
        self.assertIn("[PERM]", _descargar(_Sesion(404), "https://files.example.org/disco.zip").fallido)


class YandexDiskTest(unittest.TestCase):
    """The public API of Yandex Disk answers 429 to everything; the public page still works."""

    def test_un_link_de_yandex_se_baja_por_su_pagina_publica(self):
        archivo = {"type": "file", "hash": "hash-del-disco", "name": "Disco.zip"}
        sesion = _Sesion(429, rutas={
            "https://yadi.sk/d/disco123": _Respuesta(200, url=PAGINA_YANDEX, text=_pagina_yandex(archivo)),
            API_WEB_YANDEX: _Respuesta(200, cuerpo={"data": {"url": DESCARGA_YANDEX}}),
            DESCARGA_YANDEX: _Respuesta(
                200, url=DESCARGA_YANDEX, contenido=_zip_con_un_tema(),
                headers={"content-disposition": 'attachment; filename="Disco.zip"'}),
        })

        resultado = _descargar(sesion, "https://yadi.sk/d/disco123")

        self.assertTrue(resultado.descargado)
        self.assertIsNone(resultado.fallido)
        self.assertEqual(len(resultado.archivos), 1)
        self.assertTrue(resultado.archivos[0].endswith("01 - Tema.mp3"))
        self.assertEqual(json.loads(sesion.posts[0][1]["data"]), {"hash": "hash-del-disco", "sk": "clave-sk"})

    def test_un_link_de_yandex_borrado_queda_como_definitivo(self):
        sesion = _Sesion(429, rutas={"https://yadi.sk/d/disco123": _Respuesta(404, url=PAGINA_YANDEX)})

        self.assertIn("[PERM]", _descargar(sesion, "https://yadi.sk/d/disco123").fallido)


if __name__ == "__main__":
    unittest.main()
