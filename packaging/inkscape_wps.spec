from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path.cwd()

datas = collect_data_files("inkscape_wps")
datas += collect_data_files("qfluentwidgets")

hiddenimports = []
hiddenimports += collect_submodules("qfluentwidgets")
hiddenimports += collect_submodules("PyQt5")
hiddenimports += collect_submodules("PyQt6")


a = Analysis(
    [str(project_root / "inkscape_wps" / "__main__.py")],
    pathex=[str(project_root)],
    binaries=[],
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
    a.binaries,
    a.datas,
    [],
    name="inkscape-wps",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    name="inkscape-wps.app",
    icon=None,
    bundle_identifier="com.inkscape_wps.app",
)
