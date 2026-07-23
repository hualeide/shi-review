const STORAGE_KEY = "shi-review-scores-v2";
const REVIEWER_KEY = "shi-reviewer-name";

const stage = document.getElementById("stage");
const meta = document.getElementById("meta");
const scoreBar = document.getElementById("scoreBar");
const foot = document.getElementById("foot");
const syncStatus = document.getElementById("syncStatus");

let items = [];
let cursor = 0;
let scores = loadScores();
let reviewer = localStorage.getItem(REVIEWER_KEY) || "";

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

function ensureReviewer() {
  if (reviewer) return reviewer;
  const name = prompt("你的昵称（打分会记在你名下）:", "") || "anonymous";
  reviewer = String(name).trim() || "anonymous";
  localStorage.setItem(REVIEWER_KEY, reviewer);
  return reviewer;
}

function mediaSrc(m) {
  return m.local || m.url || "";
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/** 空白昵称 / QQ用户 时回退到 QQ 号，避免「有的显示有的空白」 */
function displayName(person) {
  const raw = String(person?.sender ?? person?.nickname ?? "").replace(/[\s\u3000]+/g, "");
  const uid = person?.user_id;
  if (raw && raw !== "QQ用户") return raw;
  if (uid) return String(uid);
  if (raw === "QQ用户") return "QQ用户";
  return "未知用户";
}

function avatarChar(name) {
  const s = String(name || "?").trim();
  return s ? s[0] : "?";
}

function fmtTime(ts) {
  if (!ts) return "";
  try {
    return new Date(Number(ts) * 1000).toLocaleString("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

let gallery = {
  open: false,
  list: [],
  index: 0,
  scale: 1,
  tx: 0,
  ty: 0,
  dragging: false,
  startX: 0,
  startY: 0,
  lastTx: 0,
  lastTy: 0,
  pinchStart: 0,
  scaleStart: 1,
};

function collectItemImages(item) {
  const list = [];
  for (const line of item?.thread || []) {
    for (const m of line.media || []) {
      if (m.type !== "image") continue;
      const src = mediaSrc(m);
      if (src) list.push(src);
    }
  }
  return list;
}

function ensureLightbox() {
  let box = document.getElementById("lightbox");
  if (box) return box;
  box = document.createElement("div");
  box.id = "lightbox";
  box.hidden = true;
  box.innerHTML = `
    <div class="lb-top">
      <span class="lb-counter" id="lbCounter"></span>
      <button type="button" class="lightbox-close" aria-label="关闭">×</button>
    </div>
    <button type="button" class="lb-nav lb-prev" aria-label="上一张">‹</button>
    <button type="button" class="lb-nav lb-next" aria-label="下一张">›</button>
    <div class="lb-stage" id="lbStage">
      <img id="lbImg" alt="" draggable="false" />
    </div>
    <div class="lb-hint">左右滑切换 · 双击/滚轮放大 · Esc 关闭</div>
  `;
  document.body.appendChild(box);

  box.querySelector(".lightbox-close").addEventListener("click", closeLightbox);
  box.querySelector(".lb-prev").addEventListener("click", (e) => {
    e.stopPropagation();
    galleryNav(-1);
  });
  box.querySelector(".lb-next").addEventListener("click", (e) => {
    e.stopPropagation();
    galleryNav(1);
  });
  box.addEventListener("click", (e) => {
    if (e.target === box || e.target.id === "lbStage") closeLightbox();
  });

  const stageEl = box.querySelector("#lbStage");
  const img = box.querySelector("#lbImg");

  img.addEventListener("click", (e) => e.stopPropagation());
  img.addEventListener("dblclick", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (gallery.scale > 1.05) resetZoom();
    else setZoom(2.5, e.clientX, e.clientY);
  });

  // wheel zoom
  stageEl.addEventListener(
    "wheel",
    (e) => {
      if (!gallery.open) return;
      e.preventDefault();
      const next = gallery.scale * (e.deltaY < 0 ? 1.12 : 1 / 1.12);
      setZoom(next, e.clientX, e.clientY);
    },
    { passive: false }
  );

  // pointer / swipe
  let pointers = new Map();
  stageEl.addEventListener("pointerdown", (e) => {
    if (!gallery.open) return;
    stageEl.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 1) {
      gallery.dragging = true;
      gallery.startX = e.clientX;
      gallery.startY = e.clientY;
      gallery.lastTx = gallery.tx;
      gallery.lastTy = gallery.ty;
    } else if (pointers.size === 2) {
      const pts = [...pointers.values()];
      gallery.pinchStart = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      gallery.scaleStart = gallery.scale;
    }
  });
  stageEl.addEventListener("pointermove", (e) => {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 2) {
      const pts = [...pointers.values()];
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      if (gallery.pinchStart > 0) {
        setZoom(gallery.scaleStart * (dist / gallery.pinchStart));
      }
      return;
    }
    if (!gallery.dragging) return;
    const dx = e.clientX - gallery.startX;
    const dy = e.clientY - gallery.startY;
    if (gallery.scale > 1.05) {
      gallery.tx = gallery.lastTx + dx;
      gallery.ty = gallery.lastTy + dy;
      applyTransform();
    }
  });
  const endPointer = (e) => {
    if (!pointers.has(e.pointerId)) return;
    const wasDrag = gallery.dragging && pointers.size === 1;
    const dx = e.clientX - gallery.startX;
    const dy = e.clientY - gallery.startY;
    pointers.delete(e.pointerId);
    if (pointers.size < 2) gallery.pinchStart = 0;
    if (pointers.size === 0) gallery.dragging = false;
    if (wasDrag && gallery.scale <= 1.05) {
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.2) {
        galleryNav(dx < 0 ? 1 : -1);
      } else if (Math.abs(dy) > 100 && Math.abs(dy) > Math.abs(dx) * 1.2 && dy > 0) {
        closeLightbox();
      }
    }
  };
  stageEl.addEventListener("pointerup", endPointer);
  stageEl.addEventListener("pointercancel", endPointer);

  document.addEventListener("keydown", (e) => {
    if (!gallery.open) return;
    if (e.key === "Escape") closeLightbox();
    if (e.key === "ArrowRight") galleryNav(1);
    if (e.key === "ArrowLeft") galleryNav(-1);
    if (e.key === "+" || e.key === "=") setZoom(gallery.scale * 1.2);
    if (e.key === "-") setZoom(gallery.scale / 1.2);
    if (e.key === "0") resetZoom();
  });
  return box;
}

function applyTransform() {
  const img = document.getElementById("lbImg");
  if (!img) return;
  img.style.transform = `translate(${gallery.tx}px, ${gallery.ty}px) scale(${gallery.scale})`;
}

function resetZoom() {
  gallery.scale = 1;
  gallery.tx = 0;
  gallery.ty = 0;
  applyTransform();
}

function setZoom(scale, clientX, clientY) {
  const next = Math.min(4, Math.max(1, scale));
  if (next === 1) {
    resetZoom();
    return;
  }
  // 简单缩放：以中心为准
  gallery.scale = next;
  applyTransform();
}

function showGalleryImage() {
  const box = ensureLightbox();
  const img = box.querySelector("#lbImg");
  const counter = box.querySelector("#lbCounter");
  const src = gallery.list[gallery.index];
  if (!src) return;
  resetZoom();
  img.src = src;
  counter.textContent = `${gallery.index + 1} / ${gallery.list.length}`;
  box.querySelector(".lb-prev").disabled = gallery.index <= 0;
  box.querySelector(".lb-next").disabled = gallery.index >= gallery.list.length - 1;
}

function galleryNav(delta) {
  const next = gallery.index + delta;
  if (next < 0 || next >= gallery.list.length) return;
  gallery.index = next;
  showGalleryImage();
}

function openLightbox(src, list) {
  const images = list && list.length ? list : src ? [src] : [];
  if (!images.length) return;
  let index = Math.max(0, images.indexOf(src));
  if (src && index < 0) {
    images.unshift(src);
    index = 0;
  }
  gallery.open = true;
  gallery.list = images;
  gallery.index = index;
  const box = ensureLightbox();
  box.hidden = false;
  document.body.style.overflow = "hidden";
  showGalleryImage();
}

function closeLightbox() {
  const box = document.getElementById("lightbox");
  if (!box) return;
  gallery.open = false;
  gallery.list = [];
  box.hidden = true;
  const img = box.querySelector("#lbImg");
  if (img) {
    img.src = "";
    img.style.transform = "";
  }
  document.body.style.overflow = "";
}

function setSync(text, ok) {
  if (!syncStatus) return;
  syncStatus.textContent = text;
  syncStatus.dataset.ok = ok ? "1" : "0";
}

async function submitScoreRemote(payload) {
  const cfg = window.SHI_SCORE || {};
  const body = JSON.stringify(payload);
  let ok = false;
  let detail = [];

  if (cfg.token && cfg.repo && cfg.issueNumber) {
    try {
      const res = await fetch(
        `https://api.github.com/repos/${cfg.repo}/issues/${cfg.issueNumber}/comments`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${cfg.token}`,
            Accept: "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
          },
          body: JSON.stringify({ body: "```json\n" + body + "\n```" }),
        }
      );
      if (res.ok) {
        ok = true;
        detail.push("GitHub");
      } else detail.push("GitHub:" + res.status);
    } catch {
      detail.push("GitHub网络失败");
    }
  }

  if (cfg.ntfyTopic) {
    try {
      const res = await fetch(`https://ntfy.sh/${cfg.ntfyTopic}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Title: "shi-score" },
        body,
      });
      if (res.ok) {
        ok = true;
        detail.push("ntfy");
      } else detail.push("ntfy:" + res.status);
    } catch {
      detail.push("ntfy失败");
    }
  }

  return { ok, detail: detail.join("+") || "无通道" };
}

function renderThreadLine(line) {
  const name = displayName(line);
  const mediaHtml = (line.media || [])
    .map((m) => {
      const src = mediaSrc(m);
      if (m.type === "image") {
        return src
          ? `<img class="zoomable" src="${src}" alt="" loading="lazy" data-full="${src}" />`
          : `<span class="hint">[图片]</span>`;
      }
      if (m.type === "video") {
        return src
          ? `<video src="${src}" controls playsinline></video>`
          : `<span class="hint">[视频]</span>`;
      }
      return "";
    })
    .join("");

  return `
    <div class="msg">
      <div class="avatar">${escapeHtml(avatarChar(name))}</div>
      <div class="msg-body">
        <div class="msg-meta">
          <span class="name">${escapeHtml(name)}</span>
          <span class="time">${escapeHtml(fmtTime(line.time))}</span>
        </div>
        ${line.text ? `<div class="bubble">${escapeHtml(line.text)}</div>` : ""}
        ${mediaHtml ? `<div class="msg-media">${mediaHtml}</div>` : ""}
      </div>
    </div>
  `;
}

function bindZoomables(root) {
  const list = collectItemImages(items[cursor]);
  root.querySelectorAll("img.zoomable").forEach((img) => {
    img.addEventListener("click", (e) => {
      e.preventDefault();
      openLightbox(img.dataset.full || img.src, list);
    });
  });
}

function renderSimpleItem(item) {
  const line = (item.thread || [])[0] || {};
  const types = item.types || [];
  const mediaHtml = (line.media || [])
    .map((m) => {
      const src = mediaSrc(m);
      if (m.type === "image") {
        return src
          ? `<img class="zoomable simple-media" src="${src}" alt="" loading="lazy" data-full="${src}" />`
          : `<p class="loading">[图片加载失败]</p>`;
      }
      if (m.type === "video") {
        return src
          ? `<video class="simple-media" src="${src}" controls playsinline></video>`
          : `<p class="loading">[视频]</p>`;
      }
      return "";
    })
    .join("");

  // 纯图/文：不套头像气泡，只平铺内容
  return `
    <div class="simple-meta">${item.index}/${items.length} · ${escapeHtml(displayName(item))} · ${escapeHtml(fmtTime(item.time))}</div>
    <div class="simple-body">
      ${line.text ? `<p class="simple-text">${escapeHtml(line.text)}</p>` : ""}
      ${mediaHtml ? `<div class="simple-media-wrap">${mediaHtml}</div>` : (!line.text ? '<p class="loading">无内容</p>' : "")}
    </div>
  `;
}

function renderChatRecord(item) {
  const thread = item.thread || [];
  return `
    <div class="chat-head">
      <div>
        <h2>${escapeHtml(item.title || "聊天记录")}</h2>
        <div class="sub">${item.index} / ${items.length} · 来自 ${escapeHtml(displayName(item))} · ${escapeHtml(fmtTime(item.time))}</div>
      </div>
      <div class="tags">
        <span class="tag">聊天记录</span>
        <span class="tag">${thread.length} 条消息</span>
      </div>
    </div>
    <div class="chat-thread" id="chatThread">
      ${thread.map(renderThreadLine).join("") || '<p class="loading">空记录</p>'}
    </div>
  `;
}

function renderItem(item) {
  const prev = scores[item.id];
  const prevLine = prev
    ? `<div class="current-score">已打：${prev.score}${prev.skip ? "（跳过）" : ""}</div>`
    : "";

  if (item.kind === "chat_record") {
    stage.innerHTML = renderChatRecord(item) + prevLine;
  } else {
    stage.innerHTML = renderSimpleItem(item) + prevLine;
  }
  bindZoomables(stage);
}

function updateMeta() {
  const done = Object.keys(scores).length;
  meta.textContent = `${cursor + 1}/${items.length} · 已评 ${done} · ${reviewer || "未命名"}`;
}

function showDone() {
  scoreBar.hidden = true;
  const vals = Object.values(scores).filter((x) => !x.skip).map((x) => x.score);
  const avg = vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2) : "-";
  stage.innerHTML = `
    <div class="done">
      <p><strong>本轮审完</strong></p>
      <p>共 ${items.length} 份聊天记录，已记录 ${Object.keys(scores).length}，均分 ${avg}</p>
      <p>打分已自动回收 · <a href="scores.html" style="color:var(--accent)">看汇总</a></p>
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

async function rate(score, skip = false) {
  const item = items[cursor];
  if (!item) return;
  ensureReviewer();
  const payload = {
    id: item.id,
    message_id: item.message_id,
    kind: item.kind,
    score: skip ? 0 : score,
    skip: !!skip,
    reviewer,
    at: Date.now(),
    title: item.title || "",
    lines: (item.thread || []).length,
  };
  scores[item.id] = payload;
  saveScores();
  setSync("提交中…", true);
  const result = await submitScoreRemote(payload);
  setSync(result.ok ? `已回收 · ${result.detail}` : `回收失败 · ${result.detail}`, result.ok);
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
    reviewer: reviewer || "anonymous",
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
  if (gallery.open) return;
  if (e.target.matches("input, textarea")) return;
  if (e.key >= "1" && e.key <= "5") rate(Number(e.key));
  if (e.key === "ArrowRight" || e.key === "s") rate(0, true);
  if (e.key === "ArrowLeft") go(cursor - 1);
});

async function boot() {
  ensureReviewer();
  const res = await fetch("data/items.json", { cache: "no-store" });
  if (!res.ok) throw new Error("无法加载 data/items.json");
  const data = await res.json();
  items = data.items || [];
  if (!items.length) {
    stage.innerHTML = `<p class="loading">没有条目。先跑 scripts/fetch_latest_shi.py</p>`;
    return;
  }
  let start = items.findIndex((it) => !scores[it.id]);
  if (start < 0) start = items.length;
  go(start);
}

boot().catch((err) => {
  stage.innerHTML = `<p class="loading">加载失败：${escapeHtml(err.message)}</p>`;
});
