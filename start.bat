@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ------ 自动安装相关变量 ------
set "NETWORK_CHECKED=0"
set "NETWORK_OK=0"

:: ============================================================
::  text2story 一键启动脚本
::  功能: 自动检测环境、安装依赖、启动程序
:: ============================================================

title text2story 启动器

echo.
echo ============================================================
echo   text2story 一键启动脚本
echo ============================================================
echo.

:: ------ 记录项目根目录 ------
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

set "TOTAL_STEPS=4"
set /a "STEP=0"

:: ============================================================
::  检测 Python 环境
:: ============================================================
set /a "STEP+=1"
echo [!STEP!/!TOTAL_STEPS!] 检测 Python 环境...

set "PYTHON_CMD="

:: 优先检测 python 命令
python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=python"
    goto :python_found
)

:: 再检测 python3 命令
python3 --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=python3"
    goto :python_found
)

:: 检测 py 启动器
py --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=py"
    goto :python_found
)

echo [提示] 未找到 Python，尝试自动安装...
call :ensure_network
if "!NETWORK_OK!"=="0" goto :python_manual

set /p "CONFIRM=是否自动安装 Python？(Y/N): "
if /i "!CONFIRM!" neq "Y" goto :python_manual

winget --version >nul 2>&1
if !ERRORLEVEL! neq 0 goto :python_no_winget

echo        正在通过 winget 安装 Python 3.13...
winget install -e --id Python.Python.3.13 --accept-source-agreements --accept-package-agreements
call :refresh_path

:: 重新检测 Python
python --version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_CMD=python"
    goto :python_found
)
python3 --version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_CMD=python3"
    goto :python_found
)
py --version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_CMD=py"
    goto :python_found
)
echo [提示] Python 已安装，但当前终端无法识别
echo        请关闭此窗口，重新运行启动脚本。
pause
exit /b 1

:python_no_winget
echo        winget 不可用，正在打开 Python 下载页面...
echo        下载地址: https://www.python.org/downloads/
echo        安装时请勾选 "Add Python to PATH"
start https://www.python.org/downloads/
pause
exit /b 1

:python_manual
echo [错误] 未找到 Python！
echo        请先安装 Python 3.8+: https://www.python.org/downloads/
echo        安装时请勾选 "Add Python to PATH"
echo.
pause
exit /b 1

:python_found
for /f "tokens=*" %%i in ('%PYTHON_CMD% --version 2^>^&1') do set "PYTHON_VER=%%i"
echo        找到 %PYTHON_VER% (命令: %PYTHON_CMD%)
echo        [模式] 单模型 OpenAI 兼容接口

:: ============================================================
::  配置 Python 虚拟环境 + 安装依赖
:: ============================================================
set /a "STEP+=1"
echo.
echo [!STEP!/!TOTAL_STEPS!] 配置 Python 虚拟环境...

if not exist "%PROJECT_DIR%venv\Scripts\activate.bat" (
    echo        正在创建虚拟环境...
    %PYTHON_CMD% -m venv venv
    if !ERRORLEVEL! neq 0 (
        echo [错误] 创建虚拟环境失败！
        pause
        exit /b 1
    )
    echo        虚拟环境创建成功
) else (
    echo        虚拟环境已存在
)

:: 激活虚拟环境
call "%PROJECT_DIR%venv\Scripts\activate.bat"

:: 安装 Python 依赖
echo        正在检查并安装 Python 依赖...
call pip install -r requirements.txt --quiet 2>nul
if %ERRORLEVEL% neq 0 (
    echo        首次安装依赖（可能需要网络连接）...
    call pip install -r requirements.txt
    if !ERRORLEVEL! neq 0 (
        echo [错误] Python 依赖安装失败！
        echo        请检查网络连接或者使用镜像源:
        echo        pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
        pause
        exit /b 1
    )
)
echo        Python 依赖已就绪

:: ============================================================
::  检查并创建配置文件和目录
:: ============================================================
set /a "STEP+=1"
echo.
echo [!STEP!/!TOTAL_STEPS!] 检查配置文件和目录...

:: 检查 .env 文件
if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    echo        .env 已从模板创建
    echo.
    echo ============================================================
    echo   [重要提示] 请先编辑 .env 文件，填入你的 API Key！
    echo   文件位置: %PROJECT_DIR%.env
    echo ============================================================
    echo.
) else (
    echo        .env 配置文件已存在
)

:: 创建输出/输入目录
if not exist "output" mkdir "output"
if not exist "input"  mkdir "input"
echo        所有目录已就绪

:: ============================================================
::  启动程序
:: ============================================================
set /a "STEP+=1"
echo.
echo [!STEP!/!TOTAL_STEPS!] 启动程序...
echo.
echo ============================================================
echo   正在启动 text2story 主程序...
echo ============================================================
echo.

cls

:: 运行 main.py
call "%PROJECT_DIR%venv\Scripts\activate.bat"
"%PROJECT_DIR%venv\Scripts\python.exe" main.py
set "MAIN_EXIT_CODE=!ERRORLEVEL!"

:: 如果程序异常退出，显示提示
if !MAIN_EXIT_CODE! neq 0 (
    echo.
    echo ============================================================
    echo   [错误] text2story 异常退出（退出码: !MAIN_EXIT_CODE!）
    echo   如果遇到 ImportError 或 RuntimeError，请尝试重新安装依赖:
    echo     .\venv\Scripts\pip install -r requirements.txt
    echo ============================================================
    echo.
    pause
)

:: ============================================================
::  程序退出
:: ============================================================
echo.
echo ============================================================
echo   text2story 已退出
echo ============================================================
echo.
pause
exit /b 0

:: ============================================================
::  辅助函数
:: ============================================================

:ensure_network
if "!NETWORK_CHECKED!"=="1" goto :eof
set "NETWORK_CHECKED=1"
echo        正在检查网络连接...
ping -n 1 -w 3000 www.baidu.com >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "NETWORK_OK=1"
    echo        网络连接正常
) else (
    set "NETWORK_OK=0"
    echo [警告] 无法连接网络！请检查网络连接后重试。
)
goto :eof

:refresh_path
echo        正在刷新 PATH 环境变量...
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYSTEM_PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%b"
set "PATH=!SYSTEM_PATH!;!USER_PATH!"
goto :eof
