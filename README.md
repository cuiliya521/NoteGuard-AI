# NoteGuard AI

> **V2 独立试验分支：** 新增「协作审核 V2」入口，体验规则与语义分析、条件决策、人工确认及采用后复检。下方公开 Demo 仍是稳定的 V1，尚未部署 V2。V2 没有配置 DeepSeek Key 时只能进行规则检查，本地建议可能不自然，需人工调整；这不代表完整的语义审核。

面向教育机构和内容运营人员的小红书招生内容助手：把参考内容拆解、招生笔记生成与发布前审核放进同一条工作流，帮助运营人员更快发现内容风险并形成可复用的内容资产。

**[在线体验 Demo](https://noteguard-ai-jwmmq9gayaddm6qkrey3cn.streamlit.app/)** · 免费实例休眠时，点击页面上的唤醒按钮并稍等片刻。

**我的工作：** 围绕教育内容运营的实际流程，参与需求分析、功能流程与审核规则设计、Prompt / AI 能力应用及产品迭代。开发过程中使用了 AI 辅助。

![NoteGuard AI 内容审核中心界面](noteguard-audit.jpg)

### 三步体验

1. 打开 Demo，在「内容审核中心」点击「体验 Demo」，载入脱敏示例。
2. 查看标题、正文和封面文字的规则命中、问题定位及修改建议。
3. 切到「招生笔记助手」体验参考内容拆解与笔记生成流程；在「历史与资产」「审核规则中心」了解记录沉淀和规则范围。

### 产品思路与我的工作

教育内容运营需要同时处理参考素材、招生表达和发布前风险，流程分散且容易重复劳动。规则检查负责可明确判断的风险表达、命中位置与可解释结果；大模型在配置 API Key 的环境下辅助内容分析、生成与改写。公开 Demo 的「体验 Demo」使用脱敏示例结果，**不调用真实 AI API**。项目定位为可运行的产品原型，代码实现使用了 AI 辅助；未涉及模型训练或微调。

当前核心模块：**内容审核中心、招生笔记助手、历史与资产、审核规则中心**。以下是功能与部署细节。

## 主要功能

- 标题、正文和封面 OCR 文字的规则审核
- 问题位置高亮与最小范围替代表达
- 小红书链接、截图和正文素材导入
- 爆款成交逻辑拆解与招生笔记生成
- 封面图片上传、粘贴与中文 OCR
- 案例库和方法模型沉淀
- 自定义审核规则管理
- 创作者资料管理
- 本地审核历史记录

## 环境要求

- Python 3.10 或更高版本，推荐 Python 3.12
- Windows、macOS 或 Linux
- 可选：DeepSeek API Key，用于 AI 改写、标题生成和分析功能
- 可选：PaddleOCR 或 Tesseract，用于自动识别图片文字

没有 API Key 或 OCR 依赖时，应用仍可使用本地规则检查和手动 OCR 文本输入。

## 环境变量配置

项目提供不包含真实凭证的 `.env.example`：

```dotenv
DEEPSEEK_API_KEY=your_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
VISION_MODEL=gpt-4.1-mini
NOTEGUARD_PUBLIC_DEMO=1
```

`OPENAI_API_KEY` 与 `VISION_MODEL` 为可选配置，仅在本地 OCR 无法读取封面文字时启用图片文字理解兜底。本地使用时复制该文件为 `.env`，再填写自己实际使用的 Key。

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

macOS/Linux：

```bash
cp .env.example .env
```

编辑 `.env`：

```dotenv
DEEPSEEK_API_KEY=你的真实_API_Key
```

`.env` 已被 `.gitignore` 忽略。不要提交、截图或分享真实 API Key。

## 本地启动

### Windows PowerShell

```powershell
cd "NoteGuard-AI"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

### macOS/Linux

```bash
cd "NoteGuard-AI"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

启动后访问终端显示的地址，默认通常为：

```text
http://localhost:8501
```

语法和测试检查：

```bash
python -m py_compile app.py
python -m unittest discover -s tests -v
```

## Streamlit Community Cloud Secrets

部署到 Streamlit Community Cloud 时，不要上传 `.env`。在应用部署页面的 **Advanced settings → Secrets** 中配置：

```toml
DEEPSEEK_API_KEY = "你的真实_API_Key"
```

根级 Secret 会作为环境变量提供给应用。修改 Secrets 后如未立即生效，请重启应用。

公开作品集部署建议保留 `NOTEGUARD_PUBLIC_DEMO=1`：审核历史仅保存在访客当前会话，规则中心为只读，并自动使用明确标注的虚构演示档案。本地受控环境如需管理规则，可设置为 `0`。

部署时建议：

1. 入口文件选择 `app.py`。
2. Python 版本选择 3.12。
3. 确认仓库根目录包含 `requirements.txt` 和 `packages.txt`。
4. 通过 Cloud Secrets 配置 Key，不要把真实 Key 写入代码或仓库。

公开 Demo 使用说明：

- Community Cloud 的应用网址可以长期访问，但免费实例空闲后可能休眠，首次打开需要等待唤醒。
- 本地 JSON 文件不是云端持久数据库，应用重启或重新部署后，访客新增的历史、案例和业务档案可能丢失。
- 公共 Demo 不应输入真实客户资料、未公开业务数据或其他敏感信息。

## OCR 依赖

图片会依次经过压缩、放大、灰度、对比度增强和阈值处理，并进行多轮 OCR。未安装本地 OCR 或多轮识别仍无结果时，如已配置视觉模型，应用会继续读取封面主标题、小字、标签和角标；两种来源统一写入 `cover_text`，视觉结果优先。

### PaddleOCR

Python 3.10–3.13 会根据 `requirements.txt` 安装：

```text
paddlepaddle>=3.0,<4
paddleocr>=3.3,<4
```

PaddleOCR 依赖较大，首次安装、模型下载和冷启动可能耗时较长。

### Tesseract

Python 包 `pytesseract` 只是调用接口，还需要安装 Tesseract 程序和中文 `chi_sim` 语言包。

Windows：

1. 安装 Tesseract OCR。
2. 安装或勾选 `chi_sim` 中文语言数据。
3. 将 Tesseract 安装目录加入系统 `PATH`。
4. 重新打开终端后运行 `tesseract --version` 验证。

Debian/Ubuntu：

```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-chi-sim
```

Streamlit Community Cloud 会读取仓库根目录的 `packages.txt` 并安装这两个系统包。

macOS：

```bash
brew install tesseract tesseract-lang
```

## 数据与安全说明

- 上传图片仅在当前 Streamlit 会话内处理，不会由应用写入图片文件。
- 历史记录、规则和创作者资料使用本地 JSON 文件，适合本地单用户或受控 Demo。
- 公开多用户部署前，应改用带用户隔离的持久存储并限制规则管理权限。
- AI 和 OCR 结果仅用于发布前辅助检查，最终内容应由用户人工确认。
