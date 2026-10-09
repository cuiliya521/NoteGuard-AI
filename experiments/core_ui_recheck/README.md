# NoteGuard 核心 UI · V2 真实审核适配实验

状态：代码与本地规则/HTTP验证完成；真实语义/LLM及新版浏览器验收未完成。禁止据此宣称完整接入成功。

独立分支：`experiment/core-ui-real-recheck-v1`，基于 V2 `4d3e737004db14c64cc6586480e66f1f9f7552d8`。
仅新增本实验目录。没有修改 main、正式 V2、V5、评测数据、冻结视觉母版、生产部署；未合并、未上线。

## 接入方式与复用

| 能力 | 现有实现 | 本实验接入方式 |
|---|---|---|
| 规则检测与准确字符范围 | `services.rule_checker.load_rules/check_text` + `data/rules.json` | 服务端直接调用，返回来源、字段、原始字符范围 |
| 语义审核 | `services.workflow_ai_v2.review_semantics` | 复用 V2 提示词、DeepSeek 调用及引用校验，引用多次出现时展示全部精确匹配位置 |
| 整稿建议 | `services.workflow_ai_v2.make_draft` | 复用真实 LLM 和最小删除约束；本地规则回退不会冒充 LLM 成功结果 |
| 人审确认/复检语义 | `services.workflow_v2.start_workflow/decide_workflow` | 已研究；该同步流程将检测、生成建议、采用复检绑在一次调用中。本实验拆成用户可独立触发的 HTTP 步骤，仍直接调用同一规则/语义/建议函数，前端复用已验收的人审操作与独立快照 |
| Streamlit 展示与状态 | `services.workflow_ui_v2.render_workflow_v2`，由 `app.py` 调用 | HTML 不调用 Streamlit WebSocket或生产 Demo；新增同源 Python HTTP 适配层 |

`server.py` 仅提供本机实验服务、会话、CSRF、请求限制与静态 HTML。`adapter.py` 只增加字段序列化、真实来源/版本/请求标识及失败状态，不增加风险规则、不使用 V5 评测代码。

V2 默认凭据读取器同时尝试 `.env`，本实验在独立进程中将这一读取器替换为服务端 `os.environ` 读取；审核函数/提示词/规则保持原样。API 密钥不进入网页、浏览器脚本、响应、日志或提交。

冻结 CSS 与母版逐字一致。新增交互按钮与真实结果内容继续使用原组件类，没有重新设计三栏、字体或配色。

## 启动独立本机测试环境

在仓库根目录或完整交付包根目录运行：

```sh
python3 -m pip install openai
python3 -m experiments.core_ui_recheck.server --port 8877
```

用本机浏览器打开 `http://127.0.0.1:8877/`。必须通过 HTTP 打开，直接双击 HTML 不能调用 API。
配置测试密钥时，通过本机/私有测试主机的安全服务端环境变量配置入口设置 `DEEPSEEK_API_KEY`，然后重启测试进程。不要写入 HTML、JS、仓库、聊天、shell 历史或本交付包。无密钥时仍可测试真实规则和不可用状态。

本服务仅监听回环地址，**没有公开测试部署或可远程访问地址**。不能直接将该实验 HTTP 服务器部署公网；远程测试前需私有认证、HTTPS反向代理、访问限制和成本控制。本轮没有进行部署。

## 操作流程

1. 输入原文，执行真实检测。示例只填入文本，不填入检测答案。
2. 规则与语义完整返回后生成真实 AI 整稿建议；原文和原检测保持独立。
3. 拒绝保留原文；直接采用复制整稿；修改后采用可编辑标题和正文，禁止空正文，不能丢失原文标题。
4. 最终采用稿显示版本、文本差异与待复检。点击复检仅提交此版本的实际标题和正文。
5. 请求未返回显示复检中。完整成功才显示结论；语义失败保留真实规则结果并明确部分失败，无完整结论，可重试。
6. 继续修改时立即失效旧结果；确认采用产生新版本。晚到的旧响应按请求标识、版本、内容快照和操作代次丢弃。
7. 原文、建议、最终稿和当前结果可在浏览器本地保存。刷新中断的请求恢复为可重试失败，不误显示为完成。

## 本轮实测结果

| 类别 | 结果与边界 |
|---|---|
| 适配/HTTP测试 | 17/17 通过；其中3项为明确标注的语义/故障模拟，其余包含真实规则与实际本机HTTP |
| 前端请求与状态测试 | 17/17 通过；Node VM/DOM替身/模拟HTTP，不是真实浏览器或在线 API 验收 |
| V2 workflow单元测试 | 9项通过；原测试包含模拟语义/建议，不是在线验收 |
| V2 rule_checker单元测试 | 见 `evidence/test_rule_checker.py.txt` 的原始报告 |
| 真实HTTP规则检测 | 原文2项；已验证建议文本0项；重新加入保证承诺1项；再次删除0项 |
| 真实在线语义/LLM | BLOCKED：服务端未配置密钥。没有取得新语义结论或真实 LLM 建议 |
| V2 Streamlit回归 | 未完成：环境没有 Streamlit，导入 `streamlit.testing.v1.AppTest` 失败 |
| 新版浏览器截图/刷新保存 | 未完成：Cloud Browser 无法访问本机回环服务（连接被拒绝）；没有以旧截图或生成图替代 |

真实HTTP报告中的建议文本是用户提供的已验证手工测试输入，**不是本轮 LLM 输出**。规则命中0项不等于完整检测通过。
前阶段17/17浏览器报告的验证方式是 `set_content/about:blank`，未验证HTTP来源下的真实localStorage刷新恢复；本轮不将此前通过结果套用到新版。

## 可复现检查

```sh
python3 -m unittest experiments.core_ui_recheck.test_adapter -v
node experiments/core_ui_recheck/test_client.cjs
python3 -m experiments.core_ui_recheck.online_acceptance --self-host --output online-acceptance.json
```

最后一项不使用Mock。无密钥会明确记录BLOCKED，并仅运行真实规则/语义不可用路径；配置可用密钥后才会执行真实建议生成、直接采用复检、加回承诺复检与再次修改复检。

## 尚需验收与上线风险

- 安全配置测试密钥与 OpenAI SDK 后，完成 DeepSeek 在线全流程与故障/超时实测。
- 在同一主机真实浏览器验证HTTP会话、刷新恢复、输入框焦点、滚动、1440×900和按钮可见性，补拍本轮关键状态截图。
- 当前为同一用户本机实验，文稿保存在浏览器localStorage、服务器会话暂存内存，缺少生产认证、跨设备保存、持久审计与生产限流；不宜公网发布。
- V2 LLM建议仍可能回退为保守删除稿；本实验将本地回退视为LLM失败，需人工处理或重试。
- 真实复检未发现明显风险仍不保证绝对合规。语义结果和模型稳定性需要实际在线评测。

等待最终验收；不自行部署或合并。
