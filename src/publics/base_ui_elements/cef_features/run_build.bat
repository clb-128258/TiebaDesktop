@echo off
echo TiebaDesktop CEF bridge builder
echo NOTICE: make sure you have run vcvars*.bat and have a CEF built.
echo Cef needs to use version 109.1.18+gf1c41e4+chromium-109.0.5414.120 and provide built path in second arg.

if "%CEF_ROOT%"=="" set "CEF_ROOT=%1"

if not exist "%CEF_ROOT%\include\cef_app.h" (
    echo CEF_ROOT does not look like a CEF binary distribution: %CEF_ROOT%
    echo Please set CEF_ROOT to the CEF binary distribution directory first.
    exit /b 1
)

mkdir build 2>nul
cd build
cmake .. -A x64 -DCEF_ROOT="%CEF_ROOT%"
cmake --build . --config Release

echo copying cef binary...
if not exist ..\..\..\..\binres\cef mkdir ..\..\..\..\binres\cef
copy /y .\Release\cef_bridge.dll ..\..\..\..\binres\cef\cef_bridge.dll
copy /y .\Release\cef_bridge_helper.exe ..\..\..\..\binres\cef\cef_bridge_helper.exe
xcopy /r /i /s /y /exclude:..\cef_exclude_list.txt "%CEF_ROOT%\Release" ..\..\..\..\binres\cef 
xcopy /r /i /s /y /exclude:..\cef_exclude_list.txt "%CEF_ROOT%\Resources" ..\..\..\..\binres\cef 

echo CEF bridge has been built.
