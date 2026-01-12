#!/usr/bin/env python3
"""
Smoke test for DeathGrind.club API endpoints.

- Logs in using .env
- Calls /posts/filter with the first genre in generos_activos.txt
- Calls /bands/{id}/discography and /posts/{id}/links using the first post

Prints only status codes and counts (no sensitive data).
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

from modules.extraer_bandas import (  # noqa: E402
    API_URL,
    cargar_env,
    cargar_generos,
    crear_sesion_autenticada,
)


def main() -> int:
    try:
        cargar_env()
        session = crear_sesion_autenticada()
    except Exception as exc:
        print(f"Login failed: {exc}")
        return 1

    generos = cargar_generos()
    if not generos:
        print("No generos found in generos_activos.txt")
        return 1

    genre_id, genre_name = generos[0]
    try:
        resp = session.get(
            f"{API_URL}/posts/filter",
            params={"genres": genre_id},
            timeout=30,
        )
    except Exception as exc:
        print(f"/posts/filter request failed: {exc}")
        return 1

    print(f"/posts/filter?genres={genre_id} ({genre_name}) status: {resp.status_code}")
    if resp.status_code != 200:
        return 1

    data = resp.json()
    posts = data.get("posts") or []
    print(f"posts: {len(posts)} | hasMore: {data.get('hasMore')}")
    if not posts:
        return 1

    first_post = posts[0]
    post_id = first_post.get("postId")
    band_id = None

    bands = first_post.get("bands") or []
    if bands and isinstance(bands[0], dict):
        band_id = bands[0].get("bandId")

    if band_id:
        try:
            resp = session.get(f"{API_URL}/bands/{band_id}/discography", timeout=30)
            print(f"/bands/{band_id}/discography status: {resp.status_code}")
            if resp.status_code == 200:
                discography = resp.json()
                disc_posts = discography.get("posts") or []
                print(f"discography posts: {len(disc_posts)}")
        except Exception as exc:
            print(f"/bands/{band_id}/discography request failed: {exc}")
    else:
        print("No band_id found in first post")

    if post_id:
        try:
            resp = session.get(f"{API_URL}/posts/{post_id}/links", timeout=30)
            print(f"/posts/{post_id}/links status: {resp.status_code}")
            if resp.status_code == 200:
                links = resp.json().get("links") or []
                print(f"links: {len(links)}")
        except Exception as exc:
            print(f"/posts/{post_id}/links request failed: {exc}")
    else:
        print("No post_id found in first post")

    return 0


if __name__ == "__main__":
    sys.exit(main())
