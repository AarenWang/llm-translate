# 依赖安装指南

本项目使用 `pyproject.toml` 管理依赖，但也提供了传统的 `requirements.txt` 文件方便安装。

## 📦 依赖文件说明

### 核心依赖
- **文件**: `requirements.txt`
- **用途**: 基础翻译功能必需的依赖
- **安装**: `pip install -r requirements.txt`

### 可选依赖
- **文件**: `requirements-dev.txt`
- **用途**: 开发和测试依赖
- **安装**: `pip install -r requirements-dev.txt`

- **文件**: `requirements-gui.txt`  
- **用途**: 桌面版GUI依赖
- **安装**: `pip install -r requirements-gui.txt`

- **文件**: `requirements-web.txt`
- **用途**: 网页版基础依赖
- **安装**: `pip install -r requirements-web.txt`

- **文件**: `requirements-web-full.txt`
- **用途**: 网页版完整依赖
- **安装**: `pip install -r requirements-web-full.txt`

- **文件**: `requirements-all.txt`
- **用途**: 所有依赖（开发+GUI+网页）
- **安装**: `pip install -r requirements-all.txt`

## 🚀 快速开始

### 1. 基础安装（CLI使用）
```bash
# 安装核心依赖
pip install -r requirements.txt

# 验证安装
python -m llm_translate.cli --help
```

### 2. 桌面版GUI安装
```bash
# 安装GUI依赖
pip install -r requirements-gui.txt

# 启动GUI
python -m llm_translate.gui.main
```

### 3. 网页版安装
```bash
# 基础网页版
pip install -r requirements-web.txt

# 完整网页版（推荐）
pip install -r requirements-web-full.txt

# 启动网页服务
python -m llm_translate.web.app
```

### 4. 开发环境安装
```bash
# 安装所有依赖
pip install -r requirements-all.txt
```

## 💡 安装建议

### 推荐方式1: 使用 pip install -e
```bash
# 开发模式安装（可编辑）
pip install -e .

# 带可选依赖的安装
pip install -e ".[gui]"
pip install -e ".[web]"
```

### 推荐方式2: 分步安装
```bash
# 1. 先安装核心依赖
pip install -r requirements.txt

# 2. 根据需要安装可选依赖
pip install -r requirements-gui.txt  # 如果需要桌面版
pip install -r requirements-web.txt  # 如果需要网页版
```

## 📋 依赖包列表

### 核心依赖 (requirements.txt)
- `beautifulsoup4>=4.12` - HTML解析
- `EbookLib>=0.18` - EPUB电子书支持
- `html5lib>=1.1` - HTML5解析
- `litellm>=1.0.0` - LLM统一接口
- `sqlalchemy>=2.0.0` - 数据库ORM
- `trafilatura>=1.6.0` - 网页内容提取
- `requests>=2.31.0` - HTTP请求

### GUI依赖 (requirements-gui.txt)
- `customtkinter>=5.0.0` - 现代化Tkinter界面
- `Pillow>=9.0.0` - 图像处理

### Web依赖 (requirements-web.txt)
- `fastapi>=0.68.0` - Web框架
- `uvicorn>=0.15.0` - ASGI服务器
- `websockets>=11.0.0` - WebSocket支持

### 开发依赖 (requirements-dev.txt)
- `pytest>=7.0.0` - 测试框架
- `black>=22.0.0` - 代码格式化
- `isort>=5.12.0` - import排序
- `flake8>=6.0.0` - 代码检查
- `mypy>=1.0.0` - 类型检查

## ⚠️ 注意事项

1. **Python版本**: 需要 Python >= 3.11
2. **网络连接**: 安装过程需要互联网连接
3. **虚拟环境**: 推荐使用虚拟环境进行安装

## 🔧 虚拟环境使用

### Windows
```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 退出虚拟环境
deactivate
```

### macOS/Linux
```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 退出虚拟环境
deactivate
```

## 🎯 不同使用场景的安装

### 场景1: 只使用CLI命令行工具
```bash
pip install -r requirements.txt
```

### 场景2: 需要桌面GUI
```bash
pip install -r requirements-gui.txt
```

### 场景3: 需要Web服务
```bash
pip install -r requirements-web-full.txt
```

### 场景4: 开发者完整环境
```bash
pip install -r requirements-all.txt
```

## 🆘 常见问题

### Q1: 安装失败怎么办？
```bash
# 尝试升级pip
python -m pip install --upgrade pip

# 清理缓存后重试
pip cache purge
pip install -r requirements.txt
```

### Q2: 某些包安装很慢？
```bash
# 使用国内镜像源
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### Q3: 依赖冲突怎么办？
```bash
# 使用虚拟环境隔离环境
python -m venv venv
venv\Scripts\activate  # Windows
# 或 source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

## 📞 获取帮助

如果遇到安装问题：
1. 检查 Python 版本: `python --version`
2. 检查 pip 版本: `pip --version`
3. 查看错误信息并搜索解决方案
4. 在虚拟环境中安装避免系统包冲突