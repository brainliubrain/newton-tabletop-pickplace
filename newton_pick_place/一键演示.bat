@echo off
title Newton Pick-Place Demo
cd /d "C:\Users\HHH\.zcode\workspace\draft-75bd8b6f-f7da-45d8-aff2-4dc217c4ed6e\newton_pick_place"
echo ============================================================
echo  One-click demo: run sim -^> record video -^> open 3D viewer
echo  (about 1-2 min; viewer keys: Space=pause, [ ]=step, R=rewind)
echo ============================================================
echo.
set PY="..\.venv\Scripts\python.exe"

%PY% run_task.py --episodes 1 --video --dump-traj results\trajectory_ep0.csv --min-success 0.0
if errorlevel 1 (
  echo [FAIL] simulation failed, see error above
  pause
  exit /b 1
)

echo.
echo Video ready: results\demo_ep0.mp4  (opening...)
start "" "results\demo_ep0.mp4"

%PY% interactive_viewer.py --speed 1.0
echo.
pause
