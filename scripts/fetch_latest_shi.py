"""拉取最新 N 条史：合并转发保留为「一条聊天记录」，内含完整对话线程。"""

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


def media_from_segs(segs, prefix: str) -> list[dict]:
    media: list[dict] = []
    if not isinstance(segs, list):
        return media
    img_i = vid_i = 0
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        t = seg.get("type")
        data = seg.get("data") or {}
        if t == "image":
            img_i += 1
            url = data.get("url") or ""
            local = MEDIA_DIR / f"{prefix}_img{img_i}.jpg"
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
            local = MEDIA_DIR / f"{prefix}_vid{vid_i}.mp4"
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


def nice_name(nickname, user_id) -> str:
    raw = str(nickname or "").replace("\u3000", "").strip()
    if raw and raw != "QQ用户":
        return raw
    if user_id:
        return str(user_id)
    return raw or "未知用户"


def node_to_line(node: dict, prefix: str, depth: int = 0) -> list[dict]:
    """把一个转发节点变成聊天行；若仍是嵌套转发则展开为多行。"""
    segs = node.get("message") or []
    nested = forward_id_from_segs(segs)
    if nested and depth < 3:
        lines: list[dict] = []
        for i, child in enumerate(get_forward_nodes(nested)):
            lines.extend(node_to_line(child, f"{prefix}_n{i}", depth + 1))
        return lines

    text = text_from_segs(segs)
    if not text:
        raw = str(node.get("raw_message") or "")
        text = re.sub(r"\[CQ:.*?\]", "", raw).strip()
    media = media_from_segs(segs, prefix)
    if not text and not media:
        return []
    nick = ((node.get("sender") or {}).get("card") or (node.get("sender") or {}).get("nickname") or "")
    sender = nice_name(nick, node.get("user_id"))
    return [
        {
            "sender": sender,
            "user_id": node.get("user_id"),
            "time": node.get("time"),
            "text": text[:2000],
            "media": media,
        }
    ]


def fetch_raw_until(min_time: int | None = None, soft_limit: int = 500) -> list[dict]:
    """往更早翻页；若给定 min_time，翻到消息时间 < min_time 为止。"""
    collected: dict[int, dict] = {}
    cursor_seq = None
    pages = 0
    max_pages = 250
    while pages < max_pages and len(collected) < soft_limit:
        params: dict = {"group_id": SOURCE, "count": 10}
        if cursor_seq is not None:
            params["message_seq"] = cursor_seq
            params["reverseOrder"] = True
        try:
            r = call("get_group_msg_history", params, timeout=45)
        except Exception as e:
            print("history error", e)
            if cursor_seq is not None:
                break
            time.sleep(2)
            continue
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
        oldest_time = int(oldest.get("time") or 0)
        next_seq = int(oldest.get("message_seq") or 0)
        pages += 1
        print(
            f"page {pages}: total={len(collected)} oldest_real={oldest.get('real_seq')} "
            f"oldest_time={oldest_time}"
        )
        if next_seq == cursor_seq or len(collected) == before:
            break
        cursor_seq = next_seq
        if min_time is not None and oldest_time < min_time:
            break
        time.sleep(0.2)

    return sorted(
        collected.values(),
        key=lambda m: (int(m.get("time") or 0), int(m.get("real_seq") or 0)),
    )


def should_skip(msg: dict) -> bool:
    if int(msg.get("user_id") or 0) == SELF_QQ:
        return True
    raw = str(msg.get("raw_message") or "")
    return any(m in raw for m in SKIP_MARKERS)


def msg_to_item(msg: dict) -> dict | None:
    mid = int(msg.get("message_id") or 0)
    segs = msg.get("message") or []
    fid = forward_id_from_segs(segs)
    nick = ((msg.get("sender") or {}).get("card") or (msg.get("sender") or {}).get("nickname") or "")
    sender = nice_name(nick, msg.get("user_id"))

    if fid:
        nodes = get_forward_nodes(fid)
        print(f"  chat-record {mid}: forward {fid} -> {len(nodes)} nodes")
        thread: list[dict] = []
        for i, node in enumerate(nodes):
            thread.extend(node_to_line(node, f"rec_{mid}_{i}"))
        if not thread:
            return None
        return {
            "id": f"shi_{mid}",
            "kind": "chat_record",
            "message_id": mid,
            "real_seq": msg.get("real_seq"),
            "time": msg.get("time"),
            "user_id": msg.get("user_id"),
            "sender": sender,
            "title": f"聊天记录（{len(thread)}条）",
            "forward_id": fid,
            "thread": thread,
            "types": ["forward"],
        }

    prefix = f"shi_{mid}"
    text = text_from_segs(segs)
    if not text:
        raw = str(msg.get("raw_message") or "")
        text = re.sub(r"\[CQ:.*?\]", "", raw).strip()
    media = media_from_segs(segs, prefix)
    if not text and not media:
        return None
    types = []
    if text:
        types.append("text")
    for m in media:
        if m["type"] not in types:
            types.append(m["type"])
    return {
        "id": prefix,
        "kind": "single",
        "message_id": mid,
        "real_seq": msg.get("real_seq"),
        "time": msg.get("time"),
        "user_id": msg.get("user_id"),
        "sender": sender,
        "title": sender or "单条消息",
        "thread": [
            {
                "sender": sender,
                "user_id": msg.get("user_id"),
                "time": msg.get("time"),
                "text": text[:2000],
                "media": media,
            }
        ],
        "types": types,
    }


def day_range(day: str) -> tuple[int, int]:
    """day: YYYY-MM-DD 或 yesterday → 本地时区 [start, end) unix。"""
    import datetime as dt

    if day in ("yesterday", "昨天"):
        d = dt.date.today() - dt.timedelta(days=1)
    else:
        d = dt.date.fromisoformat(day)
    start = dt.datetime(d.year, d.month, d.day, 0, 0, 0)
    end = start + dt.timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def load_existing_items() -> list[dict]:
    if not OUT_JSON.exists():
        return []
    try:
        data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        items = data.get("items") or []
        return items if isinstance(items, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=TARGET_COUNT, help="最新 N 条（无 --day 时）")
    ap.add_argument("--day", default="", help="YYYY-MM-DD / yesterday，拉取整天并合并进题库")
    ap.add_argument("--replace", action="store_true", help="只用这次结果，不和旧题合并")
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    min_time = max_time = None
    if args.day:
        min_time, max_time = day_range(args.day)
        print(f"拉取整天 {args.day} → [{min_time}, {max_time})")
        raw = fetch_raw_until(min_time=min_time, soft_limit=2000)
        raw = [m for m in raw if min_time <= int(m.get("time") or 0) < max_time]
        print(f"当天原始消息 {len(raw)} 条")
    else:
        print("拉取源群最近历史…")
        raw = fetch_raw_until(min_time=None, soft_limit=max(120, args.count * 4))
        raw = list(reversed(raw))  # 新→旧筛
        print(f"原始 {len(raw)} 条")

    print("组装条目…")
    new_items: list[dict] = []
    source_msgs = raw if args.day else raw
    if not args.day:
        # 新→旧取 count
        picked = []
        for msg in source_msgs:
            if should_skip(msg):
                continue
            item = msg_to_item(msg)
            if not item:
                continue
            picked.append(item)
            print(
                f"[{len(picked)}] {item['id']} kind={item['kind']} "
                f"lines={len(item['thread'])} types={item['types']}"
            )
            if len(picked) >= args.count:
                break
        new_items = picked
    else:
        # 整天：旧→新排，便于审
        for msg in source_msgs:
            if should_skip(msg):
                continue
            item = msg_to_item(msg)
            if not item:
                continue
            new_items.append(item)
            print(
                f"[{len(new_items)}] {item['id']} kind={item['kind']} "
                f"lines={len(item['thread'])} types={item['types']}"
            )

    if args.replace or not args.day:
        items = new_items
    else:
        existing = load_existing_items()
        by_id = {it.get("id"): it for it in existing if it.get("id")}
        added = 0
        for it in new_items:
            if it["id"] not in by_id:
                by_id[it["id"]] = it
                added += 1
            else:
                by_id[it["id"]] = it  # 用新方法覆盖
        items = sorted(
            by_id.values(),
            key=lambda m: (int(m.get("time") or 0), int(m.get("message_id") or 0)),
            reverse=True,
        )
        print(f"合并：新增/覆盖 {len(new_items)}，其中新 id {added}，合计 {len(items)}")

    for i, it in enumerate(items, start=1):
        it["index"] = i

    payload = {
        "source_group": str(SOURCE),
        "generated_at": int(time.time()),
        "count": len(items),
        "day": args.day or None,
        "note": "纯图文平铺；合并转发=聊天记录视图",
        "items": items,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {OUT_JSON} 共 {len(items)} 条")


if __name__ == "__main__":
    main()
