@echo off
setlocal
echo TiebaDesktop CEF bridge builder
echo NOTICE: make sure you have run vcvars*.bat and have a CEF built.
echo CEF 109+ is supported (verified with 109.1.18 and 156.0.0).

if "%CEF_ROOT%"=="" set "CEF_ROOT=%1"

if not exist "%CEF_ROOT%\include\cef_app.h" (
    echo CEF_ROOT does not look like a CEF binary distribution: %CEF_ROOT%
    echo Please set CEF_ROOT to the CEF binary distribution directory first.
    exit /b 1
)

if not exist build mkdir build
cd build
if errorlevel 1 exit /b 1

cmake .. -A x64 -DCEF_ROOT="%CEF_ROOT%"
if errorlevel 1 exit /b 1

cmake --build . --config Release
if errorlevel 1 exit /b 1

echo copying cef binary...
rem Switching CEF versions requires replacing the whole runtime.
rem cef_bridge.dll, cef_bridge_helper, libcef.dll and paks/locales must come
rem from the same CEF distribution. Mixing them causes API version 0 crashes.
if exist ..\..\..\..\binres\cef rmdir /s /q ..\..\..\..\binres\cef
if exist ..\..\..\..\binres\cef echo Failed to clean ..\..\..\..\binres\cef - close TiebaDesktop and retry.
if exist ..\..\..\..\binres\cef exit /b 1
mkdir ..\..\..\..\binres\cef
if errorlevel 1 exit /b 1

copy /y .\Release\cef_bridge.dll ..\..\..\..\binres\cef\cef_bridge.dll
if errorlevel 1 exit /b 1
copy /y .\Release\cef_bridge_helper.exe ..\..\..\..\binres\cef\cef_bridge_helper.exe
if errorlevel 1 exit /b 1

xcopy /r /i /s /y /exclude:..\cef_exclude_list.txt "%CEF_ROOT%\Release" ..\..\..\..\binres\cef
xcopy /r /i /s /y /exclude:..\cef_exclude_list.txt "%CEF_ROOT%\Resources" ..\..\..\..\binres\cef

echo CEF bridge has been built.
endlocal
