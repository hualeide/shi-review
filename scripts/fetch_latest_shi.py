"""从源群拉取最新史，合并转发拆成单条可审条目，落盘 data/items.json + media/。"""

from __future__ import annotations

import json
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


def download(url: str, dest: Path) -> bool:
    if not url or not str(url).startswith("http"):
        return False
    try:
        req = urllib.request.Request(
            str(url),
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://web.q.qq.com/"},
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read()
        if not data:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"  dl fail {dest.name}: {e}")
        return False


def text_from_segs(segs) -> str:
    parts: list[str] = []
    if isinstance(segs, list):
        for seg in segs:
            if isinstance(seg, dict) and seg.get("type") == "text":
                parts.append(str((seg.get("data") or {}).get("text") or ""))
    return "".join(parts).strip()


def forward_id_from_segs(segs) -> str | None:
    if not isinstance(segs, list):
        return None
    for seg in segs:
        if isinstance(seg, dict) and seg.get("type") in ("forward", "node"):
            data = seg.get("data") or {}
            fid = data.get("id") or data.get("content")
            if fid:
                return str(fid)
    return None


def extract_media_from_segs(segs, item_id: str) -> list[dict]:
    media: list[dict] = []
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
            url = data.get("url") or ""
            local = MEDIA_DIR / f"{item_id}_img{img_i}.jpg"
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
            url = data.get("url") or ""
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
    return media


def get_forward_nodes(fid: str) -> list[dict]:
    for params in ({"message_id": fid}, {"id": fid}):
        try:
            r = call("get_forward_msg", params, timeout=45)
        except Exception as e:
            print(f"  get_forward_msg fail {params}: {e}")
            continue
        if r.get("status") != "ok":
            continue
        nodes = (r.get("data") or {}).get("messages") or []
        if isinstance(nodes, list) and nodes:
            return nodes
    return []


def fetch_recent_raw(limit: int = 80) -> list[dict]:
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
        time.sleep(0.15)

    return sorted(
        collected.values(),
        key=lambda m: (int(m.get("time") or 0), int(m.get("real_seq") or 0)),
    )


def should_skip_top(msg: dict) -> bool:
    if int(msg.get("user_id") or 0) == SELF_QQ:
        return True
    raw = str(msg.get("raw_message") or "")
    return any(m in raw for m in SKIP_MARKERS)


def node_to_item(node: dict, item_id: str, parent: dict | None = None) -> dict | None:
    segs = node.get("message") or []
    # 若节点本身还是合并转发，继续拆
    nested_fid = forward_id_from_segs(segs)
    if nested_fid:
        return None  # 由调用方展开

    text = text_from_segs(segs)
    if not text:
        raw = str(node.get("raw_message") or "")
        text = re.sub(r"\[CQ:.*?\]", "", raw).strip()

    media = extract_media_from_segs(segs, item_id)
    types: list[str] = []
    if text:
        types.append("text")
    for m in media:
        if m["type"] not in types:
            types.append(m["type"])

    if not types:
        return None

    sender = ((node.get("sender") or {}).get("nickname")) or str(node.get("user_id") or "")
    return {
        "id": item_id,
        "message_id": int(node.get("message_id") or 0),
        "real_seq": node.get("real_seq"),
        "time": node.get("time"),
        "user_id": node.get("user_id"),
        "sender": sender,
        "types": types,
        "text": text[:2000],
        "media": media,
        "from_forward": (parent or {}).get("message_id"),
        "parent_sender": ((parent or {}).get("sender") or {}).get("nickname")
        if parent
        else None,
    }


def expand_message(msg: dict, depth: int = 0) -> list[dict]:
    """把一条群消息展开成可审叶子条目（合并转发拆开）。"""
    if depth > 4:
        return []
    segs = msg.get("message") or []
    fid = forward_id_from_segs(segs)
    out: list[dict] = []
    if fid:
        nodes = get_forward_nodes(fid)
        print(f"  expand forward {fid}: {len(nodes)} nodes")
        for i, node in enumerate(nodes):
            nested = forward_id_from_segs(node.get("message") or [])
            if nested:
                # 伪造成一条消息再递归
                fake = {
                    "message_id": node.get("message_id"),
                    "message": node.get("message"),
                    "sender": node.get("sender"),
                    "user_id": node.get("user_id"),
                    "time": node.get("time"),
                    "real_seq": node.get("real_seq"),
                    "raw_message": node.get("raw_message"),
                }
                out.extend(expand_message(fake, depth + 1))
                continue
            mid = int(node.get("message_id") or 0) or i
            item_id = f"fwd_{fid}_{mid}"
            item = node_to_item(node, item_id, parent=msg)
            if item:
                out.append(item)
        return out

    mid = int(msg.get("message_id") or 0)
    item = node_to_item(msg, f"shi_{mid}", parent=None)
    return [item] if item else []


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    print("拉取源群历史…")
    raw = fetch_recent_raw(120)
    print(f"原始 {len(raw)} 条，拆包提取中…")

    items: list[dict] = []
    seen: set[str] = set()

    for msg in reversed(raw):  # 新→旧
        if should_skip_top(msg):
            continue
        leaves = expand_message(msg)
        for leaf in leaves:
            if not leaf or leaf["id"] in seen:
                continue
            # 跳过纯空
            if not leaf.get("text") and not leaf.get("media"):
                continue
            seen.add(leaf["id"])
            items.append(leaf)
            print(
                f"[{len(items)}] {leaf['id']} types={leaf['types']} "
                f"media={len(leaf['media'])} text={str(leaf.get('text') or '')[:40]!r}"
            )
            if len(items) >= TARGET_COUNT:
                break
        if len(items) >= TARGET_COUNT:
            break

    for i, it in enumerate(items, start=1):
        it["index"] = i

    payload = {
        "source_group": str(SOURCE),
        "generated_at": int(time.time()),
        "count": len(items),
        "note": "合并转发已拆成单条；每条单独打分",
        "items": items,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {OUT_JSON} 共 {len(items)} 条")


if __name__ == "__main__":
    main()
