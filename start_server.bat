@echo off
rem ============================================================
rem 选调研 服务启动脚本（Windows）
rem - 双击运行：本机与局域网 http://<本机IP>:5000 即可访问
rem - 已放入启动文件夹，登录 Windows 自动以最小化运行
rem - 删除自启动：删除 启动文件夹 里的 xuandiaoyan-server.cmd
rem ============================================================
cd /d "%~dp0"

if not exist data\app.db (
  echo [选调研] 首次启动：生成脱敏演示数据库...
  python -m app.web.seed data\app.db
  if errorlevel 1 (
    echo [选调研] 数据库生成失败，请检查 python 环境。
    pause
    exit /b 1
  )
)

echo [选调研] 服务启动中：http://127.0.0.1:5000
echo [选调研] 局域网设备请访问 http://本机IP:5000
echo [选调研] 关闭本窗口即停止服务。
python -c "from app.web.app import create_app; create_app().run(host='0.0.0.0', port=5000, debug=False)"
echo [选调研] 服务已退出。
pause
