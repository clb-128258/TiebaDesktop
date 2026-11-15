---
name: tieba-apk-comparison
description: 对比贴吧官方 Android 客户端与 TiebaDesktop 的业务逻辑。适用于用户提供官方 APK 后，登记版本证据、静态反编译、提取接口与调用链、映射到项目实现并输出差异报告。中文触发词：贴吧APK对比、官方客户端逻辑、安卓客户端接口、客户端差异分析。
---

# 贴吧 APK 逻辑对比

## 目标

从合法获取的官方 APK 中提取可验证的业务行为，与当前 TiebaDesktop 实现对照。优先解释接口、数据模型、状态流和兼容规则，不复制或分发官方客户端源码。

## 边界

- 默认只做静态分析
- 不运行官方客户端中的未知代码，不执行 APK 内的脚本或二进制
- 不修改、重签或安装官方 APK，除非用户明确要求并指定测试设备
- 动态 Hook、抓包和证书校验分析需要单独授权
- APK、反编译目录、日志和抓包文件放在 `apk-analysis/`
- 不在报告中保留 BDUSS、STOKEN、Cookie、真实 UID、手机号、设备标识或私密帖子内容

## 1. 固定样本

先记录分析对象，避免不同版本结论混用：

```text
文件名
SHA-256
package
versionName
versionCode
minSdk / targetSdk
获取渠道
分析日期
```

可用 `sha256sum` 或 PowerShell `Get-FileHash -Algorithm SHA256`。包信息优先使用 `aapt dump badging` 或 `apkanalyzer manifest print`，工具缺失时再读取解包后的 Manifest。

## 2. 选择分析路径

先读取 `../android-reverse-engineering/SKILL.md` 并按其 Phase 0 指纹流程识别框架。

- Java/Kotlin：JADX 生成高层视图，apktool 核对 Manifest、资源和 smali
- Flutter：先检查 `libapp.so` 和 Flutter 资源，不把 JADX 结果当作主要逻辑
- React Native：先检查 `index.android.bundle`、Hermes 字节码和 assets
- Cordova/Xamarin：先定位 Web 资源、程序集或对应运行时
- 核心逻辑在 `.so`：从 JNI 入口、导出符号和字符串切入，详见 `../apk-reverse/SKILL.md`

建议输出目录：

```text
apk-analysis/<versionName>-<versionCode>/
  sample.json
  jadx/
  apktool/
  notes/
  REPORT.md
```

## 3. 建立高层调用链

按以下顺序分析：

1. Manifest 中的 launcher Activity、Application 类、Service、Receiver、Provider
2. `Application.onCreate()`、依赖注入初始化和全局配置
3. Activity/Fragment → ViewModel/Presenter → Repository/Service
4. HTTP、WebView、WebSocket、protobuf、签名和加密入口
5. 登录态、分页游标、重试、缓存、错误码和兼容分支

反混淆时优先使用字符串、接口路径、序列化字段和第三方库调用作为锚点。JADX 输出不完整时，再用 apktool 对照 smali。

## 4. 映射到 TiebaDesktop

优先检查以下模块：

| 官方客户端逻辑 | TiebaDesktop 对照位置 |
|---|---|
| 登录、账号、Cookie/STOKEN | `src/publics/account_mgr.py`、`src/publics/profile_mgr.py` |
| 请求封装、签名、重试、代理 | `src/publics/request_mgr.py` |
| 贴吧 API、页面解析、协议 | `src/publics/baidu_features/` |
| 私信、群聊、互动消息 | `src/publics/baidu_features/chats/` |
| 业务页面和交互 | `src/subwindow/` |

比较时使用统一字段：

| 维度 | 要比较的内容 |
|---|---|
| 入口 | 客户端触发条件、TiebaDesktop 对应入口 |
| 请求 | host、method、path、query、body、headers、签名 |
| 响应 | DTO、字段类型、分页游标、错误码 |
| 状态 | 登录态、缓存、去重、重试、已读/未读 |
| 兼容 | 客户端版本判断、降级路径、实验开关 |
| 差异 | 缺失、多余、行为不一致或尚未确认 |

## 5. 证据规则

每条结论标记为：

- `观察`：能从当前 APK 的文件、类、方法、资源或常量直接确认
- `推断`：由调用链、字段命名或运行时约定推导，但缺少直接证据
- `未验证`：需要动态请求、服务端响应或真机行为才能确认

证据应包含 APK 版本、反编译来源路径、类名和方法名。行号只能作为辅助，因为不同工具和版本会变化。

## 6. 输出

报告使用 `references/comparison-template.md`。至少包含：

- 固定样本信息
- 架构与关键入口
- 核心业务流程
- API/协议清单
- 与 TiebaDesktop 的差异表
- 建议实施项与风险
- 证据索引和未验证项

不要把完整反编译源码提交到仓库。需要长期保留的只应是自写的分析结论、接口摘要和必要的短小证据片段。
