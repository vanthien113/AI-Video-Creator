"""Entry point: `python -m app` from the backend folder."""

import uvicorn

from .config import load_config
from .main import create_app

if __name__ == "__main__":
    config = load_config()
    print(f"AI Video Creator: http://127.0.0.1:{config.server.port}")
    # SSE streams never end on their own; do not wait for them forever on Ctrl+C.
    uvicorn.run(create_app(config), host="127.0.0.1", port=config.server.port, log_level="warning",
                timeout_graceful_shutdown=3)
