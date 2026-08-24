from __future__ import annotations

import logging

import uvicorn

from .app import PanelConfig, create_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    config = PanelConfig()
    uvicorn.run(
        create_app(panel_config=config),
        host="0.0.0.0",
        port=config.port,
    )


if __name__ == "__main__":
    main()
