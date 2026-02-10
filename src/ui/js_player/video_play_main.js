const VERSION_STR = "1.2.0";
const THEME_COLOR = "#5b44c8";
console.info("CLB TiebaDesktop HTML5 Video Player Version " + VERSION_STR);
console.info("Video play engine made by xgplayer.js, website: https://h5player.bytedance.com/");

function getValueFromParams(key) {
    function getValueDirectly(key) {
        let searchParams = new URLSearchParams(window.location.search);
        let value = searchParams.get(key);
        return value == null ? "" : value;
    }
    function getValueBase64(key) {
        let value = atob(getValueDirectly(key + '_b64'));
        return value == null ? "" : value;
    }

    let value_native = getValueDirectly(key);
    let value_b64 = getValueBase64(key);
    return !value_native ? value_b64 : value_native;
}

function resizePlayer() {
    // 为中心player设置大小，同步窗口大小
    let video_area = document.getElementById('videoArea');
    video_area.style.height = window.innerHeight + 'px';
    video_area.style.width = window.innerWidth + 'px';
}

function initPlayer(video_url, cover_url) {
    const player = new Player({
        id: "videoArea",
        keyShortcut: "on",
        url: video_url,  // 视频链接
        poster: cover_url,  // 封面链接
        volume: 0.5,  // 默认音量
        leavePlayerTime: 600,  // 鼠标离开后，隐藏控件栏的延时时间
        pip: true,  // 画中画窗口
        enableContextmenu: false,  // webview右键菜单，这里禁用
        cssFullscreen: false,  // 样式全屏，这里禁用
        download: true,  // 下载按钮
        playbackRate: [  // 倍速选项
            2,
            1.5,
            1.25,
            1,
            0.75,
            0.5,
        ],
        commonStyle: {
            playedColor: THEME_COLOR,  // 播放完成部分进度条底色
            volumeColor: THEME_COLOR  // 音量颜色
        }
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