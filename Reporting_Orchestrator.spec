# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['orchestrator.py'],
    pathex=[],
    binaries=[],
    datas=[('Workday_Report_Discovery_Agent/static', 'Workday_Report_Discovery_Agent/static'), ('Workday_Report_Discovery_Agent/data', 'Workday_Report_Discovery_Agent/data'), ('Workday_Report_Discovery_Agent/prompts', 'Workday_Report_Discovery_Agent/prompts')],
    hiddenimports=[],
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
    name='Reporting_Orchestrator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
