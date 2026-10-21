"""Desktop entrypoint: starts the Streamlit dashboard in-process and opens the browser.

Used by the PyInstaller build (see GaliciaOptions.spec). Also works unfrozen:
    conda run -n py4fi python launcher.py
"""
import socket
import sys
from pathlib import Path

from dotenv import load_dotenv

FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
# Credentials live next to the executable so users can edit .env without rebuilding.
USER_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent


def free_port(preferred=8501):
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return sock.getsockname()[1]


def selftest():
    """Import every dashboard module so a frozen build can prove nothing is missing."""
    import plotly.express  # noqa: F401
    import dashboard_ui  # noqa: F401
    import streamlit.web.bootstrap  # noqa: F401
    for name in ("app.py", "docs/GALICIA_VOLATILITY_RESEARCH.md", "docs/GALICIA_ADR_VOLATILITY_RESEARCH.md"):
        assert (BUNDLE_DIR / name).is_file(), name
    print("selftest ok")


def main():
    if "--selftest" in sys.argv:
        return selftest()
    load_dotenv(USER_DIR / ".env")
    from streamlit.web import bootstrap

    options = {
        "server.address": "127.0.0.1",
        "server.port": free_port(),
        "server.headless": False,  # lets Streamlit open the default browser
        "server.fileWatcherType": "none",
        "browser.gatherUsageStats": False,
        "global.developmentMode": False,
    }
    bootstrap.load_config_options(options)
    bootstrap.run(str(BUNDLE_DIR / "app.py"), False, [], options)


if __name__ == "__main__":
    main()
