# 命令行用法

## 静默执行参数

用法：在任意指令后面加上 `--quiet`  
指令执行完成后默认有弹窗提示，如需不显示弹窗而直接结束程序，请添加此参数。  
该参数可以与任意参数叠加使用。

## 切换账号

用法：`--set-current-account --userid=YOUR_UID`  
其中 YOUR_UID 为你的用户 ID，可以在 软件设置-账号切换 中复制出你的用户 ID。  
不能与参数 `--sign-all-forums` 或 `--sign-grows` 叠加使用，否则程序只会执行 `--set-current-account` 所对应的操作，而忽略其它的参数。

## 签到所有关注的吧

用法：`--sign-all-forums`  
该参数还可以与 `--sign-grows` 叠加使用。
不能与参数 `--set-current-account` 叠加使用，否则程序只会执行 `--set-current-account` 所对应的操作，而忽略本参数。

## 成长等级签到

用法：`--sign-grows`  
该参数还可以与 `--sign-all-forums` 叠加使用。  
不能与参数 `--set-current-account` 叠加使用，否则程序只会执行 `--set-current-account` 所对应的操作，而忽略本参数。
