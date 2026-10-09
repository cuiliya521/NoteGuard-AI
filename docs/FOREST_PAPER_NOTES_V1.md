# 招生笔记 Forest & Paper 独立实验

基线：正式 V2 `2ea9c11`。只在 `experiment/v2-forest-paper-notes-v1` 开发，未部署。

## 启用与回退

使用原完整应用，不是静态 HTML 或另一个审核引擎：

```bash
NOTEGUARD_FOREST_PAPER=1 NOTEGUARD_FOREST_PAPER_NOTES=1 streamlit run app.py
```

从完整应用进入“招生笔记”。新版开关默认关闭，未设置或设置为 `0` 都使用原招生笔记界面：

```bash
NOTEGUARD_FOREST_PAPER_NOTES=0 streamlit run app.py
```

不修改 `NOTEGUARD_FOREST_PAPER` 核心审核开关、Cloud Secrets 或部署配置。

## 实现边界

- `services/notes_forest_paper_ui.py` 只负责呈现、导航及当前生成稿的编辑状态保留。
- `components/notes_forest_paper/visual.css` 所有规则均以 `.st-key-ngnotes` 或 `.stApp:has(.st-key-ngnotes)` 限定作用域；不会修改其他页面或冻结审核组件。
- `app.py` 仅修改招生笔记三个渲染函数，复用原导入/OCR/拆解/生成/审核回调及原控件键。
- 原 AI 生成稿不因人工编辑而被覆盖。编辑状态按生成稿指纹保留，生成新稿时清除上一稿编辑缓存。
- 拆解不完整时显示回退信息说明，并允许重试；不把业务资料回退当作完整 AI 结论。
- 当前四步指示来自素材指纹、实际拆解状态与生成稿状态，不表示内容已经审核通过。
- 现有通用创作结构有明确标签，不伪称为某篇素材的 AI 拆解结果。
- 现有一键审核仍转到原“内容审核中心”；未改审核逻辑或冻结 Forest & Paper 审核工作台。
- 保留原 Session State 模型；同会话 rerun 和页面返回有自动化验证，浏览器硬刷新与断开连接后的恢复未验收，不新增持久化机制。

## 测试

```bash
NOTEGUARD_FOREST_PAPER=0 python -m pytest tests -q
node --test tests/test_forest_paper_component.cjs
```

原完整测试中的部分旧页面用例要求旧审核模式，因此运行全套时明确设置核心开关为 `0`；现有 Forest & Paper 路由测试自行设置 `1`。

新增测试通过原生 Streamlit AppTest 操作真实控件。DeepSeek、远程链接响应及 OCR 响应在自动化用例内明确模拟，不能视为真实在线验收。截图不得从 AppTest 或合成 HTML 伪造。

## 待验收

浏览器访问本地测试入口被安全策略拒绝。未改测试应用部署或正式部署来绕过限制。新版真实浏览器截图、新旧同视口对比、1440×900、截图粘贴、真实 OCR/链接获取/DeepSeek 端到端及浏览器刷新恢复均未完成。

已有旧版真实截图视口为 1363×936，只能作为基线。当前版本不能据此宣称视觉验收通过或正式发布就绪。
