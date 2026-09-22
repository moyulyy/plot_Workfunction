# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— WF · 功函数绘图工作台（Windows 便携版）

构建：
    pyinstaller --noconfirm --clean WF-Viewer.spec

产物：
    dist/WF-Viewer/WF-Viewer.exe      ← 双击即可运行
    dist/WF-Viewer/_internal/         ← 运行时依赖（Qt / matplotlib / numpy）

打包后程序的目录约定（见 wf_viewer.py 顶部 APP_DIR / RES_DIR）：
    APP_DIR = exe 所在目录      —— 保存图片、运行期生成 assets/app.ico
    RES_DIR = sys._MEIPASS      —— 打包进来的只读资源（assets/）
"""

from pathlib import Path

ROOT = Path(SPECPATH)

# 只读资源：程序图标（运行期若 exe 同级缺失 assets/app.ico 会自动重建）
datas = [
    (str(ROOT / "assets" / "app.ico"), "assets"),
]

hiddenimports = [
    # Qt 相关（部分为动态插件/后端，显式声明更稳）
    "PySide6.QtSvg",
    "PySide6.QtPrintSupport",
    # matplotlib 的 Qt / Agg 后端
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_agg",
]

a = Analysis(
    [str(ROOT / "wf_viewer.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PyQt5", "PyQt6", "PySide2",
        "IPython", "jupyter", "notebook", "pytest",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WF-Viewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # 无控制台窗口（GUI 程序）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="WF-Viewer",
)
