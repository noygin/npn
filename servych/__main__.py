import logging

import uvicorn

from servych.app import create_app
from servych.config import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # httpx пишет в лог адреса панелей вместе с секретными путями
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings()
    uvicorn.run(
        create_app(settings), host=settings.servych_host, port=settings.servych_port,
        proxy_headers=True, log_level="info",
    )


if __name__ == "__main__":
    main()
