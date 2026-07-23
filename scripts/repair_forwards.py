"""重展开题库里所有合并转发（含嵌套 content 兜底）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_latest_shi import (  # noqa: E402
    OUT_JSON,
    get_forward_nodes,
    node_to_line,
)


def main():
    data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    items = data.get("items") or []
    fixed = 0
    for it in items:
        fid = it.get("forward_id")
        if not fid and it.get("kind") != "chat_record":
            continue
        if not fid:
            continue
        before = len(it.get("thread") or [])
        nodes = get_forward_nodes(str(fid))
        thread = []
        mid = it.get("message_id") or 0
        for i, node in enumerate(nodes):
            thread.extend(node_to_line(node, f"rec_{mid}_{i}"))
        if not thread:
            print(f"skip empty {it.get('id')}")
            continue
        it["thread"] = thread
        if len(thread) == 1:
            it["kind"] = "single"
            it["title"] = it.get("sender") or "单条消息"
            line = thread[0]
            types = []
            if line.get("text"):
                types.append("text")
            for m in line.get("media") or []:
                if m["type"] not in types:
                    types.append(m["type"])
            it["types"] = types or ["text"]
        else:
            it["kind"] = "chat_record"
            it["title"] = f"聊天记录（{len(thread)}条）"
            it["types"] = ["forward"]
        print(f"{it['id']}: {before} -> {len(thread)} kind={it['kind']}")
        fixed += 1

    for i, it in enumerate(items, start=1):
        it["index"] = i
    data["items"] = items
    data["count"] = len(items)
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"repaired {fixed}, total {len(items)}")


if __name__ == "__main__":
    main()
