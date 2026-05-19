# 抖音无水印下载服务

抖音作品无水印下载工具，通过 SSR 直连解析获取视频/图片数据。

## 特性

- 支持视频作品和图文作品解析
- SSR 直连解析：从 `window._ROUTER_DATA` 提取作品数据
- 无水印视频：直接构建原始播放 URL
- 无水印图片：直接从 CDN 获取原图
- 暗色主题单页 Web 界面（抖音品牌配色）
- 基于 IP 的简单速率限制
- 解析日志

## 架构

```
用户 → Cloudflare → Nginx (:443) → Uvicorn (127.0.0.1:8002)
```

解析流程：

1. 用户粘贴抖音分享链接（支持 `v.douyin.com`、`douyin.com/video/`、`iesdouyin.com/share/video/`）
2. 跟随短链接重定向（如需要）
3. 以移动端 UA 请求分享页面，解析 `window._ROUTER_DATA`
4. 提取视频 `uri` 构建无水印播放 URL，或提取图片 CDN URL

## 快速开始

```bash
# 创建 conda 环境
conda create -n douyin-download python=3.12 -y
conda activate douyin-download

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
ssh aliyun "systemctl enable douyin.service && systemctl restart douyin.service"

# 查看状态
ssh aliyun "systemctl status douyin.service"
ssh aliyun "journalctl -u douyin.service -n 20 --no-pager"
```

服务运行在 conda 环境 `/home/admin/miniconda3/envs/douyin-download/`。

## 技术栈

- **后端**: FastAPI + Uvicorn
- **前端**: 纯 HTML + 内联 JS/CSS
- **HTTP 客户端**: httpx
