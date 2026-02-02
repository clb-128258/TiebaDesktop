const VERSION_STR = "1.1";
console.info("CLB TiebaDesktop HTML5 Video Player Version " + VERSION_STR);
console.info("Video play engine made by xgplayer.js, website: https://v2.h5player.bytedance.com/");

function getValueFromParams(key) {
    let searchParams = new URLSearchParams(window.location.search);
    let value = searchParams.get(key);
    return value == null ? "" : value;
}

function resizePlayer() {
    // 为中心player设置大小，同步窗口大小
    let video_area = document.getElementById('videoArea');
    video_area.style.height = window.innerHeight + 'px';
    video_area.style.width = window.innerWidth + 'px';
}

function initPlayer(video_url, cover_url) {
    const player = new Player({
        "id": "videoArea",
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
        "fitVideoSize": 'auto',
        "poster": cover_url
    });

    window.addEventListener('resize', resizePlayer);
    resizePlayer();  // 初始化后立刻设置大小
}

function runMain() {
    let url = getValueFromParams('url');
    let cover_url = getValueFromParams('cover');
    if (!(url.startsWith("http://") || url.startsWith("https://"))) {
        showToastInPythonClient("你的视频链接不合法，请提供一个有效的视频链接", ToastIconType.ERROR);
        setTimeout(() => { closeCurrentPage(); }, 2400);
    }
    else {
        initPlayer(url, cover_url);
    }

}