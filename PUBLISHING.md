# Publicar el repositorio

El repositorio distribuye código, el catálogo genérico y pruebas sintéticas. Los originales y sus derivados permanecen locales.

## Archivos excluidos

- `docs/`: todos los documentos propios.
- `data/`: texto extraído, respuestas API, cachés, casos de evaluación y términos privados.
- `output/`: HTML con documentos embebidos, fichas, informes y copias de los originales.
- `exports/`: conversaciones y archivos de trabajo originales.
- `.env` y sus variantes: claves y configuración privada. Solo `.env.example`, sin credenciales, es público.
- Entornos virtuales, temporales, capturas, archivos ofimáticos, PDF, bases de datos y claves privadas.

`.gitignore` permite únicamente las rutas públicas previstas en la raíz. Las carpetas nuevas requieren añadirlas deliberadamente. No uses `git add -f` para incluir archivos locales.

## Preparar y comprobar

```bash
# Ejecutar también después de clonar: instala dependencias y activa los hooks.
make setup

git add .
python3 scripts/check_publish.py
git diff --cached --stat
```

El hook `pre-commit` inspecciona los blobs realmente preparados en el índice, incluso si un archivo ignorado se añade a la fuerza. El hook `pre-push` inspecciona todas las versiones de archivos alcanzables desde las referencias locales, no solo el último estado. Ambos rechazan rutas privadas, binarios, posibles credenciales y enlaces simbólicos.

Antes del commit también se comprueban Ruff y Prettier sobre una copia temporal del índice, usando la configuración preparada para ese commit. No se modifican los archivos ni el índice automáticamente. `make lint-fix` y `make format` corrigen el directorio de trabajo; después hay que preparar los cambios con `git add`. GitHub Actions comprueba formato, pruebas, privacidad y que `requirements.txt` siga correspondiendo al lockfile.

El control también compara las credenciales de los `.env` locales y, si existe, los términos de `data/publish-private-terms.txt`. Este archivo privado admite un nombre, identificador o término por línea; no se publica. Los mensajes del control indican la regla incumplida sin imprimir valores de credenciales.

Estas comprobaciones reducen errores accidentales; no identifican cualquier dato personal y pueden desactivarse mediante opciones de Git. Revisa el diff antes de publicar. Si una credencial ya se publicó, retirarla del último commit no basta: revócala y elimina la exposición del historial.

## Subir cuando hayas creado el repositorio en GitHub

```bash
git commit -m "Initial public source"
git remote add origin <URL_DEL_REPOSITORIO>
git push -u origin main
```

La preparación local no crea un repositorio remoto ni sube archivos. No adjuntes `output/index.html` a una release: contiene el texto de los documentos aunque sea un único HTML.

## Comprobar una copia limpia

```bash
.venv/bin/python -m pytest -q tests catalog/test_kit.py
```

Estas pruebas no requieren `.env`, PDF propios, resultados generados ni peticiones a JEV. Para usar la aplicación después de clonar, configura tu propia clave y crea `docs/` con documentos locales.
