# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:\\AI_video_render\\AI_video_render\\desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[('D:\\AI_video_render\\AI_video_render\\ui', 'ui'), ('D:\\AI_video_render\\AI_video_render\\config', 'config'), ('D:\\AI_video_render\\AI_video_render\\publishers', 'publishers'), ('D:\\AI_video_render\\AI_video_render\\core', 'core'), ('D:\\AI_video_render\\AI_video_render\\version.py', '.')],
    hiddenimports=['uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'fastapi'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pythonnet', 'clr', 'clr_loader', 'webview'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VeoStudioAI',
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
    name='VeoStudioAI',
)
