# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

抖音无水印下载服务，FastAPI 单文件应用。通过 SSR 直连解析 `window._ROUTER_DATA` 提取作品数据，无需 Cookie/签名。

**在线地址**: https://extract.51allai.com/douyin/

## 架构

```
用户 → Cloudflare → Nginx (:443, /douyin rewrite) → Uvicorn (127.0.0.1:8002)
```

Nginx 将 `/douyin/...` 重写为 `...` 后代理到 8002 端口，与 xhs-download（8001 端口）共存。

## 核心文件

| 文件 | 说明 |
|------|------|
| `main.py` | FastAPI 后端，全部逻辑（约 350 行） |
| `templates/index.html` | 单页前端，内联 CSS + JS |
| `douyin.service` | systemd 服务配置 |
| `requirements.txt` | Python 依赖 |

## 本地开发

```bash
# 创建 conda 环境
conda create -n douyin-download python=3.12 -y
conda activate douyin-download
pip install -r requirements.txt

# 启动开发服务
uvicorn main:app --reload --port 8002
```

## 部署（阿里云）

```bash
# 上传文件
scp main.py templates/index.html aliyun:/home/admin/douyin-download/

# 重启服务
ssh aliyun "sudo systemctl restart douyin.service"
ssh aliyun "journalctl -u douyin.service -n 20 --no-pager"
```

服务运行在 conda 环境 `/home/admin/miniconda3/envs/douyin-download/`。

## SSR 解析流程

1. 用户粘贴分享链接（`v.douyin.com`、`douyin.com/video/`、`douyin.com/note/` 等）
2. 跟随短链接重定向 → 提取 `aweme_id`
3. 将 `douyin.com/video/` 等主页 URL 转为 `iesdouyin.com/share/video/{id}/` 获取 SSR 数据
4. 解析 `window._ROUTER_DATA`（需处理 JS 非标准 JSON：`undefined`→`null`、`NaN`→`null`、尾逗号）
5. 查找 `loaderData["video_(id)/page"]` 或 `loaderData["note_(id)/page"]` → `videoInfoRes.item_list[0]`
6. 视频: 从 `item.video.play_addr.uri` 构建无水印 URL
7. 图集: 从 `item.images[].url_list[0]` 提取 CDN URL

## 关键函数

- `extract_douyin_url()` — 从分享文本中提取抖音 URL
- `parse_aweme_id()` — 从 URL 提取作品 ID
- `fetch_with_redirect()` — 跟随重定向并转为 iesdouyin 分享页
- `extract_router_data()` — 解析 `window._ROUTER_DATA` JSON
- `find_aweme_item()` — 在 SSR 数据中查找作品（支持视频/图文两种路径 + 递归兜底）
- `build_video_url()` — 构建无水印视频 URL（优先 uri 方式，备用 playwm→play）
- `extract_images()` — 提取图片列表
- `parse_douyin()` — 主解析入口
- `check_rate_limit()` — 10 次/分钟/IP 速率限制

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端页面 |
| `/api/parse` | POST | `{url: string}` → 返回 `{success, data, method}` |
| `/api/image` | POST | 图片代理（兜底，douyinpic CDN 限制服务端访问，前端优先直链加载） |
| `/health` | GET | 健康检查 |

## 前端

- `fetch('./api/parse')` 使用**相对路径**，确保在 `/douyin/` 下正确路由到 `/douyin/api/parse`
- 图片使用 `<img src="直链">` 直接加载（douyinpic CDN 限制服务端代理，但浏览器直访正常）
- 视频 `<video>` 直接使用 `douyin.com/aweme/v1/play/?video_id={uri}`

## 配色

抖音品牌色：`#25F4EE`（青色）+ `#FE2C55`（红色），背景 `#0F0F0F`。

## 日志

`logs/parse.log`，RotatingFileHandler（10MB 轮转，5 备份）。记录 aweme_id、来源、类型、耗时。

## 注意事项

- `douyin.com/video/` 主页返回混淆 JS，必须转为 `iesdouyin.com/share/video/` 才能获取 SSR 数据
- `v.douyin.com` 短链接重定向后可能是 `/note/`（图文）或 `/video/`（视频），需动态判断
- 图文笔记同时包含 `video` 和 `images` 字段，`extract_images()` 非空时优先判定为图集
- 图片 CDN（douyinpic.com）限制服务端 IP 访问，前端使用直链而非代理
