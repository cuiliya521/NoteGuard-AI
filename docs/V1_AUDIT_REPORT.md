# AI Reviewer V1 封版审计报告

审计日期：2026-07-13

## 1. 当前真实功能清单

### 页面

- 内容工作台：默认页面，包含内容输入、审核结果、内容优化、封面优化、内容学习和审核历史。
- 规则管理：从侧边导航进入，管理 `data/rules.json` 中的审核规则。

### 内容工作台功能

- 新手体验：一键填充内置教育内容案例并进入审核状态。
- 文本审核：检测标题和正文中的规则命中项。
- 内容安全评分：按高、中、低风险项扣分，最低为 0 分。
- 风险诊断：风险等级、风险关键词、风险详情、卖点提示和高亮原文。
- AI 安全改写：优先调用 DeepSeek；调用失败时回退到本地规则替换。
- 安全版复制：复制改写标题、正文或完整安全版内容。
- 爆款标题生成：调用 DeepSeek 生成 5 个教育赛道标题候选。
- AI 生成小红书笔记：根据主题生成 3 个标题、正文、5 个标签和封面文案。
- 图片文字审核：上传图片后可手动输入图片文字并使用现有规则审核。
- 封面 AI 分析：本地 OCR 可用时提取封面文字，再调用 DeepSeek 生成封面分析；OCR 不可用时保持图片预览并给出提示。
- 爆款拆解：根据用户粘贴的标题和正文调用 DeepSeek 进行内容拆解。
- 发布前体检：结合审核风险、评分、安全版和封面分析调用 DeepSeek 生成综合建议。
- 审核历史：本地保存最近审核记录，可查看原内容、风险分析、安全版、标题结果和封面分析。

### 规则管理功能

- 展示关键词、风险等级、分类、修改建议和启用状态。
- 新增规则，阻止空关键词、空分类、空原因和重复关键词。
- 编辑规则，包括启用或停用。
- 删除规则，页面要求用户先确认。
- 每次通过管理页保存后清除规则缓存，下一次审核立即读取新规则。

## 2. 项目文件结构

```text
ai-reviewer-app/
├── app.py                         # Streamlit 页面、交互和页面路由
├── requirements.txt               # Streamlit、OpenAI SDK、dotenv
├── data/
│   ├── rules.json                 # 可配置审核规则
│   └── history.json               # 本地审核历史，运行时生成且已忽略
├── services/
│   ├── rule_checker.py            # 规则读写、校验、匹配和风险结果
│   ├── rewriter.py                # AI 改写与本地规则回退
│   ├── llm.py                     # DeepSeek API 调用与 JSON 返回解析
│   ├── image_ocr.py               # 可选 OCR 封装
│   ├── image_reviewer.py          # 手动图片文字审核
│   └── history.py                 # 本地历史读写
└── docs/
    └── V1_AUDIT_REPORT.md         # 本报告
```

## 3. 核心调用链

### 文本审核

```text
用户输入标题/正文
-> app.py: get_rules()
-> services/rule_checker.py: load_rules()
-> data/rules.json
-> services/rule_checker.py: check_text()
-> app.py: 风险评分、高亮、风险详情、历史记录
```

### AI 安全改写

```text
用户点击“一键生成安全版”
-> app.py: rewrite_all()
-> services/rewriter.py: rewrite_all()
-> services/llm.py: rewrite_content()
-> DeepSeek API (deepseek-chat)
-> 成功：AI 改写结果
-> 失败：services/rewriter.py 本地规则替换
```

### 其他 DeepSeek 功能

```text
app.py
-> services/llm.py
-> DeepSeek API (deepseek-chat)
-> 标题候选 / 笔记生成 / 封面分析 / 爆款拆解 / 发布前体检结果
```

### 图片审核与封面分析

```text
上传图片
-> app.py 图片预览
-> 手动输入图片文字
-> services/image_reviewer.py
-> services/rule_checker.py
-> data/rules.json

上传图片并点击“AI分析封面”
-> services/image_ocr.py: extract_text()（本地 OCR 可用时）
-> services/llm.py: analyze_cover()
-> DeepSeek API
```

### 审核历史

```text
审核完成
-> app.py: create_history_record() / upsert_history_record()
-> services/history.py
-> data/history.json
```

### 规则管理

```text
规则管理页面表单
-> app.py
-> services/rule_checker.py: add/update/delete_rule_record()
-> data/rules.json
-> app.py: get_rules.clear()
-> 下一次审核加载最新规则
```

## 4. Session State 状态

- 审核流程：`review_started`、`is_reviewing`、`review_run_id`、`uploader_key`。
- 安全改写：`safe_rewrite_key`、`safe_rewrite_result`。
- 标题生成：`title_generation_key`、`title_candidates`、`title_generation_error`。
- 封面分析：`cover_analysis_requested`、`cover_analysis_key`、`cover_analysis`、`cover_analysis_error`、`cover_ocr_lines`。
- 笔记生成：`note_generation_result`、`note_generation_error`。
- 爆款拆解：`viral_note_analysis`、`viral_note_analysis_error`。
- 发布前体检：`pre_publish_report_key`、`pre_publish_report`、`pre_publish_report_error`。
- 历史与规则管理：`selected_history_id`、`rule_manager_notice`。

## 5. 已通过的检查

- `python3 -m py_compile app.py services/*.py` 通过。
- 应用导入通过。
- `data/rules.json` 当前可读取，审计时共读取 57 条规则。
- 规则服务临时文件测试通过：新增规则后立即被 `check_text()` 命中；停用后不再命中；删除后记录消失。
- 重复关键词、空关键词、空分类和空原因会被规则服务拦截。
- 规则删除页面提供确认复选框。
- `history.json` 缺失时会自动创建；损坏或非数组历史文件会回退为空列表，不阻断启动。
- `rules.json` 缺失时会自动创建为空数组；空文件或损坏 JSON 时，内容审核会安全回退为空规则集，不阻断工作台启动。规则管理页会显示读取错误。
- DeepSeek API Key 从 `.env` / `DEEPSEEK_API_KEY` 获取，未写死在代码中。
- API Key 缺失、SDK 缺失、请求异常或模型返回格式异常均由 `services/llm.py` 返回失败结果，页面显示友好错误或走本地改写回退。
- 图片未上传时不会进入图片 OCR 或图片审核调用。
- 本地页面已成功启动并返回 HTTP 200。

## 6. 本次修复的问题

1. `rules.json` 为空或 JSON 格式损坏时，内容工作台原本可能在加载规则阶段中断。
   - 修复：`load_rules()` 在读取异常时返回空规则集，应用保持可打开。
2. `.gitignore` 未覆盖本地审核历史、临时 JSON 和备份文件。
   - 修复：新增 `.env.*`、缓存目录、`*.tmp`、`*.save`、`data/history.json` 和 `outputs/` 忽略规则。

## 7. 已知问题与后续建议

- OCR 为可选能力，当前 `requirements.txt` 未声明 `Pillow` 和 `pytesseract`，未安装时封面功能会保持预览和提示，不会自动识别文字。这不阻断文本审核。
- DeepSeek 的真实网络调用未在本次封版审计中执行，以避免消耗用户 API 配额；需由有有效 Key 的环境手动验证各 AI 按钮返回质量。
- 规则管理页保存后会即时清除应用规则缓存；如果直接在应用外手改 `rules.json`，需要触发一次应用重跑或重新进入页面后才会刷新缓存。
- 本地历史采用 JSON 文件，无并发锁。单人本地工具适用；多进程或多人部署时应改用数据库或带锁的存储方案。
- 终端诊断日志只输出 API Key 前 8 位和长度，不输出完整密钥。生产部署时建议关闭前缀诊断日志，进一步降低终端日志暴露面。

## 8. 后续建议（未实施）

- 为规则管理增加导入、导出和版本备份。
- 增加自动化测试目录，覆盖页面路由、规则管理表单和历史文件异常场景。
- 在生产环境引入受控日志级别和集中式安全存储。
- 评估稳定的 OCR 依赖与部署方式后，再开启自动封面文字识别。
