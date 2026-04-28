import os
import sys
import argparse
import subprocess

from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--file', required=True, help='Your file name, e.g. main.py.')
parser.add_argument('--nvidia', action='store_true', help='Include NVIDIA CUDA and cuDNN dependencies.')

args = parser.parse_args()

main_file = args.file

# 检查 RapidOCR 模型是否已下载
model_cache = Path.home() / '.rapidocr'
if not model_cache.exists():
    print(f"提示: 未找到 RapidOCR 模型缓存目录 ({model_cache})")
    print("首次运行时 RapidOCR 会自动下载模型（约 10-20 MB）。")
else:
    print(f"找到模型缓存目录: {model_cache}")
    size = sum(f.stat().st_size for f in model_cache.rglob('*') if f.is_file())
    print(f"  模型大小: {size / 1024 / 1024:.1f} MB")

cmd = [
    "pyinstaller",
    "-w",
    main_file,
    "--add-data", f"config{os.pathsep}config",
    "--add-data", f"resources{os.pathsep}resources",
    "--collect-all", "cv2",
    "--collect-all", "rapidocr_onnxruntime",
    "--collect-binaries", "onnxruntime",
]

# 将 RapidOCR 模型打包进 exe（如果已下载）
if model_cache.exists():
    cmd += ["--add-data", f"{model_cache}{os.pathsep}.rapidocr"]
    print("已添加 RapidOCR 模型文件到打包列表。")

if args.nvidia:
    cmd += ["--collect-binaries", "nvidia"]

print("PyInstaller command:", " ".join(cmd))

try:
    result = subprocess.run(cmd, check=True)
except subprocess.CalledProcessError as e:
    print("Installation failed:", e)
    sys.exit(1)