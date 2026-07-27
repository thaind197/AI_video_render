# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Veo Studio AI PRO Server
# Build command: pyinstaller build.spec

import os
import sys
from pathlib import Path

block_cipher = None

# Project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    ['server.py'],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        # Include UI static files
        ('ui', 'ui'),
        # Include config module
        ('config', 'config'),
        # Include .env.example as template
        ('.env.example', '.'),
    ],
    hiddenimports=[
        # FastAPI & Uvicorn
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'fastapi',
        'fastapi.staticfiles',
        'fastapi.middleware.cors',
        'fastapi.responses',
        'pydantic',
        'starlette',
        'starlette.routing',
        'starlette.middleware',
        'starlette.staticfiles',
        'anyio',
        'anyio._backends',
        'anyio._backends._asyncio',
        # Google AI
        'google.genai',
        'google.generativeai',
        # Database
        'sqlalchemy',
        'sqlite3',
        # Media processing
        'ffmpeg',
        'imageio_ffmpeg',
        'edge_tts',
        # Other deps
        'yt_dlp',
        'dotenv',
        'rich',
        'PIL',
        # Project modules
        'core',
        'core.db',
        'core.script_engine',
        'core.veo_generator',
        'core.video_cloner',
        'core.video_processor',
        'publishers',
        'publishers.base_publisher',
        'publishers.facebook_publisher',
        'publishers.tiktok_publisher',
        'publishers.x_publisher',
        'publishers.fb_profile_manager',
        'publishers.tiktok_profile_manager',
        'queue_manager',
        '_login_browser',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy.testing',
        'scipy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VeoStudioServer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Console app for server logging
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VeoStudioServer',
)
