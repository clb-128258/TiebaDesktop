#include "share_bridge.h"

#include <windows.h>
#include <shobjidl.h>

#include <string>

#include <wrl.h>
#include <winrt/base.h>

#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.ApplicationModel.DataTransfer.h>

using Microsoft::WRL::ComPtr;

extern "C"
long ShareUrl(
    intptr_t hwnd_value,
    const wchar_t* url,
    const wchar_t* title
)
{
    if (!url)
    {
        return E_INVALIDARG;
    }

    if (!hwnd_value)
    {
        return E_HANDLE;
    }

    try
    {
        // 初始化 COM Apartment（STA）
        winrt::init_apartment(
            winrt::apartment_type::single_threaded
        );

        HWND hwnd =
            reinterpret_cast<HWND>(
                hwnd_value
            );

        if (!IsWindow(hwnd))
        {
            return E_HANDLE;
        }

        // 拷贝字符串，避免 Python ctypes 生命周期问题
        std::wstring url_copy =
            url;

        std::wstring title_copy =
            title
                ? title
                : L"分享";

        // 获取 IDataTransferManagerInterop
        ComPtr<IDataTransferManagerInterop>
            interop;

        winrt::hstring runtimeClassName =
            L"Windows.ApplicationModel.DataTransfer.DataTransferManager";

        HRESULT hr =
            RoGetActivationFactory(
                reinterpret_cast<HSTRING>(
                    winrt::get_abi(
                        runtimeClassName
                    )
                ),
                IID_PPV_ARGS(&interop)
            );

        if (FAILED(hr))
        {
            return hr;
        }

        // 获取 DataTransferManager
        winrt::Windows::ApplicationModel::
            DataTransfer::DataTransferManager
            manager{ nullptr };

        hr =
            interop->GetForWindow(
                hwnd,
                winrt::guid_of<
                    winrt::Windows::ApplicationModel::
                    DataTransfer::DataTransferManager
                >(),
                winrt::put_abi(manager)
            );

        if (FAILED(hr))
        {
            return hr;
        }

        // 注册分享数据回调
        manager.DataRequested(
            [url_copy, title_copy](
                const auto&,
                const winrt::Windows::ApplicationModel::
                    DataTransfer::DataRequestedEventArgs& args
            )
            {
                auto request =
                    args.Request();

                auto data =
                    request.Data();

                // 标题
                data.Properties().Title(
                    winrt::hstring(
                        title_copy
                    )
                );

                // URL
                data.SetWebLink(
                    winrt::Windows::Foundation::Uri(
                        winrt::hstring(
                            url_copy
                        )
                    )
                );
            });

        // 显示系统分享窗口
        hr =
            interop->ShowShareUIForWindow(
                hwnd
            );

        return hr;
    }
    catch (
        const winrt::hresult_error& e
    )
    {
        return e.code();
    }
    catch (...)
    {
        return E_FAIL;
    }
}