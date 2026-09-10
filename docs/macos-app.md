# Timbreloom for Mac

Timbreloom 提供原生 Apple Silicon 窗口、侧栏、菜单、文件面板和四个声音工作区。
独立安装包包含 Python、FFmpeg 和推理依赖，不需要源码目录或 Homebrew。
模型权重与 App 分开，由用户按需选择下载，首次启动不会获取模型。
当前安装包要求 macOS 26.2 或更新版本，系统要求由实际随包二进制推导，验收系统为 macOS 26.6.2。
发行验收、签名状态和实际验证结果见项目中的 `docs/release-readiness.md`。

## 日常使用

| 操作 | 快捷键 / 行为 |
| --- | --- |
| 切换工作区 | `⌘1` 声音克隆，`⌘2` 原声换色，`⌘3` 本地转录，`⌘4` 配音项目 |
| 导入文件 | `⌘O`，或工具栏的导入按钮；配音工作区导入 `.timbreloom` 项目包 |
| 开始处理 | `⌘Return`，执行当前工作区可用的生成、转录或新建配音项目操作 |
| 保存编辑 | `⌘S`，保存当前转录或配音项目的修改 |
| 显示 / 隐藏侧栏 | `⌃⌘S` |
| 管理模型 | `⌘,`，或侧栏底部的“模型管理” |
| 重新显示工作台 | 点击 Dock 图标，或使用 `⌘0` |
| 查看本地资料 | 工具栏的文件夹按钮，在 Finder 中打开资料库 |
| 导出文件 | 下载链接会打开系统保存面板，完成后在 Finder 中显示文件 |
| 关闭窗口 | `⌘W`，App 与任务继续运行，录音也不会因关闭窗口而自动结束 |
| 退出 App | `⌘Q`，存在任务、未保存的编辑、已选文件或导出时会提醒 |

克隆输入文字、参考录音文字、音色名称和转录词汇提示会保存为本机草稿。
音频文件本身不会复制进浏览器草稿存储，退出后可能需要重新选择。
转录与配音编辑仍需点击保存或使用 `⌘S`。
工作区分别记住当前阅读位置；切回来可以继续编辑。
选择了已保存音色时，取消导入录音会保留当前音色。
音频试听提供播放 / 暂停、可用方向键调整的播放位置，以及 0.75× 至 2× 倍速。
原始视频继续使用系统视频控件。
界面规范与组件验收记录见 [Mac 界面设计](macos-design.md)。
首次使用录音时，macOS / WebKit 会请求麦克风权限，需要你自行允许。

## 启动与退出

将应用复制到 Applications 后再打开。
独立包将资料保存在 `~/Library/Application Support/Timbreloom/data`，替换应用不会删除资料库。
从旧本机版升级时，先退出旧 App，再使用下方的迁移命令复制资料；源目录保留原样，已有目标资料库不会被覆盖。
App 只连接 `127.0.0.1`，并核对运行目录和资料库路径，避免连到其他项目的服务。
来自其他网站的 Origin 和非本机 Host 请求会被拒绝。
资料库的进程锁阻止新版网页服务与 App 服务同时写入同一套文件。
遇到启动错误时，窗口保留重试入口；帮助菜单也可以打开运行日志。
日志位于 `~/Library/Logs/Timbreloom/desktop.log`，超过 2 MB 会轮转保留上一份。
原生启动阶段记录在同目录的 `startup-latest.json`，区分程序入口、窗口显示、WebKit 创建和工作区就绪。

App 启动时不预加载语音模型，首次推理才导入并加载对应依赖与权重。
窗口先显示，再初始化 WebKit；网页图标在构建时生成，首次打开工作区从页面顶部开始。
启动和检测到处理任务期间使用 macOS 活动声明，防止 App Nap 和自动系统休眠打断工作；空闲后释放声明。
关闭窗口后，已开始的任务会继续运行；重新点击 Dock 图标可以返回原来的状态。
确认退出时，只会终止 App 自己启动的服务和子进程，终端启动的服务继续由终端管理。
App 意外退出时，进程监护器会清理属于它的 Python、FFmpeg、ASR 与换色子进程。
再次启动时，TTS、ASR、配音渲染与导出按现有持久化规则恢复；中断的换色任务从记录中重试并复用有效分段。

## 版本与可选功能

独立包的推理运行时、媒体工具、依赖许可和必要的对应源码都位于应用内部。
模型管理提供三个独立下载项：Qwen 声音克隆与配音约 2.52 GB，Whisper 本地转录约 464 MB，Seed-VC 原声换色及其依赖约 1.88 GB。
仅点击下载后才连接 Hugging Face，下载固定版本并检查每个文件的 SHA-256，全部完成后才启用该模型。
模型位于 `~/Library/Application Support/Timbreloom/models`，可以通过 `TIMBRELOOM_MODELS_DIR` 覆盖。
网络中断、暂停或退出时保留部分文件，用户点击继续或重试后才恢复下载。
关闭模型面板不会停止下载，退出 App 会暂停下载。
缺少模型时仍可浏览与编辑已有资料，处理前会提示下载所需模型。
已下载的模型支持离线推理，更新 App 会复用独立模型目录。
第三方许可可以从帮助菜单打开。
数据和可重建缓存写入用户目录，应用目录只读时仍可使用本地功能。
使用默认构建命令生成的开发外壳仍依赖当前项目的 `.venv`、模型、FFmpeg 和固定路径，移动项目后需要重新构建。
开发外壳与完整包核对各自的运行根目录，不会交叉连接同一端口上的另一版本。
开发签名只用于本机验收，面向其他用户的最终版本需要 Developer ID 签名与 Apple 公证。

从 Finder 启动的 App 通常不继承终端的 `GEMINI_API_KEY`。
本地声音功能不需要这个密钥。
如需可选的 Gemini 文字工具，可退出 App 后，从已经导出该环境变量的终端直接运行应用内的 `Contents/MacOS/Timbreloom`。
App 不读取整个 shell 配置，不复制密钥到 App 包或草稿，也不会自动发起云端请求。

## 构建

需要已安装的 Xcode / Command Line Tools 与项目 Python 环境。

```bash
cd ~/Projects/Timbreloom
.venv/bin/python scripts/build_macos_app.py --install
open ~/Applications/Timbreloom.app
```

以上命令构建开发外壳，产物位于 `build/Timbreloom.app`，`--install` 同时安装到 `~/Applications`。
完整包的本机验收构建如下。

```bash
.venv/bin/python scripts/build_ffmpeg.py
.venv/bin/python scripts/build_macos_app.py --release --development-signing
.venv/bin/python scripts/migrate_macos_data.py --source data
.venv/bin/python scripts/migrate_macos_models.py --source models
```

完整包位于 `build/release/Timbreloom.app`。
发行构建会创建独立临时环境，主服务仅安装 `uv.lock` 中的运行依赖，Seed-VC 使用 `packaging/seed-vc-runtime.lock` 的固定版本与下载哈希。
构建不会复制开发环境的已安装包，也不会改动开发环境。
临时环境由构建脚本在结束或失败时清理，首次构建可能需要下载已锁定的依赖包。
运行包排除 pytest、pip 等开发测试工具、依赖库测试集和 Python 的开发工具，打包前检查这些内容没有混入。
上游声明为运行依赖的库仍然保留，包括 Torch 所需的 setuptools，以及音频库所需的部分交互和绘图组件。
构建与测试流程留在项目中，不随 App 安装为开发工具。
没有 Apple Development 证书时，省略 `--development-signing` 可得到本机 ad-hoc 版本，但它不能验证 Hardened Runtime。
构建包含三项可选模型的固定版本、大小和校验值清单，不复制模型权重，并检查 Mach-O 依赖是否指向应用外的非系统库。
模型迁移命令校验并复制已有权重，保留源目录和已完整安装的目标模型，无需重新下载。
替换同名 Timbreloom App 前，构建脚本会将旧包移动保存到 `build/previous-apps/`。
移动备份保留旧包，并避免反复压缩大型模型。
App 包不包含个人音色、录音、转录、项目或密钥。
修改完整包的 Swift、Python 或静态界面后都需要重新构建和签名。

## 实现与验证

窗口、侧栏、菜单、文件选择和保存面板使用 AppKit，工作区使用系统 WebKit。
原生与网页之间只传递工作区、状态和固定命令，网页不能通过桥接任意读取本地路径。
外部导航不会取代工作台；用户主动点击的普通外链交给默认浏览器。
导出使用 WebKit 的下载代理，在临时文件完整下载后再移动或替换目标文件。
实现依据 [Apple WKDownloadDelegate](https://developer.apple.com/documentation/webkit/wkdownloaddelegate) 和 [WKUIDelegate](https://developer.apple.com/documentation/webkit/wkuidelegate) 的公开接口。

```bash
TIMBRELOOM_PRELOAD=0 TIMBRELOOM_DATA_DIR=/tmp/timbreloom-tests uv run pytest -q
node --test tests/test_browser_helpers.mjs
.venv/bin/python scripts/e2e_macos.py
.venv/bin/python scripts/e2e_macos.py --models
```

Python 检查涵盖资料库互斥、无需扫描媒体的状态接口、排队任务退出保护、延迟导入和服务进程组退出。
WebKit 集成检查在独立临时资料库内运行，使用合成音频与模拟 ASR，覆盖四个工作区在 1020、760、640pt 内容宽度下的布局、导入取消与替换、空状态跳转、上传转录、保存文字、SRT 下载与覆盖、草稿恢复和导航限制。
同一检查还验证配音创建快捷键、工作区滚动恢复、音频播放 / 暂停 / 定位 / 倍速，以及窄窗口下吸顶工具栏的高度。
每次检查会在隔离的临时资料库内保存当前 WebKit 界面截图。
权限拒绝、录音中和取消使用合成麦克风实现验证，处理进度与错误使用模拟 ASR 验证。
文件选择结果由测试实现注入，因此该检查不能证明系统文件面板的外观、真实麦克风录音或模型生成质量。

`scripts/benchmark_startup.py` 使用独立资料库和全新服务进程测量服务就绪及页面送达，并检查模型未被加载。
它不清除系统文件缓存，也不把页面送达时间当成原生窗口绘制时间。
工作进程在可选依赖导入前启动诊断，慢导入超过 15 秒时会把栈记录在本机日志中。
`scripts/verify_release.py` 从指定应用包运行真实 Whisper、Qwen、Seed-VC、配音导出、项目包回读和生成语音回转录。
它使用空白 HOME、独立资料库、离线模型标志和包内 FFmpeg，并验证输出音频、字错率及原生 H.264 回退路径。
详细测量与限制记录在发布验收文档中，单台 Mac 的数据不能作为跨机器性能或主观音色质量保证。
