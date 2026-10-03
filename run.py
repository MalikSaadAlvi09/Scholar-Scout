"""
ScholarScout - Single Command Application Launcher for Windows & Local Systems.
Starts the FastAPI server, initializes SQLite tables, and activates the persistent worker.
"""

import sys
import webbrowser
import uvicorn
from backend.config import config
from backend.logging_utils import logger

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def main():
    url = f"http://{config.app_host}:{config.app_port}"
    print("=" * 70)
    print("SCHOLARSCOUT - Academic Funding & Faculty Research Agent")
    print(f"Running locally on: {url}")
    print(f"SQLite Database:    {config.database_path}")
    print(f"LLM Model:         {config.model_name}")
    print("=" * 70)
    print("Starting background services and web server...\n")

    # Launch uvicorn server
    uvicorn.run(
        "backend.main:app",
        host=config.app_host,
        port=config.app_port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
