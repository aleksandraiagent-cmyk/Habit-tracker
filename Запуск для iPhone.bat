@echo off
chcp 65001 >nul
rem Запуск трекера так, чтобы его было видно с iPhone в той же Wi-Fi сети
set "EXE=%~dp0HabitTracker.exe"
if not exist "%EXE%" set "EXE=%~dp0dist\HabitTracker.exe"
if not exist "%EXE%" set "EXE=%LOCALAPPDATA%\Programs\HabitTracker\HabitTracker.exe"
if not exist "%EXE%" (
  echo Не найден HabitTracker.exe. Положите этот файл в одну папку с HabitTracker.exe.
  pause
  exit /b 1
)
"%EXE%" --lan
