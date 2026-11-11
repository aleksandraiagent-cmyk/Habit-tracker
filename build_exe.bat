@echo off
chcp 65001 >nul
REM Сборка HabitTracker.exe и установщика HabitTracker-Setup.exe
cd /d "%~dp0"
python -m pip install pyinstaller || goto :err
where node >nul 2>nul && (
  pushd web && call npm ci --no-audit --no-fund && node build.mjs && popd
) || echo Node.js не найден — используется готовая app\index.html
if not exist build mkdir build
python habit_app.py --make-ico build\habit.ico || goto :err
pyinstaller --noconfirm --onefile --name HabitTracker --icon build\habit.ico --add-data "app;app" habit_app.py || goto :err
echo Готово: dist\HabitTracker.exe

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
  "%ISCC%" installer.iss || goto :err
  echo Готово: dist\HabitTracker-Setup.exe
) else (
  echo Inno Setup 6 не найден — установщик не собран, только exe. Скачать: https://jrsoftware.org/isdl.php
)
pause
exit /b 0
:err
echo ОШИБКА СБОРКИ
pause
exit /b 1
