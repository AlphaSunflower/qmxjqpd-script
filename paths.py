import sys
import os

# 兼容开发环境和 PyInstaller 打包后的运行路径
if getattr(sys, 'frozen', False):
    # 打包后: sys._MEIPASS 是 PyInstaller 的临时解压目录（只读）
    _base = sys._MEIPASS
    # 保存配置到用户可写目录，而非 _MEIPASS
    _save_base = os.path.join(os.path.expanduser('~'), '.qmxChaoLian')
else:
    # 开发环境: 以 main.py 所在目录为基准
    _base = os.path.dirname(os.path.abspath(__file__))
    _save_base = _base


def resource_path(relative_path: str) -> str:
    """返回资源文件的绝对路径，兼容开发/打包两种模式"""
    return os.path.join(_base, relative_path)


def save_path(filename: str) -> str:
    """返回可写的保存路径（打包后指向用户目录）"""
    return os.path.join(_save_base, filename)


# 配置文件路径（只读，读取资源）
CONFIG_PATH = resource_path(os.path.join('config', 'settings.json'))
MODE_CONFIG_PATH = resource_path(os.path.join('resources', 'config', 'mode_config.json'))
