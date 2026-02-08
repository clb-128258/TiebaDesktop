const ToastIconType = Object.freeze({ NO_ICON: 1, INFORMATION: 2, ERROR: 3, SUCCESS: 4 });

function getStringifyJsonText(type, datas) {
    var jsonobj = { "type": type, "argDatas": datas };
    return JSON.stringify(jsonobj);
}

function postMessageToWebView(msgString) {
    chrome.webview.postMessage(msgString);
}

function showToastInPythonClient(text, icon=1, duration=2000) {
    let jsontext = getStringifyJsonText("topToast", { "text": text, "iconType": icon, "duration": duration });
    postMessageToWebView(jsontext);
}

function closeCurrentPage() {
    let jsontext = getStringifyJsonText("closePage", null);
    postMessageToWebView(jsontext);
}