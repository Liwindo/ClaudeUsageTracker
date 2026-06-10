# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[('src/claude_usage_monitor', 'claude_usage_monitor')],
    # plyer loads its platform backend dynamically (plyer.platforms.win.*),
    # which PyInstaller cannot trace — without the explicit hiddenimport the
    # frozen EXE logs "No usable implementation found!" and desktop
    # notifications silently do nothing.
    hiddenimports=[
        'pystray._win32',
        'PIL._tkinter_finder',
        'plyer.platforms.win.notification',
    ],
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
    name='ClaudeUsageTracker',
    icon='src/claude_usage_monitor/assets/logo.ico',
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
