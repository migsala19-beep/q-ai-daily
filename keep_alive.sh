#!/bin/bash
# Q虾 AI 报告站保活脚本（Cloudflare Tunnel 版）

# 1. 保活本地 HTTP 服务（8080 端口）
if ! curl -s --max-time 2 http://localhost:8080 > /dev/null 2>&1; then
  pkill -f "python3 -m http.server 8080" 2>/dev/null
  sleep 1
  cd /Users/manqinglu/qxia-reports && nohup python3 -m http.server 8080 > /tmp/qxia-http.log 2>&1 &
fi

# 2. 保活 Cloudflare Tunnel
if ! pgrep -f "cloudflared.*tunnel run" > /dev/null 2>&1; then
  nohup /Users/manqinglu/.local/bin/cloudflared --config /Users/manqinglu/.cloudflared/config.yml tunnel run b51252b9-093d-4791-8da9-230fdc353b0b > /tmp/cf_tunnel.log 2>&1 &
fi
