import AppKit
import UniformTypeIdentifiers

enum ImportKind { case reference, media, project }

@MainActor
protocol FileDialogs {
    func open(in window: NSWindow, multiple: Bool, kind: ImportKind, completion: @escaping ([URL]?) -> Void)
    func save(in window: NSWindow, filename: String, completion: @escaping (URL?) -> Void)
}

@MainActor
struct NativeFileDialogs: FileDialogs {
    func open(in window: NSWindow, multiple: Bool, kind: ImportKind, completion: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        switch kind {
        case .reference:
            panel.title = "导入参考录音"
            panel.message = "选择一段清晰的人声录音，建议 5 至 15 秒。"
            panel.prompt = "使用录音"
        case .media:
            panel.title = "导入媒体"
            panel.message = "选择要在这台 Mac 上处理的音频或视频。"
            panel.prompt = "导入"
        case .project:
            panel.title = "导入配音项目"
            panel.message = "选择包含台词、音色与媒体的 Timbreloom 项目包。"
            panel.prompt = "打开项目"
        }
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = multiple
        let extensions = kind == .project ? ["timbreloom", "zip"]
            : kind == .reference ? ["webm", "ogg", "caf"] : ["webm", "ogg", "caf", "mkv", "ts", "m2ts", "mts"]
        let types: [UTType] = kind == .project ? [] : kind == .reference ? [.audio] : [.audio, .movie]
        panel.allowedContentTypes = types
            + extensions.compactMap { UTType(filenameExtension: $0) }
        panel.beginSheetModal(for: window) { response in completion(response == .OK ? panel.urls : nil) }
    }

    func save(in window: NSWindow, filename: String, completion: @escaping (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.title = "导出文件"
        panel.prompt = "保存"
        panel.nameFieldStringValue = (filename as NSString).lastPathComponent
        if let type = UTType(filenameExtension: (filename as NSString).pathExtension) {
            panel.allowedContentTypes = [type]
        }
        panel.canCreateDirectories = true
        panel.beginSheetModal(for: window) { response in completion(response == .OK ? panel.url : nil) }
    }
}
