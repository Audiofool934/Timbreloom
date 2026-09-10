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
            panel.title = "Import Reference Audio"
            panel.message = "Choose a clear voice recording, ideally 5 to 15 seconds long."
            panel.prompt = "Use Recording"
        case .media:
            panel.title = "Import Media"
            panel.message = "Choose audio or video to process on this Mac."
            panel.prompt = "Import"
        case .project:
            panel.title = "Import Dubbing Project"
            panel.message = "Choose a Timbreloom project bundle containing dialogue, voices, and media."
            panel.prompt = "Open Project"
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
        panel.title = "Export File"
        panel.prompt = "Save"
        panel.nameFieldStringValue = (filename as NSString).lastPathComponent
        if let type = UTType(filenameExtension: (filename as NSString).pathExtension) {
            panel.allowedContentTypes = [type]
        }
        panel.canCreateDirectories = true
        panel.beginSheetModal(for: window) { response in completion(response == .OK ? panel.url : nil) }
    }
}
