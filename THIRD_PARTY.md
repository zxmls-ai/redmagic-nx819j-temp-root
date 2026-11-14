# 第三方来源与发布范围

本项目公开实测流程和配套脚本，不是核心利用程序的完整开源发行版。尚未确认作者工具包内每一个二进制的对应源码、构建方法和完整再分发许可，因此不把这些文件上传到仓库或 Release。

## 上游工具包

- 作者：卒迹v。
- [教程](https://www.bilibili.com/video/BV1KFxK6ZEZF)
- [作者置顶下载入口](https://wwbne.lanzoue.com/iICRi4dnrlsh)
- 压缩包：`临时root.7z`，公开提取密码 `6gef`。
- 精确校验值见 [materials.json](materials.json)。

流程使用 `越狱助手_3.0.0.Apk` 内的 10 个配套文件，以及压缩包中的 `KernelSU.apk`。提取程序只写入使用者电脑的 `vendor/assets`。APK、原始符号表、上游 run.sh、核心提权程序、KernelSU 模块及 ksud 均不随仓库分发。

核心提权二进制没有修改。运行时会对使用者本地的上游 run.sh 做一次文本替换，将目录清理限制到本次工作目录；这个派生文件保存在本地 `logs/`，不纳入发布文件。

哈希只能确认与实测文件相同，不能证明二进制安全、完整源码可用或允许任意再分发。若作者更换内容导致哈希不同，应停止并重新审查。

## KernelSU 与研究参考

- [KernelSU](https://github.com/tiann/KernelSU)：内核 Root 方案与管理器；其组件按各自上游许可证使用。本仓库未证明第三方包内所有文件与官方发布完全一致。
- [KernelSU 官方文档](https://kernelsu.org/guide/installation.html)：LKM 概念参考。
- [Feng1586/CVE-2026-64560-public](https://github.com/Feng1586/CVE-2026-64560-public)：采样顺序与交叉验证参考，覆盖其他机型，不能当作 NX819J 工具包逐项对应的完整源码。本仓库没有复制其利用代码。
- [Android Platform-Tools](https://developer.android.com/tools/releases/platform-tools)：用户自行从 Google 获取的 ADB。

CVE 标记沿用上游工具输出和公开研究名称；本项目没有独立审计整个漏洞链，不据此声称所有相同版本内核都可利用。

## MIT 的范围

`LICENSE` 适用于仓库原创文档、Python/批处理/采样脚本和测试，不覆盖链接的软件、自行下载的文件或 APK 内资产。KernelSU 截图用于记录本次测试，第三方软件名称、标识和界面的权利仍归各自权利人。
