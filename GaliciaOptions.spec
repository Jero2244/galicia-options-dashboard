# PyInstaller spec. Build with build_exe.bat.
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = [("app.py", "."), ("docs/GALICIA_VOLATILITY_RESEARCH.md", "docs"), ("docs/GALICIA_ADR_VOLATILITY_RESEARCH.md", "docs")]
binaries = []
hiddenimports = [
    # Imported by app.py at run time, which PyInstaller's analysis cannot see.
    "dashboard_ui", "dashboard_data", "alpaca_data", "byma_data", "analytics_ui",
    "option_analytics", "volatility_ui", "volatility_index", "adr_volatility",
    "adr_volatility_ui", "funding_ui", "funding_curve",
]
for package in ("streamlit", "plotly", "tzdata"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
# Jupyter lab extension assets are unused outside notebooks.
datas = [d for d in datas if "labextension" not in d[0].replace("\\", "/")]
for dist in ("streamlit", "pandas", "requests", "python-dotenv"):
    datas += copy_metadata(dist)

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "IPython", "matplotlib", "tkinter", "tensorflow", "torch", "scipy", "sklearn", "numba"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="GaliciaOptions",
    console=True,  # keep the console so server logs and errors stay visible
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="GaliciaOptions")
