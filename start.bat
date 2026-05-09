@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
::  text2story 一键启动脚本
::  功能: 自动检测环境、安装依赖、启动程序
::  目标: 纯净 Windows 环境（无 Python 也能从零开始）
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

set "PYTHON_CMD="
set "TOTAL_STEPS=5"
set /a "STEP=0"

:: ============================================================
::  步骤 0: 纯净环境辅助检查
:: ============================================================
set /a "STEP+=1"
echo [!STEP!/!TOTAL_STEPS!] 系统环境检查...

:: 长路径支持（如以管理员运行则尝试启用）
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

:: VC++ Redist 检查
if not exist "%SystemRoot%\System32\vcruntime140.dll" (
    echo        [提示] VC++ 运行库可能缺失，Python 包编译可能失败
    echo        如需安装: winget install -e --id Microsoft.VCRedist.2015+.x64
)

echo        系统环境检查完成
echo.

:: ============================================================
::  步骤 1: 检测 Python 环境（支持 >= 3.10）
:: ============================================================
set /a "STEP+=1"
echo [!STEP!/!TOTAL_STEPS!] 检测 Python 环境...

:: 检测链: python → python3 → py → 直接搜索安装目录
call :detect_python

if defined PYTHON_CMD goto :python_found

:: ---- 未找到 Python，启动三级安装链 ----
echo [提示] 未找到 Python 3.10+，尝试自动安装...
call :ensure_network
if "!NETWORK_OK!"=="1" (
    set /p "CONFIRM=是否自动安装 Python？(Y/N): "
) else (
    echo [错误] 无网络连接，请联网后运行。
    goto :python_manual
)

if /i "!CONFIRM!" neq "Y" goto :python_manual

:: 一级安装：winget（推荐）
winget --version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    call :install_python_winget
    if defined PYTHON_CMD goto :python_found
)

:: 二级安装：Microsoft Store
echo        winget 安装未生效，尝试打开 Microsoft Store...
echo        请在商店中搜索 "Python" 并安装 Python 3.10 以上版本
start ms-windows-store://pdp/?productid=9PJPW5LDXLZ5
echo        安装完成后按任意键继续...
pause
call :detect_python
if defined PYTHON_CMD goto :python_found

:: 三级安装：浏览器下载
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
:: 验证版本 >= 3.10
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

:: 验证 pip
%PYTHON_CMD% -m pip --version >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [错误] Python 已找到，但 pip 模块不可用！
    echo        请重新安装 Python 并确保勾选 pip 组件
    pause
    exit /b 1
)

:: 验证 ensurepip（创建 venv 需要）
%PYTHON_CMD% -m ensurepip --version >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [警告] ensurepip 模块不可用，创建虚拟环境可能失败
    echo        如遇 venv 错误，请重新安装 Python 并确保包含 pip 组件
)

:: ============================================================
::  步骤 2: 配置虚拟环境 + 安装依赖
:: ============================================================
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

:: 激活虚拟环境
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

:: 升级 pip（可选，静默执行）
"%PROJECT_DIR%venv\Scripts\python.exe" -m pip install --upgrade pip --quiet 2>nul

:: 安装 Python 依赖
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

:: 验证核心包可导入
echo        验证关键依赖模块...
"%PROJECT_DIR%venv\Scripts\python.exe" -c "[__import__(p) for p in ['requests','click','rich','dotenv','charset_normalizer']]" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [错误] 依赖验证失败，部分模块未正确安装！
    echo        检查网络后手动重试: .\venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
echo        所有关键模块验证通过

:: ============================================================
::  步骤 3: 检查配置文件和目录
:: ============================================================
set /a "STEP+=1"
echo [!STEP!/!TOTAL_STEPS!] 检查配置文件和目录...

:: 检查 .env 文件
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

:: 创建输出/输入目录
if not exist "output" mkdir "output"
if not exist "input"  mkdir "input"
echo        所有目录已就绪
echo.

:: ============================================================
::  步骤 4: 启动程序
:: ============================================================
set /a "STEP+=1"
echo [!STEP!/!TOTAL_STEPS!] 启动程序...
echo.
echo ============================================================
echo   正在启动 text2story 主程序...
echo ============================================================

cls

:: 运行 main.py
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

:: 如果程序异常退出，显示提示
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

:detect_python
:: 清除之前的结果
set "PYTHON_CMD="

:: 1) python 命令
python --version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    python -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_CMD=python"
        goto :eof
    )
)

:: 2) python3 命令
python3 --version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_CMD=python3"
        goto :eof
    )
)

:: 3) py 启动器（尝试所有版本）
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

:: 4) 直接扫描常见安装目录
call :find_python_direct 313
if defined PYTHON_CMD goto :eof
call :find_python_direct 312
if defined PYTHON_CMD goto :eof
call :find_python_direct 311
if defined PYTHON_CMD goto :eof
call :find_python_direct 310
if defined PYTHON_CMD goto :eof

:: 5) Anaconda / Miniconda 安装路径
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

:: 6) Windows Store 别名（%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe）
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
:: 扫描 Python 常见安装路径，参数为版本号简写（如 313）
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
:: winget 安装链: 3.13 → 3.12 → 3.11 → 3.10
:: 关键：一项安装成功后如 Python 不可识别则停止尝试（避免装 4 个 Python）
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

:: 方法1: ping（最常用，但部分网络禁 ICMP）
ping -n 1 -w 3000 www.baidu.com >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "NETWORK_OK=1"
    echo        网络连接正常
    goto :eof
)

:: 方法2: curl（Windows 10 1803+ 内置）
curl -s --connect-timeout 3 https://www.baidu.com >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "NETWORK_OK=1"
    echo        网络连接正常
    goto :eof
)

:: 方法3: PowerShell
powershell -Command "try {Invoke-WebRequest https://www.baidu.com -TimeoutSec 3 -UseBasicParsing | Out-Null; exit 0} catch {exit 1}" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "NETWORK_OK=1"
    echo        网络连接正常
    goto :eof
)

:: 三项全部失败
set "NETWORK_OK=0"
echo [警告] 无法连接网络！请检查网络连接后重试。
goto :eof

:refresh_path
echo        正在刷新 PATH 环境变量...
:: 从注册表读取系统 PATH 和用户 PATH
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
    :: 将 Python 常用安装路径前置到 PATH 头部（避免旧版本优先）
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
