# 抖音无水印下载

抖音作品无水印下载工具，通过 SSR 直连解析获取视频/图片数据。

在线地址：https://extract.51allai.com/douyin/

## 特性

- 支持视频作品和图文作品解析
- SSR 直连解析：从 `window._ROUTER_DATA` 提取作品数据，无需 Cookie/签名
- 无水印视频：直接构建原始播放 URL
- 无水印图片：浏览器直链加载 CDN 原图
- 暗色主题单页 Web 界面（抖音品牌配色）
- 基于 IP 的简单速率限制
- 解析日志

## 支持链接格式

- 短链接：`https://v.douyin.com/xxxxx/`
- 视频直链：`https://www.douyin.com/video/7xxxxxx`
- 图文直链：`https://www.douyin.com/note/7xxxxxx`
- 分享页：`https://www.iesdouyin.com/share/video/7xxxxxx/`
- 复制文本：`1.56 复制打开抖音，看看【xxx的作品】 xxx https://v.douyin.com/xxxxx/`

## 架构

```
用户 → Cloudflare → Nginx (:443) → Uvicorn (127.0.0.1:8002)
```

解析流程：

1. 用户粘贴抖音分享链接
2. 跟随短链接重定向，提取 `aweme_id`
3. 转为 `iesdouyin.com/share/video/{id}/` 获取 SSR 数据
4. 解析 `window._ROUTER_DATA` JSON
5. 提取视频 URI 或图片 CDN URL

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 本地启动
uvicorn main:app --reload --port 8002

# 访问 http://localhost:8002
```

## 部署（阿里云 systemd）

```bash
# 推送代码
scp main.py templates/index.html aliyun:/home/admin/douyin-download/
ssh aliyun "systemctl restart douyin.service"

# 查看状态
ssh aliyun "systemctl status douyin.service"
ssh aliyun "journalctl -u douyin.service -n 20 --no-pager"
```

服务运行在 conda 环境 `/home/admin/miniconda3/envs/douyin-download/`。

## 技术栈

- **后端**: FastAPI + Uvicorn
- **前端**: 纯 HTML + 内联 JS/CSS
- **HTTP 客户端**: httpx

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端页面 |
| `/api/parse` | POST | `{url: string}` 解析抖音链接 |
| `/health` | GET | 健康检查 |

## 注意事项

- `douyin.com/video/` 主页返回混淆 JS，需转为 `iesdouyin.com/share/video/` 获取 SSR 数据
- 图片 CDN（douyinpic.com）限制服务端访问，前端使用直链加载
- SSR 数据结构可能随抖音更新变化，需持续关注
