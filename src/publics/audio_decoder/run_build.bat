@echo off
echo tieba_audiodec builder (mp3 + amr-nb)
echo NOTICE: make sure you have ran vcvars*.bat.

mkdir build 2>nul
cd build
cmake .. -A x64
cmake --build . --config Release
copy /y .\Release\tieba_audiodec.dll ..\..\..\binres\tieba_audiodec.dll