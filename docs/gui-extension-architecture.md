# 翻译系统GUI扩展架构方案

## 1. 架构设计原则

### 1.1 分层架构
```
┌─────────────────────────────────────────────────────────────┐
│                    UI Layer (用户界面层)                      │
├──────────────────────┬──────────────────────────────────────┤
│   Desktop GUI        │         Web Interface               │
│   (Tkinter/PyQt)    │         (Flask/FastAPI)             │
└──────────────────────┴──────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  Application Layer (应用层)                  │
├─────────────────────────────────────────────────────────────┤
│  - TranslationController (翻译控制器)                       │
│  - ProjectManager (项目管理器)                               │
│  - ProgressTracker (进度跟踪器)                              │
│  - EventManager (事件管理器)                                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│               Core Business Logic (核心业务层)                │
├─────────────────────────────────────────────────────────────┤
│  - TranslationService (翻译服务) ✅ 已有                     │
│  - FormatAdapter (格式适配器) ✅ 已有                        │
│  - LLMProvider (LLM提供者) ✅ 已有                           │
│  - Validator (验证器) ✅ 已有                                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Data Access Layer (数据访问层)                   │
├─────────────────────────────────────────────────────────────┤
│  - SQLiteStore (数据库存储) ✅ 已有                          │
│  - FileSystem (文件系统操作)                                 │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计理念
- **代码复用**: 核心业务逻辑完全不变，只是添加不同的UI层
- **事件驱动**: 使用事件系统实现UI与核心逻辑的解耦
- **状态管理**: 集中式状态管理，支持实时更新
- **异步处理**: 后台任务不阻塞UI

## 2. 桌面版GUI方案

### 2.1 技术栈选择

#### 方案A: Tkinter (推荐快速开发)
```python
# 优点
- Python 内置，无需额外安装
- 快速原型开发
- 跨平台支持

# 缺点  
- 外观相对简陋
- 高级功能需要额外代码
```

#### 方案B: PyQt6/PySide6 (推荐专业应用)
```python
# 优点
- 专业级外观
- 丰富的组件库
- 优秀的文档和社区

# 缺点
- 需要额外安装
- 学习曲线较陡
```

#### 方案C: CustomTkinter (推荐现代化外观)
```python
# 优点
- 基于Tkinter，但外观现代化
- 内置主题支持
- 相对简单

# 缺点
- 社区相对较小
```

### 2.2 桌面版模块设计

```
llm_translate/
├── gui/                          # GUI模块
│   ├── __init__.py
│   ├── main.py                   # 主入口
│   ├── controllers/              # 控制器层
│   │   ├── __init__.py
│   │   ├── translation_controller.py
│   │   ├── project_controller.py
│   │   └── settings_controller.py
│   ├── views/                   # 视图层
│   │   ├── __init__.py
│   │   ├── main_window.py       # 主窗口
│   │   ├── project_view.py      # 项目管理视图
│   │   ├── translation_view.py  # 翻译视图
│   │   ├── settings_view.py     # 设置视图
│   │   └── components/          # 通用组件
│   │       ├── progress_bar.py
│   │       ├── code_viewer.py
│   │       └── log_viewer.py
│   ├── models/                  # 数据模型
│   │   ├── __init__.py
│   │   ├── view_models.py       # 视图模型
│   │   └── observable.py        # 可观察对象
│   ├── services/                # GUI服务层
│   │   ├── __init__.py
│   │   ├── event_service.py     # 事件服务
│   │   └── progress_service.py  # 进度服务
│   └── resources/               # 资源文件
│       ├── icons/
│       ├── styles/
│       └── ui/
└── ...
```

### 2.3 桌面版核心功能

#### 功能列表
1. **项目管理**
   - 创建新项目
   - 查看项目列表
   - 项目状态监控
   - 批量操作

2. **翻译执行**
   - 实时进度显示
   - 分块翻译监控
   - 错误处理和重试
   - 日志实时显示

3. **结果预览**
   - 双语对照预览
   - 代码高亮显示
   - 导出功能

4. **设置管理**
   - LLM配置
   - 环境变量配置
   - 界面设置

### 2.4 桌面版实现示例 (CustomTkinter)

```python
# gui/main.py
import customtkinter as ctk
from typing import Callable
from ..service import TranslationService
from ..config import Settings

class TranslationApp(ctk.CTk):
    """主应用窗口"""
    
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.service = TranslationService(settings)
        
        self.title("LLM Translate")
        self.geometry("1200x800")
        
        # 创建界面
        self.create_widgets()
        self.setup_menu()
        
    def create_widgets(self):
        """创建界面组件"""
        # 主框架
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 侧边栏
        self.sidebar = ctk.CTkFrame(self.main_frame, width=200)
        self.sidebar.pack(side="left", fill="y", padx=(0, 10))
        
        # 主内容区
        self.content_area = ctk.CTkFrame(self.main_frame)
        self.content_area.pack(side="right", fill="both", expand=True)
        
        # 导航按钮
        self.create_nav_buttons()
        
        # 默认显示项目页面
        self.show_projects_view()
    
    def create_nav_buttons(self):
        """创建导航按钮"""
        ctk.CTkLabel(
            self.sidebar, 
            text="导航", 
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(0, 10))
        
        self.projects_btn = ctk.CTkButton(
            self.sidebar, 
            text="📁 项目管理", 
            command=self.show_projects_view
        )
        self.projects_btn.pack(fill="x", pady=5)
        
        self.translation_btn = ctk.CTkButton(
            self.sidebar, 
            text="🌍 翻译任务", 
            command=self.show_translation_view
        )
        self.translation_btn.pack(fill="x", pady=5)
        
        self.settings_btn = ctk.CTkButton(
            self.sidebar, 
            text="⚙️ 设置", 
            command=self.show_settings_view
        )
        self.settings_btn.pack(fill="x", pady=5)
    
    def show_projects_view(self):
        """显示项目管理视图"""
        self.clear_content_area()
        from .views.project_view import ProjectView
        self.current_view = ProjectView(self.content_area, self.service)
        self.current_view.pack(fill="both", expand=True)
    
    def show_translation_view(self):
        """显示翻译视图"""
        self.clear_content_area()
        from .views.translation_view import TranslationView
        self.current_view = TranslationView(self.content_area, self.service)
        self.current_view.pack(fill="both", expand=True)
    
    def show_settings_view(self):
        """显示设置视图"""
        self.clear_content_area()
        from .views.settings_view import SettingsView
        self.current_view = SettingsView(self.content_area, self.settings)
        self.current_view.pack(fill="both", expand=True)
    
    def clear_content_area(self):
        """清空内容区"""
        for widget in self.content_area.winfo_children():
            widget.destroy()

def launch_gui():
    """启动GUI应用"""
    settings = Settings.from_env()
    app = TranslationApp(settings)
    app.mainloop()

if __name__ == "__main__":
    launch_gui()
```

## 3. 网页版方案

### 3.1 技术栈选择

#### 方案A: Flask (推荐小型应用)
```python
# 优点
- 轻量级
- 学习曲线平缓
- 灵活性高

# 缺点
- 大型应用需要额外架构
```

#### 方案B: FastAPI (推荐现代应用)
```python
# 优点
- 自动API文档
- 类型检查
- 异步支持
- 性能优秀

# 缺点
- 相对较新
```

#### 方案C: Flask + Vue.js (推荐专业应用)
```python
# 前后端分离
# 前端: Vue.js + Element Plus
# 后端: FastAPI
```

### 3.2 网页版模块设计

```
llm_translate/
├── web/                          # Web模块
│   ├── __init__.py
│   ├── app.py                    # 应用入口
│   ├── api/                      # REST API
│   │   ├── __init__.py
│   │   ├── routes/               # 路由
│   │   │   ├── __init__.py
│   │   │   ├── projects.py       # 项目API
│   │   │   ├── translation.py    # 翻译API
│   │   │   ├── websocket.py      # WebSocket支持
│   │   │   └── export.py        # 导出API
│   │   └── schemas/              # API模式
│   │       ├── __init__.py
│   │       └── models.py         # 数据模型
│   ├── services/                 # Web服务层
│   │   ├── __init__.py
│   │   ├── background_tasks.py  # 后台任务
│   │   └── progress_stream.py   # 进度流
│   ├── static/                   # 静态文件
│   │   ├── css/
│   │   ├── js/
│   │   └── img/
│   └── templates/                # 模板文件
│       ├── index.html
│       ├── projects.html
│       └── translation.html
└── ...
```

### 3.3 网页版API设计

#### RESTful API端点

```python
# 项目管理
GET    /api/projects              # 获取项目列表
POST   /api/projects              # 创建项目
GET    /api/projects/{id}         # 获取项目详情
DELETE /api/projects/{id}         # 删除项目

# 翻译操作
POST   /api/projects/{id}/parse   # 解析项目
POST   /api/projects/{id}/prepare # 准备翻译
POST   /api/projects/{id}/translate # 开始翻译
GET    /api/projects/{id}/progress # 获取翻译进度
DELETE /api/projects/{id}/cancel  # 取消翻译

# 导出操作
GET    /api/projects/{id}/export  # 导出结果

# 实时通信
WS     /api/projects/{id}/ws      # WebSocket连接
```

#### FastAPI实现示例

```python
# web/api/routes/projects.py
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from ...service import TranslationService
from ...config import Settings
from .schemas import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    settings: Settings = Depends(get_settings)
):
    """获取项目列表"""
    service = TranslationService(settings)
    service.init_db()
    return service.list_projects()

@router.post("", response_model=ProjectResponse)
async def create_project(
    project: ProjectCreate,
    settings: Settings = Depends(get_settings)
):
    """创建新项目"""
    service = TranslationService(settings)
    service.init_db()
    
    translation_project = service.create_project(
        source_path=project.source_path,
        name=project.name,
        target_language=project.target_language
    )
    
    return translation_project

@router.post("/{project_id}/translate")
async def start_translation(
    project_id: str,
    provider: str = "litellm",
    settings: Settings = Depends(get_settings)
):
    """开始翻译任务"""
    service = TranslationService(settings)
    llm_provider = provider_from_name(provider)
    
    # 异步执行翻译
    import asyncio
    asyncio.create_task(run_translation_async(service, project_id, llm_provider))
    
    return {"message": "Translation started", "project_id": project_id}

async def run_translation_async(service, project_id, provider):
    """异步执行翻译"""
    try:
        service.translate_project(project_id, provider, include_need_review=False)
    except Exception as e:
        # 记录错误
        print(f"Translation failed: {e}")
```

### 3.4 前端设计

#### 现代化界面
```html
<!-- templates/index.html -->
<!DOCTYPE html>
<html>
<head>
    <title>LLM Translate</title>
    <link rel="stylesheet" href="https://unpkg.com/element-plus/dist/index.css">
</head>
<body>
    <div id="app">
        <el-container>
            <el-header>
                <h1>🌍 LLM Translate</h1>
            </el-header>
            <el-container>
                <el-aside width="200px">
                    <el-menu>
                        <el-menu-item index="projects">📁 项目管理</el-menu-item>
                        <el-menu-item index="translation">🌍 翻译任务</el-menu-item>
                        <el-menu-item index="settings">⚙️ 设置</el-menu-item>
                    </el-menu>
                </el-aside>
                <el-main>
                    <router-view></router-view>
                </el-main>
            </el-container>
        </el-container>
    </div>
    
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://unpkg.com/element-plus/dist/index.full.js"></script>
    <script src="/static/app.js"></script>
</body>
</html>
```

## 4. 事件驱动架构

### 4.1 事件系统设计

```python
# gui/services/event_service.py
from typing import Callable, Dict, List
from dataclasses import dataclass
from enum import Enum

class EventType(Enum):
    PROJECT_CREATED = "project_created"
    PROJECT_UPDATED = "project_updated"
    PROJECT_DELETED = "project_deleted"
    TRANSLATION_STARTED = "translation_started"
    TRANSLATION_PROGRESS = "translation_progress"
    TRANSLATION_COMPLETED = "translation_completed"
    TRANSLATION_FAILED = "translation_failed"
    CHUNK_STARTED = "chunk_started"
    CHUNK_COMPLETED = "chunk_completed"
    ERROR_OCCURRED = "error_occurred"

@dataclass
class Event:
    type: EventType
    data: Dict[str, Any]

class EventBus:
    """事件总线，支持发布-订阅模式"""
    
    def __init__(self):
        self._listeners: Dict[EventType, List[Callable]] = {}
    
    def subscribe(self, event_type: EventType, callback: Callable):
        """订阅事件"""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)
    
    def publish(self, event: Event):
        """发布事件"""
        if event.type in self._listeners:
            for callback in self._listeners[event.type]:
                callback(event.data)
    
    def unsubscribe(self, event_type: EventType, callback: Callable):
        """取消订阅"""
        if event_type in self._listeners:
            self._listeners[event_type].remove(callback)

# 全局事件总线
event_bus = EventBus()
```

### 4.2 进度跟踪系统

```python
# gui/services/progress_service.py
from typing import Dict, Any
import threading
import time

class ProgressTracker:
    """进度跟踪器"""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._current_progress: Dict[str, Any] = {}
    
    def start_translation(self, project_id: str, total_chunks: int):
        """开始翻译"""
        self._current_progress[project_id] = {
            "total_chunks": total_chunks,
            "completed_chunks": 0,
            "failed_chunks": 0,
            "current_chunk": 0,
            "start_time": time.time(),
            "status": "translating"
        }
        
        self.event_bus.publish(Event(
            EventType.TRANSLATION_STARTED,
            {"project_id": project_id, "total_chunks": total_chunks}
        ))
    
    def update_chunk_progress(self, project_id: str, chunk_index: int, status: str):
        """更新chunk进度"""
        if project_id not in self._current_progress:
            return
        
        progress = self._current_progress[project_id]
        progress["current_chunk"] = chunk_index
        
        if status == "completed":
            progress["completed_chunks"] += 1
        elif status == "failed":
            progress["failed_chunks"] += 1
        
        percentage = (progress["completed_chunks"] / progress["total_chunks"]) * 100
        
        self.event_bus.publish(Event(
            EventType.TRANSLATION_PROGRESS,
            {
                "project_id": project_id,
                "current_chunk": chunk_index,
                "completed_chunks": progress["completed_chunks"],
                "total_chunks": progress["total_chunks"],
                "percentage": percentage
            }
        ))
    
    def complete_translation(self, project_id: str, success: bool):
        """完成翻译"""
        if project_id not in self._current_progress:
            return
        
        progress = self._current_progress[project_id]
        progress["status"] = "completed" if success else "failed"
        progress["end_time"] = time.time()
        
        self.event_bus.publish(Event(
            EventType.TRANSLATION_COMPLETED if success else EventType.TRANSLATION_FAILED,
            {"project_id": project_id, **progress}
        ))
```

## 5. 异步任务处理

### 5.1 后台任务系统

```python
# web/services/background_tasks.py
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any

class BackgroundTaskExecutor:
    """后台任务执行器"""
    
    def __init__(self, max_workers: int = 2):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: Dict[str, Any] = {}
    
    def submit_task(
        self, 
        task_id: str, 
        func: Callable, 
        callback: Callable = None
    ):
        """提交后台任务"""
        def task_wrapper():
            try:
                result = func()
                if callback:
                    callback(task_id, "success", result)
            except Exception as e:
                if callback:
                    callback(task_id, "error", str(e))
        
        future = self.executor.submit(task_wrapper)
        self._tasks[task_id] = future
    
    def get_task_status(self, task_id: str) -> str:
        """获取任务状态"""
        if task_id not in self._tasks:
            return "not_found"
        
        future = self._tasks[task_id]
        if future.done():
            return "completed"
        else:
            return "running"

# 全局后台任务执行器
task_executor = BackgroundTaskExecutor()
```

## 6. 配置文件更新

### 6.1 pyproject.toml 更新

```toml
[project]
name = "llm-translate"
version = "0.1.0"
description = "Recoverable structured long-document translation workflow."
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "beautifulsoup4>=4.12",
  "EbookLib>=0.18",
  "html5lib>=1.1",
  "litellm>=1.0.0",
  "sqlalchemy>=2.0.0",
  "trafilatura>=1.6.0",
  "requests>=2.31.0",
]

# GUI dependencies
[project.optional-dependencies]
gui = [
  "customtkinter>=5.0.0",
  "Pillow>=9.0.0",
]
pyqt = [
  "PyQt6>=6.0.0",
]
web = [
  "fastapi>=0.68.0",
  "uvicorn>=0.15.0",
  "websockets>=11.0.0",
]
web-full = [
  "fastapi>=0.68.0",
  "uvicorn>=0.15.0",
  "websockets>=11.0.0",
  "jinja2>=3.0.0",
  "python-multipart>=0.0.0",
]

[project.scripts]
llm-translate = "llm_translate.cli:main"
llm-translate-gui = "llm_translate.gui.main:launch_gui"
llm-translate-web = "llm_translate.web.app:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["llm_translate*"]
```

## 7. 实现优先级建议

### Phase 1: 基础GUI (2-3周)
- [x] 核心业务逻辑完善
- [ ] CustomTkinter 基础界面
- [ ] 项目管理功能
- [ ] 简单的翻译执行

### Phase 2: 功能完善 (2-3周)
- [ ] 实时进度显示
- [ ] 事件系统集成
- [ ] 后台任务处理
- [ ] 错误处理和重试

### Phase 3: Web版基础 (3-4周)
- [ ] FastAPI 后端
- [ ] 基础前端界面
- [ ] REST API实现
- [ ] WebSocket 实时通信

### Phase 4: 高级功能 (2-3周)
- [ ] 双语对照预览
- [ ] 代码高亮显示
- [ ] 批量操作
- [ ] 主题切换

## 8. 开发建议

### 8.1 技术选型推荐
- **桌面版**: CustomTkinter (快速原型) → PyQt6 (专业版)
- **网页版**: FastAPI + Vue.js (专业分离架构)

### 8.2 开发顺序
1. **先做桌面版**: 验证UI概念，快速迭代
2. **后做网页版**: 基于桌面版经验，实现Web版

### 8.3 关键点
- **复用核心逻辑**: 不修改现有的 service.py
- **事件驱动**: 使用事件系统解耦UI和业务逻辑
- **异步处理**: 所有耗时操作都要异步执行
- **状态管理**: 集中式状态管理，避免UI不一致

这个架构方案可以让你在保持现有核心代码不变的情况下，快速开发出桌面版和网页版GUI！