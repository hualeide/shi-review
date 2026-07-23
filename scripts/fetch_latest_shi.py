"""从源群拉取最新 N 条可审「史」，落盘为 data/items.json + media/。"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MEDIA_DIR = ROOT / "media"
OUT_JSON = DATA_DIR / "items.json"

NAPCAT = "http://127.0.0.1:6200"
SOURCE = 1087805702
SELF_QQ = 1506172300
SKIP_MARKERS = ("搬史测试", "pipeline-test", "banshi-fwd-", "ping3 ", "ping2 ")
ALLOWED = {"text", "image", "video", "forward"}
TARGET_COUNT = 30


def call(action: str, params: dict | None = None, timeout: int = 60) -> dict:
    body = json.dumps(params or {}).encode()
    req = urllib.request.Request(
        f"{NAPCAT.rstrip('/')}/{action}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def seg_types(message) -> set[str]:
    found: set[str] = set()
    if isinstance(message, list):
        for seg in message:
            if not isinstance(seg, dict):
                continue
            t = seg.get("type", "")
            if t == "image":
                found.add("image")
            elif t == "video":
                found.add("video")
            elif t in ("forward", "node"):
                found.add("forward")
            elif t == "text":
                text = str((seg.get("data") or {}).get("text") or "").strip()
                if text:
                    found.add("text")
            elif t in ("face", "at", "reply"):
                found.add("text")
    elif isinstance(message, str):
        if "[CQ:image" in message:
            found.add("image")
        if "[CQ:video" in message:
            found.add("video")
        if "[CQ:forward" in message or "[CQ:node" in message:
            found.add("forward")
        if re.sub(r"\[CQ:.*?\]", "", message).strip():
            found.add("text")
    return found


def is_allowed(message) -> bool:
    found = seg_types(message)
    for t in ("image", "video", "forward"):
        if t in found and t not in ALLOWED:
            return False
    return bool(found.intersection(ALLOWED))


def should_skip(msg: dict) -> str | None:
    if int(msg.get("user_id") or 0) == SELF_QQ:
        return "self"
    raw = str(msg.get("raw_message") or "")
    for m in SKIP_MARKERS:
        if m in raw:
            return "noise"
    if not is_allowed(msg.get("message")):
        return "type"
    return None


def fetch_recent(limit: int = 80) -> list[dict]:
    collected: dict[int, dict] = {}
    cursor_seq = None
    pages = 0
    while len(collected) < limit and pages < 40:
        params: dict = {"group_id": SOURCE, "count": 10}
        if cursor_seq is not None:
            params["message_seq"] = cursor_seq
            params["reverseOrder"] = True
        try:
            r = call("get_group_msg_history", params, timeout=45)
        except Exception as e:
            print("history error", e)
            break
        batch = (r.get("data") or {}).get("messages") or []
        if not batch:
            break
        before = len(collected)
        for msg in batch:
            mid = int(msg.get("message_id") or 0)
            if mid:
                collected[mid] = msg

        def sort_key(m):
            try:
                return int(m.get("real_seq") or 0)
            except (TypeError, ValueError):
                return int(m.get("time") or 0)

        oldest = min(batch, key=sort_key)
        next_seq = int(oldest.get("message_seq") or 0)
        pages += 1
        print(f"page {pages}: total={len(collected)} oldest_real={oldest.get('real_seq')}")
        if next_seq == cursor_seq or len(collected) == before:
            break
        cursor_seq = next_seq
        time.sleep(0.2)

    msgs = sorted(
        collected.values(),
        key=lambda m: (int(m.get("time") or 0), int(m.get("real_seq") or 0)),
    )
    return msgs


def download(url: str, dest: Path) -> bool:
    if not url or not url.startswith("http"):
        return False
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://web.q.qq.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest.stat().st_size > 0
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"  download fail {dest.name}: {e}")
        return False


def extract_media(msg: dict, item_id: str) -> list[dict]:
    media: list[dict] = []
    segs = msg.get("message") or []
    if not isinstance(segs, list):
        return media
    img_i = 0
    vid_i = 0
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        t = seg.get("type")
        data = seg.get("data") or {}
        if t == "image":
            img_i += 1
            url = data.get("url") or data.get("file") or ""
            ext = ".jpg"
            local = MEDIA_DIR / f"{item_id}_img{img_i}{ext}"
            ok = download(str(url), local) if str(url).startswith("http") else False
            media.append(
                {
                    "type": "image",
                    "url": url if str(url).startswith("http") else "",
                    "local": f"media/{local.name}" if ok else "",
                }
            )
        elif t == "video":
            vid_i += 1
            url = data.get("url") or data.get("file") or ""
            local = MEDIA_DIR / f"{item_id}_vid{vid_i}.mp4"
            ok = download(str(url), local) if str(url).startswith("http") else False
            media.append(
                {
                    "type": "video",
                    "url": url if str(url).startswith("http") else "",
                    "local": f"media/{local.name}" if ok else "",
                    "file": data.get("file") or "",
                }
            )
        elif t in ("forward", "node"):
            media.append({"type": "forward", "id": data.get("id") or data.get("content") or ""})
    return media


def text_of(msg: dict) -> str:
    parts: list[str] = []
    segs = msg.get("message") or []
    if isinstance(segs, list):
        for seg in segs:
            if isinstance(seg, dict) and seg.get("type") == "text":
                parts.append(str((seg.get("data") or {}).get("text") or ""))
    raw = str(msg.get("raw_message") or "")
    cleaned = re.sub(r"\[CQ:.*?\]", "", raw).strip()
    text = "".join(parts).strip() or cleaned
    return text[:2000]


def expand_forward_summary(msg: dict) -> str:
    segs = msg.get("message") or []
    fid = None
    if isinstance(segs, list):
        for seg in segs:
            if isinstance(seg, dict) and seg.get("type") in ("forward", "node"):
                fid = (seg.get("data") or {}).get("id")
                break
    if not fid:
        return ""
    try:
        r = call("get_forward_msg", {"message_id": fid}, timeout=30)
    except Exception:
        try:
            r = call("get_forward_msg", {"id": fid}, timeout=30)
        except Exception as e:
            return f"(合并转发无法展开: {e})"
    nodes = (r.get("data") or {}).get("messages") or (r.get("data") or {}).get("message") or []
    lines = []
    for i, node in enumerate(nodes[:8]):
        if not isinstance(node, dict):
            continue
        sender = ((node.get("sender") or {}).get("nickname")) or node.get("user_id") or "?"
        content = node.get("message") or node.get("content") or []
        snippet = ""
        if isinstance(content, list):
            for seg in content:
                if isinstance(seg, dict) and seg.get("type") == "text":
                    snippet += str((seg.get("data") or {}).get("text") or "")
                elif isinstance(seg, dict) and seg.get("type") == "image":
                    snippet += "[图片]"
                elif isinstance(seg, dict) and seg.get("type") == "video":
                    snippet += "[视频]"
        elif isinstance(content, str):
            snippet = content
        lines.append(f"{i+1}. {sender}: {snippet[:80]}")
    if len(nodes) > 8:
        lines.append(f"…共 {len(nodes)} 条")
    return "\n".join(lines)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    print("拉取源群历史…")
    raw = fetch_recent(100)
    print(f"原始 {len(raw)} 条，筛选中…")

    candidates = []
    for msg in reversed(raw):  # 新→旧筛
        reason = should_skip(msg)
        if reason:
            continue
        candidates.append(msg)
        if len(candidates) >= TARGET_COUNT:
            break

    # 审核页按旧→新或新→旧？「最新30条」一般先审最新，队列新→旧
    items = []
    for idx, msg in enumerate(candidates, start=1):
        mid = int(msg.get("message_id") or 0)
        item_id = f"shi_{mid}"
        types = sorted(seg_types(msg.get("message")))
        text = text_of(msg)
        media = extract_media(msg, item_id)
        forward_summary = ""
        if "forward" in types:
            forward_summary = expand_forward_summary(msg)
        item = {
            "id": item_id,
            "index": idx,
            "message_id": mid,
            "real_seq": msg.get("real_seq"),
            "time": msg.get("time"),
            "user_id": msg.get("user_id"),
            "sender": ((msg.get("sender") or {}).get("nickname")) or str(msg.get("user_id") or ""),
            "types": types,
            "text": text,
            "media": media,
            "forward_summary": forward_summary,
            "raw_preview": str(msg.get("raw_message") or "")[:300],
        }
        items.append(item)
        print(f"[{idx}/{len(candidates)}] {item_id} types={types} media={len(media)}")

    payload = {
        "source_group": str(SOURCE),
        "generated_at": int(time.time()),
        "count": len(items),
        "items": items,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {OUT_JSON} 共 {len(items)} 条")


if __name__ == "__main__":
    main()
