# 全明星街球派对自动化脚本

> 基于 ADB 的 Android 模拟器自动化工具，为手游《全明星街球派对》提供多模式自动挂机功能。

## 支持的游戏模式

| 模式 | 说明 |
|------|------|
| 季前赛 | 自动匹配、执行战术、处理结算 |
| 挑战赛 | 支持国际服匹配、自动策略执行 |
| 天梯赛 | 自动排位、战术执行 |
| 王朝 3v3 | 3v3 模式自动挂机 |
| 王朝 5v5 | 5v5 全场争霸自动挂机 |
| 王朝综合 | 3v3 + 5v5 综合模式 |
| 全自动 | 按队列依次执行多个模式，支持自定义任务列表 |

## 功能特性

- **多设备并行**：支持同时控制多个 ADB 端口（模拟器实例）
- **屏幕识别**：RapidOCR (ONNX) + OpenCV 模板匹配 + SIFT 特征匹配
- **自动决策**：根据屏幕状态自动执行点击、滑动等操作
- **CPU 限流**：可设置 CPU 占用阈值，超限时自动暂停
- **午夜执行**：支持设定午夜自动开始执行
- **GUI 界面**：基于 customtkinter 的现代化界面，实时日志显示
- **自动重连**：ADB 连接断开时自动重试

## 环境要求

- **Python** 3.10+
- **ADB**：需要安装 Android Debug Bridge 并加入系统 PATH
- **Android 模拟器**：雷电模拟器、夜神模拟器等（需开启 ADB 调试）
- **模拟器分辨率**：建议设置为 1280×720（脚本坐标基于此分辨率设计，会自动缩放适配）

## 安装

```bash
# 克隆仓库
git clone https://github.com/Stu-Wcy/qmxjqpd-script.git
cd qmxjqpd-script

# 创建虚拟环境
python -m venv myenv
source myenv/Scripts/activate  # Windows Git Bash
# 或
myenv\Scripts\activate.bat     # Windows CMD

# 安装依赖
pip install -r requirements.txt

# 复制配置模板
cp config/settings.example.json config/settings.json
```

## 使用

```bash
# 启动 GUI
python main.py
```

1. 在界面中选择游戏模式
2. 配置 ADB 端口（默认 16384，即雷电模拟器默认端口）
3. 点击「开始执行」
4. 脚本将自动控制模拟器完成对局

### ADB 端口说明

| 模拟器 | 默认端口 |
|--------|----------|
| 雷电模拟器 | 16384 (第一个实例), 16416, 16448 ... |
| 夜神模拟器 | 62001, 62025 ... |
| MuMu 模拟器 | 7555 |

## 打包为 EXE

```bash
# 标准打包
python package.py --file main.py

# 包含 NVIDIA CUDA/cuDNN 支持
python package.py --file main.py --nvidia
```

打包产物位于 `dist/` 目录。

## 项目结构

```
main.py                          # 入口文件
├── ui/                          # GUI 界面
│   ├── main_window.py           #   主窗口（模式选择、端口配置、日志）
│   └── full_auto_window.py      #   全自动任务配置对话框
├── core/                        # 核心逻辑
│   ├── base_strategy.py         #   策略基类（ADB 操作、OCR、模板匹配）
│   ├── strategy_manager.py      #   线程管理器
│   └── strategies/              #   各模式策略实现
├── services/                    # 服务层
│   ├── adb_service.py           #   ADB 封装
│   ├── image_service.py         #   图像识别（OpenCV + RapidOCR）
│   └── logger_service.py        #   日志服务
├── config/                      # 配置
│   └── settings.example.json    #   用户配置模板
├── resources/
│   ├── config/mode_config.json  #   模式声明与选项
│   └── images/                  #   模板图片
└── docs/DEVELOPMENT_GUIDE.md    # 开发指南
```

## 开发

详见 [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md)。

### 添加新模式

1. 在 `core/strategies/` 下新建策略类，继承 `BaseStrategy`
2. 在 `core/strategies/__init__.py` 的 `STRATEGY_MAP` 中注册
3. 在 `resources/config/mode_config.json` 中添加模式配置

### 坐标系统

所有点击/滑动坐标基于 **1280×720** 分辨率设计。`BaseStrategy` 会根据设备实际分辨率自动缩放，无需手动适配。

## 许可证

[MIT License](LICENSE) - Copyright (c) 2026 魏辰益
