const VERSION_STR = "1.1";
console.info("CLB TiebaDesktop HTML5 Video Player Version " + VERSION_STR);
console.info("Video play engine made by xgplayer.js, website: https://v2.h5player.bytedance.com/");

function getUrlFromParams() {
    let searchParams = new URLSearchParams(window.location.search);
    let value = searchParams.get('url');
    return value == null ? "" : value;
}


function initPlayer(video_url) {
    const player = new Player({
        "id": "videoArea",
        "playsinline": true,
        "keyShortcut": "on",
        "playbackRate": [
            0.5,
            1,
            1.5,
            2,
            4,
        ],
        "download": true,
        "pip": true,
        "screenShot": true,
        "url": video_url,
        "autoplay": true,
        "volume": 0.5,
        "fitVideoSize": 'fill',
        "fluid": true,
    });
}

function runMain() {
    let url = getUrlFromParams();
    if (!(url.startsWith("http://") || url.startsWith("https://"))) {
        showToastInPythonClient("你的视频链接不合法，请提供一个有效的视频链接", ToastIconType.ERROR);
        setTimeout(() => {closeCurrentPage();}, 2400);
    }
    else {
        initPlayer(url);
    }

}