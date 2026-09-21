@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ==============================================================
echo   모닝 모바일 웹 리포트 및 카카오톡 자동 발송 스케줄러 설정
echo ==============================================================
echo.
echo [1] 매일 아침 07:00에 자동 실행 스케줄 등록
echo [2] 사용자 지정 시간에 자동 실행 스케줄 등록
echo [3] 기존 등록된 스케줄 삭제 (해제)
echo [4] 모닝 리포트 즉시 수동 실행 (테스트)
echo [5] 종료
echo.

set /p CHOICE="원하시는 작업 번호를 입력하세요 (1-5): "

if "%CHOICE%"=="1" goto SET_DEFAULT
if "%CHOICE%"=="2" goto SET_CUSTOM
if "%CHOICE%"=="3" goto REMOVE_TASK
if "%CHOICE%"=="4" goto RUN_NOW
if "%CHOICE%"=="5" goto END

:SET_DEFAULT
set SCHEDULE_TIME=07:00
goto REGISTER_TASK

:SET_CUSTOM
set /p SCHEDULE_TIME="발송할 시간을 입력하세요 (예: 07:30, 08:00): "
goto REGISTER_TASK

:REGISTER_TASK
echo.
echo 지정된 시간: !SCHEDULE_TIME!
echo Windows 작업 스케줄러(Task Scheduler)에 등록 중...

set TASK_NAME=RetirementPortfolio_MorningReport
set WORK_DIR=%~dp0..

:: 파이썬 실행 경로 찾기
for /f "delims=" %%i in ('where python 2^>nul') do (
    set PYTHON_EXE=%%i
    goto FOUND_PYTHON
)

:FOUND_PYTHON
if not defined PYTHON_EXE (
    echo [오류] Python 실행 파일을 찾을 수 없습니다. 환경변수 PATH를 확인하세요.
    pause
    goto END
)

set CMD_TO_RUN="!PYTHON_EXE!" -m services.daily_report_service

schtasks /create /tn "!TASK_NAME!" /tr "cmd.exe /c cd /d \"!WORK_DIR!\" && !CMD_TO_RUN!" /sc daily /st !SCHEDULE_TIME! /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo ==============================================================
    echo [성공] 매일 !SCHEDULE_TIME!에 모닝 리포트 자동 발송이 등록되었습니다!
    echo 앱이 닫혀 있어도 지정된 시간에 백그라운드로 실행되어 카카오톡으로 발송됩니다.
    echo ==============================================================
) else (
    echo.
    echo [실패] 스케줄러 등록에 실패했습니다. 관리자 권한으로 실행해 보세요.
)
echo.
pause
goto END

:REMOVE_TASK
echo.
echo 스케줄러 삭제 중: RetirementPortfolio_MorningReport...
schtasks /delete /tn "RetirementPortfolio_MorningReport" /f
if %ERRORLEVEL% equ 0 (
    echo [성공] 모닝 리포트 자동 실행 스케줄이 정상적으로 삭제되었습니다.
) else (
    echo [안내] 등록된 스케줄이 없거나 이미 삭제되었습니다.
)
echo.
pause
goto END

:RUN_NOW
echo.
echo 모닝 리포트 즉시 생성을 시작합니다...
cd /d "%~dp0.."
python -m services.daily_report_service
echo.
pause
goto END

:END
endlocal
