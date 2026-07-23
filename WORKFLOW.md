# 史审核工作流（GitHub 当网盘）

仓库：https://github.com/hualeide/shi-review  
预览：https://hualeide.github.io/shi-review/

## 一句话

源群史 → 本机脚本拆好放进仓库 → GitHub Pages 纯看/轻打分 → 需要时一键推到三人群。

## 日常三步

```powershell
cd C:\Users\LENOVO\projects\shi-review

# 1) 拉某天史进题库（例：昨天）
python scripts\fetch_latest_shi.py --day yesterday

# 1b) 昨天之前、记录为主（合并转发）
python scripts\fetch_latest_shi.py --before yesterday --records-only --records-first

# 2) 嵌套转发补全图（可选）
python scripts\repair_forwards.py

# 3) 上传到 GitHub（网盘）
python scripts\upload_github.py
```

打开 Pages 就能看。打分在后台悄悄传，不挡翻页。

## 推到三人群

```powershell
# 先看会转哪些
python scripts\push_items_to_group.py --dry-run

# 真转（默认 529383950，去重）
python scripts\push_items_to_group.py --cooldown 2
```

## 目录

| 路径 | 作用 |
|------|------|
| `data/items.json` | 题库（网盘主文件） |
| `media/` | 图片视频 |
| `scripts/fetch_latest_shi.py` | 拉史+拆包 |
| `scripts/repair_forwards.py` | 嵌套转发补图 |
| `scripts/push_items_to_group.py` | 推小群 |
| `scripts/upload_github.py` | 整仓推 GitHub |

## 需要本机开着

- NapCat HTTP `6200`
- 要推群时 QQ 已登录
