import json
import os
from urllib import request

from loguru import logger


def main() -> None:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    url = f"{base_url}/capture"
    req = request.Request(url, method="POST")
    try:
        with request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            logger.info("status: {}", resp.status)
            logger.info("response: {}", body)
            data = json.loads(body)
            logger.info("url: {}", data.get("url"))
    except Exception as exc:
        logger.exception("request failed")
        raise exc


if __name__ == "__main__":
    main()
