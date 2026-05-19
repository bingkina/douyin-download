# douyin-download 开发指南

## 核心文件
- `main.py` — FastAPI 后端，所有解析逻辑
- `templates/index.html` — 单页前端（内联 CSS + JS）
- `douyin.service` — systemd 服务配置
- `requirements.txt` — Python 依赖

## SSR 解析
- 提取标记：`window._ROUTER_DATA`
- 数据路径：`loaderData["video_(id)/page"]["videoInfoRes"]["item_list"][0]`
- 需要移动端 User-Agent，无需 Cookie/签名

## 视频 URL 构建
- 从 `item_list[0].video.play_addr.uri` 获取 video_id
- 无水印 URL：`https://www.douyin.com/aweme/v1/play/?video_id={uri}`

## 图片提取
- 从 `item_list[0].images[]` 提取，每个元素有 `url_list[0]`
- 图片通过 `/api/image` 代理获取（解决 CORS）

## 部署
- 地址：`https://extract.51allai.com/douyin`
- 端口：`8002`（避免与 xhs-download 的 8001 冲突）
- conda 环境：`/home/admin/miniconda3/envs/douyin-download/`
- Nginx location：`/douyin` → `http://127.0.0.1:8002`
