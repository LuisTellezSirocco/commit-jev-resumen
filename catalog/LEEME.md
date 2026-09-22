# Clasificación documental generalista con Jev

**Catálogo propuesto v1.0.0 · 22 de septiembre de 2026**

## Entrega

El banco contiene **235 preguntas**: **223 facetas sustantivas y 12 controles de aplicabilidad** de sus escalas. Se sugieren **49 preguntas iniciales**, ampliables con **38 áreas temáticas independientes** y el resto de bloques. El tipo principal ofrece 63 opciones, incluidas compilación heterogénea, otro y no determinable. Hay 12 escalas de cinco niveles descriptivos.

Los **30 campos deterministas** se calculan o extraen fuera de Jev. No se incluyen en las 235 preguntas.

| Archivo | Uso |
|---|---|
| `preguntas_jev.json` | Mapa completo de preguntas nativas: usar como `questions` o seleccionar parte. |
| `catalogo.json` | IDs, grupos, etiquetas de interfaz, núcleo y controles de aplicabilidad. No enviar como petición API. |
| `catalogo_completo.md` | Todas las preguntas y todas las opciones, para lectura y revisión humana. |
| `estado_plantilla.json` | Estructura de `state` que se debe rellenar con texto y cobertura reales. |
| `plantilla_peticion_nucleo.json` | Cuerpo HTTP nativo del núcleo de 49 preguntas. El estado contiene marcadores, no un documento real. |
| `metadatos_deterministas.json` | Contrato de los 30 campos que no debe inferir el modelo. |
| `ejemplos_filtros.json` | Consultas de ejemplo en una DSL ilustrativa propia, no sintaxis de TypeSafe. |
| `crear_peticiones.py` | Selector y empaquetador local. No accede a la red ni envía datos. |
| `normalizar_respuestas.py` | Conserva resultados brutos y aplica decisiones de aceptación externas. |
| `casos_prueba_sinteticos.json` | 11 casos inventados con expectativas iniciales; no se han ejecutado contra Jev. |
| `preguntas.schema.json` | Esquema local de validación estructural, no OpenAPI oficial. |
| `test_kit.py` | Pruebas unitarias del catálogo, selección, lotes y normalización. |
| `fuentes.json` | Documentación oficial consultada para el contrato técnico. |

`build_catalogue.py` y `build_support.py` permiten regenerar el banco y sus archivos descriptivos. Los IDs son claves de software; el significado completo figura en las instrucciones porque Jev no utiliza el ID para inferir [1, 2].

## 1. Qué significa clasificar aquí

Una factura de un curso no debe confundirse con un curso. Se separan **tipo**, **finalidad**, **temas**, **contenido presente**, **estado declarado** y **dimensiones puntuadas**.

Ejemplo de etiquetas esperadas, no una predicción ejecutada:

```json
{
  "tipo_documental": "factura",
  "tema_finanzas_contabilidad": "central",
  "tema_educacion_formacion": "mencion",
  "tiene_campos": "presente",
  "importes_monetarios": "presente",
  "componente_didactico": "no_observado"
}
```

La organización propuesta es deliberadamente multidimensional. Un informe puede contener un procedimiento y un cuestionario. Eso no es una contradicción. Varias áreas pueden ser centrales: por ejemplo, una investigación de inteligencia artificial aplicada a medicina.

El catálogo es una propuesta de diseño, **no una taxonomía oficial de TypeSafe ni una clasificación ya calibrada para tu colección**. Su cobertura puede ampliarse tras revisar los documentos que acaben en `otro`. No conviene crear etiquetas arbitrarias nuevas en cada llamada: cambia el vocabulario de manera versionada.

## 2. Formato nativo y elección de primitivas

La API usa `model`, `state` y `questions`. Una pregunta tiene `type`, `instructions` y, según su tipo, `criteria`. Aquí las opciones de `Choice` son un mapa de códigos a descripciones; los niveles de `Score` son una lista ordenada [1].

El catálogo utiliza `Choice` para categorías y estados de observación, y `Score` para grados definidos. Jev también dispone de `Noul`, que devuelve una probabilidad de sí [3]. Se ha preferido **Choice con salidas explícitas** cuando importa separar `no_observado` de `no_determinable`. No se introduce un supuesto tipo `multiselect`: cada tema tiene una pregunta independiente.

Ejemplo opcional de Noul, fuera del banco de 235 preguntas:

```json
{
  "type": "noul",
  "instructions": "¿El texto examinado contiene una pregunta seguida de una respuesta explícitamente asociada?",
  "criteria": {
    "true": "Existe al menos una pareja pregunta-respuesta identificable.",
    "false": "No hay una pareja pregunta-respuesta en el texto examinado."
  }
}
```

`Noul = 0.8` no significa que el documento tenga un 80 % de preguntas y respuestas, sino la probabilidad asignada al sí [3]. No trasladar umbrales de Noul a Choice sin validación.

## 3. Las respuestas que evitan etiquetas falsas

### Propiedades de presencia

- `presente`: se observa evidencia en la unidad examinada.
- `no_observado`: no aparece en el material suficientemente legible examinado; **no equivale a ausencia global**.
- `no_determinable`: falta el material necesario, hay ambigüedad o la extracción impide comprobarlo.

Una descripción de una página no permite negar firmas en el resto del PDF. En un archivo escaneado sin descripción visual, preguntas sobre gráficos pueden ser no determinables aunque algunas frases sean legibles.

### Temas

Cada una de las 38 áreas se clasifica como `central`, `secundario`, `mencion`, `no_observado` o `no_determinable`. Estas opciones no son una escala de confianza: describen la relación del documento con el tema. Para búsquedas temáticas generales, empezaría con central o secundario; para localizar una factura por el servicio facturado, incluiría también mencion.

### Otras categorías

`otro` significa que hay un tipo reconocible fuera del vocabulario. `no_determinable` significa falta de fundamento para decidir. `no_aplica` significa que no se cumple la premisa de una pregunta condicional. `no_declarado` o `estado_no_declarado` conservan la ausencia de una declaración explícita. No deben fundirse en un único null.

## 4. Puntuaciones, aplicabilidad y confianza

Las 12 escalas tienen cinco situaciones descritas, numeradas por su posición de 0 a 4. Jev devuelve la media ponderada de esos niveles; puede ser fraccionaria. Es posible normalizarla con `100 * score / 4`, pero eso **no la convierte en probabilidad ni porcentaje de contenido** [4].

Cada escala tiene un control independiente `evaluabilidad_*`. Publicar la puntuación solamente cuando el control aceptado sea `evaluable`. Si es `no_aplica`, guardar puntuación null y ese motivo. Si es `no_determinable`, guardar null con evidencia insuficiente. La puntuación bruta puede conservarse para auditoría, sin presentarla como una etiqueta válida.

La aplicabilidad y la escala pueden enviarse juntas: ninguna debe pedirle al modelo que lea la respuesta de la otra. **Las preguntas de una misma petición se evalúan de manera independiente**; la combinación la hace la aplicación [2].

Conservar la distribución completa y `confidence`. La confianza resume la concentración de la distribución y no demuestra corrección factual [5]. Una media de 2 puede provenir de certeza sobre el nivel 2 o de incertidumbre entre los extremos 0 y 4: la media sola no basta para distinguirlo.

`normalizar_respuestas.normalize` recibe `approved_ids`, decididos por una política calibrada o revisión humana. Intencionadamente no impone un `confidence > 0.8` universal. Resultados no aceptados se mantienen como `review_required`; preguntas no ejecutadas, como `not_evaluated`. Nunca convertir una pregunta omitida en false.

## 5. Ingesta y longitud

Medir con código bytes, páginas y recuento de palabras. Los tramos de longitud propuestos son: sin texto; 1–250; 251–1.000; 1.001–5.000; 5.001–20.000; más de 20.000 palabras. Son una decisión del producto, no un estándar. Mantener además el valor numérico para que el usuario cambie el filtro.

Distinguir el original del texto realmente examinado. Un PDF de 200 páginas del que se han leído dos no es un documento corto: es una **extracción parcial de un documento largo**. No afirmar longitud textual completa si faltan páginas o contenido. Tampoco tratar la fecha de modificación del sistema de archivos como la fecha semántica del documento.

La documentación consultada describe entrada de texto, no imágenes, audio ni vídeo. La extracción o descripción de esos soportes debe realizarse previamente [6]. Preservar tablas y campos cuando sea posible. El OCR se utiliza cuando no existe una extracción textual adecuada, no como paso obligatorio para todo archivo.

Las fechas tienen roles: emisión, actualización, periodo de referencia, evento, vencimiento. Jev puede ayudar a seleccionar candidatos; el parser valida la fecha y el código compara con una referencia temporal. Lo mismo se aplica a sumas de importes y duplicados exactos: no pedir al clasificador que los calcule [7].

## 6. Cómo ejecutar por grupos

Rellena `estado_plantilla.json` y guárdalo como `estado.json`. Cambia cobertura y banderas según el pipeline, no según una suposición. `full` significa cobertura declarada del original por tu extractor; la calidad y la disponibilidad de contenido visual siguen siendo dimensiones separadas.

```bash
python crear_peticiones.py --state estado.json --nucleo --salida peticiones_nucleo
python crear_peticiones.py --state estado.json --grupos temas --salida peticiones_temas
python crear_peticiones.py --state estado.json --grupos estructura,operaciones --salida peticiones_extra
python crear_peticiones.py --state estado.json --grupos escalas --salida peticiones_escalas
```

El script construye archivos que la integración puede enviar al endpoint oficial. No instala paquetes, no solicita una clave, no envía documentos y no presupone que tengas un SDK. Por defecto usa lotes de hasta 32 preguntas, una preferencia local configurable.

**El número de preguntas no garantiza que quepa la petición.** A fecha de consulta, TypeSafe publica 64k tokens para estado más todas las preguntas y 32k para estado más la pregunta individual más larga [6]. Antes de enviar, comprueba ambos presupuestos mediante el mecanismo de conteo apropiado de tu integración; este kit no incluye un tokenizador oficial de Jev ni promete un margen exacto. No se debe truncar silenciosamente el documento.

El alias `jev-latest` es práctico para probar. Para reproducibilidad, registrar el modelo resuelto que devuelve la API y fijar una versión al validar en producción [6].

## 7. Documentos largos y conjuntos heterogéneos

Propuesta de ejecución:

1. Ingesta, extracción, identificación de componentes y metadatos.
2. Núcleo de 49 preguntas sobre una unidad coherente. Añadir las 38 áreas temáticas si el objetivo es navegación general.
3. Ampliaciones pertinentes por grupo. Para no ocultar tipos raros, mantener una vía de revisión y aplicar periódicamente el catálogo amplio a una muestra.
4. Normalización, controles de confianza y construcción del índice.

Para documentos largos, segmentar por unidades semánticas preservando identificadores de página y sección. Un resumen o una selección inicial puede servir para enrutar provisionalmente, pero no para negar la presencia de elementos en todo el archivo.

Reglas de agregación propuestas:

- **Presencia:** una evidencia local aceptada permite afirmar presencia en el documento. Para certificar que no se ha observado en todo el material disponible, hace falta cobertura completa de las unidades pertinentes y resultados aceptados en ellas. Aun así, no es una garantía de ausencia real.
- **Temas:** un tema central en un anexo pequeño no tiene por qué ser central en todo el documento. Preservar etiquetas por sección y usar un resumen estructural representativo para la valoración global.
- **Tipos:** varias facturas dentro de un PDF son una compilación homogénea; una factura más una receta es heterogénea. Indexar las piezas hijas sin perder su vínculo con el archivo padre.
- **Puntuaciones:** no promediar automáticamente escalas de secciones dispares. Conservar alcance y revisar si tiene sentido una puntuación global.

No usar `max(probabilidades)` ni productos de probabilidades como si fueran una probabilidad global calibrada. Al revisar muchos fragmentos también puede aumentar el número de falsas alarmas; evaluar ese comportamiento a nivel documento.

## 8. Búsqueda, trazabilidad y seguridad

La ficha mínima de una clasificación debería registrar `document_id`, hash de contenido, versión del extractor, versión de catálogo, modelo resuelto, fecha de clasificación, IDs de segmentos examinados, cobertura, respuestas brutas, estado de aceptación y facetas publicadas.

Si necesitas justificar una etiqueta con texto, hay que conservar los segmentos de origen. Jev no genera una explicación libre de evidencia. Una fase opcional puede seleccionar IDs de candidatos que previamente proporcionó el código; no inventar que la respuesta estándar incluye citas o spans.

Para buscar una combinación precisa, aplicar filtros de facetas aceptadas y después búsqueda textual o semántica sobre los candidatos autorizados. El catálogo generalista no identifica por sí solo todas las entidades concretas —clientes, productos, expedientes, lugares o tecnologías—. Añadir índices de texto y extracción de entidades con valores respaldados por el original cuando esos filtros sean necesarios.

Los filtros deben admitir encontrar `no_determinable`, `review_required` y `not_evaluated`; así se puede localizar lo pendiente de completar y no solo las etiquetas positivas.

Las señales de sensibilidad no sustituyen permisos del repositorio. **No autorizar acceso, publicación o descarga porque un clasificador no haya detectado información sensible.** Aplicar permisos antes de recuperar texto y mostrar resultados. Los documentos se envían a un servicio externo al invocar la API: comprobar las condiciones de uso de esos datos y minimizar el material enviado.

El contenido se trata como dato no confiable y todas las preguntas lo recuerdan. Esta instrucción ayuda a delimitar la tarea, pero **no constituye una defensa infalible ante prompt injection**; TypeSafe reconoce sensibilidad a contenido adversarial [7]. No conectar etiquetas directamente a ejecución de código, transferencias, publicación o cambios irreversibles.

## 9. Evaluación propuesta

Empezaría con una muestra estratificada de unas 100–200 piezas, cuando el tamaño de la colección lo permita: tipos diversos, documentos cortos y largos, idiomas presentes, OCR deficiente, plantillas, compuestos y casos ambiguos. No basta una muestra aleatoria si deja fuera tipos raros. Los 11 ejemplos sintéticos del kit ayudan a comprobar criterios, pero no sustituyen documentos representativos.

Anotar las facetas que interesan realmente al buscador y separar conjuntos para ajustar preguntas, calibrar aceptación y evaluar el resultado final. Medir errores por faceta y grupo: precisión de etiquetas positivas, omisiones relevantes, tasa de revisión y cobertura de clasificaciones automáticas. En escalas, revisar desacuerdos ordinales y si el orden resulta útil para el usuario. Medir también búsquedas reales: encontrar el documento adecuado importa más que acumular etiquetas.

Comparar instrucciones en español y, si procede, una versión traducida y versionada: la documentación indica mejor rendimiento actual en inglés; no se puede garantizar el mismo rendimiento para todos los idiomas [6]. No traducir datos sensibles mediante otro servicio sin autorización.

Versionar cambios de opciones y significado. Si cambia la definición de un campo, no mezclar resultados antiguos y nuevos como si fueran equivalentes. Una actualización de modelo o extractor también requiere comprobar regresiones.

## Verificación realizada y límites de esta entrega

Se ha comprobado el formato de la API en documentación oficial y se han preparado pruebas locales de estructura y utilidades. **No se ha llamado a Jev, no se han clasificado tus archivos, no se ha medido precisión, coste ni latencia real.** Las rúbricas y decisiones de producto deben validarse sobre tu colección.

## Referencias técnicas

[1] TypeSafe, HTTP API. [2] TypeSafe, Choice y guía de preguntas independientes. [3] TypeSafe, Noul. [4] TypeSafe, Score. [5] TypeSafe, Confidence. [6] TypeSafe, Models. [7] TypeSafe, Jev 1.13 jaggedness. Direcciones oficiales y fecha de consulta en `fuentes.json`.
