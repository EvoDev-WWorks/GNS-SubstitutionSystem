# GNS Substitution System — PyInstaller Spec

import sys
import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas_ortools,   binaries_ortools,   hiddenimports_ortools   = collect_all('ortools')
datas_fastapi,   binaries_fastapi,   hiddenimports_fastapi   = collect_all('fastapi')
datas_uvicorn,   binaries_uvicorn,   hiddenimports_uvicorn   = collect_all('uvicorn')
datas_webview,   binaries_webview,   hiddenimports_webview   = collect_all('webview')
datas_pydantic,  binaries_pydantic,  hiddenimports_pydantic  = collect_all('pydantic')
datas_anyio,     binaries_anyio,     hiddenimports_anyio     = collect_all('anyio')
datas_starlette, binaries_starlette, hiddenimports_starlette = collect_all('starlette')

a = Analysis(
    ['launch.py'],
    pathex=['.'],
    binaries=(
        binaries_ortools +
        binaries_fastapi +
        binaries_uvicorn +
        binaries_webview +
        binaries_pydantic +
        binaries_anyio +
        binaries_starlette
    ),
    datas=(
        datas_ortools +
        datas_fastapi +
        datas_uvicorn +
        datas_webview +
        datas_pydantic +
        datas_anyio +
        datas_starlette +
        [('.env', '.')]
    ),
    hiddenimports=(
        hiddenimports_ortools +
        hiddenimports_fastapi +
        hiddenimports_uvicorn +
        hiddenimports_webview +
        hiddenimports_pydantic +
        hiddenimports_anyio +
        hiddenimports_starlette +
        [
            'ortools.sat.python.cp_model',
            'ortools.sat.python._pywrapsat',
            'uvicorn.logging',
            'uvicorn.loops',
            'uvicorn.loops.auto',
            'uvicorn.loops.asyncio',
            'uvicorn.protocols',
            'uvicorn.protocols.http',
            'uvicorn.protocols.http.auto',
            'uvicorn.protocols.http.h11_impl',
            'uvicorn.protocols.websockets',
            'uvicorn.protocols.websockets.auto',
            'uvicorn.lifespan',
            'uvicorn.lifespan.on',
            'fastapi.applications',
            'fastapi.routing',
            'fastapi.middleware.cors',
            'pydantic',
            'pydantic.v1',
            'anyio',
            'anyio._backends._asyncio',
            'starlette',
            'starlette.middleware',
            'starlette.middleware.cors',
            'httpx',
            'h11',
            'h2',
            'hpack',
            'hyperframe',
            'email.mime',
            'email.mime.text',
            'email.mime.multipart',
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='GNS-SubstitutionSystem',
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GNS-SubstitutionSystem',
)
