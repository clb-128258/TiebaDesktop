#pragma once

#include <stdint.h>

#ifdef SHAREBRIDGE_EXPORTS
#define SHARE_API __declspec(dllexport)
#else
#define SHARE_API __declspec(dllimport)
#endif

extern "C"
{
    SHARE_API long ShareUrl(
        intptr_t hwnd,
        const wchar_t* url,
        const wchar_t* title
    );
}