"""Login against fakes: the site is never contacted."""

import os
import unittest
from unittest import mock

import requests

from modules import utils


class _Respuesta:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class _SesionFalsa(requests.Session):
    """Answers the sign-in page and the login like DeathGrind does since the 419.

    The login only accepts the token printed in the page, not the cookie one.
    """

    def __init__(self, html, token_valido):
        super().__init__()
        self.html = html
        self.token_valido = token_valido
        self.tokens_enviados = []

    def get(self, url, **kwargs):
        self.cookies.set("csrfToken", "token-de-la-cookie")
        return _Respuesta(200, self.html)

    def post(self, url, json=None, headers=None, **kwargs):
        self.tokens_enviados.append(headers.get("x-csrf-token"))
        if headers.get("x-csrf-token") != self.token_valido:
            return _Respuesta(419)
        self.cookies.set("csrfToken", "token-de-la-sesion")
        return _Respuesta(202)


class CrearSesionAutenticada(unittest.TestCase):
    def setUp(self):
        credenciales = {"DEATHGRIND_EMAIL": "alguien@example.com", "DEATHGRIND_PASSWORD": "x"}
        parche = mock.patch.dict(os.environ, credenciales)
        parche.start()
        self.addCleanup(parche.stop)

    def _login(self, sesion):
        with mock.patch.object(utils.requests, "Session", return_value=sesion):
            return utils.crear_sesion_autenticada(max_retries=1)

    def test_envia_el_token_de_la_pagina_y_no_el_de_la_cookie(self):
        html = '<script>window.__USER_DATA__ = {userId: 0, "csrfToken": "token-del-html"};</script>'
        sesion = _SesionFalsa(html, token_valido="token-del-html")

        resultado = self._login(sesion)

        self.assertIs(resultado, sesion)
        self.assertEqual(sesion.tokens_enviados, ["token-del-html"])
        self.assertEqual(sesion.headers["x-csrf-token"], "token-de-la-sesion")

    def test_sin_token_en_la_pagina_usa_el_de_la_cookie(self):
        sesion = _SesionFalsa("<html>sin datos</html>", token_valido="token-de-la-cookie")

        self._login(sesion)

        self.assertEqual(sesion.tokens_enviados, ["token-de-la-cookie"])


if __name__ == "__main__":
    unittest.main()
