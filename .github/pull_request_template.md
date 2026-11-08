> **Escribir para quien revisa.** La descripción debe leerse en un minuto: qué cambia, por
> qué, y qué mirar con atención. Sin tablas, sin secciones decorativas, sin repetir lo que
> el diff ya muestra. Si no entra en pocas líneas, el PR es demasiado grande: dividirlo.
> El detalle técnico va en el issue o en el mensaje del commit.
>
> **Un diagrama cuando explique mejor que el texto.** Para flujos, orden de ejecución o
> relaciones entre componentes, un diagrama reemplaza párrafos: incluirlo en lugar de
> describirlos en prosa, no además de.

## 📝 Descripción
<!-- Resumen de los cambios realizados siguiendo el formato del commit template -->
<!-- Ejemplo: :bug: fix(login): read the csrf token from the sign-in page -->

**Contexto detallado:**
<!-- Qué cambia y por qué, en pocas líneas. Mencionar incidencias vinculadas (Closes #123) -->

---

## 🧪 Verificación Técnica
- [ ] **Tests locales**: `PYTHONDONTWRITEBYTECODE=1 env/bin/python -m unittest discover -s tests -t .` pasa.
- [ ] **Sin tocar el sitio en los tests**: los tests usan dobles; no hacen login ni piden links (los links dependen de los créditos de descarga).
- [ ] **Smoke de la API**: si cambia el login o un endpoint, `python scripts/api_smoke_test.py` hace login real y pide los links de un post, que puede gastar un crédito de descarga; correrlo una vez, porque varios logins seguidos bloquean la cuenta un rato.
- [ ] **Dependencias**: ¿Se modificó `requirements.txt`? (Si es sí, `pip install -r requirements.txt` en `env`).
- [ ] **Datos y bytecode**: se dicen los archivos versionados de `data/` o `__pycache__/` que cambian, o que no cambia ninguno.
- [ ] **Seguridad de Entorno**: sin credenciales (`.env`, `api_requests.json`) ni rutas de descarga en el diff, logs o capturas.

---

## 📸 Anexos (Opcional)
<!-- Salida de consola del pipeline o de los tests si aplica, sin credenciales -->
