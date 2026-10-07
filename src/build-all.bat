@echo off
echo TiebaDesktop Total C++ Builder
echo NOTICE: make sure you have run vcvars*.bat.
echo About CEF: need to use version 109.1.18+gf1c41e4+chromium-109.0.5414.120 and provide built path in second arg for this script.

cd ./publics/audio_decoder
call run_build.bat
cd ../../../

cd ./publics/winrt_url_share
call run_build.bat
cd ../../../

if "%1"=="" ( 
    echo CEF build skipped
) else (
    cd ./publics/base_ui_elements/cef_features
    call run_build.bat %1
    cd ../../../../
)

echo ALL builds complete.