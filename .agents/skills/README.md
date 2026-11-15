# Android APK 分析技能

本目录存放用于静态分析 Android 客户端、对照贴吧官方 APK 逻辑的技能。

| 技能 | 用途 |
|---|---|
| `tieba-apk-comparison/` | 贴吧官方 APK 与 TiebaDesktop 的取证、调用链和差异对比流程 |
| `android-reverse-engineering/` | JADX、Vineflower/Fernflower、Kotlin 名称恢复、API 与调用链提取 |
| `apk-reverse/` | apktool、Manifest、smali、重打包，以及按需进入 native/Frida |

建议入口：

```text
读取 tieba-apk-comparison/SKILL.md，按其中流程分析这个 APK
```


默认约束：

- 默认静态分析，不修改原始包，不安装重打包产物
- APK、反编译源码和抓包产物放入 `apk-analysis/`，该目录已被忽略
- 报告中不得出现 BDUSS、STOKEN、Cookie、真实 UID、手机号或其他用户私密数据
- 动态 Hook、绕过证书校验或重打包安装仅在明确授权的测试环境中执行



安装说明见 `android-reverse-engineering/references/setup-guide.md` 和 apktool 官方文档。工具安装独立于本技能库，未自动执行。

上游来源、固定提交和本地修改见 `THIRD_PARTY_NOTICES.md`。
