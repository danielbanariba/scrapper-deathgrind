"""Download step against fake hosts: nothing is downloaded and data/ is not touched."""

import contextlib
import io
import json
import os
import shutil
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

        with mock.patch.dict(os.environ, {"CLICK_AUTO_EDITOR_DIR": str(Path(tmp) / "sin-editor")}), \
                contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(descarga, "cargar_repertorio", return_value=[release]), \
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

    def test_un_404_despues_de_un_429_en_el_mismo_thread_sigue_siendo_definitivo(self):
        # run() reparte los releases entre threads que reutilizan su estado: el 429 del primero
        # no debe teñir al segundo
        sesion = _Sesion(404, rutas={"https://files.example.org/uno.zip": _Respuesta(429)})
        primero = {"post_id": "1", "band": "Banda", "album": "Uno",
                   "download_links": [{"url": "https://files.example.org/uno.zip"}]}
        segundo = {"post_id": "2", "band": "Banda", "album": "Dos",
                   "download_links": [{"url": "https://files.example.org/dos.zip"}]}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(descarga, "_get_session", return_value=sesion), \
                mock.patch.object(descarga.time, "sleep"):
            destino, temporal = Path(tmp) / "destino", Path(tmp) / "temp"
            destino.mkdir()
            temporal.mkdir()
            resultados = [
                descarga.procesar_release(release, destino_base=str(destino),
                                          temp_dir=str(temporal), verbose=False)
                for release in (primero, segundo)
            ]

        self.assertEqual(resultados[0][1], "Error temporal del servidor")
        self.assertEqual(resultados[1][1], "Todos los links fallaron (definitivo)")


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

    def test_un_429_o_un_5xx_al_pedir_el_link_de_yandex_no_marca_el_release_como_definitivo(self):
        archivo = {"type": "file", "hash": "hash-del-disco", "name": "Disco.zip"}
        for status_code in (429, 502):
            with self.subTest(status_code=status_code):
                sesion = _Sesion(429, rutas={
                    "https://yadi.sk/d/disco123": _Respuesta(200, url=PAGINA_YANDEX, text=_pagina_yandex(archivo)),
                    API_WEB_YANDEX: _Respuesta(status_code),
                })

                fallido = _descargar(sesion, "https://yadi.sk/d/disco123").fallido

                self.assertIsNotNone(fallido)
                self.assertNotIn("[PERM]", fallido)

    def test_un_link_de_yandex_borrado_queda_como_definitivo(self):
        sesion = _Sesion(429, rutas={"https://yadi.sk/d/disco123": _Respuesta(404, url=PAGINA_YANDEX)})

        self.assertIn("[PERM]", _descargar(sesion, "https://yadi.sk/d/disco123").fallido)


# The part of click-auto-editor's registro_publicados.py that the band blacklist uses:
# "banda|album" with no case, accents or signs
REGISTRO_CON_CLAVE = """
import unicodedata


def _compacto(texto):
    texto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in texto if c.isalnum())


def clave(nombre):
    if " - " not in nombre:
        return None
    banda, album = (_compacto(parte) for parte in nombre.split(" - ", 1))
    return f"{banda}|{album}" if banda and album else None
"""
ZIP = "https://files.example.org/disco.zip"
MEGA = "https://mega.nz/file/abc#clave"


def _release_con_links(post_id, banda, url):
    return {"post_id": post_id, "band": banda, "album": "Disco", "download_links": [{"url": url}]}


class BandasBloqueadasTest(unittest.TestCase):
    """Releases that already carry links (an old repertorio_con_links.json, the Mega queue)
    reach the download without asking the site for links, so the band blacklist has to
    stop them here too."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.enterContext(contextlib.chdir(self.tmp))  # the queue lives in data/ under the cwd
        self.editor = self.tmp / "editor"
        self.editor.mkdir()
        (self.editor / "registro_publicados.py").write_text(REGISTRO_CON_CLAVE, encoding="utf-8")
        (self.editor / "lista_negra_bandas.txt").write_text("Prophecy\n", encoding="utf-8")
        self.enterContext(mock.patch.dict(os.environ, {"CLICK_AUTO_EDITOR_DIR": str(self.editor)}))
        self.destino = self.tmp / "destino"
        self.destino.mkdir()
        self.intentados = []
        self.salida = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.salida))
        self.enterContext(mock.patch.object(descarga, "cargar_descargados", return_value=set()))
        self.enterContext(mock.patch.object(descarga, "cargar_fallidos", return_value=set()))
        self.enterContext(mock.patch.object(descarga, "_mega_cooldown_activo", return_value=False))
        self.enterContext(mock.patch.object(descarga, "TEMP_DIR", str(self.tmp / "temp")))
        self.enterContext(mock.patch.object(descarga, "procesar_release", side_effect=self._procesar))
        self.enterContext(mock.patch.object(descarga, "delay_con_jitter"))
        self.enterContext(mock.patch.object(descarga.time, "sleep"))

    def _procesar(self, release, *args, **kwargs):
        self.intentados.append(release["post_id"])
        return True, "Ya existe", None

    def _poner_cola_mega(self, releases):
        (self.tmp / "data").mkdir(exist_ok=True)
        (self.tmp / "data" / "mega_pendientes.json").write_text(json.dumps(releases), encoding="utf-8")

    def test_no_baja_releases_de_bandas_bloqueadas_que_ya_traen_links(self):
        # A repertorio_con_links.json written before the band went on the list
        repertorio = [_release_con_links("1", "PROPHECY", ZIP), _release_con_links("2", "Otra Banda", ZIP),
                      _release_con_links("3", "Próphecy", MEGA), _release_con_links("4", "Otra Mas", MEGA)]

        with mock.patch.object(descarga, "cargar_repertorio", return_value=repertorio):
            descarga.run(destino_base=str(self.destino), verbose=True)

        self.assertEqual(sorted(self.intentados), ["2", "4"])
        self.assertIn("2 releases de bandas en la lista negra", self.salida.getvalue())

    def test_no_baja_las_bandas_bloqueadas_de_la_cola_de_mega(self):
        self._poner_cola_mega([_release_con_links("5", "Prophecy", MEGA), _release_con_links("6", "Otra Banda", MEGA)])

        with mock.patch.object(descarga, "cargar_repertorio", return_value=[]):
            descarga.run(destino_base=str(self.destino), verbose=False)

        self.assertEqual(self.intentados, ["6"])

    def test_el_daemon_de_mega_no_baja_bandas_bloqueadas(self):
        import procesar_mega_pendientes as daemon

        self._poner_cola_mega([_release_con_links("5", "Prophecy", MEGA), _release_con_links("6", "Otra Banda", MEGA)])
        self.enterContext(mock.patch.object(daemon, "verificar_dependencias", return_value=True))
        self.enterContext(mock.patch.object(daemon, "DESTINO_BASE", str(self.destino)))
        self.enterContext(mock.patch.object(daemon, "TEMP_DIR", str(self.tmp / "temp")))
        self.enterContext(mock.patch.object(daemon, "_attach_file_handler"))
        self.enterContext(mock.patch.object(daemon, "_mega_cooldown_activo", return_value=False))
        self.enterContext(mock.patch.object(daemon, "cargar_descargados", return_value=set()))
        self.enterContext(mock.patch.object(daemon, "cargar_fallidos", return_value=set()))
        self.enterContext(mock.patch.object(daemon, "procesar_release", side_effect=self._procesar))
        self.enterContext(mock.patch.object(daemon.signal, "signal"))

        self.assertEqual(daemon.main(), 0)

        self.assertEqual(self.intentados, ["6"])


if __name__ == "__main__":
    unittest.main()
