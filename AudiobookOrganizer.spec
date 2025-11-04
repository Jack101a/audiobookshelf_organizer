# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import copy_metadata

datas = [('config.json', '.'), ('DejaVuSans.ttf', '.'), ('app.py', '.'), ('audible_client.py', '.'), ('config_loader.py', '.'), ('file_manager.py', '.'), ('logger.py', '.'), ('main.py', '.'), ('metadata_writer.py', '.'), ('tag_reader.py', '.'), ('utils.py', '.')]
datas += copy_metadata('streamlit')
datas += copy_metadata('altair')
datas += copy_metadata('pandas')
datas += copy_metadata('pillow')
datas += copy_metadata('PyQt5')
datas += copy_metadata('qtpy')


a = Analysis(
    ['run_app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['_cffi_backend'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['boto3', 'botocore', 'snowflake-connector-python', 'scipy'],
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
    name='AudiobookOrganizer',
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
