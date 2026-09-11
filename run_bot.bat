@echo off
title CHIROQCHIMUZ - Telegram Musiqa Boti
color 0b
echo ========================================================
echo           CHIROQCHIMUZ TELEGRAM MUSIQA BOTI
echo ========================================================
echo.

where python >nul 2>&1
if %errorlevel% equ 0 (
    python main.py
) else (
    "C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe" main.py
)

if %errorlevel% neq 0 (
    echo.
    echo [!] Agar xatolik bo'lsa, .env faylida BOT_TOKEN to'g'ri kiritilganligini tekshiring.
)
pause
