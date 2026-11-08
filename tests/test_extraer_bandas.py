"""Genre crawl against fakes shaped like the current DeathGrind API: the site is never contacted."""

import unittest
from unittest import mock

from modules import extraer_bandas


class _Respuesta:
    def __init__(self, status_code, cuerpo):
        self.status_code = status_code
        self._cuerpo = cuerpo

    def json(self):
        return self._cuerpo


class _SesionPaginas:
    """Answers /posts/filter with the page of each cursor (None is the first page)."""

    def __init__(self, paginas):
        self.paginas = paginas
        self.params = []

    def get(self, url, params=None, **kwargs):
        self.params.append(dict(params or {}))
        pagina = self.paginas.get((params or {}).get("cursor"), {"posts": [], "hasMore": False})
        return _Respuesta(200, pagina)


def _post(post_id, tipos, sello="Independent"):
    return {
        "postId": post_id,
        "album": f"Album {post_id}",
        "bands": [{"name": f"Band {post_id}", "bandId": post_id}],
        "releaseTypes": tipos,
        "releaseDate": [2026, 11, 6],
        "labels": [{"name": sello, "labelId": 1, "lookupKeys": [sello.lower()]}],
    }


class ExtraerPostsGenero(unittest.TestCase):
    def _extraer(self, paginas, sellos_blacklist=frozenset()):
        sesion = _SesionPaginas(paginas)
        with mock.patch.object(extraer_bandas, "_get_thread_session", return_value=sesion), \
                mock.patch.object(extraer_bandas, "delay_con_jitter", lambda *a, **k: None):
            resultado = extraer_bandas.extraer_posts_genero(
                {}, 1, "Death Metal", set(sellos_blacklist), [1, 2, 9], verbose=False
            )
        return sesion, resultado

    def test_sigue_las_paginas_por_cursor_y_filtra_por_release_types(self):
        sesion, resultado = self._extraer({
            None: {"posts": [_post(10, [1]), _post(11, [7])], "hasMore": True, "nextCursor": "c1"},
            "c1": {"posts": [_post(12, [2])], "hasMore": False},
        })
        releases, _, posts_total, _, _, _, filtrados_tipo = resultado

        self.assertEqual([r["post_id"] for r in releases], [10, 12])
        self.assertEqual([r["type"] for r in releases], ["Album", "EP"])
        self.assertEqual((posts_total, filtrados_tipo), (3, 1))
        self.assertEqual(sesion.params[1], {"genres": 1, "cursor": "c1"})

    def test_salta_los_sellos_de_la_blacklist_por_su_nombre(self):
        _, resultado = self._extraer(
            {None: {"posts": [_post(20, [1], "Bad Records"), _post(21, [1])], "hasMore": False}},
            sellos_blacklist={"bad records"},
        )
        releases, _, _, filtrados_sello, _, _, _ = resultado

        self.assertEqual([r["post_id"] for r in releases], [21])
        self.assertEqual(filtrados_sello, 1)


if __name__ == "__main__":
    unittest.main()
