#!/bin/bash
# Tunnel & HTTP keeper
if ! curl -s --max-time 5 https://348afb4850b528.lhr.life > /dev/null 2>&1; then
  pkill -f "ssh.*localhost:9000.*localhost.run" 2>/dev/null
  sleep 1
  nohup ssh -T -o StrictHostKeyChecking=no -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -R 80:localhost:9000 nokey@localhost.run > /tmp/localhost-run.log 2>&1 &
fi
if ! curl -s --max-time 2 http://localhost:9000 > /dev/null 2>&1; then
  pkill -f "python3 -m http.server 9000" 2>/dev/null
  sleep 1
  cd ~/qxia-reports && nohup python3 -m http.server 9000 > /tmp/qxia-http.log 2>&1 &
fi
