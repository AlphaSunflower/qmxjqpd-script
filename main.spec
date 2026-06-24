# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs
import os

import glob

datas = [('config', 'config'), ('resources', 'resources')]
binaries = []
hiddenimports = ['onnxruntime']

# Tcl/Tk support + system DLLs (Anaconda)
_conda_prefix = os.environ.get('CONDA_PREFIX', r'D:\ProgramData\anaconda3')
_conda_lib = os.path.join(_conda_prefix, 'Library')
_conda_bin = os.path.join(_conda_lib, 'bin')

# Tcl/Tk core DLLs
binaries += [
    (os.path.join(_conda_bin, 'tcl86t.dll'), '.'),
    (os.path.join(_conda_bin, 'tk86t.dll'), '.'),
]
# Tcl/Tk scripts
datas += [
    (os.path.join(_conda_lib, 'lib', 'tcl8'), 'tcl8'),
    (os.path.join(_conda_lib, 'lib', 'tcl8.6'), 'tcl8.6'),
    (os.path.join(_conda_lib, 'lib', 'tk8.6'), 'tk8.6'),
]

# Anaconda system DLLs missing from PyInstaller detection
_sys_dlls = [
    'ffi.dll',                            # _ctypes
    'libcrypto-3-x64.dll', 'libssl-3-x64.dll',  # _hashlib, _ssl
    'libmpdec-4.dll',                      # _decimal
    'libexpat.dll',                        # pyexpat
    'liblzma.dll',                         # _lzma
    'libbz2.dll',                          # _bz2
]
for _dll in _sys_dlls:
    _dll_path = os.path.join(_conda_bin, _dll)
    if os.path.exists(_dll_path):
        binaries += [(_dll_path, '.')]
tmp_ret = collect_all('cv2')
datas += [(src, dst) for src, dst in tmp_ret[0] if 'cv2/data' not in src]
binaries += [(src, dst) for src, dst in tmp_ret[1] if 'opencv_videoio_ffmpeg' not in src]
hiddenimports += tmp_ret[2]
tmp_ret = collect_all('rapidocr_onnxruntime')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='main',
)
