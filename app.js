const STORAGE_KEY = "shi-review-scores-v1";

const stage = document.getElementById("stage");
const meta = document.getElementById("meta");
const scoreBar = document.getElementById("scoreBar");
const foot = document.getElementById("foot");

let items = [];
let cursor = 0;
let scores = loadScores();

function loadScores() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveScores() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(scores));
}

function mediaSrc(m) {
  if (m.local) return m.local;
  if (m.url) return m.url;
  return "";
}

function renderItem(item) {
  const tags = (item.types || []).map((t) => `<span class="tag">${t}</span>`).join("");
  const when = item.time
    ? new Date(Number(item.time) * 1000).toLocaleString("zh-CN")
    : "";
  const mediaHtml = (item.media || [])
    .map((m) => {
      const src = mediaSrc(m);
      if (m.type === "image") {
        if (!src) return `<p class="loading">[图片加载失败]</p>`;
        return `<img src="${src}" alt="" loading="lazy" />`;
      }
      if (m.type === "video") {
        if (!src) return `<p class="loading">[视频暂无本地文件：${m.file || ""}]</p>`;
        return `<video src="${src}" controls playsinline></video>`;
      }
      if (m.type === "forward") {
        return "";
      }
      return "";
    })
    .join("");

  const forward =
    item.forward_summary
      ? `<div class="forward-box">${escapeHtml(item.forward_summary)}</div>`
      : "";

  const prev = scores[item.id];
  const prevLine = prev
    ? `<div class="current-score">已打：${prev.score}${prev.skip ? "（跳过）" : ""}</div>`
    : "";

  stage.innerHTML = `
    <div class="item-head">
      <span><strong>${item.index}</strong> / ${items.length} · ${escapeHtml(item.sender || "")}</span>
      <span>${escapeHtml(when)}</span>
    </div>
    <div class="tags">${tags || '<span class="tag">unknown</span>'}</div>
    ${item.text ? `<p class="body-text">${escapeHtml(item.text)}</p>` : ""}
    <div class="media">${mediaHtml}</div>
    ${forward}
    ${prevLine}
  `;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function updateMeta() {
  const done = Object.keys(scores).length;
  meta.textContent = `${cursor + 1}/${items.length} · 已评 ${done}`;
}

function showDone() {
  scoreBar.hidden = true;
  const vals = Object.values(scores).filter((x) => !x.skip).map((x) => x.score);
  const avg = vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2) : "-";
  stage.innerHTML = `
    <div class="done">
      <p><strong>本轮审完</strong></p>
      <p>共 ${items.length} 条，已记录 ${Object.keys(scores).length} 条，均分 ${avg}</p>
      <p>点下方「导出打分 JSON」发给汇总的人。</p>
    </div>
  `;
  meta.textContent = `完成 · 已评 ${Object.keys(scores).length}`;
  foot.hidden = false;
}

function go(to) {
  if (!items.length) return;
  if (to >= items.length) {
    cursor = items.length;
    showDone();
    return;
  }
  if (to < 0) to = 0;
  cursor = to;
  renderItem(items[cursor]);
  updateMeta();
  scoreBar.hidden = false;
  foot.hidden = false;
}

function rate(score, skip = false) {
  const item = items[cursor];
  if (!item) return;
  scores[item.id] = {
    id: item.id,
    message_id: item.message_id,
    score: skip ? 0 : score,
    skip: !!skip,
    at: Date.now(),
  };
  saveScores();
  go(cursor + 1);
}

document.getElementById("scores").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-score]");
  if (!btn) return;
  rate(Number(btn.dataset.score));
});

document.getElementById("btnSkip").addEventListener("click", () => rate(0, true));
document.getElementById("btnBack").addEventListener("click", () => go(cursor - 1));

document.getElementById("btnExport").addEventListener("click", () => {
  const payload = {
    exported_at: new Date().toISOString(),
    reviewer: localStorage.getItem("shi-reviewer-name") || "anonymous",
    scores,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `shi-scores-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
});

document.getElementById("btnReset").addEventListener("click", () => {
  if (!confirm("清空本机打分记录？")) return;
  scores = {};
  saveScores();
  go(0);
});

window.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea")) return;
  if (e.key >= "1" && e.key <= "5") rate(Number(e.key));
  if (e.key === "ArrowRight" || e.key === "s") rate(0, true);
  if (e.key === "ArrowLeft") go(cursor - 1);
});

async function boot() {
  const res = await fetch("data/items.json", { cache: "no-store" });
  if (!res.ok) throw new Error("无法加载 data/items.json");
  const data = await res.json();
  items = data.items || [];
  if (!items.length) {
    stage.innerHTML = `<p class="loading">没有条目。先跑 scripts/fetch_latest_shi.py</p>`;
    return;
  }
  // 从第一条未打分处开始
  let start = items.findIndex((it) => !scores[it.id]);
  if (start < 0) start = items.length;
  go(start);
}

boot().catch((err) => {
  stage.innerHTML = `<p class="loading">加载失败：${escapeHtml(err.message)}</p>`;
});
