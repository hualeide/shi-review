# 史审核（一条一条打分）

源群最新 30 条「史」→ 打开网页 → **打 1–5 分自动下一条**。

## 打开

GitHub Pages 部署后访问仓库 Pages 地址。本地预览：

```bash
cd shi-review
python -m http.server 8765
```

浏览器打开 http://127.0.0.1:8765

## 操作

- 点 **1–5** 打分（键盘也可）
- **跳过** / ← 上一条
- **导出打分 JSON**（本机记录，发给汇总的人）

## 更新条目

需本机 NapCat HTTP `6200`：

```bash
python scripts/fetch_latest_shi.py
```

然后重新提交 `data/` 与 `media/`。
