#!/usr/bin/env python3
"""
抖音无水印下载服务 - FastAPI 后端
SSR 直连解析: window._ROUTER_DATA
"""

import json
import logging
import re
import time
from collections import defaultdict
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI(title="Douyin Parser")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# ─── 日志配置 ───
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logger = logging.getLogger("douyin_parse")
logger.setLevel(logging.DEBUG)
fh = RotatingFileHandler(
    LOG_DIR / "parse.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)

# ─── 简易速率限制 ───
_rate_limit = defaultdict(list)
RATE_LIMIT = 10
RATE_WINDOW = 60


def check_rate_limit(ip: str) -> bool:
    now = time.time()
    _rate_limit[ip] = [t for t in _rate_limit[ip] if now - t < RATE_WINDOW]
    if len(_rate_limit[ip]) >= RATE_LIMIT:
        return False
    _rate_limit[ip].append(now)
    return True


# ─── URL 提取 ───
def extract_douyin_url(text: str) -> str:
    """从分享文本中提取抖音 URL"""
    patterns = [
        r'(https?://[^\s<>"{}|\\^`\[\]]*v\.douyin\.com[^\s<>"{}|\\^`\[\]]*)',
        r'(https?://[^\s<>"{}|\\^`\[\]]*iesdouyin\.com[^\s<>"{}|\\^`\[\]]*)',
        r'(https?://[^\s<>"{}|\\^`\[\]]*douyin\.com/video[^\s<>"{}|\\^`\[\]]*)',
        r'(https?://[^\s<>"{}|\\^`\[\]]*douyin\.com/note[^\s<>"{}|\\^`\[\]]*)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return text.strip()


def parse_aweme_id(url: str) -> str | None:
    """从 URL 中提取作品 ID"""
    # www.douyin.com/video/7xxxxx
    m = re.search(r'/video/(\d+)', url)
    if m:
        return m.group(1)
    # www.douyin.com/note/7xxxxx（图文）
    m = re.search(r'/note/(\d+)', url)
    if m:
        return m.group(1)
    # iesdouyin.com/share/video/7xxxxx/
    m = re.search(r'/share/video/(\d+)', url)
    if m:
        return m.group(1)
    return None


# ─── SSR 解析 ───
async def fetch_with_redirect(url: str) -> tuple[str, str]:
    """跟随短链接重定向，转为 iesdouyin 分享页获取 SSR 数据"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 "
                      "Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.douyin.com/",
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as c:
        r = await c.get(url, headers=headers)
        final_url = str(r.url)
        # douyin.com 主页返回混淆 JS，需转为 iesdouyin 分享页
        aweme_id = parse_aweme_id(final_url)
        if aweme_id:
            # 判断是视频还是图文
            is_note = "note" in final_url
            share_url = f"https://www.iesdouyin.com/share/note/{aweme_id}/" if is_note else f"https://www.iesdouyin.com/share/video/{aweme_id}/"
            r2 = await c.get(share_url, headers=headers)
            return share_url, r2.text
        return final_url, r.text


def extract_router_data(html: str) -> dict | None:
    """从页面 HTML 中提取 window._ROUTER_DATA JSON"""
    marker = "window._ROUTER_DATA"
    pos = html.find(marker)
    if pos == -1:
        # 回退：尝试 __INITIAL_STATE__
        marker = "__INITIAL_STATE__"
        pos = html.find(marker)
        if pos == -1:
            return None

    start = html.index("{", pos)
    end_tag = html.index("</script>", start)
    js_str = html[start:end_tag]

    # JS → JSON 转换
    js_str = re.sub(r'\bundefined\b', 'null', js_str)
    js_str = re.sub(r'\bNaN\b', 'null', js_str)
    js_str = re.sub(r',\s*}', '}', js_str)
    js_str = re.sub(r',\s*]', ']', js_str)

    try:
        return json.loads(js_str)
    except json.JSONDecodeError:
        return None


def find_aweme_item(data: dict) -> dict | None:
    """在 _ROUTER_DATA 中查找作品数据（支持视频和图文两种路径）"""
    if not data or not isinstance(data, dict):
        return None

    # 视频: loaderData["video_(id)/page"]["videoInfoRes"]["item_list"][0]
    # 图文: loaderData["note_(id)/page"]["videoInfoRes"]["item_list"][0]
    for page_key in ("video_(id)/page", "note_(id)/page"):
        try:
            item = data["loaderData"][page_key]["videoInfoRes"]["item_list"][0]
            if isinstance(item, dict):
                return item
        except (KeyError, TypeError, IndexError):
            pass

    # 递归兜底查找 item_list
    def search_item_list(obj, depth=0):
        if depth > 5 or not isinstance(obj, dict):
            return None
        if "item_list" in obj:
            il = obj["item_list"]
            if isinstance(il, list) and len(il) > 0 and isinstance(il[0], dict):
                return il[0]
        for v in obj.values():
            if isinstance(v, dict):
                found = search_item_list(v, depth + 1)
                if found:
                    return found
        return None

    return search_item_list(data)


def build_video_url(item: dict) -> str | None:
    """构建无水印视频 URL"""
    video = item.get("video", {})
    if not video:
        return None

    # 优先：play_addr.uri → 构建无水印 URL
    uri = video.get("play_addr", {}).get("uri", "")
    if uri:
        return f"https://www.douyin.com/aweme/v1/play/?video_id={uri}"

    # 备用：play_addr.url_list，替换 playwm → play
    url_list = video.get("play_addr", {}).get("url_list", [])
    for u in url_list:
        if isinstance(u, str):
            return u.replace("playwm", "play")

    # 备用：bit_rate
    bit_rate = video.get("bit_rate", [])
    if isinstance(bit_rate, list) and len(bit_rate) > 0:
        pa = bit_rate[0].get("play_addr", {})
        urls = pa.get("url_list", [])
        for u in urls:
            if isinstance(u, str):
                return u.replace("playwm", "play")

    return None


def extract_images(item: dict) -> list[str]:
    """提取图片列表"""
    images = []
    img_list = item.get("images", [])
    if not isinstance(img_list, list):
        return images
    for img in img_list:
        if not isinstance(img, dict):
            continue
        url_list = img.get("url_list", [])
        if isinstance(url_list, list) and len(url_list) > 0:
            url = url_list[0]
            if isinstance(url, str) and url.startswith("http"):
                images.append(url)
        elif isinstance(img.get("url_list"), str):
            images.append(img["url_list"])
    return images


async def parse_douyin(url: str) -> tuple[dict | None, str]:
    """SSR 直连解析"""
    aweme_id = parse_aweme_id(url) or "unknown"
    t0 = time.monotonic()
    logger.info("开始解析 aweme_id=%s url=%s", aweme_id, url)

    try:
        final_url, html = await fetch_with_redirect(url)

        # 如果输入未提取到 ID，从重定向 URL 提取
        if aweme_id == "unknown":
            aweme_id = parse_aweme_id(final_url) or "unknown"

        router_data = extract_router_data(html)
        if not router_data:
            logger.warning("未找到 _ROUTER_DATA aweme_id=%s", aweme_id)
            return None, "未找到页面数据"

        item = find_aweme_item(router_data)
        if not item:
            return None, "未找到作品数据"

        result = {
            "title": item.get("desc") or "抖音作品",
            "author": item.get("author", {}).get("nickname", "") if isinstance(item.get("author"), dict) else "",
        }

        # 判断类型：视频或图集
        # 图文笔记同时包含 video 和 images，优先 images
        images = extract_images(item)
        if images:
            result["type"] = "image"
            result["images"] = images
        elif item.get("video"):
            result["type"] = "video"
            result["video_url"] = build_video_url(item)
            result["cover"] = item.get("video", {}).get("cover", {}).get("url_list", [None])[0]

        if result.get("video_url") or result.get("images"):
            elapsed = time.monotonic() - t0
            note_type = result.get("type", "unknown")
            logger.info("解析成功 aweme_id=%s 来源=SSR 类型=%s 耗时=%.2fs",
                        aweme_id, note_type, elapsed)
            return result, "SSR直连"

        return None, "未提取到视频/图片 URL"
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.warning("解析异常 aweme_id=%s 耗时=%.2fs 原因=%s", aweme_id, elapsed, e)
        return None, str(e)


# ─── 路由 ───
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


class ParseRequest(BaseModel):
    url: str


@app.post("/api/parse")
async def api_parse(req: ParseRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    raw_url = req.url.strip()
    if not raw_url:
        raise HTTPException(status_code=400, detail="请提供抖音链接")

    douyin_url = extract_douyin_url(raw_url)
    if not douyin_url:
        raise HTTPException(status_code=400, detail="无法提取抖音链接，请检查格式")

    if not re.search(r"(v\.douyin\.com|douyin\.com|iesdouyin\.com)", douyin_url):
        raise HTTPException(status_code=400, detail="仅支持抖音链接")

    result, method = await parse_douyin(douyin_url)
    if not result:
        raise HTTPException(status_code=404, detail="解析失败，请确认链接有效且作品未被删除")

    return JSONResponse(content={
        "success": True,
        "data": result,
        "method": method,
    })


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/image")
async def proxy_image(req: ParseRequest):
    """代理获取抖音图片/视频"""
    original_url = req.url.strip()
    if not original_url or not original_url.startswith("http"):
        raise HTTPException(status_code=400, detail="无效的图片 URL")

    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 "
                      "Mobile Safari/537.36",
        "Referer": "https://www.douyin.com/",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as c:
        # 先获取 SSR 页面以获取 cookies（ttwid 等）
        try:
            await c.get("https://www.iesdouyin.com/", headers=headers)
        except Exception:
            pass

        r = await c.get(original_url, headers=headers)
        if r.status_code == 200 and len(r.content) > 1000:
            content_type = r.headers.get("content-type", "image/jpeg")
            logger.info("图片代理成功 url=%s size=%d type=%s", original_url[:80], len(r.content), content_type)
            return HTMLResponse(content=r.content, media_type=content_type)
        # 尝试不带 Referer（douyinpic 可能检查 Referer）
        headers_no_ref = {k: v for k, v in headers.items() if k != "Referer"}
        r2 = await c.get(original_url, headers=headers_no_ref)
        if r2.status_code == 200 and len(r2.content) > 1000:
            content_type = r2.headers.get("content-type", "image/jpeg")
            logger.info("无Referer图片代理成功 url=%s size=%d", original_url[:80], len(r2.content))
            return HTMLResponse(content=r2.content, media_type=content_type)
        raise HTTPException(status_code=502, detail=f"图片获取失败 (status={r.status_code})")
