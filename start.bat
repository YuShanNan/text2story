@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

rem ============================================================

rem ============================================================

title text2story 启动器

echo.
echo ============================================================
echo   text2story 一键启动脚本
echo ============================================================
echo.

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

rem --- 参数解析 ---
set "FORCE_SETUP=0"
set "FORCE_FAST=0"
if /i "%~1"=="--setup" set "FORCE_SETUP=1"
if /i "%~1"=="--fast"  set "FORCE_FAST=1"

rem --- 哨兵检测（首次运行执行完整安装，后续跳过）---
if "!FORCE_SETUP!"=="1" goto :full_setup
if "!FORCE_FAST!"=="1"  goto :quick_launch
if exist ".setup_complete" goto :quick_launch

:full_setup

set "PYTHON_CMD="
set "TOTAL_STEPS=5"
set /a "STEP=0"

rem ============================================================

rem ============================================================
set /a "STEP+=1"
echo [!STEP!/!TOTAL_STEPS!] 系统环境检查...

reg query "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    for /f "skip=2 tokens=3" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled 2^>nul') do (
        if %%a equ 0 (
            echo        [提示] 长路径未启用，部分 Python 包在深层目录可能安装失败
        )
    )
) else (
    echo        [提示] 无法检测长路径设置状态
)

if not exist "%SystemRoot%\System32\vcruntime140.dll" (
    echo        [提示] VC++ 运行库可能缺失，Python 包编译可能失败
    echo        如需安装: winget install -e --id Microsoft.VCRedist.2015+.x64
)

echo        系统环境检查完成
echo.

rem ============================================================

rem ============================================================
set /a "STEP+=1"
echo [!STEP!/!TOTAL_STEPS!] 检测 Python 环境...

call :detect_python

if defined PYTHON_CMD goto :python_found

echo [提示] 未找到 Python 3.10+，尝试自动安装...
call :ensure_network
if "!NETWORK_OK!"=="1" (
    set /p "CONFIRM=是否自动安装 Python？(Y/N): "
) else (
    echo [错误] 无网络连接，请联网后运行。
    goto :python_manual
)

if /i "!CONFIRM!" neq "Y" goto :python_manual

winget --version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    call :install_python_winget
    if defined PYTHON_CMD goto :python_found
)

echo        winget 安装未生效，尝试打开 Microsoft Store...
echo        请在商店中搜索 "Python" 并安装 Python 3.10 以上版本
start ms-windows-store://pdp/?productid=9PJPW5LDXLZ5
echo        安装完成后按任意键继续...
pause
call :detect_python
if defined PYTHON_CMD goto :python_found

echo        仍未检测到 Python，打开下载页面...
start https://www.python.org/downloads/
echo.
echo        请手动安装 Python 3.10+，并确保勾选 "Add Python to PATH"
echo        安装完成后重新运行本脚本。
pause
exit /b 1

:python_manual
echo [错误] 未找到 Python 3.10+！
echo        请手动安装 Python 3.10~3.13: https://www.python.org/downloads/
echo        安装时请勾选 "Add Python to PATH"
echo.
pause
exit /b 1

:python_found

%PYTHON_CMD% -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    %PYTHON_CMD% --version
    echo [错误] 需要 Python 3.10+，请升级 Python 版本
    pause
    exit /b 1
)

%PYTHON_CMD% --version
echo        命令: %PYTHON_CMD%
echo.

%PYTHON_CMD% -m pip --version >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [错误] Python 已找到，但 pip 模块不可用！
    echo        请重新安装 Python 并确保勾选 pip 组件
    pause
    exit /b 1
)

%PYTHON_CMD% -m ensurepip --version >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [警告] ensurepip 模块不可用，创建虚拟环境可能失败
    echo        如遇 venv 错误，请重新安装 Python 并确保包含 pip 组件
)

rem ============================================================

rem ============================================================
set /a "STEP+=1"
echo [!STEP!/!TOTAL_STEPS!] 配置 Python 虚拟环境...

if not exist "%PROJECT_DIR%venv\Scripts\activate.bat" (
    echo        正在创建虚拟环境...
    %PYTHON_CMD% -m venv venv
    if !ERRORLEVEL! neq 0 (
        echo [错误] 创建虚拟环境失败！
        echo        尝试: python -m venv venv --without-pip
        echo        如仍失败，请手动安装: pip install virtualenv ^&^& python -m virtualenv venv
        pause
        exit /b 1
    )
    echo        虚拟环境创建成功
) else (
    echo        虚拟环境已存在
)

call "%PROJECT_DIR%venv\Scripts\activate.bat"
if !ERRORLEVEL! neq 0 (
    echo [警告] venv 激活失败（可能 Python 版本已变更），重建虚拟环境...
    rmdir /s /q "%PROJECT_DIR%venv" 2>nul
    %PYTHON_CMD% -m venv venv
    if !ERRORLEVEL! neq 0 (
        echo [错误] 重建虚拟环境失败！
        pause
        exit /b 1
    )
    call "%PROJECT_DIR%venv\Scripts\activate.bat"
)

"%PROJECT_DIR%venv\Scripts\python.exe" -m pip install --upgrade pip --quiet 2>nul

echo        正在安装 Python 依赖...
pip install -r requirements.txt
if !ERRORLEVEL! neq 0 (
    echo        pip 安装失败，尝试使用清华镜像源重试...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if !ERRORLEVEL! neq 0 (
        echo [错误] Python 依赖安装失败！
        echo        可尝试手动安装:
        echo        pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
        pause
        exit /b 1
    )
)
echo        Python 依赖已就绪

echo        验证关键依赖模块...
"%PROJECT_DIR%venv\Scripts\python.exe" -c "[__import__(p) for p in ['requests','click','rich','dotenv','charset_normalizer']]" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [错误] 依赖验证失败，部分模块未正确安装！
    echo        检查网络后手动重试: .\venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
echo        所有关键模块验证通过

rem ============================================================

rem ============================================================
set /a "STEP+=1"
echo [!STEP!/!TOTAL_STEPS!] 检查配置文件和目录...

if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    echo        .env 已从模板创建
    if "!MODEL_API_KEY!"=="" (
        echo.
        echo ============================================================
        echo   [重要提示] 请先编辑 .env 文件，填入你的 API Key！
        echo   文件位置: %PROJECT_DIR%.env
        echo   编辑后保存，重新运行本脚本
        echo ============================================================
        echo.
    )
) else (
    echo        .env 配置文件已存在
)

if not exist "output" mkdir "output"
if not exist "input"  mkdir "input"
echo        所有目录已就绪
echo.

echo. > ".setup_complete"
echo        首次安装标记已创建

rem ============================================================

rem ============================================================
set /a "STEP+=1"
echo [!STEP!/!TOTAL_STEPS!] 启动程序...
echo.
echo ============================================================
echo   正在启动 text2story 主程序...
echo ============================================================

:launch_app
cls

call "%PROJECT_DIR%venv\Scripts\activate.bat"
if !ERRORLEVEL! neq 0 (
    echo [错误] venv 激活失败，请手动重建虚拟环境：
    echo        rmdir /s /q venv
    echo        重新运行本脚本
    pause
    exit /b 1
)
"%PROJECT_DIR%venv\Scripts\python.exe" main.py
set "MAIN_EXIT_CODE=!ERRORLEVEL!"

if !MAIN_EXIT_CODE! neq 0 (
    echo.
    echo ============================================================
    echo   [错误] text2story 异常退出（退出码: !MAIN_EXIT_CODE!）
    echo   ImportError → 尝试重装依赖: .\venv\Scripts\pip install -r requirements.txt
    echo   API 错误   → 检查 .env 中的 API Key 和 Base URL
    echo   模块缺失   → 检查 Python 版本 >= 3.10
    echo ============================================================
    echo.
    pause
)

rem ============================================================

rem ============================================================
echo.
echo ============================================================
echo   text2story 已退出
echo ============================================================
echo.
pause
exit /b 0

:quick_launch
echo.
echo ============================================================
echo   检测到已完成首次安装，跳过环境检测，直接启动...
echo ============================================================
echo.

rem 兜底检查：虚拟环境是否完整
if not exist "%PROJECT_DIR%venv\Scripts\activate.bat" (
    echo [错误] 虚拟环境不存在！请运行 start.bat --setup 重建环境
    pause
    exit /b 1
)

rem 兜底检查：配置文件是否存在
if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    echo        .env 已从模板创建
)

goto :launch_app

rem ============================================================

rem ============================================================

:detect_python

set "PYTHON_CMD="

python --version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    python -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_CMD=python"
        goto :eof
    )
)

python3 --version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_CMD=python3"
        goto :eof
    )
)

py --version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    for %%v in (3.13 3.12 3.11 3.10) do (
        py -%%v --version >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            set "PYTHON_CMD=py -%%v"
            goto :eof
        )
    )
)

call :find_python_direct 313
if defined PYTHON_CMD goto :eof
call :find_python_direct 312
if defined PYTHON_CMD goto :eof
call :find_python_direct 311
if defined PYTHON_CMD goto :eof
call :find_python_direct 310
if defined PYTHON_CMD goto :eof

for %%c in (
    "%USERPROFILE%\anaconda3\python.exe"
    "%USERPROFILE%\miniconda3\python.exe"
    "%USERPROFILE%\AppData\Local\anaconda3\python.exe"
    "%ALLUSERSPROFILE%\anaconda3\python.exe"
    "%ALLUSERSPROFILE%\miniconda3\python.exe"
    "C:\Anaconda3\python.exe"
    "C:\Miniconda3\python.exe"
) do (
    if exist %%c (
        %%c --version >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            %%c -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
            if !ERRORLEVEL! equ 0 (
                set "PYTHON_CMD=%%c"
                goto :eof
            )
        )
    )
)

if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" (
    "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" --version >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            set "PYTHON_CMD=%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"
            goto :eof
        )
    )
)

goto :eof

:find_python_direct

set "VER=%~1"
set "PY_EXE="

if exist "%LOCALAPPDATA%\Programs\Python\Python%VER%\python.exe" set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python%VER%\python.exe"
if exist "%ProgramFiles%\Python%VER%\python.exe" set "PY_EXE=%ProgramFiles%\Python%VER%\python.exe"
if exist "C:\Python%VER%\python.exe" set "PY_EXE=C:\Python%VER%\python.exe"

if defined PY_EXE (
    "!PY_EXE!" --version >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_CMD=!PY_EXE!"
    )
)
goto :eof

:install_python_winget

for %%v in (3.13 3.12 3.11 3.10) do (
    echo        正在通过 winget 安装 Python %%v...
    winget install -e --id Python.Python.%%v --accept-source-agreements --accept-package-agreements
    if !ERRORLEVEL! equ 0 (
        echo        Python %%v 安装成功
        call :refresh_path
        call :detect_python
        if defined PYTHON_CMD goto :eof
        echo [警告] Python %%v 已安装但当前终端无法识别
        echo        请关闭此窗口并重新运行启动脚本即可
        goto :eof
    )
    echo        Python %%v 安装失败，继续尝试下一版本...
)
echo        winget 全部版本安装失败，或 winget 不可用
goto :eof

:ensure_network
if "!NETWORK_CHECKED!"=="1" goto :eof
set "NETWORK_CHECKED=1"
set "NETWORK_OK=0"
echo        正在检查网络连接...

ping -n 1 -w 3000 www.baidu.com >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "NETWORK_OK=1"
    echo        网络连接正常
    goto :eof
)

curl -s --connect-timeout 3 https://www.baidu.com >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "NETWORK_OK=1"
    echo        网络连接正常
    goto :eof
)

powershell -Command "try {Invoke-WebRequest https://www.baidu.com -TimeoutSec 3 -UseBasicParsing | Out-Null; exit 0} catch {exit 1}" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "NETWORK_OK=1"
    echo        网络连接正常
    goto :eof
)

set "NETWORK_OK=0"
echo [警告] 无法连接网络！请检查网络连接后重试。
goto :eof

:refresh_path
echo        正在刷新 PATH 环境变量...

reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path > "%TEMP%\syspath.txt" 2>nul
reg query "HKCU\Environment" /v Path > "%TEMP%\userpath.txt" 2>nul

set "SYSTEM_PATH="
if exist "%TEMP%\syspath.txt" (
    for /f "skip=2 tokens=2*" %%a in ('type "%TEMP%\syspath.txt"') do set "SYSTEM_PATH=%%b"
)
set "USER_PATH="
if exist "%TEMP%\userpath.txt" (
    for /f "skip=2 tokens=2*" %%a in ('type "%TEMP%\userpath.txt"') do set "USER_PATH=%%b"
)
del "%TEMP%\syspath.txt" "%TEMP%\userpath.txt" 2>nul

set "FRESH_PATH="
if defined SYSTEM_PATH set "FRESH_PATH=!SYSTEM_PATH!"
if defined USER_PATH (
    if defined FRESH_PATH (
        set "FRESH_PATH=!FRESH_PATH!;!USER_PATH!"
    ) else (
        set "FRESH_PATH=!USER_PATH!"
    )
)
if defined FRESH_PATH (
    set "PATH=!FRESH_PATH!"

    set "PY_PATHS="
    for /d %%p in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
        if exist "%%p\Scripts" set "PY_PATHS=!PY_PATHS!;%%p;%%p\Scripts"
    )
    for /d %%p in ("%ProgramFiles%\Python*") do (
        if exist "%%p\Scripts" set "PY_PATHS=!PY_PATHS!;%%p;%%p\Scripts"
    )
    if defined PY_PATHS set "PATH=!PY_PATHS!;!PATH!"
)
goto :eof
