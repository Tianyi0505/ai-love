from __future__ import annotations

import logging
import os

import uvicorn

from shared.infrastructure.runtime_config import required_value

from .app import create_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    port = int(required_value(os.environ.get("PANEL_PORT"), "PANEL_PORT"))
    uvicorn.run(create_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
