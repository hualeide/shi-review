"""把题库/媒体/页面推到 GitHub（当网盘）。需本机 gh 已登录。"""

from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNER_REPO = "hualeide/shi-review"
SKIP = {".git", ".codegraph", ".cursor", "chatlab_extract", "__pycache__", "node_modules"}


def req(method: str, url: str, token: str, data=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "shi-review-uploader",
        "Content-Type": "application/json",
    }
    body = None if data is None else json.dumps(data).encode()
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"{e.code} {method} {url}\n{detail}") from e


def main():
    token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    api = f"https://api.github.com/repos/{OWNER_REPO}"
    paths = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(x in SKIP for x in p.parts):
            continue
        if p.stat().st_size > 90_000_000:
            continue
        paths.append(p)
    print(f"upload {len(paths)} files")

    ref = req("GET", f"{api}/git/ref/heads/main", token)
    base = req("GET", f"{api}/git/commits/{ref['object']['sha']}", token)
    blobs = []
    for i, p in enumerate(paths, 1):
        rel = p.relative_to(ROOT).as_posix()
        for attempt in range(3):
            try:
                blob = req(
                    "POST",
                    f"{api}/git/blobs",
                    token,
                    {
                        "content": base64.b64encode(p.read_bytes()).decode(),
                        "encoding": "base64",
                    },
                )
                break
            except Exception as e:
                print("retry", rel, e)
                time.sleep(2)
        else:
            raise SystemExit(f"fail {rel}")
        blobs.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        if i % 25 == 0 or i == len(paths):
            print(f"  {i}/{len(paths)}")

    tree = req(
        "POST",
        f"{api}/git/trees",
        token,
        {"base_tree": base["tree"]["sha"], "tree": blobs},
    )
    commit = req(
        "POST",
        f"{api}/git/commits",
        token,
        {
            "message": "Sync shi-review netdisk",
            "tree": tree["sha"],
            "parents": [ref["object"]["sha"]],
        },
    )
    try:
        req("PATCH", f"{api}/git/refs/heads/main", token, {"sha": commit["sha"]})
    except RuntimeError:
        # 上传期间 tip 变了就强制指过去
        req(
            "PATCH",
            f"{api}/git/refs/heads/main",
            token,
            {"sha": commit["sha"], "force": True},
        )
    print("pushed", commit["sha"])
    print("pages https://hualeide.github.io/shi-review/")


if __name__ == "__main__":
    main()
