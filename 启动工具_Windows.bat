@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ════════════════════════════════════════
echo   焦点堆叠批量处理工具 v4
echo   支持 RAF + 镜头矫正
echo ════════════════════════════════════════
echo.

echo [1/4] 检查 Python...
python --version
if errorlevel 1 (
    echo.
    echo ❌ 未找到 Python！请先安装：https://www.python.org/downloads/
    echo    安装时务必勾选 "Add Python to PATH"
    pause & exit /b 1
)

echo.
echo [2/4] 安装 / 检查基础依赖...
python -c "import cv2" 2>nul || pip install opencv-python-headless
python -c "import flask" 2>nul || pip install flask
python -c "import PIL"  2>nul || pip install pillow
python -c "import skimage" 2>nul || pip install scikit-image

echo.
echo [3/4] 安装 / 检查 RAF 和镜头矫正依赖...
python -c "import rawpy" 2>nul
if errorlevel 1 (
    echo 正在安装 rawpy（RAF格式支持）...
    pip install rawpy
    if errorlevel 1 (
        echo ⚠️  rawpy 安装失败，将无法读取 RAF 文件
        echo    （JPG格式仍然可以正常处理）
    ) else (
        echo ✅ rawpy 安装成功
    )
) else (
    echo ✅ rawpy 已安装
)

python -c "import lensfunpy" 2>nul
if errorlevel 1 (
    echo 正在安装 lensfunpy（镜头矫正）...
    pip install lensfunpy
    if errorlevel 1 (
        echo ⚠️  lensfunpy 安装失败，将使用简易色差矫正
    ) else (
        echo ✅ lensfunpy 安装成功
    )
) else (
    echo ✅ lensfunpy 已安装
)

echo.
echo [4/4] 启动服务...
echo.
echo ════════════════════════════════════════
echo   🌐 请在浏览器中打开：
echo.
echo      http://localhost:5050
echo.
echo   保持此窗口开着，关闭 = 程序停止
echo ════════════════════════════════════════
echo.

timeout /t 2 /nobreak >nul
start "" "http://localhost:5050"
python server.py

echo.
echo 服务已停止。
pause
