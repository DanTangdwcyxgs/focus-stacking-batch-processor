#!/bin/bash
# 焦点堆叠批量处理工具 - 一键启动 (Mac)
cd "$(dirname "$0")"

echo "════════════════════════════════════════"
echo "  焦点堆叠批量处理工具"
echo "  Focus Stacking Batch Processor"
echo "════════════════════════════════════════"

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 Python3，请先安装 Python 3.8+"
    echo "   下载地址: https://www.python.org/downloads/"
    read -p "按回车键退出..."
    exit 1
fi

# 检查依赖
echo "🔍 检查依赖..."
python3 -c "import cv2, numpy, flask, PIL, skimage" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 安装依赖包..."
    pip3 install opencv-python-headless numpy flask pillow scikit-image --break-system-packages 2>/dev/null || \
    pip3 install opencv-python-headless numpy flask pillow scikit-image
fi

echo "✅ 依赖检查完成"
echo ""
echo "🚀 启动服务..."
echo "🌐 请在浏览器中访问: http://localhost:5050"
echo ""

# 自动打开浏览器 (Mac)
sleep 1.5
open "http://localhost:5050" 2>/dev/null &

python3 server.py
