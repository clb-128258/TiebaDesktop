@echo off
echo winrt_url_share cpp part builder
echo NOTICE: make sure you have ran vcvars*.bat.

mkdir build
cd build
cmake ..
cmake --build . --config Release
copy /y .\Release\ShareBridge.dll ..\..\..\binres\ShareBridge.dll