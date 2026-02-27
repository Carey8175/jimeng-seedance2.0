import datetime
import os
import uuid
from pathlib import Path

from loguru import logger
import tos
from fastapi import FastAPI, HTTPException
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
import uvicorn

app = FastAPI()


def parse_cookies(cookie_header: str, domain: str) -> list[dict]:
    cookies = []
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": "/",
            }
        )
    return cookies


def get_tos_client() -> tos.TosClientV2:
    access_key = os.getenv("TOS_ACCESS_KEY")
    secret_key = os.getenv("TOS_SECRET_KEY")
    endpoint = os.getenv("TOS_ENDPOINT", "tos-ap-southeast-1.bytepluses.com")
    region = os.getenv("TOS_REGION", "ap-southeast-1")
    if not access_key or not secret_key:
        raise ValueError("TOS_ACCESS_KEY and TOS_SECRET_KEY must be set")
    return tos.TosClientV2(access_key, secret_key, endpoint, region)


def build_object_key(file_path: Path, prefix: str) -> str:
    date_str = datetime.date.today().isoformat()
    return f"{prefix}/{date_str}/{uuid.uuid4().hex}{file_path.suffix}"


def upload_file_to_tos(file_path: Path, object_key: str | None = None) -> str:
    client = get_tos_client()
    bucket_name = os.getenv("TOS_BUCKET_NAME")
    endpoint = os.getenv("TOS_ENDPOINT", "tos-ap-southeast-1.bytepluses.com")
    if not bucket_name:
        raise ValueError("TOS_BUCKET_NAME must be set")
    if object_key is None:
        object_key = build_object_key(file_path, "jimeng")
    with file_path.open("rb") as file_obj:
        client.put_object(bucket_name, object_key, content=file_obj)
    return f"https://{bucket_name}.{endpoint}/{object_key}"


async def capture_screenshot() -> Path:
    base_dir = Path(__file__).resolve().parent
    cookies_path = base_dir.parent / "cookies.txt"
    output_dir = base_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = output_dir / f"jimeng_{uuid.uuid4().hex}.png"
    url = "https://jimeng.jianying.com/ai-tool/generate?type=video"

    if not cookies_path.exists():
        raise FileNotFoundError("cookies.txt not found")

    cookie_header = cookies_path.read_text(encoding="utf-8").strip()
    cookies = parse_cookies(cookie_header, ".jianying.com")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        if cookies:
            await context.add_cookies(cookies)
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
        except PlaywrightTimeoutError:
            logger.warning("networkidle timeout, retry with domcontentloaded")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(screenshot_path), full_page=True)
        await context.close()
        await browser.close()

    logger.info("screenshot saved: {}", screenshot_path)
    return screenshot_path


@app.post("/capture")
async def capture() -> dict:
    try:
        screenshot_path = await capture_screenshot()
        url = upload_file_to_tos(screenshot_path)
        return {"url": url}
    except FileNotFoundError as exc:
        logger.exception("capture failed: missing file")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing file",
                "exception": type(exc).__name__,
                "message": str(exc),
            },
        ) from exc
    except ValueError as exc:
        logger.exception("capture failed: invalid config")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid config",
                "exception": type(exc).__name__,
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        logger.exception("capture failed: unexpected error")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "capture failed",
                "exception": type(exc).__name__,
                "message": str(exc),
            },
        ) from exc


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
