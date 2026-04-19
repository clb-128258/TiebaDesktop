<p align="center">
<img height="300" width="300" src="./docs/appicon-transparent.png" alt="APP Logo"/>
</p>
<div align="center">

# 贴吧桌面

![STARS](https://img.shields.io/github/stars/clb-128258/TiebaDesktop?style=round-square&logo=github&color=yellow) ![FORKS](https://img.shields.io/github/forks/clb-128258/TiebaDesktop?style=round-square) ![License](https://img.shields.io/badge/License-MIT-purple)

一个第三方百度贴吧电脑客户端, 使用 PyQt5 开发
</div>

> [!note]
>
> 由于学业原因，更新会较为缓慢，一些 Bug 可能无法及时修复，还请谅解。  
> 如对本项目有任何建议或问题，欢迎提交 Issues 或 PR。

## 项目特色

* 基于 Qt5 开发，原生框架性能开销低，兼容旧版系统
* 现代化的 UI 设计，针对电脑设备优化的 UI 布局
* 支持多种账号登录方式
* 丰富的个性化设置选项
* [启动参数调用功能](https://github.com/clb-128258/TiebaDesktop/blob/main/docs/command-usages.md)
* 更多强大且实用的贴吧功能...

## UI 展示

![Show Image 1](./docs/app-ui-grabs/1.png)
![Show Image 2](./docs/app-ui-grabs/2.png)
![Show Image 3](./docs/app-ui-grabs/3.png)
![Show Image 4](./docs/app-ui-grabs/4.png)

## 功能实现

- 账号管理
    - [x] 内置浏览器登录
    - [x] 扫码登录
    - [x] bduss + stoken 直接登录
    - [x] 多账号切换
    - [ ] 无痕登录模式
- 看贴
    - [x] 首页推荐看贴
    - [x] 吧内看贴
    - [x] 贴子详情页、楼层查看
    - [x] 楼中楼查看
    - [x] 查看富媒体（图片、视频、语音等）
    - [x] 保存贴内视频
    - [x] 跳页功能
- 发贴（不建议使用，可能导致 `封号` `发贴秒删` 等后果）
    - [ ] 发主题
    - [x] 发回复
    - [ ] 回复楼层 / 楼中楼
- 吧
    - [x] 查看自己关注的吧
    - [x] 查看吧详情信息
    - [x] 吧内关注、签到
    - [x] 一键签到、成长等级签到
    - [x] [命令行启动参数签到](https://github.com/clb-128258/TiebaDesktop/blob/main/docs/command-usages.md#%E7%AD%BE%E5%88%B0%E6%89%80%E6%9C%89%E5%85%B3%E6%B3%A8%E7%9A%84%E5%90%A7)
    - [x] 首页进吧页签到
    - [x] 翻倍的签到经验值
- 用户
    - [x] 个人主页
    - [x] 关注 / 拉黑 / 禁言用户
- 社区互动
    - [x] 点赞
    - [ ] 点踩
    - [x] 收藏
    - [x] 查看 点赞 / 回复 / @ 我的人
    - [x] 互动消息推送
- 足迹
    - [x] 收藏列表
    - [x] 点赞历史列表
    - [x] 内容浏览记录
- 实用功能
    - [x] 内置浏览器
    - [x] 全吧搜索
    - [x] 吧内搜索
    - [x] 右键文字搜索 / 链接跳转
    - [x] 剪切板链接跳转
    - [x] 无网络通知提示
    - [ ] 下载贴子数据
- 个性化
    - [x] 首页屏蔽视频贴
    - [x] 隐藏用户 IP 属地
    - [x] 设置贴内默认楼层顺序
    - [x] 设置吧内默认贴子排序
- 视觉体验
    - [x] 深色 / 浅色主题
    - [x] 跟随系统设置自动切换主题
- 等等...

> [!warning]
>
> `翻倍的签到经验值` 功能是基于 `官方小组件签到入口`
> 实现的，即通过手机端的桌面小组件进入贴吧再签到可获得双倍经验值。本软件通过这一原理实现了双倍签到经验。    
> 由于该特性可能涉及 `功能滥用`，因此默认情况下是关闭的，可以在软件设置中手动打开。

## 项目结构

```text
TiebaDesktop
├─ aiotieba-fix-files/  # aiotieba 修补文件
├─ build-tools/  # 构建工具
└─ src/  # 源代码
   ├─ binres/  # 二进制依赖
   ├─ proto/  # protobuf 相关文件
   ├─ publics/  # 公用组件代码库
   ├─ resf/  # 原始资源文件，原始 `.proto` 文件
   ├─ subwindow/  # 核心业务代码，包含了主要的子窗口类
   ├─ ui/  # UI 资源文件
   │  └─ js_player/  # 前端视频播放器
   ├─ consts.py  # 常量定义文件
   ├─ main.py  # 主程序入口点
   └─ requirements.txt  # 依赖列表
```

> [!note]
>
> 如果你有对本项目进行二次开发的需求，请参阅：
> * [如何配置贴吧桌面的开发环境](https://github.com/clb-128258/TiebaDesktop/blob/main/docs/how-to-set-up-env.md)
> * [主程序构建指南](https://github.com/clb-128258/TiebaDesktop/blob/main/docs/build-guide.md)

## 致谢

另外要特别感谢以下开源仓库：  
[lumina37/aiotieba - 贴吧 API 的 Python 实现](https://github.com/lumina37/aiotieba)，没有这个仓库就没有本软件的诞生。  
[n0099/tbclient.protobuf - 贴吧 .proto 定义合集](https://github.com/n0099/tbclient.protobuf)，该仓库为本项目的 protobuf
开发提供了很大的便利.  
[bytedance/xgplayer - 西瓜播放器](https://h5player.bytedance.com/)，本项目的视频播放器基于 `xgplayer` 开发。

## 友情链接

[TiebaLite - 一个第三方安卓贴吧客户端，已停更](https://github.com/HuanCheng65/TiebaLite)  
[TiebaLite (zzc10086) - 由第三方维护的 TiebaLite](https://github.com/zzc10086/TiebaLite)  
[NeoTieBa - 一个基于 Tauri2.0 + Vue3 + TypeScript 构建的非官方贴吧客户端](https://github.com/Vkango/NeoTieBa)  
[eazy-tieba - 一个强大且开源的百度贴吧工具箱](https://github.com/Dilettante258/eazy-tieba)

## 免责声明

1) 本软件只会在本地处理你的个人信息与账号数据，绝对不会被分享或上传到其他任何地方。
2) 本软件遵循 MIT License 发布，请在遵守 MIT License 的前提下使用本软件。
3) 本软件仅供学习交流使用，请勿用于任何商业或非法用途。使用本软件所产生的任何后果都与作者无关。

