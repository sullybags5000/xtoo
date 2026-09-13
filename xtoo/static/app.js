"use strict";
const $ = (id) => document.getElementById(id);
let offset = 0;
const limit = 40;
let searchSequence = 0;
let previewSequence = 0;
let selectedPath = "";
let entity = "";
let timer;
let lastFinished;

function notice(message = "") {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : `Request failed (${response.status})`,
    );
  }
  return response.json();
}

function highlighted(element, text) {
  element.replaceChildren();
  const terms = $("query").value.match(/[\p{L}\p{N}]+/gu) || [];
  if (!terms.length) {
    element.textContent = text;
    return;
  }
  const pattern = new RegExp(
    `(${terms.sort((a, b) => b.length - a.length).join("|")})`,
    "giu",
  );
  let start = 0;
  for (const match of text.matchAll(pattern)) {
    element.append(document.createTextNode(text.slice(start, match.index)));
    const mark = document.createElement("mark");
    mark.textContent = match[0];
    element.append(mark);
    start = match.index + match[0].length;
  }
  element.append(document.createTextNode(text.slice(start)));
}

function date(ns) {
  return new Date(ns / 1e6).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function clearPreview() {
  previewSequence++;
  selectedPath = "";
  $("preview-document").hidden = true;
  $("preview-empty").hidden = false;
}

async function preview(item, button) {
  const sequence = ++previewSequence;
  document.querySelectorAll(".result").forEach((row) => {
    row.classList.remove("selected");
    row.setAttribute("aria-pressed", "false");
  });
  button.classList.add("selected");
  button.setAttribute("aria-pressed", "true");
  $("preview-document").hidden = true;
  $("preview-empty").hidden = false;
  try {
    const doc = await api(`/api/documents/${item.id}`);
    if (sequence !== previewSequence) return;
    selectedPath = doc.path;
    $("preview-empty").hidden = true;
    $("preview-document").hidden = false;
    $("preview-kind").textContent = doc.kind;
    highlighted($("preview-title"), doc.title);
    $("preview-meta").textContent =
      `${doc.document_ns === doc.modified_ns ? "Modified" : "Dated"} ${date(doc.document_ns)} · ${Math.max(1, Math.round(doc.size / 1024)).toLocaleString()} KB`;
    $("preview-entities").replaceChildren(
      ...(doc.entities || []).map((link) => {
        const chip = node("button", "entity");
        chip.type = "button";
        chip.append(node("span", "entity-kind", link.kind), link.name);
        chip.addEventListener("click", () => filterByEntity(link.name));
        return chip;
      }),
    );
    $("preview-path").textContent = doc.path;
    $("copy-path").textContent = "Copy path";
    $("preview-warning").textContent = doc.preview_truncated
      ? "Preview shows the first 100,000 characters. More text may be searchable."
      : "";
    highlighted(
      $("preview-content"),
      doc.content ||
        "No text was extracted. This file is searchable by name. Scanned PDFs need OCR, which is not yet included.",
    );
  } catch (error) {
    if (sequence === previewSequence) notice(error.message);
  }
}

async function search() {
  const sequence = ++searchSequence;
  const params = new URLSearchParams({
    q: $("query").value,
    kind: $("kind").value,
    entity,
    collapse: $("collapse").checked,
    meaning: $("meaning").checked,
    offset,
    limit,
  });
  $("entity-filter").hidden = !entity;
  $("entity-name").textContent = entity;
  clearPreview();
  $("result-count").textContent = "Searching…";
  try {
    const data = await api(`/api/search?${params}`);
    if (sequence !== searchSequence) return;
    notice();
    $("results").replaceChildren();
    $("result-count").textContent =
      `${data.total.toLocaleString()} ${data.total === 1 ? "document" : "documents"}${$("query").value ? " found" : " in your library"}`;
    for (const item of data.items) {
      const button = node("button", "result");
      button.type = "button";
      button.setAttribute("aria-pressed", "false");
      const heading = node("div", "result-heading");
      const title = node("span", "result-title");
      highlighted(title, item.title);
      heading.append(node("span", "badge", item.kind), title);
      if (item.thread_size > 1)
        heading.append(node("span", "badge", `${item.thread_size} messages`));
      const snippet = node("p", "result-snippet");
      highlighted(
        snippet,
        item.snippet || "Searchable by filename · no extracted text",
      );
      button.append(
        heading,
        snippet,
        node("div", "result-meta", `${date(item.document_ns)} · ${item.path}`),
      );
      button.addEventListener("click", () => preview(item, button));
      $("results").append(button);
    }
    if (!data.items.length) {
      const empty = node("div", "empty");
      empty.append(
        node(
          "h2",
          "",
          $("query").value || $("kind").value || entity
            ? "No matching documents"
            : "Your library starts here",
        ),
      );
      empty.append(
        node(
          "p",
          "",
          $("query").value || $("kind").value || entity
            ? "Try fewer words, a different file type, or clear the link."
            : "Documents appear as your configured folders are indexed. Check the scan status above for progress or folder errors.",
        ),
      );
      $("results").append(empty);
    }
    $("previous").disabled = offset === 0;
    $("next").disabled = offset + limit >= data.total;
    $("page").textContent = data.total
      ? `${offset + 1}–${Math.min(offset + limit, data.total)} of ${data.total}`
      : "";
  } catch (error) {
    if (sequence === searchSequence) {
      notice(`Search unavailable: ${error.message}`);
      $("result-count").textContent = "Could not load results";
    }
  }
}

async function status() {
  try {
    const data = await api("/api/status");
    $("library-count").textContent = data.total_documents.toLocaleString();
    $("index-status").textContent = data.running
      ? `Indexing · ${data.indexed || 0} updated · ${data.unchanged || 0} unchanged`
      : data.last_finished
        ? `Last scan ${new Date(data.last_finished).toLocaleTimeString()} · ${data.skipped || 0} oversized files skipped`
        : "Waiting for first scan";
    $("meaning-toggle").hidden = !data.semantic;
    $("refresh").disabled = data.running;
    $("refresh").textContent = data.running ? "Indexing…" : "Refresh index";
    $("folders").replaceChildren(
      ...data.folders.map((folder) => node("li", "", folder)),
    );
    const selected = $("kind").value;
    const kinds = Object.keys(data.kinds);
    if (selected && !kinds.includes(selected)) kinds.push(selected);
    const options = [
      new Option("All file types", ""),
      ...kinds
        .sort()
        .map(
          (kind) =>
            new Option(
              `${kind.toUpperCase()} (${data.kinds[kind] || 0})`,
              kind,
            ),
        ),
    ];
    $("kind").replaceChildren(...options);
    $("kind").value = selected;
    $("scan-errors").hidden = !data.error_count;
    $("error-summary").textContent =
      `${data.error_count} indexing ${data.error_count === 1 ? "issue" : "issues"} — show details`;
    $("error-list").replaceChildren(
      ...data.errors.map((error) =>
        node("li", "", `${error.path}: ${error.message}`),
      ),
    );
    if (data.error_count > data.errors.length)
      $("error-list").append(
        node("li", "", "Only the first 20 issues are shown."),
      );
    if (lastFinished !== undefined && data.last_finished !== lastFinished) {
      offset = 0;
      search();
    }
    lastFinished = data.last_finished;
  } catch {
    $("index-status").textContent =
      "Connection lost — check that xtoo serve is running";
  }
}

$("query").addEventListener("input", () => {
  clearTimeout(timer);
  searchSequence++;
  previewSequence++;
  offset = 0;
  timer = setTimeout(search, 180);
});
function filterByEntity(name) {
  entity = name;
  offset = 0;
  search();
}

$("kind").addEventListener("change", () => {
  offset = 0;
  search();
});
$("collapse").addEventListener("change", () => {
  offset = 0;
  search();
});
$("meaning").addEventListener("change", () => {
  offset = 0;
  search();
});
$("entity-clear").addEventListener("click", () => filterByEntity(""));
$("previous").addEventListener("click", () => {
  offset = Math.max(0, offset - limit);
  search();
});
$("next").addEventListener("click", () => {
  offset += limit;
  search();
});
$("refresh").addEventListener("click", async () => {
  $("refresh").disabled = true;
  try {
    await api("/api/index", {
      method: "POST",
      headers: { "X-Xtoo-Request": "1" },
    });
    notice("Scan requested. Results will refresh when it finishes.");
    await status();
  } catch (error) {
    notice(error.message);
    $("refresh").disabled = false;
  }
});
$("copy-path").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(selectedPath);
    $("copy-path").textContent = "Copied";
  } catch {
    notice(
      "Clipboard unavailable. Select and copy the path shown in the preview.",
    );
  }
});
document.addEventListener("keydown", (event) => {
  if (
    event.key === "/" &&
    !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)
  ) {
    event.preventDefault();
    $("query").focus();
  }
});
search();
status();
setInterval(status, 3000);
