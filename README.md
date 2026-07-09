# AI Reviewer MVP

小红书教育内容 AI 初审助手。第一版使用 Python + Streamlit 实现，暂不接真实 AI API，先用本地规则库检测疑似风险词并生成基础改写结果。

## 当前功能

- 标题输入
- 正文输入
- 图片上传和预览
- 规则库风险词检测
- 输出整体风险提示
- 输出疑似风险词、出现位置、风险原因、替换建议
- 基于替换建议生成基础改写结果

## 项目结构

```text
ai-reviewer-app/
├── app.py
├── requirements.txt
├── README.md
├── data/
│   └── rules.json
├── services/
│   ├── __init__.py
│   ├── rule_checker.py
│   └── rewriter.py
└── outputs/
```

## Mac 运行步骤

### 1. 进入项目目录

```bash
cd "/Users/edy/Desktop/AI Reviewer/开发/ai-reviewer-app"
```

### 2. 创建虚拟环境

```bash
python3 -m venv ".venv"
```

### 3. 激活虚拟环境

```bash
source ".venv/bin/activate"
```

### 4. 安装依赖

```bash
pip install -r "requirements.txt"
```

### 5. 启动应用

```bash
streamlit run "app.py"
```

启动后浏览器会自动打开页面。如果没有自动打开，可以访问终端里显示的本地地址，通常是：

```text
http://localhost:8501
```

## 使用说明

1. 输入小红书标题。
2. 输入正文、视频脚本或封面文案。
3. 可选上传图片查看预览。
4. 点击“开始审核”。
5. 查看风险提示和基础改写结果。

## 注意事项

当前版本只做疑似风险提示，不做最终违规判定。审核结果需要人工复核后再使用。
