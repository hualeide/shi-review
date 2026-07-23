# 史审核

合并转发会拆成单条（图/文/视频），一次一条打分，自动回收。

- 审核页: https://hualeide.github.io/shi-review/
- 汇总页: https://hualeide.github.io/shi-review/scores.html

打分 → ntfy → GitHub Action 写入 `data/scores.json`（也可在汇总页实时看）。
