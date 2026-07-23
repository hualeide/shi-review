# 史审核 · GitHub 网盘

纯看为主，打分不挡翻页。

- 预览：https://hualeide.github.io/shi-review/
- 流程：见 [WORKFLOW.md](./WORKFLOW.md)

```powershell
python scripts\fetch_latest_shi.py --day yesterday
python scripts\repair_forwards.py
python scripts\upload_github.py
python scripts\push_items_to_group.py   # 推三人群（已去重）
```
