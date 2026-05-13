# 超联自动化工具 — 开发指南

> 适用于 v1.0.0 重构后版本。本文档记录所有 API 变更、开发规范和最佳实践。

## 目录

- [架构概览](#架构概览)
- [重构变更清单](#重构变更清单)
- [BaseStrategy API 参考](#basestrategy-api-参考)
- [BaseChaolianStrategy API 参考](#basechaolianstrategy-api-参考)
- [ImageService 变更](#imageservice-变更)
- [ADBService 变更](#adbservice-变更)
- [StrategyManager 变更](#strategymanager-变更)
- [新建策略指南](#新建策略指南)
- [注册新游戏模式](#注册新游戏模式)
- [打包注意事项](#打包注意事项)
- [开发规范与最佳实践](#开发规范与最佳实践)

---

## 架构概览

```
main.py                          # 入口
├── ui/main_window.py            # GUI：模式选择、端口、启停控制
├── core/
│   ├── base_strategy.py         # 策略基类（ABC）：ADB、OCR、模板/SIFT匹配、颜色检测
│   ├── strategy_manager.py      # 线程管理：每端口一个 daemon 线程
│   └── strategies/
│       ├── __init__.py          # STRATEGY_MAP 注册表
│       ├── base_chaolian.py     # 超联系列基类：导航、战术、卡死检测
│       ├── chaolian_front.py    #   季前赛
│       ├── chaolian_challenge.py #  挑战赛
│       ├── chaolian_step.py     #   天梯赛
│       ├── dynasty_55.py        #   5v5（stub，待开发）
│       └── dynasty_33.py        #   3v3（stub，待开发）
├── services/
│   ├── adb_service.py           # ADB 封装：连接(含重试)、截图、点击、滑动
│   ├── image_service.py         # RapidOCR + OpenCV 模板匹配 + SIFT + 颜色检测
│   └── logger_service.py        # 单例日志：文件 + 控制台 + 队列（GUI 轮询）
├── config/settings.json         # 用户配置（持久化到 ~/.qmxChaoLian）
├── resources/
│   ├── config/mode_config.json  # 模式声明
│   └── images/                  # 模板图片（SIFT/模板匹配用）
├── paths.py                     # 开发/打包路径兼容
├── package.py                   # PyInstaller 打包脚本
├── main.spec                    # PyInstaller spec 文件
└── hooks/                       # 运行时钩子（当前为空）
```

---

## 重构变更清单

### 依赖变更

| 操作 | 包名 | 原因 |
|------|------|------|
| **移除** | `paddleocr` `paddlepaddle` `paddlex` | 体积大（~500MB），替换为轻量方案 |
| **新增** | `rapidocr-onnxruntime>=1.3.0` | ONNX 推理，相同 PP-OCR 模型，~20MB |
| **替换** | `opencv-contrib-python` → `opencv-python` | 标准版包含 SIFT（4.4.0+），省 ~40MB |

### 新增的方法/能力

| 位置 | 方法/功能 | 说明 |
|------|-----------|------|
| `base_strategy.py` | `detecting_hall()` | 检测是否在大厅（SIFT 匹配 `begin.png`） |
| `base_strategy.py` | `detecting_chaolian()` | OCR 检测是否在超联主界面 |
| `base_strategy.py` | `_ocr(area, context)` | 快捷 OCR：裁剪区域 → 匹配关键词，返回 bool |
| `base_chaolian.py` | `_navigate_to_chaolian_main()` | 从大厅导航到超联主界面 |
| `base_chaolian.py` | `_execute_tactic()` | 执行战术 + 62秒冷却管理 |
| `base_chaolian.py` | `_check_enter_match()` | 检测"开始/进入"按钮并点击 |
| `base_chaolian.py` | `_setup_match_count()` | 初始化比赛计数（含30场限制逻辑） |
| `base_chaolian.py` | `_not_inner_match_simple()` | 非局内模式循环（仅排队不进入比赛画面） |
| `base_chaolian.py` | `_init_stuck_detection()` | 初始化卡死检测 |
| `base_chaolian.py` | `_is_stuck(timeout)` | 状态超过指定秒数未变化则触发恢复 |
| `adb_service.py` | `connect(retries, retry_delay)` | 新增重试参数，`adb connect` 后等设备注册 |

### 移除的内容

| 位置 | 内容 | 原因 |
|------|------|------|
| `hooks/rthook_paddlex.py` | 整个文件 | paddlex 不再安装 |
| `image_service.py` | `get_real_path()` 函数 | 未使用 |
| `image_service.py` | Paddle 环境变量 4 行 | `FLAGS_*` 不再需要 |
| `package.py` | `import paddlex` 及相关逻辑 | 不再收集 paddle 元数据 |
| `package.py` | `--collect-data paddlex` | 已移除 |
| `package.py` | `--collect-binaries paddle` | 已移除 |
| `main.spec` | 20 行 `copy_metadata` 调用 | 不再收集 paddle 生态元数据 |

### 行为变更

| 位置 | 变更 | 说明 |
|------|------|------|
| `adb_service.connect()` | 添加 3 次重试 | `adb connect` 后设备注册有延迟 |
| `adb_service` 所有 `subprocess.run()` | 添加 `CREATE_NO_WINDOW` | 防止打包后弹黑窗 |
| `strategy_manager.stop()` | 启动后台清理线程 | 防止 UI 卡死 |
| `main_window._on_stop()` | 即时禁用停止按钮 | 防止重复点击 |
| `main_window._run_bootstrap()` | 检测线程提前退出 | 连接失败时自动恢复 UI |

---

## BaseStrategy API 参考

`core/base_strategy.py` — 所有策略的抽象基类。新策略必须继承它（或 `BaseChaolianStrategy`）。

### 构造函数注入的属性

策略实例由 `MainWindow._on_start()` 动态创建，以下属性在 `__init__` 中自动设置：

```python
self.port            # int: ADB 端口号
self.config          # dict: 该模式的用户选项，如 {"is_inter_match": True, ...}
self.click_offset    # int: 点击随机偏差
self.adb             # ADBService | None: _connect() 后可用
self.image           # ImageService | None: _connect() 后可用（全局单例）
self.screen_size     # tuple | None: (width, height)
self.victory_count   # int: 胜利计数（需自行维护）
self.failure_count   # int: 失败计数（需自行维护）
self._strategy_name  # str: 类名，用于日志
```

### 生命周期

```
run()                           # StrategyManager 调用
  ├── _connect()                # 初始化 ADB + 获取屏幕尺寸
  ├── _execute()                # 【子类必须实现】核心逻辑
  └── _disconnect()             # finally 块中执行
```

### 继承方法一览

#### 连接与生命周期

| 方法 | 签名 | 说明 |
|------|------|------|
| `_connect()` | `() -> bool` | 创建 ADBService、连接设备、获取屏幕尺寸、注册到管理器。失败返回 False |
| `_disconnect()` | `() -> None` | 断开 ADB，清理资源 |
| `run()` | `() -> None` | 入口，调用 _connect → _execute → _disconnect |
| `_execute()` | `() -> None` | **抽象方法，子类必须实现** |

#### 屏幕交互

| 方法 | 签名 | 说明 |
|------|------|------|
| `_tap_with_offset(x, y, offset)` | `(x, y: 1280×720 坐标, offset: int) -> bool` | 带随机偏移的点击，坐标基于 1280×720，自动缩放 |
| `_swipe(x1, y1, x2, y2, duration)` | `(1280×720 坐标, duration: ms) -> None` | 滑动，坐标自动缩放 |
| `_sleep(seconds)` | `(float) -> None` | 每 0.5s 检查 stop_event 的可中断 sleep |

#### 图像匹配

| 方法 | 签名 | 返回 | 说明 |
|------|------|------|------|
| `_match_template(template_name, threshold)` | `(str, float) -> tuple` | `(x, y)` 或 `None` | 模板匹配（`resources/images/` 下的文件） |
| `_match_sift(template_name, min_match)` | `(str, int) -> tuple` | `(x, y)` 或 `None` | SIFT 特征匹配，适用旋转/缩放场景 |
| `_wait_for_image(template_name, timeout, interval, method)` | `(str, float, float, str) -> tuple` | `(x, y)` 或 `None` | 循环等待图像出现，尊重 stop_event |

#### OCR 文字识别

| 方法 | 签名 | 返回 | 说明 |
|------|------|------|------|
| `_ocr_area(area)` | `(tuple: (x,y,w,h) 1280×720 坐标或 None) -> list` | `[str, ...]` | **同步** OCR，返回识别文本列表 |
| `_ocr_area_async(area)` | `(tuple) -> str` | `request_id` | **异步** OCR，立即返回 request_id，推理在线程池执行 |
| `_ocr_result(request_id)` | `(str) -> list` | `[str, ...]` 或 `None` | 查询异步 OCR 结果，非阻塞，未完成返回 None |
| `_ocr(area, context)` | `(tuple, str) -> bool` | 布尔 | **快捷方法**：OCR + 关键词包含检测 |

#### 颜色检测

| 方法 | 签名 | 返回 | 说明 |
|------|------|------|------|
| `_get_pixel_color(x, y)` | `(1280×720 坐标) -> tuple` | `(B, G, R)` 或 `None` | 获取指定坐标像素颜色 |
| `_is_color_in_range(x, y, lower, upper)` | `(坐标, (B,G,R)下界, (B,G,R)上界) -> bool` | 布尔 | 判断颜色是否在范围内 |
| `_wait_for_color(x, y, lower, upper, timeout, interval)` | `(... + float, float) -> bool` | 布尔 | 循环等待颜色匹配，尊重 stop_event |

#### 大厅/超联界面检测

| 方法 | 说明 |
|------|------|
| `detecting_hall()` | SIFT 匹配 `begin.png`，在大厅返回 True |
| `detecting_chaolian()` | OCR 区域 (70,9,160,61) 检测 "超级" 文字 |

### 坐标系统

**所有策略方法的坐标参数基于 1280×720 设计分辨率。** `BaseStrategy._scale_coords()` 自动按 `screen_size[0] / 1280` 比例缩放。这意味着你无需关心设备实际分辨率，统一用 1280×720 坐标即可。

---

## BaseChaolianStrategy API 参考

`core/strategies/base_chaolian.py` — 超联系列策略基类，继承自 `BaseStrategy`。

### 新增属性

```python
self.status                   # str: 状态机当前状态 ("FREE", "MATCHING", "INNER", "ENDING", "CHOSE")
self.inner_strategy_status    # int: 战术状态 0=可执行, -1=冷却中
self.loading                  # float | None: 战术冷却开始时间戳 (time.monotonic())
self.match_count              # int: 比赛计数
self.change_count             # int: 每场计数增量 (0 或 1)
```

### 新增方法

| 方法 | 说明 |
|------|------|
| `_navigate_to_chaolian_main()` | 自动从大厅进入超联主界面（检测 → 点击） |
| `_execute_tactic()` | 执行战术（点击"战术"→"鼓舞士气"），62秒冷却自动管理。设置 `self.inner_strategy_status` 和 `self.loading` |
| `_check_enter_match()` | OCR 检测 "开始" 或 "进入" 按钮并点击。返回 `"MATCHING"`、`"INNER"` 或 `None` |
| `_setup_match_count()` | 初始化 `self.match_count=0`，根据 `config.only_thirty_match` 设置 `self.change_count` |
| `_not_inner_match_simple()` | 不进入比赛画面的循环：排队→等待→计数。用于季前赛、天梯赛 |
| `_init_stuck_detection()` | 初始化 `_last_status` 和 `_last_status_time` |
| `_is_stuck(timeout=90)` | 状态未变化超过 timeout 秒返回 True，否则更新计时 |

### 状态机模式

超联策略通常使用 `self.status` 状态机：

```
FREE ──(开始)──→ MATCHING ──(进入)──→ INNER ──(结束)──→ ENDING ──(返回)──→ FREE
```

- **FREE**: 空闲，搜索匹配按钮
- **MATCHING**: 已点击开始，等待匹配
- **INNER**: 比赛中（可使用 `_execute_tactic()` 执行战术）
- **ENDING**: 比赛结束画面，检测胜/负
- **CHOSE**: 挑战赛专用：选择对手阶段

---

## ImageService 变更

`services/image_service.py` — 全局单例 `image_service`。

### OCR 引擎替换

```python
# 之前（已废弃）
from paddleocr import PaddleOCR
self.ocr = PaddleOCR(use_angle_cls=True, lang='ch', ...)
result = self.ocr.ocr(img)

# 现在
from rapidocr_onnxruntime import RapidOCR
self.ocr = RapidOCR()
result, elapsed = self.ocr(img)  # result: [[box, text, score], ...] 或 None
```

### _parse_ocr_result 行为

返回格式已从 PaddleOCR 的嵌套字典简化为 `[[box, text, score], ...]` 的平铺列表。`_parse_ocr_result()` 提取每个 item[1]（text）组成文本列表。

### 未变更的方法

`match_template()`, `match_sift()`, `match_sift_details()`, `bytes_to_cv2()`, `get_pixel_color()`, `is_color_in_range()`, `wait_for_color()`, `ocr_text()`, `ocr_text_async()`, `ocr_poll()` — **全部保持不变**，只是底层 OCR 引擎换了。

---

## ADBService 变更

`services/adb_service.py`

### connect() 签名变更

```python
# 之前
def connect(self) -> bool:

# 现在
def connect(self, retries: int = 3, retry_delay: float = 1.0) -> bool:
```

`adb connect` 后以 1 秒间隔重试 3 次查找设备，解决设备注册延迟导致的偶发连接失败。

### 平台兼容常量

```python
_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
```

所有 `subprocess.run()` 调用都传入了 `creationflags=_CREATE_NO_WINDOW`，防止打包后弹出控制台黑窗。

---

## StrategyManager 变更

`core/strategy_manager.py`

### stop() 签名变更

```python
# 之前
def stop(self) -> None:   # 只设置 stop_event，不等待线程结束

# 现在
def stop(self, on_finished=None) -> None:  # 启动后台清理线程，完成后回调 on_finished
```

`on_finished` 回调由 `MainWindow._on_stop()` 传入 `lambda: self.after(0, self._on_execution_finished)`。

### 全局变量（未变）

```python
from core.strategy_manager import stop_event     # threading.Event，全局停止信号
from core.strategy_manager import register_screen_size  # 上报屏幕尺寸
from core.strategy_manager import get_screen_size       # 查询指定端口尺寸
from core.strategy_manager import get_all_screen_sizes   # 查询全部端口尺寸
```

---

## 新建策略指南

### 步骤 1：确定继承哪个基类

- **超联系列**（季前赛/挑战赛/天梯赛）：继承 `BaseChaolianStrategy`
- **王朝系列**（5v5/3v3 等）：继承 `BaseStrategy`
- 如果已有 `base_xxx.py`，优先继承它

### 步骤 2：创建策略文件

在 `core/strategies/` 下新建 `.py` 文件。以创建一个新的超联子模式为例：

```python
from core import stop_event
from core.strategies.base_chaolian import BaseChaolianStrategy
from services.logger_service import logger


class ChaolianXxxStrategy(BaseChaolianStrategy):
    """超联 XXX 策略"""

    def _execute(self):
        # 1. 读取用户选项
        self.is_excu_strategy = self.config.get('is_excu_strategy')
        self.is_inter_match = self.config.get('is_inter_match')
        self._setup_match_count()

        # 2. 导航到超联主界面
        self._navigate_to_chaolian_main()

        # 3. 检测目标子模式（用 OCR 确认）
        if not self._ocr((区域), "目标文字"):
            logger.error("没有看到 XXX 目标！")
            return

        # 4. 点击进入
        self._tap_with_offset(x, y, offset=1)
        self._sleep(1)

        # 5. 进入主循环（二选一）
        if self.is_inter_match:
            self._inner_match()          # 进入比赛画面
        else:
            self._not_inner_match_simple()  # 仅排队不进入
        logger.info("已完成任务")

    def _inner_match(self):
        self.loading = None
        self.status = "FREE"
        self.inner_strategy_status = 0

        while not stop_event.is_set():
            # 状态机逻辑...
            self._sleep(0.3)
```

### 步骤 3：注册策略

编辑 `core/strategies/__init__.py`：

```python
from core.strategies.chaolian_xxx import ChaolianXxxStrategy  # 新增

STRATEGY_MAP = {
    ...
    "chaolian_xxx": ChaolianXxxStrategy,  # 新增
}
```

### 步骤 4：注册模式配置

编辑 `resources/config/mode_config.json`，在对应 `group` 下添加：

```json
"chaolian_xxx": {
  "display_name": "XXX 模式",
  "group": "chaolian",
  "options": [
    { "id": "is_inter_match", "display_name": "进入局内", "default": false },
    { "id": "is_excu_strategy", "display_name": "执行战术（默认鼓舞士气）", "default": false }
  ]
}
```

- `display_name`：UI 中显示的中文名
- `group`：`"chaolian"` 或 `"dynasty"`，决定在哪个单选组下显示
- `options`：用户可勾选的选项，`id` 对应 `self.config.get(id)`

### 步骤 5：准备模板图片

将需要的模板图片放入 `resources/images/`，策略中使用文件名即可（不需要路径前缀）：

```python
pos = self._match_sift("your_template.png", min_match=50)
```

---

## 注册新游戏模式

非超联的新模式（如王朝 5v5）完整注册流程：

### 1. 创建策略文件 `core/strategies/dynasty_55.py`

```python
from core import stop_event
from core.base_strategy import BaseStrategy
from services.logger_service import logger


class Dynasty55Strategy(BaseStrategy):
    """5V5 全场争霸策略"""

    def _execute(self):
        if not self._connect():
            return

        # 读取配置
        auto_attack = self.config.get('auto_attack', False)
        # ...

        while not stop_event.is_set():
            # 核心循环
            self._sleep(0.3)
```

### 2. 更新 `core/strategies/__init__.py`

```python
from core.strategies.dynasty_55 import Dynasty55Strategy  # 确保已导入

# STRATEGY_MAP 已存在该条目则无需修改
```

### 3. 更新 `resources/config/mode_config.json`

确认模式条目存在且 `group` 正确。如果是在已有 group 下新增，添加条目即可。

### 4. 可选：如果该系列模式有共享逻辑，提取基类

参照 `BaseChaolianStrategy` 模式，在 `core/strategies/` 下创建 `base_xxx.py`。

---

## 全自动任务系统

`core/strategies/full_auto.py` + `ui/full_auto_window.py` — 弹窗配置 → 队列编排 → 顺序执行多个策略。

### 架构

```
mode_config.json (模式声明)
        │
        ▼
FullAutoWindow (弹窗 UI)
  ├── 王朝模式 (group=dynasty) ── 单选 ──┐
  ├── 超级联赛 (group=chaolian) ── 多选 ─┤
  ├── 每项独立选项复选框                  │
  └── 排序（上移/下移/删除）              │
        │                                  │
        ▼  task_list [{mode_id, options}]  │
FullAutoTaskStrategy._execute()           │
  ├── 遍历 task_list                       │
  ├── 对每项: sub_cls = STRATEGY_MAP[mode_id]
  ├── sub = sub_cls(port, sub_opts, click_offset)
  ├── sub.adb/image/screen_size 共享引用（不重复连接）
  ├── sub._execute() 直接调用（不调 sub.run()，跳过连接/断开）
  └── 跳舞/关机推迟到全部完成后统一执行
```

### 核心文件

| 文件 | 职责 |
|------|------|
| `core/strategies/full_auto.py` | `FullAutoTaskStrategy` — 队列编排器，遍历 task_list 依次执行子策略 |
| `ui/full_auto_window.py` | `FullAutoWindow` — 弹窗 UI，模式选择 + 选项配置 + 队列排序 |
| `ui/theme.py` | `THEME` 颜色字典，供 main_window 和 full_auto_window 共享 |

### FullAutoTaskStrategy 关键行为

```python
# core/strategies/full_auto.py
class FullAutoTaskStrategy(BaseStrategy):
    def _execute(self):
        from core.strategies import STRATEGY_MAP  # 延迟导入，避免循环引用
        tasks = self.config.get("tasks", [])
        for i, task in enumerate(tasks):
            mode_id = task["mode_id"]
            sub_opts = dict(task.get("options", {}))
            # 跳舞/关机推迟到最后
            if sub_opts.pop("dancing", False): final_dancing = True
            if sub_opts.pop("turn_off", False): final_turn_off = True
            # 创建子策略 → 共享 ADB/image/screen_size → 直接调 _execute()
            sub_cls = STRATEGY_MAP[mode_id]
            sub = sub_cls(self.port, sub_opts, self.click_offset)
            sub.adb = self.adb; sub.image = self.image; sub.screen_size = self.screen_size
            sub._execute()
            self.victory_count += sub.victory_count
            self.failure_count += sub.failure_count
```

`sub_opts` 就是子策略的 `self.config`，所以子策略现有的 `self.config.get("ending_good")` 等读取方式**完全不需要改动**。

### FullAutoWindow 模式发现机制

弹窗从 `mode_config.json` 的 `modes` 字典读取所有模式，**按 `group` 字段自动分类**：

- `"group": "dynasty"` → 王朝模式区（单选 RadioButton）
- `"group": "chaolian"` → 超级联赛区（多选 CheckBox）

选项复选框也从 `mode_config.json` 的 `"options"` 数组动态生成，默认值取自 `"default"` 字段。

### 新增策略后需要改什么

假设新增了一个超联子模式 `chaolian_xxx`：

**必须改的：**

1. `core/strategies/__init__.py` — 导入类 + 加入 `STRATEGY_MAP`
2. `resources/config/mode_config.json` — 添加模式声明（`display_name`、`group`、`options`）

**不需要改的：**

- `core/strategies/full_auto.py` — 零改动。策略从 `STRATEGY_MAP[mode_id]` 动态查找，自动覆盖新模式。
- `ui/full_auto_window.py` — 零改动。弹窗从 `mode_config.json` 动态读取模式和选项，自动显示新模式。

### 修改现有策略选项后需要改什么

假设给 `chaolian_front` 新增一个选项 `"auto_restart"`：

**必须改的：**

1. `resources/config/mode_config.json` — 在对应模式的 `options` 数组中添加条目
2. 对应的策略文件 — 通过 `self.config.get("auto_restart")` 读取并使用

**不需要改的：**

- `ui/full_auto_window.py` — 零改动。弹窗的 `_rebuild_queue_ui()` 从 `mode_config.json` 动态读取 option 列表，自动显示新复选框。
- `core/strategies/full_auto.py` — 零改动。策略透传 `task["options"]` 字典给子策略，新 option 自动包含在内。
- `ui/main_window.py` — 主窗口的选项区也是从 `mode_config.json` 动态生成的，同样不需要改。

### 修改现有策略逻辑后需要改什么

假设修改了 `dynasty_33._execute()` 的内部逻辑：

**完全不需要改全自动相关文件。** `FullAutoTaskStrategy` 只负责按队列顺序调用 `sub._execute()`，不关心子策略内部实现。子策略的 `_execute()` 签名不变（无参数，通过 `self.config` 读取选项），即可直接兼容。

### 数据流总结

```
mode_config.json                    settings.json
      │                                   │
      │ mode_id + options 定义             │ full_auto_task.tasks (上次保存)
      ▼                                   ▼
FullAutoWindow.__init__(mode_config, saved_tasks)
      │
      │ 用户操作: 选模式 → 配选项 → 排序
      ▼
_collect_tasks() → task_list
      │
      ├── [保存配置] → callback_on_save → settings["full_auto_task"] = {"tasks": task_list}
      │
      └── [开始执行] → callback_on_start → Configured(FullAutoTaskStrategy, {"tasks": task_list})
                                                 └── StrategyManager.start()
                                                       └── FullAutoTaskStrategy._execute()
                                                             └── 遍历 task_list → sub._execute()
```

### 调试

- 如果全自动任务执行时跳过某个模式，检查日志中是否有 `"未知模式 xxx"` — 这表示该 `mode_id` 未在 `STRATEGY_MAP` 中注册。
- 如果弹窗中某个模式没有显示，检查 `mode_config.json` 中该模式的 `group` 字段是否为 `"dynasty"` 或 `"chaolian"` — `FullAutoWindow` 只识别这两个 group。

---

## 打包注意事项

### 打包命令

```bash
# 普通打包
python package.py --file main.py

# 包含 NVIDIA CUDA/cuDNN（仅在有 NVIDIA GPU 时需要）
python package.py --file main.py --nvidia
```

### 新增依赖后打包

如果添加了新的 pip 包，需要在 `package.py` 中添加对应的收集指令：

- Python 包（含数据文件）：`"--collect-all", "包名"`
- 仅动态库：`"--collect-binaries", "包名"`
- 同时在 `main.spec` 中同步更新

### 模型文件

RapidOCR 首次运行会自动下载 ONNX 模型到 `~/.rapidocr/`。如需将模型预打包到 exe，在 `package.py` 中已有相应逻辑（检测 `~/.rapidocr` 目录自动添加）。

### 模板图片路径

`base_strategy.py` 中 `_match_template()` 和 `_match_sift()` 使用 `resources/images/` 的相对路径。PyInstaller 打包时 `--add-data resources resources` 已包含此目录。**不要在策略中硬编码绝对路径。**

---

## 开发规范与最佳实践

### 1. 停止信号检查

**所有循环必须检查 `stop_event.is_set()`。** 使用 `_sleep()` 而非 `time.sleep()`，前者每 0.5s 检查一次停止信号。

```python
# ✅ 正确
while not stop_event.is_set():
    ...
    self._sleep(0.3)

# ❌ 错误
while True:
    ...
    time.sleep(0.3)  # 不响应停止信号
```

### 2. OCR 坐标

OCR 区域坐标使用 1280×720 设计分辨率。BaseStrategy 方法会自动缩放。

```python
# OCR 检测 "开始" 按钮，区域为 (700, 580, 120, 40)
if self._ocr((700, 580, 120, 40), "开始"):
    self._tap_with_offset(770, 600, offset=3)
```

### 3. 异步 OCR（推荐用于性能敏感场景）

```python
# 提交 OCR 请求
rid = self._ocr_area_async((700, 580, 120, 40))

# 稍后检查结果
result = self._ocr_result(rid)
if result is not None:
    # OCR 完成，处理结果
    ...
# else: OCR 还在推理中，下个循环再查
```

### 4. 模板匹配 vs SIFT 匹配

- **模板匹配** (`_match_template`)：目标位置固定、无旋转缩放。更快。
- **SIFT 匹配** (`_match_sift`)：目标有旋转/缩放/透视变化。更鲁棒但更慢。

```python
# 大厅检测：场景固定 → SIFT（鲁棒性优先）
pos = self._match_sift("begin.png", min_match=50)

# 按钮检测：位置固定 → 模板匹配（速度优先）
pos = self._match_template("ready.png", threshold=0.8)
```

### 5. 状态机模式

超联策略推荐使用 `self.status` 状态机而非深层嵌套 if-else。每个状态做一件事，状态切换清晰：

```python
if self.status == "FREE":
    # 寻找匹配
    ...
elif self.status == "MATCHING":
    # 等待匹配成功
    ...
elif self.status == "INNER":
    # 比赛中
    ...
```

### 6. 日志规范

```python
logger.info("关键状态变更")       # 用户关心的信息：进入比赛、比赛结束
logger.debug("循环内高频信息")     # 调试细节：点击坐标、匹配置信度
logger.warning("可恢复的异常")    # 卡死检测触发、连接重试
logger.error("影响执行的错误")    # 连接失败、OCR 失败、找不到目标
```

### 7. 卡死检测

使用 `BaseChaolianStrategy` 内置的卡死检测：

```python
self._init_stuck_detection()
while not stop_event.is_set():
    ...
    self.status = new_status  # status 赋值即触发了计时更新
    if self._is_stuck(timeout=120):
        logger.warning("卡死，退出当前循环")
        break
```

### 8. 线程安全

- **工作线程**（策略执行）：可以调用任意 BaseStrategy 方法，通过 log queue 安全写日志
- **不要直接操作 Tkinter 组件**：UI 更新必须通过 `self.after(0, callback)` 回主线程
- **全局单例**：`image_service`、`logger` 是模块级单例，线程安全

### 9. 坐标偏移

```python
self._tap_with_offset(x, y, offset=3)   # ±3px 随机偏移
self._tap_with_offset(x, y, offset=1)   # ±1px 精确点击（导航用）
self._tap_with_offset(x, y, offset=30)  # ±30px 大范围随机（防检测）
```

### 10. 比赛计数

```python
self._setup_match_count()              # 初始化 match_count=0
# self.change_count = 1  if config.only_thirty_match else 0

# 每场比赛结束时
self.match_count += self.change_count
if self.match_count >= 30:
    logger.info("已达到30场比赛，退出循环")
    break
```
