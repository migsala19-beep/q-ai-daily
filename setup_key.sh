#!/bin/bash
# 安全配置 Kimi API Key（输入时不回显，不留痕迹）

echo "=================================="
echo "  Q虾 AI 报告站 - API Key 配置"
echo "=================================="
echo ""
echo "请粘贴你的 Kimi API Key（以 sk- 开头）"
echo "注意：输入时屏幕不会显示任何字符，这是正常的"
echo ""

read -s -p "Kimi API Key: " KIMI_KEY
echo ""

if [[ -z "$KIMI_KEY" ]]; then
    echo "❌ 未输入 Key，配置取消"
    exit 1
fi

# 写入本地文件，权限仅自己可读
echo "$KIMI_KEY" > ~/.kimi_key
chmod 600 ~/.kimi_key

# 写入 shell 配置，方便脚本调用
grep -q "KIMI_API_KEY" ~/.zshrc 2>/dev/null || echo 'export KIMI_API_KEY=$(cat ~/.kimi_key)' >> ~/.zshrc

echo ""
echo "✅ 配置成功！Key 已安全存储在 ~/.kimi_key"
echo "   仅当前用户可读，不会泄露到任何聊天记录"
echo ""
echo "测试命令：source ~/.zshrc && echo \$KIMI_API_KEY"
