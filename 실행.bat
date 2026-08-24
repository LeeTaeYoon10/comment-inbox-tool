@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [댓글 통합관리] 준비 중... 잠시만요.
where python >nul 2>nul || (echo Python이 필요합니다. python.org 에서 설치하세요. & pause & exit /b)
python -c "import playwright" 2>nul || (echo 최초 1회 설치 중... & pip install -r requirements.txt & python -m playwright install chromium)
echo 브라우저에 화면이 열립니다. 이 창은 켜둔 채로 사용하세요.
python webapp.py
if errorlevel 1 pause
