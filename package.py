import os
import sys
import argparse
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--file', required=True, help='Your file name, e.g. main.py.')
parser.add_argument('--nvidia', action='store_true', help='Include NVIDIA CUDA and cuDNN dependencies.')

args = parser.parse_args()

spec_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.spec")

cmd = ["pyinstaller", spec_file]

if args.nvidia:
    cmd += ["--collect-binaries", "nvidia"]

print("PyInstaller command:", " ".join(cmd))

try:
    result = subprocess.run(cmd, check=True)
except subprocess.CalledProcessError as e:
    print("Installation failed:", e)
    sys.exit(1)