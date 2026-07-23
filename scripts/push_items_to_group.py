"""把 data/items.json 里的史按顺序转到小群（默认三人群）。

用法:
  python scripts/push_items_to_group.py
  python scripts/push_items_to_group.py --target 529383950 --cooldown 2
  python scripts/push_items_to_group.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "data" / "items.json"
NAPCAT = "http://127.0.0.1:6200"
DEFAULT_TARGET = "529383950"
DEDUP_PATH = os.path.expanduser(
    r"~\.astrbot_launcher\instances\d9632eed-9534-4548-9559-42588b5e9a3d"
    r"\core\data\sowing_discord_cache\dedup_hashes.json"
)


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


def load_dedup(path: str) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_dedup(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--cooldown", type=float, default=2.0)
    ap.add_argument("--dedup", default=DEDUP_PATH)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-dedup", action="store_true")
    args = ap.parse_args()

    data = json.loads(ITEMS.read_text(encoding="utf-8"))
    items = data.get("items") or []
    # 旧→新发，像补历史
    items = sorted(items, key=lambda x: (int(x.get("time") or 0), int(x.get("message_id") or 0)))
    print(f"题库 {len(items)} 条 → 群 {args.target}")

    dedup = {} if args.no_dedup else load_dedup(args.dedup)
    stats = {"ok": 0, "dedup": 0, "fail": 0, "skip": 0}

    for i, it in enumerate(items, 1):
        mid = int(it.get("message_id") or 0)
        if not mid:
            stats["skip"] += 1
            continue
        idk = f"id:{mid}"
        if not args.no_dedup and idk in dedup:
            stats["dedup"] += 1
            print(f"[{i}/{len(items)}] skip dedup {mid} {it.get('id')}")
            continue
        if args.dry_run:
            print(f"[{i}/{len(items)}] dry {mid} {it.get('kind')} {it.get('title') or it.get('id')}")
            stats["ok"] += 1
            continue
        try:
            r = call(
                "forward_group_single_msg",
                {"group_id": int(args.target), "message_id": mid},
            )
            if r.get("status") != "ok":
                stats["fail"] += 1
                print(f"[{i}/{len(items)}] fail {mid} {r.get('message') or r}")
            else:
                stats["ok"] += 1
                dedup[idk] = time.time()
                save_dedup(args.dedup, dedup)
                print(f"[{i}/{len(items)}] ok {mid} {it.get('kind')}")
        except Exception as e:
            stats["fail"] += 1
            print(f"[{i}/{len(items)}] err {mid} {e}")
        time.sleep(args.cooldown)

    print("完成", stats)


if __name__ == "__main__":
    main()
