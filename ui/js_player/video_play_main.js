const VERSION_STR = "1.1";
console.info("CLB TiebaDesktop HTML5 Video Player Version " + VERSION_STR);
console.info("Video play engine made by xgplayer.js, website: https://v2.h5player.bytedance.com/");

function getUrlFromParams() {
    let searchParams = new URLSearchParams(window.location.search);
    return searchParams.get('url');
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


    window.addEventListener('resize', () => {
        //player.resize(); // 通知播放器重新计算尺寸
    });
}

