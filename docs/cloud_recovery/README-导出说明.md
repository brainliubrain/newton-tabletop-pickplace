# Devin 会话导出说明

导出自 Devin 会话「优化光轮智能面试项目」(2026-11-11,因 out_of_quota 暂停)。

## 文件清单

| 文件/目录 | 内容 |
|---|---|
| `devin-session-full.md` | **完整会话记录**(207 个事件全部渲染):用户消息、Devin 消息、全部 53 条 shell 操作(含命令+完整输出+退出码+耗时)、32 次文件编辑、todo 变更、暂停原因 |
| `session-328cdf-events.json` | 原始事件 JSON(549KB,从 Devin Web 应用的内存状态提取) |
| `session-meta.json` | 会话元数据(标题、状态、创建者等) |
| `files/` | **18 个被编辑文件的最终版快照**(按真实文件名归档,`_index.txt` 是 原路径→文件 映射)。包括 bench.py、physics_probe.py、rsi_loop.py、asset_audit.py、STATE.md、PROBLEMS.md、results/*.json 等 |
| `editor-*.txt` | 全部 58 个编辑器快照原始文件(每次打开/编辑文件时的完整内容) |
| `editor-files-manifest.json` | 快照与 S3 key 的对应清单 |
| `HANDOFF-for-new-session.md` | **给新 Devin 账号会话的交接提示词**,直接粘贴使用 |
| `to_markdown.py` | 事件 JSON → Markdown 的转换脚本(可重复使用) |
| `analyze.py` / `sample.py` / `probe2.py` | 数据结构分析脚本 |

## 重要提醒

1. **未推送的代码只存在于本导出中**:上个会话以 `git clone` 方式工作,改动没有 push(最终 PR 未开出)。`files/` 里的快照是这些工作成果的唯一副本(Devin VM 会在一段时间后回收)。
2. `files/` 中有两个不同路径的 bench.py / env.py / run_task.py(`~` 与 `/home/ubuntu` 前缀是同一台机器的两种写法,内容可能有先后版本,以时间戳新的为准,对照 `devin-session-full.md` 里的时间线)。
3. `devin-session-full.md` 中 shell 输出用了折叠块(`<details>`),在支持 HTML 的 Markdown 查看器(如 VS Code 预览、GitHub)里点击展开。

## 复现导出方法(下次额度用完前可自救)

本次导出的技术路径(供以后参考):

1. 浏览器登录 app.devin.ai 打开会话页
2. 会话数据存在 Web 应用的 React 内存里,从虚拟列表的 React fiber 上找到 `props.value.progress.inputs` 数组(全部事件)提取
3. 文件快照通过 `POST /api/presigned-url/batch/devin-{id}`(body: `{"s3_key_list": [...]}`,key 从事件的 `contents_key` 字段收集)换取 S3 预签名 URL 后下载
4. API 请求需要带头:`Authorization: Bearer <token>`(token 可从页面自身的请求头抓取)、`x-cog-org-id` 等
