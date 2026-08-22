"""Shared entry point for both deployment modes: `python3 -m app`.

The Dockerfile's `CMD` and the systemd unit under `deploy/systemd/` both
call this module, so a single code path reads `PLD_HOST` / `PLD_PORT` (see
config.py) regardless of whether the process is inside a container or
running natively on a Linux VM. Previously these two environment variables
were defined in config.py but never actually consumed anywhere - the
Docker `CMD` hardcoded `--host`/`--port` flags on the uvicorn command
line instead, so setting `PLD_PORT` had no effect. This module fixes that:
set the environment variable once, and both Docker and native runs honour
it.
"""
import uvicorn

from . import config


def main() -> None:
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
