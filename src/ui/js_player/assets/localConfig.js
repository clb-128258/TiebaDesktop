const DEFAULT_LOCAL_CONFIG = { video_volume: 0.5 }

function getLocalConfig() {
    var configString = localStorage.getItem("js_player_config");

    if (configString == null) {
        saveLocalConfig(DEFAULT_LOCAL_CONFIG);
        var configJson = DEFAULT_LOCAL_CONFIG;
    }
    else {
        var configJson = JSON.parse(configString);
    }
    return configJson;
}
function saveLocalConfig(config) {
    localStorage.setItem("js_player_config", JSON.stringify(config));
}
function getVolume() {
    return getLocalConfig().video_volume;
}
function saveVolume(volume) {
    let config = getLocalConfig();
    config.video_volume = volume;
    saveLocalConfig(config);
}