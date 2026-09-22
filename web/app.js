"use strict";
const DATA = JSON.parse(document.getElementById("dataset").textContent);
const DOCS = DATA.documents,
  BANK = DATA.questions,
  META = DATA.catalog.preguntas;
const $ = (id) => document.getElementById(id);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
const norm = (v) =>
  String(v ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
const labels = {
  presente: "Presente",
  no_observado: "No observado",
  no_determinable: "No determinable",
  central: "Central",
  secundario: "Secundario",
  mencion: "Mención",
  accepted: "Aceptada",
  review_required: "Por revisar",
  conflicting: "Discrepancia entre fragmentos",
  not_evaluated: "Sin evaluar",
  not_applicable: "No aplicable",
  applicability_unresolved: "Aplicabilidad dudosa",
  insufficient_evidence: "Evidencia insuficiente",
  segment_values: "Valores por fragmento",
  factura: "Factura",
  presupuesto_oferta: "Presupuesto / oferta",
  informe: "Informe",
  informe_auditoria: "Informe de auditoría",
  contrato_convenio: "Contrato / convenio",
  presentacion: "Presentación",
  acta: "Acta",
  manual_guia: "Manual / guía",
  espanol: "Español",
  ingles: "Inglés",
  es: "Español",
  en: "Inglés",
  invitacion_anuncio: "Invitación / anuncio",
};
const label = (v) =>
  labels[v] ||
  (typeof v === "number"
    ? v.toFixed(2)
    : String(v ?? "")
        .replaceAll("_", " ")
        .replace(/^./, (s) => s.toUpperCase()));
const qlabel = (k) => META[k]?.etiqueta_ui || label(k);
const fmt = (n) => new Intl.NumberFormat("es-ES").format(n);
const STATUS_OPTIONS = {
  "@review": "Por revisar / discrepancia",
  "@not_evaluated": "Sin evaluar",
  "@not_applicable": "No aplicable",
  "@unknown": "No determinable",
};
let filters = {},
  query = "",
  mode = "text",
  semantic = null,
  searchSequence = 0,
  detailDoc = null,
  activeTab = "summary";
let visibleDocs = [...DOCS];
const searchTexts = new Map(
  DOCS.map((d) => [d.id, norm(d.filename + " " + d.pages.map((p) => p.text).join("\n"))]),
);
try {
  const saved = JSON.parse(decodeURIComponent(location.hash.slice(1)));
  filters = saved.f || {};
  query = saved.q || "";
} catch {}
function saveState() {
  try {
    history.replaceState(
      null,
      "",
      "#" + encodeURIComponent(JSON.stringify({ q: query, f: filters })),
    );
  } catch {}
}
function reviewCount(d) {
  return Object.values(d.facets).filter(
    (f) => !["accepted", "segment_values", "not_applicable"].includes(f.status),
  ).length;
}
function facetValues(d, key) {
  if (key === "$length") return [d.length_band];
  if (key === "$coverage") return [d.extraction.coverage];
  if (key === "$review") return [reviewCount(d) > 0 ? "yes" : "no"];
  if (key === "$topic")
    return Object.entries(d.facets)
      .filter(
        ([k, f]) =>
          k.startsWith("tema_") &&
          f.status === "accepted" &&
          ["central", "secundario"].includes(f.value),
      )
      .map(([k]) => k);
  const f = d.facets[key];
  if (!f) return [];
  if (f.status === "accepted") return [f.value];
  if (f.status === "segment_values")
    return f.observations.filter((o) => o.status === "accepted").map((o) => o.value);
  return [];
}
function matchesValue(d, key, value) {
  const f = d.facets[key];
  if (value === "@review")
    return (
      f &&
      [
        "review_required",
        "conflicting",
        "applicability_unresolved",
        "insufficient_evidence",
      ].includes(f.status)
    );
  if (value === "@not_evaluated") return f?.status === "not_evaluated";
  if (value === "@not_applicable") return f?.status === "not_applicable";
  if (value === "@unknown") return f?.status === "accepted" && f.value === "no_determinable";
  return facetValues(d, key).includes(value);
}
function matches(d, ignoreKey = null) {
  if (
    mode === "text" &&
    query.trim() &&
    !norm(query)
      .split(/\s+/)
      .every((term) => searchTexts.get(d.id).includes(term))
  )
    return false;
  if (mode === "jev" && semantic && (semantic[d.id]?.score ?? 0) < Number($("relevance").value))
    return false;
  return Object.entries(filters).every(([key, values]) => {
    if (key === ignoreKey) return true;
    if (key.startsWith("$range:")) {
      const id = key.slice(7);
      return facetValues(d, id).some(
        (v) =>
          typeof v === "number" &&
          (values[0] === "" || v >= Number(values[0])) &&
          (values[1] === "" || v <= Number(values[1])),
      );
    }
    return !values.length || values.some((v) => matchesValue(d, key, v));
  });
}
function count(key, value) {
  return DOCS.filter((d) => matches(d, key) && matchesValue(d, key, value)).length;
}
function setFilter(key, value) {
  const current = new Set(filters[key] || []);
  current.has(value) ? current.delete(value) : current.add(value);
  if (current.size) filters[key] = [...current];
  else delete filters[key];
  render();
}
function clearFilters() {
  filters = {};
  query = "";
  $("query").value = "";
  semantic = null;
  searchSequence++;
  $("search-message").hidden = true;
  render();
}
function checkbox(key, value, text) {
  const selected = filters[key]?.includes(value);
  return `<label class="check-option"><input type="checkbox" data-filter="${esc(key)}" value="${esc(value)}" ${selected ? "checked" : ""}><span>${esc(text)}</span><em>${count(key, value)}</em></label>`;
}
function block(key, title, content, open = false) {
  return `<details class="filter-block" data-block="${esc(key)}" ${open ? "open" : ""}><summary>${esc(title)}</summary><div class="filter-body">${content}</div></details>`;
}
function renderFilters() {
  const oldOpen = new Set(
    [...document.querySelectorAll("[data-block][open]")].map((el) => el.dataset.block),
  );
  const first = !$("filters").children.length,
    term = norm($("filter-search").value);
  const open = (k) => (first ? ["types", "topics"].includes(k) : oldOpen.has(k));
  const types = [...new Set(DOCS.flatMap((d) => facetValues(d, "tipo_documental")))];
  let html = "";
  if (!term) {
    html += block(
      "types",
      "Tipo de documento",
      types.map((v) => checkbox("tipo_documental", v, label(v))).join(""),
      open("types"),
    );
    const topics = DATA.catalog.grupos.temas.preguntas.filter((k) =>
      DOCS.some((d) => facetValues(d, "$topic").includes(k)),
    );
    html += block(
      "topics",
      "Temas principales",
      topics.map((k) => checkbox("$topic", k, qlabel(k))).join("") +
        '<p class="filter-topic-name">Central o secundario en alguna unidad. Las menciones están en filtros avanzados.</p>',
      open("topics"),
    );
    html += block(
      "length",
      "Longitud del texto",
      ["Muy corto", "Corto", "Medio", "Largo", "Muy largo", "Sin texto"]
        .filter((v) => DOCS.some((d) => d.length_band === v))
        .map((v) => checkbox("$length", v, v))
        .join(""),
      open("length"),
    );
    html += block(
      "quality",
      "Cobertura y revisión",
      checkbox("$review", "yes", "Con decisiones por revisar") +
        checkbox("$coverage", "partial", "Extracción parcial") +
        checkbox("$coverage", "full", "Texto en todas las páginas"),
      open("quality"),
    );
  }
  for (const [group, g] of Object.entries(DATA.catalog.grupos)) {
    const keys = g.preguntas.filter(
      (k) =>
        !term || norm(qlabel(k) + " " + k + " " + BANK[k].instructions.pregunta).includes(term),
    );
    if (!keys.length) continue;
    let content = "";
    for (const k of keys) {
      const q = BANK[k];
      content += `<div><label class="filter-topic-name" for="f-${esc(k)}">${esc(qlabel(k))}</label>`;
      if (q.type === "score") {
        const range = filters["$range:" + k] || ["", ""];
        content += `<div class="range-row"><input type="number" min="0" max="4" step="0.1" data-range="${esc(k)}" data-bound="0" value="${esc(range[0])}" aria-label="Mínimo ${esc(qlabel(k))}" placeholder="Mín. 0"><input type="number" min="0" max="4" step="0.1" data-range="${esc(k)}" data-bound="1" value="${esc(range[1])}" aria-label="Máximo ${esc(qlabel(k))}" placeholder="Máx. 4"></div>`;
      }
      content += `<select id="f-${esc(k)}" data-facet="${esc(k)}" class="advanced-select"><option value="">Cualquier respuesta</option>`;
      if (q.type === "choice")
        for (const v of Object.keys(q.criteria))
          content += `<option value="${esc(v)}" ${filters[k]?.includes(v) ? "selected" : ""}>${esc(label(v))} (${count(k, v)})</option>`;
      for (const [v, t] of Object.entries(STATUS_OPTIONS))
        content += `<option value="${v}" ${filters[k]?.includes(v) ? "selected" : ""}>${t} (${count(k, v)})</option>`;
      content += "</select></div>";
    }
    html += block("g-" + group, g.nombre, content, term || open("g-" + group));
  }
  $("filters").innerHTML = html || '<p class="side-note">No se encontraron filtros.</p>';
}
function download(name, data) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function shortName(name) {
  return name
    .replace(/\.pdf$/i, "")
    .replaceAll("_", " ")
    .replace(/ \(1\)$/, "");
}
function originalURL(d, page = null) {
  return (
    "originals/" +
    d.relative_path.split("/").map(encodeURIComponent).join("/") +
    (page ? "#page=" + page : "")
  );
}
function highlighted(text) {
  if (!query.trim() || mode !== "text") return esc(text);
  const tokens = query
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .sort((a, b) => b.length - a.length);
  const regex = new RegExp(
    "(" + tokens.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")",
    "gi",
  );
  return text
    .split(regex)
    .map((s, i) => (i % 2 ? "<mark>" + esc(s) + "</mark>" : esc(s)))
    .join("");
}
function excerpt(d) {
  let text = d.pages
    .filter((p) => !p.text_quality_suspect)
    .map((p) => p.text)
    .join("\n");
  if (mode === "text" && query.trim()) {
    const needle = norm(query.trim().split(/\s+/)[0]);
    const p = d.pages.find((p) => norm(p.text).includes(needle));
    if (p) {
      const start = Math.max(0, norm(p.text).indexOf(needle) - 65);
      text = (start ? "… " : "") + p.text.slice(start, start + 330);
    }
  }
  return text.slice(0, 330).replace(/\s+/g, " ");
}
function positiveTags(d) {
  const localCount = (f) =>
    f.observations.filter(
      (o) => o.status === "accepted" && ["central", "secundario"].includes(o.value),
    ).length;
  const topics = Object.entries(d.facets)
    .filter(
      ([k, f]) =>
        k.startsWith("tema_") &&
        ["central", "secundario"].includes(f.value) &&
        f.status === "accepted",
    )
    .sort((a, b) => localCount(b[1]) - localCount(a[1]))
    .slice(0, 3);
  const preferred = [
    "tiene_tablas",
    "incluye_recomendaciones",
    "condiciones_pago",
    "incluye_resultados",
    "tiene_pasos",
    "obligaciones",
    "tiene_codigo",
    "fecha_limite_accion",
  ];
  const content = preferred.filter((k) => d.facets[k]?.value === "presente").slice(0, 2);
  return (
    topics
      .map(
        ([k, f]) =>
          `<button class="tag topic" data-tag="${esc(k)}" title="${esc(label(f.value))}${f.scope === "segments" ? " en fragmentos" : ""}">${esc(qlabel(k))}</button>`,
      )
      .join("") +
    content
      .map((k) => `<button class="tag" data-presence="${esc(k)}">${esc(qlabel(k))}</button>`)
      .join("")
  );
}
function renderCards() {
  visibleDocs = DOCS.filter((d) => matches(d));
  const sort = $("sort").value;
  visibleDocs.sort((a, b) =>
    mode === "jev" && semantic
      ? (semantic[b.id]?.score || 0) - (semantic[a.id]?.score || 0)
      : sort === "pages"
        ? b.page_count - a.page_count
        : sort === "words"
          ? b.word_count - a.word_count
          : sort === "review"
            ? reviewCount(b) - reviewCount(a)
            : a.filename.localeCompare(b.filename, "es"),
  );
  $("result-count").textContent = visibleDocs.length;
  $("result-context").textContent = Object.keys(filters).length
    ? `${Object.keys(filters).length} filtros combinados · Coincidencia entre dimensiones (Y)`
    : mode === "jev" && semantic
      ? `Ordenados por relevancia JEV · mínimo ${Number($("relevance").value) * 100}%`
      : "Toda tu colección, clasificada.";
  $("results").innerHTML =
    visibleDocs
      .map((d) => {
        const f = d.facets.tipo_documental,
          review = reviewCount(d),
          value = f.value
            ? label(f.value)
            : f.status === "segment_values"
              ? f.values.map(label).join(" / ")
              : "Tipo por revisar";
        return `<article class="card"><div class="card-top"><div class="pdf-icon">▤<small>PDF</small></div><div class="card-heading"><h3><button class="card-title" data-open="${d.id}">${esc(shortName(d.filename))}</button></h3><small>${d.page_count} ${d.page_count === 1 ? "página" : "páginas"} &nbsp;·&nbsp; ${fmt(d.word_count)} palabras &nbsp;·&nbsp; ${esc(d.length_band)}</small></div><button class="card-menu" data-open="${d.id}" aria-label="Ver ficha de ${esc(d.filename)}">↗</button></div><span class="doc-type ${f.value ? "" : "amber"}">${esc(value)}${f.scope === "segments" ? " · por fragmentos" : ""}</span><p class="excerpt" title="Extracto literal del documento">${highlighted(excerpt(d))}</p><div class="tags">${positiveTags(d)}</div><div class="card-bottom"><small>${mode === "jev" && semantic ? `<span class="score-tag">JEV ${Math.round((semantic[d.id]?.score || 0) * 100)}%</span>` : `${d.extraction.coverage === "full" ? "◉ Texto de todas las páginas" : "◐ Extracción parcial"}${review ? ` &nbsp;<span class="review-dot">· ${review} dudas</span>` : ""}`}</small><button data-open="${d.id}">Explorar ficha &nbsp;→</button></div></article>`;
      })
      .join("") ||
    '<div class="empty"><h3>No hay documentos con esta combinación.</h3><p>Prueba a quitar un filtro o ampliar los términos de búsqueda.</p><button class="primary" id="empty-clear">Restablecer búsqueda</button></div>';
  $("empty-clear")?.addEventListener("click", clearFilters);
}
function renderChips() {
  $("active-filters").innerHTML = Object.entries(filters)
    .map(([k, vs]) => {
      const keyLabel =
        { $topic: "Tema", $length: "Longitud", $coverage: "Cobertura", $review: "Revisión" }[k] ||
        qlabel(k.replace("$range:", ""));
      const valueLabel = k.startsWith("$range:")
        ? `${vs[0] || 0} – ${vs[1] || 4}`
        : vs.map((v) => (k === "$topic" ? qlabel(v) : STATUS_OPTIONS[v] || label(v))).join(" o ");
      return `<button class="filter-chip" data-remove="${esc(k)}">${esc(keyLabel)}: ${esc(valueLabel)} &nbsp;×</button>`;
    })
    .join("");
}
function render() {
  renderCards();
  renderFilters();
  renderChips();
  saveState();
}
function detailSummary(d) {
  const facts = [
    "tipo_documental",
    "finalidad_principal",
    "idioma_principal",
    "audiencia_principal",
    "estado_elaboracion",
    "ambito_uso",
  ];
  const presence = Object.entries(d.facets).filter(([, f]) => f.value === "presente");
  return `<div class="detail-summary"><img class="thumbnail" src="${d.thumbnail}" alt="Miniatura de la primera página"><div><span class="doc-type">Ficha a partir de decisiones JEV</span><div class="info-grid">${facts.map((k) => `<div class="info-cell"><small>${esc(qlabel(k))}</small><strong>${esc(d.facets[k].value ? label(d.facets[k].value) : d.facets[k].status === "segment_values" ? d.facets[k].values.map(label).join(" / ") + " (fragmentos)" : label(d.facets[k].status))}</strong></div>`).join("")}</div></div></div><h3>Temas y contenido</h3><div class="tags">${positiveTags(d)}</div><p>${presence.map(([k]) => esc(qlabel(k))).join(" · ") || "No hay presencias aceptadas."}</p><h3>Primeras líneas · extracto literal</h3><div class="page-text"><pre>${esc(d.pages.find((p) => p.text && !p.text_quality_suspect)?.text.slice(0, 1300) || "Sin texto extraíble")}</pre></div><div class="notice">${d.units.length > 1 ? `Este documento se examinó en ${d.units.length} unidades. Los temas y presencias pueden proceder de una sola unidad; revisa su alcance en «Todas las facetas». ` : ""}Las páginas asociadas son las examinadas por JEV, no citas probatorias seleccionadas por el modelo. ${d.extraction.warnings.map(esc).join(" ")}</div><h3>Trazabilidad</h3><p>${esc(DATA.models.join(", "))} · catálogo ${esc(DATA.catalog_version)} · ${d.units.reduce((n, u) => n + u.requests.length, 0)} peticiones.<br>SHA-256: <code style="overflow-wrap:anywhere">${d.sha256}</code></p><div class="download-row"><button class="secondary" id="download-doc">↓ Descargar ficha JSON</button><a class="secondary" href="${originalURL(d)}" target="_blank" rel="noopener">Abrir PDF original ↗</a></div>`;
}
function facetHTML(d, k) {
  const f = d.facets[k],
    q = BANK[k];
  const val =
    f.value !== null
      ? label(f.value)
      : f.status === "segment_values"
        ? f.values.map(label).join(" / ")
        : label(f.status);
  return `<details class="facet-row"><summary><span>${esc(qlabel(k))}</span><b>${esc(val)}</b>${f.status === "accepted" ? "" : `<small>${esc(label(f.status))}</small>`}</summary><div class="facet-explain"><p><strong>${esc(q.instructions.pregunta)}</strong></p><p>${esc(q.instructions.regla_especifica || q.instructions.reglas || "")}</p>${f.scope === "segments" ? "<p>Alcance: fragmentos del documento. No es una medida global.</p>" : ""}${
    f.observations
      .map(
        (o) =>
          `<div class="observation"><div class="observation-head"><span>${esc(o.unit)} · páginas ${o.pages.join(", ")} · ${esc(label(o.status))}</span><span>Confianza ${Math.round(o.confidence * 100)}%</span></div><p>Respuesta: <strong>${esc(label(o.value))}</strong> · ${esc(q.type === "choice" ? q.criteria[o.value] : ["not_applicable", "applicability_unresolved", "insufficient_evidence"].includes(o.status) ? "Puntuación bruta excluida: no usar como etiqueta." : "Escala 0–4; no es un porcentaje.")}</p>${Object.entries(
            o.raw.probabilities || {},
          )
            .sort((a, b) => b[1] - a[1])
            .filter(([, p], i) => p > 0.005 || i < 2)
            .map(
              ([v, p]) =>
                `<div class="probability" title="${esc(q.type === "score" ? q.criteria[Number(v)] : q.criteria[v])}"><span>${esc(q.type === "score" ? "Nivel " + v : label(v))}</span><div class="bar"><i style="width:${p * 100}%"></i></div><span>${(p * 100).toFixed(1)}%</span></div>`,
            )
            .join("")}</div>`,
      )
      .join("") || "<p>Esta pregunta no se ha ejecutado.</p>"
  }</div></details>`;
}
function renderFacetList() {
  const d = detailDoc,
    term = norm($("facet-search").value),
    only = $("only-useful").checked;
  $("facet-list").innerHTML = Object.values(DATA.catalog.grupos)
    .map((g) => {
      const keys = g.preguntas.filter(
        (k) =>
          (!term || norm(qlabel(k) + " " + k).includes(term)) &&
          (!only || !["no_observado", "no_declarado"].includes(d.facets[k].value)),
      );
      return keys.length
        ? `<section class="facet-group"><h3>${esc(g.nombre)} · ${keys.length}</h3>${keys.map((k) => facetHTML(d, k)).join("")}</section>`
        : "";
    })
    .join("");
}
function renderDetail() {
  const d = detailDoc;
  $("detail-content").innerHTML =
    `<div class="detail-header"><div class="detail-header-top"><h2>${esc(shortName(d.filename))}</h2><button class="close" id="close-detail" aria-label="Cerrar ficha">×</button></div><div class="detail-meta">${d.page_count} páginas · ${fmt(d.word_count)} palabras · ${d.units.length} unidades examinadas · ${reviewCount(d)} facetas por revisar</div><div class="detail-tabs">${[
      ["summary", "Resumen"],
      ["facets", "Todas las facetas · 235"],
      ["text", "Texto por páginas"],
      ["raw", "Datos y trazabilidad"],
    ]
      .map(
        ([id, title]) =>
          `<button class="detail-tab ${activeTab === id ? "active" : ""}" data-tab="${id}">${title}</button>`,
      )
      .join("")}</div></div><div class="detail-body" id="detail-body"></div>`;
  $("close-detail").onclick = () => $("detail").close();
  if (activeTab === "summary") {
    $("detail-body").innerHTML = detailSummary(d);
    $("download-doc").onclick = () => download(d.filename + ".json", d);
  }
  if (activeTab === "facets") {
    $("detail-body").innerHTML =
      '<div class="facet-tools"><input class="small-input" id="facet-search" placeholder="Buscar entre las 235 preguntas…" aria-label="Buscar facetas"><label><input type="checkbox" id="only-useful"> Ocultar no observados</label></div><div id="facet-list"></div>';
    $("facet-search").oninput = renderFacetList;
    $("only-useful").onchange = renderFacetList;
    renderFacetList();
  }
  if (activeTab === "text") {
    $("detail-body").innerHTML =
      `<p>Texto de todas las páginas. Orden y tablas pueden haber cambiado durante la extracción; abre el original para contrastar.</p>${d.pages.map((p) => `<section class="page-text"><header><span>Página ${p.page} · ${esc(p.method)} · ${p.words} palabras</span><a href="${originalURL(d, p.page)}" target="_blank" rel="noopener">Ver original ↗</a></header><pre>${highlighted(p.text || "[Sin texto extraíble]")}</pre></section>`).join("")}`;
  }
  if (activeTab === "raw") {
    $("detail-body").innerHTML =
      `<p>Las respuestas brutas mantienen distribuciones, confianza, unidades y huellas de las peticiones. Ningún campo contiene la clave API.</p><button id="download-doc" class="secondary">↓ Descargar ficha completa</button><pre class="raw-json">${esc(JSON.stringify({ ...d, thumbnail: undefined, pages: undefined }, null, 2))}</pre>`;
    $("download-doc").onclick = () => download(d.filename + ".json", d);
  }
}
function openDoc(id) {
  detailDoc = DOCS.find((d) => d.id === id);
  activeTab = "summary";
  renderDetail();
  $("detail").showModal();
}
function setMode(next) {
  mode = next;
  semantic = null;
  searchSequence++;
  $("run-search").disabled = false;
  $("text-mode").classList.toggle("active", next === "text");
  $("jev-mode").classList.toggle("active", next === "jev");
  $("run-search").hidden = next !== "jev";
  $("semantic-options").hidden = next !== "jev";
  $("search-help").textContent =
    next === "text"
      ? "Busca en el texto completo, sin enviar nuevas peticiones."
      : "Evalúa tu consulta sobre los fragmentos con JEV. Requiere el servidor local.";
  $("query").placeholder =
    next === "text"
      ? "Busca un nombre, concepto o frase en tus documentos…"
      : "Ej.: ¿Qué documentos describen pruebas antes de poner un sistema en marcha?";
  $("search-message").hidden = true;
  render();
}
async function runSemantic() {
  const requested = query.trim();
  if (!requested) return;
  const seq = ++searchSequence;
  semantic = null;
  $("search-message").hidden = false;
  $("search-message").textContent = "JEV está contrastando tu consulta con los documentos…";
  $("run-search").disabled = true;
  try {
    if (!["http:", "https:"].includes(location.protocol))
      throw Error(
        "Para preguntar a JEV, inicia el servidor con .venv/bin/python -m jevdocs serve y abre http://127.0.0.1:8765. Los filtros y la búsqueda textual funcionan sin servidor.",
      );
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: requested }),
    });
    const body = await response.json();
    if (!response.ok) throw Error(body.error || "No se pudo consultar JEV.");
    if (seq !== searchSequence) return;
    semantic = Object.fromEntries(body.results.map((r) => [r.id, r]));
    $("search-message").textContent =
      `Consulta completada en ${body.seconds.toFixed(1)} s. Puedes ampliar el umbral para revisar posibles coincidencias. El valor es el máximo por fragmento, no una probabilidad global del documento.${body.errors.length ? " Algunas unidades no se pudieron evaluar." : ""}`;
    render();
  } catch (e) {
    if (seq === searchSequence) $("search-message").textContent = e.message;
  } finally {
    if (seq === searchSequence) $("run-search").disabled = false;
  }
}
document.addEventListener("click", (e) => {
  const el = e.target.closest("button");
  if (!el) return;
  if (el.dataset.open) openDoc(el.dataset.open);
  if (el.dataset.tag) setFilter("$topic", el.dataset.tag);
  if (el.dataset.presence) setFilter(el.dataset.presence, "presente");
  if (el.dataset.remove) {
    delete filters[el.dataset.remove];
    render();
  }
  if (el.dataset.tab) {
    activeTab = el.dataset.tab;
    renderDetail();
  }
});
$("filters").addEventListener("change", (e) => {
  const el = e.target;
  if (el.dataset.filter) setFilter(el.dataset.filter, el.value);
  if (el.dataset.facet) {
    el.value ? (filters[el.dataset.facet] = [el.value]) : delete filters[el.dataset.facet];
    render();
  }
  if (el.dataset.range) {
    const key = "$range:" + el.dataset.range;
    const range = filters[key] || ["", ""];
    range[Number(el.dataset.bound)] = el.value;
    if (range.every((v) => v === "")) delete filters[key];
    else filters[key] = range;
    render();
  }
});
$("filter-search").oninput = renderFilters;
$("mobile-filters").onclick = () => {
  const open = document.querySelector(".sidebar").classList.toggle("mobile-open");
  $("mobile-filters").textContent = open ? "Ocultar filtros −" : "Mostrar filtros +";
  $("mobile-filters").setAttribute("aria-expanded", String(open));
};
$("clear").onclick = clearFilters;
$("all-docs").onclick = clearFilters;
$("query").value = query;
$("query").oninput = (e) => {
  query = e.target.value;
  semantic = null;
  searchSequence++;
  $("run-search").disabled = false;
  if (mode === "text") render();
  else {
    renderCards();
    $("search-message").hidden = true;
  }
};
$("query").onkeydown = (e) => {
  if (e.key === "Enter" && mode === "jev") runSemantic();
};
$("text-mode").onclick = () => setMode("text");
$("jev-mode").onclick = () => setMode("jev");
$("run-search").onclick = runSemantic;
$("sort").onchange = renderCards;
$("relevance").onchange = () => {
  renderCards();
  renderFilters();
};
$("export").onclick = () =>
  download("atlas-resultados.json", {
    created_at: new Date().toISOString(),
    filters,
    query,
    mode,
    semantic,
    documents: visibleDocs.map(({ thumbnail, ...d }) => d),
  });
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "k") {
    e.preventDefault();
    $("query").focus();
  }
});
$("detail").addEventListener("click", (e) => {
  if (e.target === $("detail")) $("detail").close();
});
const presets = [
  ["Importes y pagos", { importes_monetarios: ["presente"], condiciones_pago: ["presente"] }],
  [
    "Software y próximos pasos",
    { $topic: ["tema_informatica_software"], incluye_recomendaciones: ["presente"] },
  ],
  ["Viajes y obligaciones", { $topic: ["tema_viajes_turismo"], obligaciones: ["presente"] }],
  ["Documentos breves", { $length: ["Muy corto", "Corto"] }],
];
$("presets").innerHTML = presets
  .map(([title], i) => `<button class="preset" data-preset="${i}">${esc(title)} ↗</button>`)
  .join("");
$("presets").onclick = (e) => {
  const b = e.target.closest("[data-preset]");
  if (!b) return;
  filters = structuredClone(presets[Number(b.dataset.preset)][1]);
  query = "";
  $("query").value = "";
  setMode("text");
};
$("total-side").textContent = DOCS.length;
$("model-label").textContent = DATA.models.join(", ") || "JEV · sin respuestas";
const topicCount = DATA.catalog.grupos.temas.preguntas.filter((k) =>
  DOCS.some((d) => ["central", "secundario"].includes(d.facets[k]?.value)),
).length;
$("stats").innerHTML = [
  [DOCS.length, "Documentos", "en la colección"],
  [Object.keys(BANK).length, "Preguntas", "por unidad"],
  [topicCount, "Temas detectados", "centrales o secundarios"],
  [DOCS.reduce((s, d) => s + d.page_count, 0), "Páginas", "procesadas"],
]
  .map(
    ([n, title, note]) =>
      `<div class="stat"><div class="stat-top">${title}</div><b>${fmt(n)}</b><small>${note}</small></div>`,
  )
  .join("");
$("generated").textContent = "Actualizado " + new Date(DATA.created_at).toLocaleDateString("es-ES");
render();
