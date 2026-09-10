# Timbreloom Mac 本机候选版验收

验收日期为 2026-09-08，目标版本为 1.1.0 RC6，内部构建号为 8。
本次使用独立生产依赖环境组装发行包，移除开发测试工具、依赖库测试集和重复元数据。
模型仍由用户按需下载，权重不在 App 内。
交付范围为本机候选版，没有公开发布或提交 Apple 公证。
验收环境为 Apple Silicon、macOS 26.6.2，最低系统要求为 macOS 26.2。

## 当前产物

应用位于 `build/release/Timbreloom.app`，同一构建已安装至 `~/Applications/Timbreloom.app`。
镜像为 `build/release/Timbreloom-1.1.0-rc6-arm64.dmg`，校验文件为同目录的 `.sha256`。
汇总回执位于 `build/release-validation/release-receipt-rc6.json`。

| 体积 | RC5 | RC6 | 减少 |
| --- | --- | --- | --- |
| DMG | 1197930044 字节，约 1.20 GB | 1052827613 字节，约 1.05 GB | 145102431 字节，约 12.1% |
| App 内普通文件的逻辑总大小 | 2718255443 字节，约 2.72 GB | 2489549594 字节，约 2.49 GB | 228705849 字节，约 8.4% |

逻辑大小不计符号链接，也不代表 APFS 克隆后的实际新增磁盘占用。
镜像 SHA-256 为 `e9d7c8c93b41ec81013d979be0d5450fd45734683eda300d17ce18fea47c2d0d`。
签名为 Apple Development，启用 Hardened Runtime；没有 Developer ID 发行签名或公证票据。
Python 3.12、Seed-VC 专用 Python 3.10、推理库、FFmpeg 9.0.1 和必要的对应源码仍随包提供，因此不需要源码目录或 Homebrew。
这些运行组件仍占据安装包的大部分体积。

## 生产依赖隔离

`scripts/release_runtime.py` 为每次构建创建新的临时环境。
主服务通过 `uv sync --locked --no-default-groups --no-editable` 安装 `uv.lock` 中的运行依赖。
Seed-VC 通过 `packaging/seed-vc-runtime.lock` 安装固定版本并核对分发文件哈希。
构建使用已有 Python 解释器，但不复制开发环境的已安装包，也不改动开发环境。
便携解释器的基础 site-packages 不再混入发行环境，消除了旧包中 pip 和 setuptools 的重复版本元数据。
两个锁文件的 SHA-256、实际依赖清单、裁剪路径与字节数都记录在 App 的 `ReleaseManifest.json` 中。
打包脚本拒绝未标记为生产环境的旧包。
主服务从 90 个依赖分发条目减至 83 个，Seed-VC 从 103 个元数据条目减至 99 个。
保留的依赖版本与原来验证过的环境一致，没有借本次清理升级依赖。
发行副本移除了名为 `test`、`tests` 的测试集目录、pip / pytest、Python 自带安装引导及开发界面、解释器构建头文件。
`numpy.testing`、`unittest`、包内头文件和上游声明的运行依赖仍保留，以满足现有导入与执行需求。
其中包括 Torch 需要的 setuptools，以及音频库依赖链中的部分交互与绘图组件。
第三方许可与必要的对应源码仍保留。
构建和测试流程留在项目中，检查最终 App 时使用项目的开发工具。

## 本次直接验证

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| 发行环境约束与裁剪 | 2 项通过，覆盖开发依赖和重复元数据拒绝，以及运行辅助模块、头文件、资料与许可保留 | `build/release-validation/runtime-clean/unit-final.log` |
| 独立环境依赖检查 | 两套环境的 uv pip check 通过，主服务与实际 Seed-VC 推理模块导入通过 | `build/release-validation/runtime-clean/preflight-report.json`、同目录 `import-main.log`、`import-seed.log` |
| 依赖版本比较 | 保留的包没有版本变化 | `build/release-validation/runtime-clean/dependency-diff.json` |
| 最终包内容 | 两套生产环境、无测试集与 pip / pytest、无模型权重、应用源码哈希一致 | `build/release-validation/rc6-bundle-check.json` |
| 镜像与签名 | DMG 校验、打包前签名、只读推理后的严格签名、安装副本的严格签名均通过 | `build/release-validation/package-rc6.log`、`verify-rc6.log`、汇总回执 |
| 无模型的独立启动 | 空 HOME、独立资料库、只读 App 启动通过，未创建模型目录，处理请求返回先下载的提示 | `build/release-validation/fresh-rc6/receipt.json` |
| 真实离线流程 | Whisper、Qwen、Seed-VC、WAV / SRT / MP4、项目包回读与实际原生 H.264 回退通过，217.10 秒 | `build/release-validation/real-models-rc6-readonly/receipt.json` |
| 安装版界面 | 首页正常，模型管理的三个已有模型就绪，外部目录可见，检查后返回首页 | `build/release-validation/native-rc6.json` |
| 原资料保留 | 56 个内容文件、337721107 字节全部哈希相同，2 个音色和 5 条换声记录保留 | 同上，另有 1 个空的服务锁文件 |
| 退出与临时资源 | 验证服务退出，镜像正常卸载，临时生产环境与安装暂存目录已清理 | `build/release-validation/verify-rc6.log`、汇总回执 |

无模型的第一次执行到服务可用耗时 91.03 秒，包括程序入口之前的系统执行检查。
随后独立功能测试的服务就绪耗时 0.391 秒，这不是首次安装性能承诺。
本次生成语音回转录中，Qwen 字错率为 10.71%，Seed-VC 为 25%，后者恰好达到现有门槛。
两者均通过有效响度和无严重削波检查，但不能据此保证人工试听质量。
真实推理使用外部模型目录和独立测试资料库，没有重新下载用户已有模型。

## 沿用的模型下载功能证据

应用源码与模型下载流程在本次清理中没有改变，因此没有重复完整网络下载或全部 WebKit 回归。
RC5 的 79 项 Python 回归、5 项播放录音逻辑检查、真实 Whisper 完整下载与中断恢复、WebKit 下载交互和四工作区回归记录保留在 `build/release-validation/release-readiness-rc5.md`。
对应汇总回执为 `build/release-validation/release-receipt-rc5.json`。
这些是 RC5 的验证记录，本次 RC6 的直接验证范围见上表。
模型仍位于 `~/Library/Application Support/Timbreloom/models`，更新 App 会复用它们。
启动和读取状态不会下载模型，下载、暂停、续传及失败重试由用户选择。

## 本机候选版的边界

此次没有完成 Developer ID 签名、公证或其他 Mac 上的 Gatekeeper 首次启动复验。
真实麦克风权限与录音仍未验收，本次没有授予新权限或录制声音。
人工试听、跨说话人与长音频质量评估仍应单独进行。

## 构建与复验

```bash
.venv/bin/python scripts/build_macos_app.py --release --development-signing --build-number 8
.venv/bin/python scripts/package_macos_release.py --app build/release/Timbreloom.app --output build/release/Timbreloom-1.1.0-rc6-arm64.dmg
.venv/bin/python scripts/verify_release.py --app build/release/Timbreloom.app --models-dir "$HOME/Library/Application Support/Timbreloom/models" --output build/release-validation/new-offline-run
```

最后一条命令要求外部目录已下载三组模型，并且输出目录尚不存在。
更多依赖维护细节见 `packaging/README.md`。
旧 App 备份和 RC5 镜像保留，方便回退。
本次未执行 commit、push、公开发布或公证上传。
安装版 App 留在首页供日常使用，其本地服务由 App 管理，`⌘Q` 退出时停止。
