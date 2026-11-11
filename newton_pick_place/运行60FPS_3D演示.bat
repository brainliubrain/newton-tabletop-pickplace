@echo off
chcp 65001 >nul
title Newton Pick-Place 60FPS 3D 物理交互复核窗口
cd /d "%~dp0"
echo ========================================================================
echo  正在启动 Newton Pick-Place 60FPS 原生 3D 物理接触交互窗口...
echo  驱动机制: 100%% 纯正向运动学 (FK) 真实物理轨迹复核 (零 Mocap 作弊)
echo ========================================================================
echo.
"C:\Users\HHH\.zcode\workspace\draft-75bd8b6f-f7da-45d8-aff2-4dc217c4ed6e\.venv\Scripts\python.exe" interactive_viewer.py --speed 1.0
pause
