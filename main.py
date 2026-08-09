from pathlib import Path
import sys
import uvicorn

# Add src to sys.path
_src_path = str(Path(__file__).resolve().parent / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from app.main import app  # noqa: E402, F401

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True, app_dir="src")
