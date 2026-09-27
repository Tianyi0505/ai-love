from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import signal
from pathlib import Path

from .host import PluginHost


async def run(role: str, roots: list[Path], state: Path) -> None:
    from shared.nats_bus import create_bus
    from shared.telemetry_runtime import TelemetryRuntime

    host = PluginHost(
        role,
        roots=roots,
        state_directory=state,
        bus=create_bus(os.environ["AILOVE_BUS_URL"], os.getenv("AILOVE_BUS_TOKEN")),
    )
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stopped.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stopped.set))
    telemetry = TelemetryRuntime(role)
    telemetry.start()
    try:
        await host.start()
        await stopped.wait()
    finally:
        try:
            if host.manager is not None:
                await host.close()
        finally:
            telemetry.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-Love 通用插件宿主")
    parser.add_argument("--role", required=True)
    parser.add_argument(
        "--catalog", action="append", type=Path, help="本地 plugin.json 父目录；可重复指定。显式指定会替代内置目录。"
    )
    parser.add_argument(
        "--state-directory", type=Path, default=Path(os.getenv("AILOVE_PLUGIN_STATE_DIR", "data/plugins"))
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", args.role):
        parser.error("无效宿主名称")
    roots = args.catalog or [Path(__file__).resolve().parents[1] / "plugins" / "catalog"]
    roots += [Path(path) for path in os.getenv("AILOVE_PLUGIN_PATH", "").split(os.pathsep) if path]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(run(args.role, roots, args.state_directory))


if __name__ == "__main__":
    main()
