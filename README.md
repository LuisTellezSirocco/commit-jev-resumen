# Atlas · Explorador documental con JEV

Implementación del catálogo de `catalog`: clasifica PDF con las **235 preguntas originales**, conserva las decisiones por unidad y genera un **HTML autónomo** con filtros y fichas documentales. Incluye un servidor local para consultas en lenguaje natural contra JEV.

El repositorio público no incluye documentos propios, claves, conversaciones ni resultados de clasificación. Consulta [PUBLISHING.md](PUBLISHING.md) para activar los controles de Git y revisar qué se publica.

## Abrir el resultado

```bash
.venv/bin/python -m jevdocs serve
```

Abre **http://127.0.0.1:8765**. También puedes ejecutar `./iniciar.sh`.

`output/index.html` funciona directamente en el navegador, sin servidor, para filtros, búsqueda textual, fichas y exportación. Los enlaces a PDF requieren conservar la carpeta `output/originals` junto al HTML. **Preguntar a JEV** requiere el servidor y `JEV_API_KEY` en `.env`.

## Instalación reproducible

Python 3.12 o posterior:

```bash
uv sync --locked
cp .env.example .env
# Añade tu JEV_API_KEY a .env sin comillas adicionales ni espacios.
```

Si ya tienes `.env`, consérvalo. No reemplaces la clave existente.

`pyproject.toml` define el proyecto y `uv.lock` fija las versiones de las dependencias. Ruff y pytest están en el grupo de desarrollo; para instalar solo las dependencias de ejecución utiliza `uv sync --locked --no-dev`. La aplicación se ejecuta desde el repositorio (`uv run --locked python -m jevdocs`); no se distribuye como wheel porque utiliza los recursos locales de `catalog/` y `web/`. `requirements.txt` es una exportación de compatibilidad generada, no se edita a mano.

## Desarrollo y formato

Con `uv`, Node.js 24 y npm disponibles:

```bash
make setup        # Dependencias bloqueadas y hooks locales
make lint         # Ruff: errores, imports, prácticas y compatibilidad Python
make lint-fix     # Correcciones automáticas seguras de Ruff
make format       # Ruff para Python; Prettier para HTML, CSS y JavaScript
make check        # Lint, comprobación de formato y pruebas sin llamar a JEV
make serve        # Servidor local
```

Ruff utiliza `pyproject.toml` y Prettier `.prettierrc.json`. `.editorconfig` y los ajustes de VS Code comparten esas reglas y usan las herramientas instaladas en el proyecto. Los hooks comprueban una copia temporal del **índice de Git**, sin reformatear archivos ni añadir cambios por su cuenta. Tras corregir el formato, prepara de nuevo los archivos con `git add`.

El workflow de GitHub Actions ejecuta los mismos controles y las comprobaciones de privacidad sin documentos propios ni clave API. Node y Prettier solo son herramientas de desarrollo; el explorador generado sigue sin depender de un servidor Node.

Para actualizar dependencias, cambia `pyproject.toml` o `package.json`, regenera sus lockfiles y ejecuta `make check`. Si cambias Ruff, alinea también `tool.ruff.required-version`. Regenera `requirements.txt` con `make export-requirements`.

Para PDF escaneados o fuentes corruptas se utiliza **Tesseract** si está disponible:

```bash
brew install tesseract
.venv/bin/python scripts/setup_ocr.py
```

El script descarga el modelo español oficial de `tesseract-ocr/tessdata_fast` a `data/tessdata/spa.traineddata`. Si falta, se intenta OCR con el modelo inglés instalado. Si el OCR no está disponible o no recupera texto, se registra una extracción parcial: no se inventa su contenido.

## Clasificar documentos nuevos

Crea la carpeta `docs/` y coloca allí tus PDF (admite subcarpetas). Los documentos no se distribuyen con el repositorio. Después ejecuta:

```bash
# Planificar extracción y lotes sin llamar a JEV
.venv/bin/python -m jevdocs classify --dry-run

# Catálogo completo, por defecto
.venv/bin/python -m jevdocs classify

# Núcleo original de 49 preguntas + 38 temas
.venv/bin/python -m jevdocs classify --profile core

# Otra carpeta, modelo o concurrencia
.venv/bin/python -m jevdocs classify --docs /ruta/documentos --model jev-1.13.0 --workers 3

# Regenerar HTML tras cambiar la interfaz, sin llamadas API
.venv/bin/python -m jevdocs build
```

La clasificación envía a la **API oficial de TypeSafe** el texto extraído y los criterios. La caché evita repetir peticiones idénticas; la extracción y el OCR sí se vuelven a ejecutar. Los cambios de contenido, preguntas, modelo o versión del pipeline invalidan la caché pertinente. Se usa el modelo fijo `jev-1.13.0` por defecto; `.env` permite `JEV_MODEL`.

Después de reclasificar, reinicia el servidor para cargar el nuevo índice de búsqueda semántica y recarga la página. El HTML no depende de CDNs, fuentes remotas ni librerías de terceros en el navegador.

## Cómo buscar

- **Texto:** busca palabras en el nombre y texto completo, ignorando mayúsculas y tildes. Todas las palabras deben aparecer; no necesariamente en la misma frase.
- **Filtros rápidos:** tipo, tema central/secundario, longitud y cobertura. Varias opciones dentro de una misma dimensión se combinan con **O**; dimensiones diferentes con **Y**. Para exigir dos temas distintos, usa sus preguntas independientes en filtros avanzados.
- **Filtros avanzados:** todas las preguntas agrupadas, incluidas menciones temáticas, presencia, «no determinable», «sin evaluar», decisiones por revisar y escalas. Los recuentos tienen en cuenta los otros filtros.
- **Escalas:** mínimos/máximos 0–4. En documentos divididos, coincide si una unidad aceptada está en ese intervalo; no se calcula un promedio del documento.
- **Preguntar a JEV:** evalúa una pregunta `Noul` sobre cada unidad con la necesidad de búsqueda. Ordena por la mayor respuesta local y muestra resultados ≥ 0,50. Puedes ampliar a 0,25 para ver posibles coincidencias o exigir 0,75. La probabilidad local máxima no es una probabilidad calibrada global. Los filtros activos siguen aplicándose.
- **Fichas:** etiquetas, extractos literales, criterios, decisiones por unidad, distribuciones de probabilidades, estado de aplicabilidad, texto de cada página y PDF original. Las páginas son el alcance examinado, **no citas probatorias localizadas por el modelo**.
- **Exportar:** descarga los documentos que coinciden con la consulta y los filtros en JSON. La URL conserva filtros y texto para recuperar una búsqueda textual.

Las fichas combinan decisiones cerradas y extractos, no resúmenes narrativos inventados. Puedes buscar nombres concretos con texto y aspectos generales mediante facetas.

## Reglas de clasificación

1. **Metadatos mediante código.** Hash SHA-256, bytes, páginas, palabras, longitud, método de extracción y cobertura. No se confunde la fecha del archivo o los metadatos PDF con una fecha semántica validada.
2. **Extracción.** PyMuPDF conserva el texto por página. Se compactan espacios; no se promete fidelidad de tablas. Un detector de caracteres de control y texto anómalo activa OCR, además de las páginas sin texto. El OCR breve se marca como sospechoso; las imágenes no se interpretan semánticamente.
3. **Segmentación sin truncamiento.** Las unidades agrupan páginas; una página muy grande se parte conservando su número. No se descartan caracteres. El estado tiene unos 19 KB de texto JSON, cada estado + pregunta se limita a 29 KB y cada petición a 55 KB UTF-8. Son presupuestos deliberadamente conservadores en bytes, no un tokenizador oficial. La API publica 32k tokens para estado + pregunta mayor y 64k por petición.
4. **Lotes y caché.** Preguntas originales completas, autenticación Bearer solo en Python, validación estricta de respuestas, reintentos para errores transitorios y guardado atómico. La caché guarda petición y respuesta sin cabeceras ni clave.
5. **Aceptación provisional.** Confianza ≥ 0,70. Es una política exploratoria **no calibrada**, no una precisión del 70%. Las dudas no se sobrescriben ni se aprueban manualmente para maquillar resultados.
6. **Puntuaciones.** Solo se usan cuando el control de aplicabilidad en la misma unidad es aceptado y dice `evaluable`. No aplicable no se convierte en cero. No se promedian unidades.
7. **Agregación.** Una presencia aceptada basta para localizar contenido. Para publicar «no observado» hacen falta todas las unidades aceptadas y cobertura textual completa. Temas centrales/secundarios se conservan como locales si hay varias unidades. Las categorías contradictorias quedan en revisión. Un tipo aceptado solo en fragmentos sigue siendo buscable con ese alcance explícito.
8. **Fallos visibles.** Se conservan respuestas parciales y preguntas sin evaluar. La CLI termina con error si hay archivos o lotes fallidos. Volver a ejecutar reutiliza lo ya guardado.

`catalog/` contiene únicamente el catálogo genérico publicable. Las conversaciones y exportaciones de trabajo permanecen en `exports/`, excluido de Git. `normalizar_respuestas.py` del paquete original se mantiene como referencia; la aplicación incorpora su propia normalización porque necesita reglas por fragmento, aceptación provisional y agregación.

## Archivos

| Ruta | Contenido |
|---|---|
| `jevdocs/core.py` | Extracción, segmentación, cliente HTTP, validación, caché y normalización |
| `jevdocs/__main__.py` | CLI, ejecución y generación del HTML y del informe |
| `jevdocs/server.py` | Servidor local y búsqueda `Noul` sobre las unidades |
| `web/` | Fuentes del HTML, estilos y JavaScript sin dependencias |
| `data/cache/` | Peticiones/respuestas reales, hash, modelo, uso y latencia |
| `data/documents/` | Fichas completas con texto, decisiones y trazabilidad |
| `data/index.json` | Índice interno reproducible |
| `output/index.html` | Explorador autónomo con datos y recursos embebidos |
| `output/index.json` | Índice exportable con catálogo y resultados |
| `output/originals/` | Copias de PDF para abrir desde el explorador |
| `output/informe.md` | Informe detallado generado sobre la ejecución |
| `output/validacion.md` | Resultados de las comprobaciones y búsquedas reales |
| `tests/` | Pruebas de integridad, incertidumbre, caché y servidor |

## Pruebas

```bash
.venv/bin/python -m pytest -q tests catalog/test_kit.py

# Evaluación configurable con tus propios casos privados (usa JEV; caché disponible)
.venv/bin/python scripts/evaluate.py
```

Las pruebas automáticas usan datos sintéticos y no necesitan documentos personales ni clave API. Para evaluar una colección real, crea `data/evaluation-cases.json` siguiendo `examples/evaluation-cases.example.json`. Los casos, consultas y resultados reales son privados y quedan fuera de Git; los informes se generan en `output/validacion.md`. Esta evaluación mide los casos seleccionados, no la exactitud global de las 235 facetas.

## Alcance y límites

La entrada implementada es PDF; no hay ingesta de DOCX, Excel o imágenes sueltas. No hay edición manual persistente de etiquetas, permisos multiusuario ni motor de entidades. La recuperación combina palabras, facetas y evaluación de fragmentos; no interpreta relaciones complejas entre fragmentos alejados. La cobertura por páginas no garantiza que una tabla o ilustración se haya extraído bien. Los datos de sensibilidad son señales de clasificación, nunca permisos.

El servidor escucha únicamente en `127.0.0.1`, comprueba host y origen y sirve una lista explícita de archivos. `.env` no se sirve. Tanto `data/` como `output/` contienen texto documental potencialmente privado; `.gitignore` excluye estas carpetas, `.env` y el entorno virtual. Conserva el HTML y las exportaciones como conservarías los originales.

Fuentes técnicas oficiales: [API](https://docs.typesafe.ai/api), [modelos y límites](https://docs.typesafe.ai/models), [confianza](https://docs.typesafe.ai/confidence).
