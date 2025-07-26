# DeepMuse

## 项目简介
本项目具有基于React+FastAPI的用户登录注册系统与基于DeepSeek的智能学习助手，实现了一个支持音视频/文本内容自动转写、笔记（Notes）生成、测验题（Quiz）生成、原文显示、AI聊天对话的完整AI学习辅助平台。

- 前端：React（美观现代，支持Markdown渲染与数学公式渲染，体验友好）
- 后端：FastAPI（RESTful API，支持多媒体处理与AI内容生成）
- AI能力：DeepSeek大模型，支持内容总结、问答、测验生成

---

## 主要功能
- 用户注册、登录、鉴权、个人信息管理
- 文件上传（音频、视频、文本）
- Notes（学习笔记）自动生成（必选）
- Quiz（测验题）自动生成（可选）
- Q&A问答系统（右侧独立区，多轮对话，历史消息记忆）
- **文件下载功能** - 支持下载生成的笔记和测验题文件
- **实时错误提示** - 美观的错误提示横幅
- **实时AI回复** - WebSocket实时显示AI生成内容
- 一键清空所有内容，便于新一轮使用
- 前端美观，支持Markdown/代码高亮、进度条、加载动画、错误提示

---

## 目录结构

```
AI-Learning-Assistant/
|
├── docs/
│   ├── design.md                         # 设计文档
│   └── API_reference.md                  # API参考文档
│
├── src/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── ai/
│   │   │   │   ├── ai_core.py            # AI主处理逻辑（main_process等）
│   │   │   │   ├── llm.py                # DeepSeek API调用
│   │   │   │   ├── prompts.yml           # 提示词配置
│   │   │   │   ├── utils.py              # 工具函数（重试装饰器）
│   │   │   │   └── video_processor/
│   │   │   │       ├── splitter.py       # 音视频切分
│   │   │   │       └── transcriber.py    # 音频转写
│   │   │   ├── authentication/
│   │   │   │   ├── auth.py               # JWT认证
│   │   │   │   └── crud.py               # 数据库操作
│   │   │   ├── config.py                 # 配置管理
│   │   │   ├── database.py               # 数据库连接
│   │   │   ├── main.py                   # FastAPI主应用
│   │   │   ├── models.py                 # 数据库模型
│   │   │   └── schemas.py                # Pydantic模型
│   │   └── requirements.txt              # Python依赖
│   └── frontend/
│       ├── src/
│       │   ├── components/
│       │   │   ├── AssistantPage.jsx     # AI助手主界面（修复错误显示、实时回复、文件下载）
│       │   │   ├── AuthLayout.jsx        # 认证页面
│       │   │   ├── FullPageLoader.jsx    # 全局加载动画
│       │   │   ├── LoginForm.jsx         # 登录表单
│       │   │   ├── ProtectedRoute.jsx    # 登录保护路由
│       │   │   ├── RegisterForm.jsx      # 注册表单
│       │   │   └── StarsBackground.jsx   # 星星背景
│       │   ├── context/
│       │   │   └── AuthContext.js        # 认证上下文
│       │   ├── hooks/
│       │   │   └── useAuth.js            # 认证Hook
│       │   ├── services/
│       │   │   ├── assistant.js          # API调用服务
│       │   │   └── auth.js               # 认证服务
│       │   ├── icon/                     # 图标
│       │   ├── samples/                  # 示例图片
│       │   ├── App.js                    # 主入口文件
│       │   ├── App.css                   # 主样式
│       │   ├── index.js                  # 入口文件
│       │   └── routes.js                 # 路由配置
│       └── package.json                  # npm依赖
├── .env                                  # 环境变量
└── Readme.md                             # 本说明文档
```

---

## 环境依赖与安装

### 后端
- Python 3.12.11
- FastAPI, openai, pydub, requests, sqlalchemy, ...
- FFmpeg（音视频处理，需配置环境变量）
- DeepSeek API密钥、豆包API密钥（.env配置）

### 前端
- Node.js 16+
- 依赖：react, react-markdown, react-syntax-highlighter, ...

### 安装步骤
1. 后端依赖安装：
   ```Anaconda Powershell
   conda create -n DeepMuse python=3.12.11
   conda activate DeepMuse
   pip install -r requirements.txt
   ```

2. 配置.env（后端根目录），填写API密钥, API Key, database URL

3. 启动后端：
   ```Anaconda Powershell
   cd backend
   uvicorn app.main:app --reload
   ```

5. 启动前端：
   ```bash
   cd frontend
   npm start
   ```

---

## 主要API说明
| 路径                | 方法 | 说明                       |
|---------------------|------|----------------------------|
| /upload/            | POST | 文件上传，返回file_id      |
| /conversations/     | GET  | 获取用户对话历史           |
| /conversations/{id} | GET  | 获取特定对话详情           |
| /process            | POST | 处理文件生成Notes/Quiz     |
| /download/{path}    | GET  | **下载生成的文件**         |
| /ws/{conversation_id} | WebSocket | 实时通信，处理进度和Q&A |

---

## 前端使用指引
1. 登录/注册后，访问 `/assistant` 进入AI学习助手主界面。
2. 左侧上传文件，输入额外需求，点击生成Notes/Quiz。
3. 可勾选显示原始文本，支持一键清空所有内容。
4. 右侧Q&A区输入问题，支持多轮对话，历史消息自动记忆。
5. **生成完成后可下载笔记/测验题文件**。
6. **实时显示AI生成过程和错误提示**。
7. 所有内容支持Markdown渲染与代码高亮，体验美观。

---

## 技术实现细节

### 实时通信机制
- 使用WebSocket实现前后端实时通信
- 支持处理进度实时更新
- AI生成内容流式显示
- 多轮对话上下文记忆

### 文件处理流程
1. 文件上传 → 创建对话记录
2. 音视频切分 → 音频块生成
3. 语音转写 → 文本内容提取
4. AI处理 → 笔记/测验题生成
5. 文件保存 → 本地存储
6. 下载功能 → 用户获取文件

### 错误处理机制
- 前端错误状态管理
- 美观的错误提示UI
- 后端异常捕获和返回
- 用户友好的错误信息

---

## 常见问题
- 若音视频转写失败，请检查FFmpeg和API密钥配置。
- 大文件处理建议服务器性能充足，避免超时。