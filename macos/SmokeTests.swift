// Runs against synthetic providers in an isolated library, using the real WebKit view.
import AppKit
import WebKit

@MainActor
final class TestDialogs: FileDialogs {
    let input: URL
    let output: URL
    var openCount = 0
    var saveCount = 0
    var cancelNextOpen = false
    init(root: URL) {
        input = root.appendingPathComponent("reference.wav")
        output = root.appendingPathComponent("export.srt")
    }
    func open(in window: NSWindow, multiple: Bool, kind: ImportKind, completion: @escaping ([URL]?) -> Void) {
        openCount += 1
        if cancelNextOpen { cancelNextOpen = false; completion(nil) }
        else { completion([input]) }
    }
    func save(in window: NSWindow, filename: String, completion: @escaping (URL?) -> Void) {
        saveCount += 1
        completion(output)
    }
}

@MainActor
final class SmokeDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var workspace: WebWorkspace!
    var dialogs: TestDialogs!
    var began = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        let backend = Backend()
        dialogs = TestDialogs(root: backend.dataRoot)
        workspace = WebWorkspace(backend: backend, initialView: "clone", fileDialogs: dialogs)
        workspace.revealExport = { _ in }
        window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 1020, height: 800),
                          styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.title = "Timbreloom isolated WebKit checks"
        window.contentViewController = workspace
        window.setContentSize(NSSize(width: 1020, height: 640))
        window.orderFront(nil)
        workspace.onReady = { [weak self] in
            guard let self, !self.began else { return }
            self.began = true
            Task {
                do {
                    try await self.runChecks()
                    if ProcessInfo.processInfo.environment["TIMBRELOOM_TEST_MODEL_DOWNLOADS"] != "1" {
                        print("PASS: WebKit responsive workspaces, native import cancellation, scroll restoration, ASR, dub creation, save, export, drafts")
                    }
                    exit(0)
                }
                catch { fputs("FAIL: \(error)\n", stderr); exit(1) }
            }
        }
        workspace.loadWorkspace()
        DispatchQueue.main.asyncAfter(deadline: .now() + 90) { fputs("FAIL: WebKit smoke timed out\n", stderr); exit(1) }
    }

    func js(_ source: String) async throws -> Any? {
        try await workspace.webView.evaluateJavaScript(source)
    }
    func waitFor(_ label: String, _ expression: String) async throws {
        for _ in 0..<100 {
            if try await js(expression) as? Bool == true { return }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        let state = try? await js("JSON.stringify({view: document.querySelector('.mode-button.is-active')?.dataset.view, scroll: scrollY, focus: document.activeElement?.id, height: document.documentElement.scrollHeight})")
        throw DesktopError.message("Timed out: \(label); \(state ?? "no state")")
    }
    func require(_ condition: Bool, _ label: String) throws {
        if !condition { throw DesktopError.message(label) }
    }
    func capture(_ name: String) async throws {
        let config = WKSnapshotConfiguration()
        let snapshot: NSImage = try await withCheckedThrowingContinuation { continuation in
            workspace.webView.takeSnapshot(with: config) { image, error in
                if let image { continuation.resume(returning: image) }
                else { continuation.resume(throwing: error ?? DesktopError.message("No snapshot")) }
            }
        }
        guard let tiff = snapshot.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff),
              let png = bitmap.representation(using: .png, properties: [:]) else {
            throw DesktopError.message("Snapshot failed: \(name)")
        }
        try png.write(to: workspace.backend.dataRoot.appendingPathComponent("\(name).png"))
    }
    func checkLayout(_ name: String) async throws {
        let overflowing = try await js("""
          [...document.querySelectorAll('main *, main')].filter(el => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0 && (r.right > innerWidth + 1 || r.left < -1)
              && !el.closest('[hidden]') && !el.matches('input[type=file], .sr-only');
          }).map(el => el.id || el.className).join(', ')
          """) as? String ?? "unknown"
        try require(overflowing.isEmpty, "Overflow in \(name): \(overflowing)")
    }
    func runModelChecks() async throws {
        try await waitFor("missing model banner", "!document.querySelector('#cloneView .model-required').hidden")
        try require(!FileManager.default.fileExists(atPath: workspace.backend.dataRoot.appendingPathComponent("model-requests.json").path),
                    "Startup unexpectedly downloaded a model")
        try await capture("models-missing-home")
        workspace.command("openModels")
        try await waitFor("native model command", "document.getElementById('modelManager').open && document.querySelectorAll('.model-download-card').length === 3")
        try await capture("models-missing-wide")
        window.setContentSize(NSSize(width: 640, height: 640))
        try await waitFor("narrow model panel", "innerWidth === 640")
        try require(try await js("document.getElementById('modelManager').scrollWidth <= document.getElementById('modelManager').clientWidth + 1") as? Bool == true,
                    "Model manager overflows horizontally")
        try await capture("models-missing-narrow")
        _ = try await js("document.querySelector('#model-whisper button').click(); true")
        try await waitFor("offline download error", "document.getElementById('model-whisper').dataset.state === 'error'")
        try await capture("models-network-error")
        _ = try await js("document.querySelector('#model-whisper button').click(); true")
        try await waitFor("download makes progress", "document.querySelector('#model-whisper progress').value > 0 && document.getElementById('model-whisper').dataset.state === 'downloading'")
        try await capture("models-downloading")
        _ = try await js("document.querySelector('#model-whisper button').click(); true")
        try await waitFor("paused download", "document.getElementById('model-whisper').dataset.state === 'paused'")
        try await capture("models-paused")
        _ = try await js("document.querySelector('#model-whisper button').click(); true")
        try await waitFor("resumed download completes", "document.getElementById('model-whisper').dataset.state === 'ready'")
        try require(try await js("document.getElementById('model-qwen').dataset.state === 'missing' && document.getElementById('model-seed-vc').dataset.state === 'missing'") as? Bool == true,
                    "Downloading Whisper also activated unselected models")
        try await capture("models-whisper-ready")
        _ = try await js("document.getElementById('closeModelManager').click(); true")
        workspace.selectView("asr")
        try await waitFor("ASR model banner removed", "document.querySelector('#asrView .model-required').hidden")
        workspace.selectView("clone")
        try await waitFor("Qwen remains optional", "!document.querySelector('#cloneView .model-required').hidden")
        let requests = try JSONSerialization.jsonObject(with: Data(contentsOf: workspace.backend.dataRoot.appendingPathComponent("model-requests.json"))) as? [[String: Any]] ?? []
        try require(requests.count == 3 && requests.allSatisfy { ($0["url"] as? String)?.contains("/test/whisper/") == true },
                    "Unexpected download requests")
        try require(requests.last?["range"] as? String != nil, "Resume did not request partial bytes")
        print("PASS: optional downloads, missing-model UI, offline retry, pause/resume, per-model selection, narrow layout")
    }
    func runChecks() async throws {
        if ProcessInfo.processInfo.environment["TIMBRELOOM_TEST_MODEL_DOWNLOADS"] == "1" {
            try await runModelChecks()
            return
        }
        _ = try await workspace.backend.runtime()
        try require(try await js("scrollY === 0 && document.querySelector('#cloneView h1').getBoundingClientRect().top >= 24") as? Bool == true,
                    "A fresh short window must open at the heading, not a restored bottom offset")
        for width in [1020, 760, 640] {
            window.setContentSize(NSSize(width: width, height: 800))
            try await waitFor("content width \(width)", "innerWidth === \(width)")
            for id in ["clone", "vc", "asr", "dub"] {
                workspace.selectView(id)
                try await waitFor("\(id) selected", "!document.getElementById('\(id)View').hidden")
                try await checkLayout("\(id)-\(width)")
                if width != 760 { try await capture("\(id)-\(width)") }
            }
        }
        window.setContentSize(NSSize(width: 1020, height: 800))
        workspace.selectView("dub")
        _ = try await js("document.querySelector('#dubProjectList .quiet-button').click(); true")
        try await waitFor("empty library next step", "!document.getElementById('asrView').hidden")
        try require(workspace.selectedView == "asr", "In-app navigation did not synchronize native import type")
        workspace.selectView("clone")
        _ = try await js("document.getElementById('targetText').value = 'Desktop draft recovery test.'; document.getElementById('targetText').dispatchEvent(new Event('input', {bubbles:true})); true")
        try await waitFor("singular English segment estimate", "document.getElementById('segmentEstimate').textContent.includes('1 segment ·')")
        _ = try await js("""
          window.originalGetUserMedia = navigator.mediaDevices.getUserMedia;
          navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Synthetic denial', 'NotAllowedError'); };
          document.getElementById('cloneRecordStart').click(); true
          """)
        try await waitFor("microphone refusal feedback", "document.getElementById('cloneRecorder').dataset.state === 'error'")
        try await capture("recording-permission-denied")
        _ = try await js("""
          window.originalRecorder = MediaRecorder; window.syntheticTrackStops = 0;
          navigator.mediaDevices.getUserMedia = async () => ({getTracks: () => [{stop: () => window.syntheticTrackStops++}]});
          window.MediaRecorder = class {
            static isTypeSupported() { return true; }
            state = 'inactive'; start() { this.state = 'recording'; }
            stop() { this.state = 'inactive'; this.onstop?.(); }
          };
          document.getElementById('cloneRecordStart').click(); true
          """)
        try await waitFor("recording controls", "document.getElementById('cloneRecorder').classList.contains('is-recording')")
        try await capture("recording-active")
        _ = try await js("document.getElementById('cloneRecordCancel').click(); navigator.mediaDevices.getUserMedia = window.originalGetUserMedia; window.MediaRecorder = window.originalRecorder; true")
        let released = try await js("window.syntheticTrackStops === 1 && document.getElementById('cloneRecordStop').hidden") as? Bool
        try require(released == true, "Cancelling recording did not release its track")
        workspace.command("openFile")
        try await waitFor("reference import", "document.getElementById('referenceAudio').files.length === 1")
        _ = try await js("document.getElementById('referenceText').value = 'A test reference voice.'; document.getElementById('voiceName').value = 'Warm narrator'; document.getElementById('saveVoiceButton').click(); true")
        try await waitFor("saved reference voice", "!!document.getElementById('voiceSelect').value")
        dialogs.cancelNextOpen = true
        workspace.command("openFile")
        for _ in 0..<40 {
            if dialogs.openCount == 2 { break }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        try require(dialogs.openCount == 2, "Saved voice import did not open panel")
        try await waitFor("cancelled picker cleanup", "!document.querySelector('body > input[type=file]')")
        let preserved = try await js("!!document.getElementById('voiceSelect').value && !document.getElementById('savedVoiceCard').hidden && document.getElementById('referenceAudio').disabled") as? Bool
        try require(preserved == true, "Cancelling import lost the saved voice")
        try await capture("clone-saved-voice")
        workspace.command("openFile")
        try await waitFor("replace saved reference", "!document.getElementById('voiceSelect').value && document.getElementById('referenceAudio').files.length === 1")
        _ = try await js("document.getElementById('voiceSelect').selectedIndex = 1; document.getElementById('voiceSelect').dispatchEvent(new Event('change')); true")
        workspace.selectView("asr")
        workspace.command("openFile")
        try await waitFor("native import callback", "document.getElementById('asrMedia').files.length === 1")
        try require(dialogs.openCount == 4, "Open file command did not use native delegate")
        workspace.command("primaryAction")
        try await waitFor("ASR progress", "!document.getElementById('asrProgressCard').hidden")
        _ = try await js("document.getElementById('asrProgressCard').scrollIntoView({behavior:'instant', block:'center'}); true")
        try await capture("transcription-progress")
        try await waitFor("ASR completion", "!document.getElementById('transcriptEditor').hidden")
        _ = try await js("const field = document.querySelector('#transcriptSegments textarea'); field.value = 'Native save test.'; field.dispatchEvent(new Event('input', {bubbles:true})); true")
        try await waitFor("dirty transcript", "!document.getElementById('saveTranscriptButton').disabled")
        workspace.command("save")
        try await waitFor("saved transcript", "document.getElementById('saveTranscriptButton').disabled")
        _ = try await js("document.getElementById('transcriptEditor').scrollIntoView({behavior:'instant'}); true")
        try await waitFor("audio metadata", "document.getElementById('transcriptAudio').duration === 3")
        _ = try await js("document.getElementById('transcriptAudio').nextElementSibling.querySelector('.desktop-play').click(); true")
        try await waitFor("custom audio playback", "!document.getElementById('transcriptAudio').paused")
        _ = try await js("const player = document.getElementById('transcriptAudio').nextElementSibling; player.querySelector('.desktop-play').click(); player.querySelector('.desktop-seek').value = 1.5; player.querySelector('.desktop-seek').dispatchEvent(new Event('input')); player.querySelector('.desktop-speed').value = '1.5'; player.querySelector('.desktop-speed').dispatchEvent(new Event('change')); true")
        let mediaControls = try await js("document.getElementById('transcriptAudio').paused && Math.abs(document.getElementById('transcriptAudio').currentTime - 1.5) < .1 && document.getElementById('transcriptAudio').playbackRate === 1.5") as? Bool
        try require(mediaControls == true, "Custom media controls did not update the audio element")
        try await capture("asr-editor-wide")
        _ = try await js("window.scrollTo(0, 260); true")
        try await waitFor("initial scroll position", "Math.abs(scrollY - 260) < 2")
        workspace.selectView("vc")
        try await waitFor("intermediate workspace", "!document.getElementById('vcView').hidden")
        workspace.selectView("asr")
        try await waitFor("workspace scroll restoration", "Math.abs(scrollY - 260) < 2")
        for width in [760, 640] {
            window.setContentSize(NSSize(width: width, height: 800))
            try await checkLayout("transcript-editor-\(width)")
        }
        _ = try await js("document.getElementById('transcriptEditor').scrollIntoView({behavior:'instant'}); true")
        try await capture("asr-editor-narrow")
        window.setContentSize(NSSize(width: 1020, height: 800))
        // Existing destination verifies atomic replacement instead of truncating the user's export.
        try Data("old test export".utf8).write(to: dialogs.output)
        _ = try await js("document.getElementById('exportSrt').click(); true")
        for _ in 0..<100 {
            if dialogs.saveCount > 0 && !workspace.downloading { break }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        try require(dialogs.saveCount == 1, "Download did not use native save delegate")
        let srt = try String(contentsOf: dialogs.output, encoding: .utf8)
        try require(srt.contains("Native save test.") && srt.contains("-->"), "Exported subtitle content is wrong")
        workspace.selectView("dub")
        _ = try await js("document.getElementById('dubTranscriptSelect').selectedIndex = 1; document.getElementById('dubDefaultVoice').selectedIndex = 1; document.getElementById('dubTitleInput').value = 'Autumn field notes'; true")
        workspace.command("primaryAction")
        try await waitFor("native shortcut creates project", "!document.getElementById('dubEditor').hidden")
        _ = try await js("document.getElementById('dubEditor').scrollIntoView({behavior:'instant'}); true")
        try await checkLayout("dub-editor-wide")
        try await capture("dub-editor-wide")
        for width in [760, 640] {
            window.setContentSize(NSSize(width: width, height: 800))
            try await waitFor("dub content width \(width)", "innerWidth === \(width)")
            try await checkLayout("dub-editor-\(width)")
        }
        try await waitFor("sticky toolbar measurement", "Math.abs(parseFloat(document.getElementById('dubEditor').style.getPropertyValue('--toolbar-offset')) - document.querySelector('.dub-toolbar').getBoundingClientRect().height - 16) < 1")
        _ = try await js("document.querySelector('#dubSegments .dub-segment').scrollIntoView({behavior:'instant', block:'start'}); true")
        try await waitFor("segment clears sticky toolbar", "document.querySelector('#dubSegments .dub-segment').getBoundingClientRect().top >= document.querySelector('.dub-toolbar').getBoundingClientRect().bottom")
        let toolbarHeight = try await js("document.querySelector('.dub-toolbar').getBoundingClientRect().height") as? Double ?? 999
        try require(toolbarHeight < 160, "Narrow sticky toolbar obscures the editor")
        try await capture("dub-segments-narrow")
        workspace.selectView("asr")
        _ = try await js("document.getElementById('asrPrompt').value = 'UI_TEST_FAILURE'; true")
        workspace.command("primaryAction")
        try await waitFor("processing failure feedback", "!document.getElementById('errorCard').hidden")
        _ = try await js("document.getElementById('errorCard').scrollIntoView({behavior:'instant', block:'center'}); true")
        try await capture("processing-error")
        _ = try await js("document.querySelector('.desktop-error-dismiss').click(); document.getElementById('asrPrompt').value = ''; true")
        let dismissed = try await js("document.getElementById('errorCard').hidden") as? Bool
        try require(dismissed == true, "Error message cannot be dismissed")
        _ = try await js("location.href = 'https://example.invalid/timbreloom-navigation-test'; true")
        try await Task.sleep(nanoseconds: 150_000_000)
        try require(workspace.webView.url?.host == "127.0.0.1", "External navigation escaped the workspace")
        workspace.webView.reload()
        try await waitFor("draft after reload", "document.getElementById('targetText')?.value === 'Desktop draft recovery test.'")
        print("Native dialog results are supplied by the test harness; OS panel appearance and microphone consent require manual QA.")
    }
}

@main
struct SmokeMain {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = SmokeDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
        withExtendedLifetime(delegate) {}
    }
}
