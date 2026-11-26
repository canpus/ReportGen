"use strict";

const $ = (id) => document.getElementById(id);
const session = document.querySelector('meta[name="local-session"]').content;
const fields = {
  item: "检测项",
  component: "部件",
  scenario: "工况",
  interface: "界面",
  stage: "阶段",
  condition: "试验条件",
  test_temp: "试验温度",
  conditioning: "预处理或周期",
  requirement: "合格限值或处置要求",
  typical: "典型值",
  unit: "单位",
  method: "方法",
  value_role: "数值角色",
  quantity_kind: "物理量类别",
  pqt: "PQT",
  ppt: "PPT",
  production: "Production",
  sampling_basis: "抽样基数",
  frequency: "检验频次",
  failure_action: "失败处置",
  destination: "检测地点",
};
const roles = [
  "acceptance_limit",
  "test_condition",
  "typical_only",
  "typical_reference",
  "by_vendor",
  "tba",
  "by_agreement",
  "dash_not_listed",
  "conditional_exception",
];
const statuses = {
  candidate: "待核对",
  confirmed: "已确认",
  clarify: "待澄清",
};
let current = null,
  records = [],
  selected = null,
  frequency = false;
let pageNumber = 1,
  pageCount = 0,
  pageData = null,
  picking = false,
  region = null;
let loadEpoch = 0,
  pageEpoch = 0,
  displayedPage = "";

function element(tag, content, className) {
  const el = document.createElement(tag);
  if (content !== undefined) el.textContent = content;
  if (className) el.className = className;
  return el;
}
function notice(message = "") {
  $("message").textContent = message;
  $("message").hidden = !message;
}
async function request(path, { body, params, binary = false } = {}) {
  const url = new URL(path, location.origin);
  if (params) url.search = new URLSearchParams(params);
  const options =
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            "X-Order-Session": session,
            "Content-Type":
              body instanceof File ? "application/pdf" : "application/json",
          },
          body: body instanceof File ? body : JSON.stringify(body),
        };
  const response = await fetch(url, options);
  if (!response.ok) {
    const failure = await response.json().catch(() => ({}));
    throw new Error(failure.error || "请求失败 " + response.status);
  }
  return binary ? response : response.json();
}
function run(task) {
  return (...args) => {
    if (args[0]?.type === "submit") args[0].preventDefault();
    return Promise.resolve()
      .then(() => task(...args))
      .catch((err) => notice(err.message));
  };
}
function option(select, value, label) {
  select.add(new Option(label, value));
}
async function documents(preferred) {
  const docs = await request("/api/documents");
  const sel = $("documents");
  sel.replaceChildren();
  option(sel, "", "选择已导入文档");
  for (const d of docs) {
    option(
      sel,
      d.id,
      [d.order_id, d.doc_no, d.doc_rev].join(" / ") +
        (d.active ? "" : " · 历史版") +
        (d.alias_of ? " · 同文副本" : ""),
    );
  }
  sel.value = preferred || docs.find((d) => d.active)?.id || "";
  await load(sel.value);
}
async function load(id, keep = "") {
  const epoch = ++loadEpoch;
  if (!id) {
    current = null;
    selected = null;
    $("desk").hidden = true;
    $("welcome").hidden = false;
    $("export").disabled = true;
    $("docinfo").textContent = "";
    return;
  }
  const data = await request("/api/document", { params: { id } });
  if (epoch !== loadEpoch) return;
  const switched = current?.id !== id;
  current = data.document;
  records = data.rows;
  pageCount = data.pages;
  $("desk").hidden = false;
  $("welcome").hidden = true;
  $("export").disabled = false;
  $("docinfo").textContent =
    pageCount + " 个物理页 · SHA-256 " + current.sha256.slice(0, 12);
  $("docinfo").title = current.sha256;
  $("page").max = pageCount;
  $("total").textContent = "/ " + pageCount;
  for (const key of ["component", "scenario", "stage"]) {
    const sel = $(key),
      before = switched ? "" : sel.value;
    sel.replaceChildren();
    option(sel, "", "全部");
    const values = records.flatMap((r) =>
      key === "stage" && r.channel === "frequency"
        ? ["PQT", "PPT", "Production"]
        : [r[key]],
    );
    for (const val of [...new Set(values.filter(Boolean))].sort())
      option(sel, val, val);
    if ([...sel.options].some((o) => o.value === before)) sel.value = before;
  }
  if (switched) {
    $("status").value = "";
    frequency = !records.some((r) => r.channel !== "frequency");
  }
  await drawList(keep);
  if (!selected) await showPage(switched ? 1 : pageNumber);
}
async function drawList(preferred) {
  const filter = records.filter(
    (r) =>
      (r.channel === "frequency") === frequency &&
      ["status", "component", "scenario", "stage"].every(
        (k) =>
          !$(k).value ||
          (k === "stage" && r.channel === "frequency"
            ? r.stage.split(" / ").includes($(k).value)
            : r[k] === $(k).value),
      ),
  );
  $("requirements").setAttribute("aria-pressed", String(!frequency));
  $("frequencies").setAttribute("aria-pressed", String(frequency));
  const confirmed = records.filter((r) => r.status === "confirmed").length;
  $("counts").textContent = confirmed + " / " + records.length + " 项已确认";
  const head = element("tr");
  for (const title of frequency
    ? ["活动 / 工况", "PQT", "PPT", "Production", "状态"]
    : ["检测项", "工况", "物理页", "状态"])
    head.append(element("th", title));
  $("listHead").replaceChildren(head);
  $("rows").replaceChildren();
  for (const r of filter) {
    const line = element("tr");
    line.dataset.id = r.id;
    line.tabIndex = 0;
    const cells = frequency
      ? [
          [r.item, r.scenario].filter(Boolean).join(" · "),
          r.pqt,
          r.ppt,
          r.production,
          statuses[r.status],
        ]
      : [r.item, r.scenario, r.source_pages.join(", "), statuses[r.status]];
    for (const content of cells) line.append(element("td", content));
    line.addEventListener(
      "click",
      run(() => select(r)),
    );
    line.addEventListener("keydown", (e) => {
      if (["Enter", " "].includes(e.key)) {
        e.preventDefault();
        line.click();
      }
    });
    $("rows").append(line);
  }
  const next = filter.find((r) => r.id === preferred) || filter[0];
  if (next) await select(next);
  else {
    selected = null;
    $("detail").hidden = true;
    highlight();
  }
}
async function select(row) {
  selected = row;
  $("detail").hidden = false;
  $("rowtitle").textContent = row.id + " · " + statuses[row.status];
  for (const tr of $("rows").rows)
    tr.setAttribute("aria-selected", String(tr.dataset.id === row.id));
  $("verbatim").textContent = row.verbatim || "该页需要人工核对";
  $("sourcepages").replaceChildren();
  const evidencePages = new Set([
    ...row.source_pages,
    ...row.evidence.map((id) => Number(id.split(".")[0])),
  ]);
  for (const page of [...evidencePages].sort((a, b) => a - b)) {
    const b = element("button", "第 " + page + " 页");
    b.onclick = run(() => showPage(page));
    $("sourcepages").append(b);
  }
  $("alerts").replaceChildren(
    ...row.alerts.map((a) =>
      element(
        "div",
        a.level + " · " + a.message,
        "flag" + (a.level === "RED" ? " red" : ""),
      ),
    ),
  );
  $("notes").textContent = row.notes
    .map((n) => n.marker + " (" + n.field + ") " + n.text)
    .join("\n");
  $("refs").replaceChildren();
  for (const ref of [...row.links, ...row.reference]) {
    $("refs").append(element("pre", JSON.stringify(ref, null, 2)));
    for (const p of ref.pages || []) {
      const b = element("button", "查看引用第 " + p + " 页");
      b.onclick = run(() => showPage(p));
      $("refs").append(b);
    }
  }
  if (!$("refs").childElementCount) $("refs").textContent = "无引用";
  $("fields").replaceChildren();
  for (const [key, title] of Object.entries(fields)) {
    if (
      row.channel !== "frequency" &&
      ["pqt", "ppt", "production"].includes(key)
    )
      continue;
    const label = element("label", title);
    const input = element(
      ["value_role", "destination"].includes(key) ? "select" : "textarea",
    );
    if (input.tagName === "SELECT") {
      for (const v of key === "value_role" ? roles : ["laboratory", "field"])
        option(input, v, v);
    }
    input.value = row[key] || "";
    input.dataset.field = key;
    label.append(input);
    $("fields").append(label);
  }
  $("coverageDecision").hidden = row.channel !== "coverage";
  $("emptyPage").checked = false;
  $("note").value = "";
  $("checked").checked = false;
  $("question").value =
    row.question || (row.clarification_suggestions || []).join("\n");
  $("respondent").value = row.respondent || "";
  $("audit").replaceChildren();
  const primary = (row.bindings.item || row.bindings.requirement || [])[0];
  await showPage(
    primary ? Number(primary.split(".")[0]) : row.source_pages[0] || 1,
  );
  if ($("auditPanel").open) await showAudit();
}
async function showPage(target) {
  if (!current) return;
  const n = Math.min(pageCount, Math.max(1, Number(target) || 1)),
    epoch = ++pageEpoch;
  const params = { id: current.id, page: n };
  const key = current.id + "/" + n;
  pageNumber = n;
  $("page").value = n;
  $("prev").disabled = n === 1;
  $("next").disabled = n === pageCount;
  if (displayedPage === key) {
    highlight();
    return;
  }
  displayedPage = "";
  pageData = null;
  highlight();
  $("original").style.visibility = "hidden";
  $("carrier").textContent = "正在载入原页…";
  for (const k of ["confirm", "edit", "checked", "addrow"])
    $(k).disabled = true;
  const data = await request("/api/page", { params });
  if (epoch !== pageEpoch) return;
  $("original").src = "/api/image?" + new URLSearchParams(params);
  await $("original")
    .decode()
    .catch(() => {
      if (epoch === pageEpoch)
        throw new Error("原页图像载入失败，请重新选择该页。");
    });
  if (epoch !== pageEpoch) return;
  pageData = data;
  displayedPage = key;
  $("original").style.visibility = "";
  for (const k of ["confirm", "edit", "checked", "addrow"])
    $(k).disabled = false;
  $("carrier").textContent = {
    native: "原生文本",
    scan: "扫描图像",
    mixed: "混合页",
  }[data.carrier];
  picking = false;
  $("surface").classList.remove("selecting");
  highlight();
}
function rectangle(box) {
  const rect = element("i");
  const [x, y, x2, y2] = box;
  Object.assign(rect.style, {
    left: x * 100 + "%",
    top: y * 100 + "%",
    width: (x2 - x) * 100 + "%",
    height: (y2 - y) * 100 + "%",
  });
  return rect;
}
function highlight() {
  const ids = new Set([
    ...(selected?.evidence || []),
    ...(selected?.links || []).flatMap((l) => l.evidence || []),
  ]);
  $("boxes").replaceChildren(
    ...(pageData?.fragments || [])
      .filter((f) => ids.has(f.id))
      .map((f) => rectangle(f.box)),
  );
}
async function showAudit() {
  if (!selected) return;
  const rid = selected.id,
    doc = current.id;
  const data = await request("/api/audit", { params: { id: doc, rid } });
  if (selected?.id === rid && current?.id === doc)
    $("audit").replaceChildren(
      ...data.map((a) =>
        element(
          "pre",
          [a.stamp, a.user, a.action, JSON.stringify(a.detail, null, 2)].join(
            " ",
          ),
        ),
      ),
    );
}
async function decide(action) {
  if (!selected) return;
  const user = $("reviewer").value.trim();
  if (!user) {
    $("reviewer").reportValidity();
    return;
  }
  const changes = {};
  for (const el of $("fields").querySelectorAll("[data-field]")) {
    const k = el.dataset.field;
    if (el.value !== selected[k]) changes[k] = el.value;
  }
  const id = current.id,
    rid = selected.id;
  await request("/api/review", {
    body: {
      doc: id,
      rid,
      version: selected.version,
      action,
      user,
      changes,
      checked: $("checked").checked,
      no_requirements: $("emptyPage").checked,
      note: $("note").value,
      question: $("question").value,
      respondent: $("respondent").value,
    },
  });
  if ($("tqDialog").open) $("tqDialog").close();
  await load(id, rid);
  notice(rid + " 已保存。");
}
$("start").onclick = $("new").onclick = () => {
  $("importStatus").textContent = "";
  $("importDialog").showModal();
};
for (const b of document.querySelectorAll("[data-close]"))
  b.onclick = () => b.closest("dialog").close();
$("intake").onsubmit = run(async (event) => {
  event.preventDefault();
  const data = new FormData($("intake"));
  const file = data.get("pdf");
  data.delete("pdf");
  $("submitImport").disabled = true;
  $("importStatus").textContent = "正在本机逐页提取…";
  try {
    const doc = await request("/api/import", {
      params: Object.fromEntries(data),
      body: file,
    });
    $("importDialog").close();
    await documents(doc.id);
    notice("已导入，待核对 " + records.length + " 项。");
  } catch (e) {
    $("importStatus").textContent = e.message;
  } finally {
    $("submitImport").disabled = false;
  }
});
$("documents").onchange = run(() => load($("documents").value));
for (const k of ["status", "component", "scenario", "stage"])
  $(k).onchange = run(() => drawList(selected?.id));
for (const [id, mode] of [
  ["requirements", false],
  ["frequencies", true],
])
  $(id).onclick = run(() => {
    frequency = mode;
    return drawList();
  });
$("page").onchange = run(() => showPage($("page").value));
$("prev").onclick = run(() => showPage(pageNumber - 1));
$("next").onclick = run(() => showPage(pageNumber + 1));
$("zoom").onclick = () => {
  const enlarged = $("surface").style.width === "180%";
  $("surface").style.width = enlarged ? "100%" : "180%";
  $("zoom").textContent = enlarged ? "放大" : "适宽";
};
$("auditPanel").ontoggle = run(() => $("auditPanel").open && showAudit());
$("confirm").onclick = run(() => decide("confirm"));
$("edit").onclick = run(() => decide("edit"));
$("tq").onclick = () => {
  if ($("reviewer").reportValidity()) $("tqDialog").showModal();
};
$("tqForm").onsubmit = run(async (event) => {
  event.preventDefault();
  try {
    await decide("clarify");
  } catch (e) {
    $("tqDialog").close();
    throw e;
  }
});
$("export").onclick = run(async () => {
  const response = await request("/api/export", {
    body: { order: current.order_id },
    binary: true,
  });
  const url = URL.createObjectURL(await response.blob());
  const link = element("a");
  link.href = url;
  link.download =
    response.headers
      .get("Content-Disposition")
      ?.match(/filename="([^"]+)"/)?.[1] || "order-review.zip";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
  notice("已生成确认清单及实验室空白模板。");
});
const surface = $("surface");
let startPoint, draftBox;
function position(e) {
  const b = surface.getBoundingClientRect();
  return [
    Math.max(0, Math.min(1, (e.clientX - b.x) / b.width)),
    Math.max(0, Math.min(1, (e.clientY - b.y) / b.height)),
  ];
}
function selectionBox(end) {
  return [
    Math.min(startPoint[0], end[0]),
    Math.min(startPoint[1], end[1]),
    Math.max(startPoint[0], end[0]),
    Math.max(startPoint[1], end[1]),
  ];
}
$("addrow").onclick = () => {
  picking = !picking;
  surface.classList.toggle("selecting", picking);
  notice(picking ? "在左侧原页拖选证据区域。" : "");
};
surface.onpointerdown = (e) => {
  if (!picking) return;
  e.preventDefault();
  surface.setPointerCapture(e.pointerId);
  startPoint = position(e);
};
surface.onpointermove = (e) => {
  if (!picking || !startPoint) return;
  draftBox?.remove();
  draftBox = rectangle(selectionBox(position(e)));
  $("boxes").append(draftBox);
};
surface.onpointerup = (e) => {
  if (!picking || !startPoint) return;
  region = selectionBox(position(e));
  startPoint = null;
  if (region[2] - region[0] < 0.003 || region[3] - region[1] < 0.003) return;
  picking = false;
  surface.classList.remove("selecting");
  $("manualText").value = "";
  $("manualUser").value = $("reviewer").value;
  $("region").value =
    "第 " + pageNumber + " 页 · " + region.map((v) => v.toFixed(3)).join(", ");
  $("manualDialog").showModal();
};
$("manualForm").onsubmit = run(async (event) => {
  event.preventDefault();
  const added = await request("/api/manual", {
    body: {
      doc: current.id,
      page: pageNumber,
      box: region,
      text: $("manualText").value,
      user: $("manualUser").value,
    },
  });
  $("manualDialog").close();
  frequency = false;
  for (const k of ["component", "scenario", "stage", "status"]) $(k).value = "";
  await load(current.id, added.id);
  notice("已补录，待对照原页确认。");
});
run(() => documents())();
