# Timbreloom 项目格式

Timbreloom 1.0 把每个配音项目保存在 `data/projects/<project-id>/`。
项目目录是日常工作的权威副本，网页只是该数据的本地编辑界面。

## 目录结构

```text
<project-id>/
├── project.json
├── source.wav
├── source-media.<ext>       可选的视频源文件
├── waveform-<points>.json   可重建的波形缓存
├── renders/                 内容指纹命名的片段 WAV
├── jobs/                    生成和导出任务快照
├── exports/                 WAV、SRT 和可选 MP4
└── bundles/                 最近生成的 .timbreloom 项目包
```

`project.json` 当前使用 schema version 4。
服务读取旧 schema 1、2 或 3 项目时会在原目录中执行向前迁移，并保留源媒体、片段文字、缓存和已有导出记录。

## 片段不变量

每个片段同时保存只读 `source_text` 和可编辑 `active_text`。
拆分和合并操作会更新 `source_segment_ids`，因此仍然可以追溯到原始 ASR 片段。
片段按 `order` 和非递减 `start` 排序，且 `end` 不能早于 `start`。

渲染内容指纹包含配音文字、实际音色、目标语言、模型 ID 和生成设置。
修改时间戳、音量或时长适配方式不会重新生成语音，因为这些字段只影响最终时间线。
修改文字或实际音色只会把受影响片段标记为过期。

## 角色和音色

角色是项目级对象，包含名称、显示颜色和可选音色 ID。
片段保存 `role_id` 与解析后的 `voice_id`，所以导出不依赖运行时猜测。
修改角色绑定的音色会只使引用该角色的片段缓存过期。

## 安全时长适配

`fit_mode` 为 `natural` 时，生成语音按自然时长放回原起点。
`fit_mode` 为 `slot` 时，导出任务使用保音高变速向片段时间槽靠拢。
速度限制固定为 0.8x 到 1.25x，任何超出范围的内容都不会被截断。

## 项目包

`.timbreloom` 是 ZIP 容器，当前 bundle version 为 2，包含版本化 `manifest.json`、`project.json`、项目使用的参考音色、源媒体、片段渲染和已有导出。
导入音色时，同 ID 且内容一致的档案会复用；同 ID 但内容不同的档案会使整个导入失败，不会静默覆盖本地音色。
任务快照、波形缓存和嵌套项目包不进入项目包，因为它们不是迁移后的运行前提。
导入器拒绝绝对路径、父目录穿越、过多条目和超过安全上限的解压数据。
导入始终生成新的项目 ID 并重置未完成任务引用，不覆盖本地现有项目。
