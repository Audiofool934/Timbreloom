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
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        workspace.onReady = { [weak self] in
            guard let self, !self.began else { return }
            self.began = true
            Task {
                do {
                    try await self.runChecks()
                    if ProcessInfo.processInfo.environment["TIMBRELOOM_TEST_MODEL_DOWNLOADS"] != "1" {
                        print("PASS: WebKit responsive workspaces, native import cancellation, scroll restoration, ASR, dub creation, save, export, drafts, cloning and conversion history, live microphone capture and saving")
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
        let state = try? await js("JSON.stringify({view: document.querySelector('.mode-button.is-active')?.dataset.view, scroll: scrollY, focus: document.activeElement?.id, height: document.documentElement.scrollHeight, live: document.getElementById('asrLiveControls')?.dataset.state, liveStatus: document.getElementById('asrLiveStatus')?.textContent, syntheticAudio: window.liveTestContext?.state, audioContexts: window.liveTestContexts?.map(ctx => ({state:ctx.state,stage:ctx.testStage})), model: document.getElementById('asrModel')?.value, language: document.getElementById('asrLanguage')?.value})")
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
            let left = r.left, right = r.right;
            // Horizontal timelines and libraries deliberately scroll inside their viewport.
            // Measure their visible rectangle without exempting the viewport itself.
            for (let parent = el.parentElement; parent; parent = parent.parentElement) {
              if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(parent).overflowX)) {
                const bounds = parent.getBoundingClientRect();
                left = Math.max(left, bounds.left); right = Math.min(right, bounds.right);
              }
            }
            return r.width > 0 && r.height > 0 && right > left && (right > innerWidth + 1 || left < -1)
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
        try await waitFor("native model command", "document.getElementById('modelManager').open && document.querySelectorAll('.model-download-card').length === 6")
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
    func runHistoryChecks() async throws {
        workspace.selectView("clone")
        try await waitFor("cloning history", "document.querySelectorAll('#cloneJobList .history-item').length === 1")
        _ = try await js("const search = document.getElementById('cloneJobListSearch'); search.value = 'no such recording'; search.dispatchEvent(new Event('input')); true")
        try require(try await js("document.querySelector('#cloneJobList .history-item').hidden && !document.querySelector('#cloneJobList + .library-no-results').hidden") as? Bool == true,
                    "Library search did not hide unmatched recordings")
        _ = try await js("document.getElementById('cloneJobListSearch').dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true})); true")
        try require(try await js("!document.querySelector('#cloneJobList .history-item').hidden && !document.getElementById('cloneJobListSearch').value") as? Bool == true,
                    "Clearing library search did not restore recordings")
        _ = try await js("document.querySelector('#cloneJobList .history-open').click(); true")
        try await waitFor("saved script and audio", "!document.getElementById('cloneHistoryDetail').hidden && document.getElementById('cloneHistoryText').value === 'History narration.\\n\\nA second paragraph.' && document.getElementById('audioPlayer').readyState >= 1")
        _ = try await js("document.getElementById('cloneHistoryDetail').scrollIntoView({behavior:'instant', block:'start'}); true")
        try await checkLayout("cloning-history")
        try await capture("cloning-history")
        _ = try await js("document.querySelector('#cloneJobList .history-action').click(); true")
        try await waitFor("history rename dialog", "document.getElementById('historyDialog').open")
        try await capture("history-rename")
        _ = try await js("document.getElementById('historyTitleInput').value = 'Saved narration'; document.getElementById('historyDialogSubmit').click(); true")
        try await waitFor("history renamed", "!document.getElementById('historyDialog').open && document.getElementById('cloneHistoryTitle').textContent === 'Saved narration'")
        _ = try await js("document.getElementById('targetText').value = ''; document.getElementById('editCloneJob').click(); true")
        try await waitFor("uploaded reference restored", "document.getElementById('targetText').value.startsWith('History narration.') && document.getElementById('referenceAudio').files.length === 1 && document.getElementById('referenceText').value === 'A test reference voice.' && !document.getElementById('referenceAudio').disabled")
        _ = try await js("document.querySelector('#cloneJobList .danger-text').click(); true")
        try await waitFor("history deletion defaults to cancel", "document.getElementById('historyDialog').open && document.activeElement.id === 'historyDialogCancel'")
        try await capture("history-delete")
        _ = try await js("document.getElementById('historyDialogCancel').click(); true")
        try require(try await js("document.querySelectorAll('#cloneJobList .history-item').length === 1") as? Bool == true, "Cancel removed a history entry")
        _ = try await js("document.querySelector('#cloneJobList .danger-text').click(); document.getElementById('historyDialogSubmit').click(); true")
        try await waitFor("cloning history deleted", "document.querySelectorAll('#cloneJobList .history-item').length === 0 && document.getElementById('resultCard').hidden && document.getElementById('cloneHistoryDetail').hidden")
        workspace.selectView("vc")
        _ = try await js("document.querySelector('#vcJobList .history-open').click(); true")
        try await waitFor("conversion history opened", "!document.getElementById('vcResultCard').hidden")
        _ = try await js("document.querySelector('#vcJobList .history-action').click(); document.getElementById('historyTitleInput').value = 'Saved conversion'; document.getElementById('historyDialogSubmit').click(); true")
        try await waitFor("conversion renamed", "document.querySelector('#vcJobList strong').textContent === 'Saved conversion'")
        _ = try await js("document.getElementById('vcJobList').scrollIntoView({behavior:'instant', block:'center'}); true")
        try await capture("conversion-history")
        _ = try await js("document.querySelector('#vcJobList .danger-text').click(); document.getElementById('historyDialogSubmit').click(); true")
        try await waitFor("conversion history deleted", "document.querySelectorAll('#vcJobList .history-item').length === 0 && document.getElementById('vcResultCard').hidden && !localStorage.getItem('timbreloomCurrentVcJob')")
        let root = workspace.backend.dataRoot
        try require(!FileManager.default.fileExists(atPath: root.appendingPathComponent("jobs/" + String(repeating: "a", count: 32)).path), "Deleted cloning files remain")
        try require(!FileManager.default.fileExists(atPath: root.appendingPathComponent("conversions/" + String(repeating: "c", count: 32)).path), "Deleted conversion files remain")
        try require(FileManager.default.fileExists(atPath: root.appendingPathComponent("reference.wav").path), "Deleting history removed the original imported file")
    }

    func runLiveTranscriptionChecks() async throws {
        workspace.selectView("asr")
        _ = try await js("document.getElementById('asrModel').value = 'nemotron'; document.getElementById('asrModel').dispatchEvent(new Event('change')); true")
        _ = try await js("document.getElementById('asrLiveMode').click(); true")
        try await waitFor("live input mode", "!document.getElementById('asrLiveControls').hidden && document.getElementById('asrMedia').disabled")
        _ = try await js("""
          window.liveOriginalGetUserMedia = navigator.mediaDevices.getUserMedia;
          navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Synthetic denial', 'NotAllowedError'); };
          document.getElementById('asrLiveStart').click(); true
          """)
        try await waitFor("live microphone denial", "document.getElementById('asrLiveControls').dataset.state === 'error'")
        _ = try await js("""
          window.liveOriginalAudioContext = window.AudioContext;
          window.liveTestContexts = [];
          window.AudioContext = class extends liveOriginalAudioContext {
            constructor(...args) {
              super(...args); liveTestContexts.push(this); this.testStage = 'created';
              const addModule = this.audioWorklet.addModule.bind(this.audioWorklet);
              this.audioWorklet.addModule = async (...values) => {
                this.testStage = 'loading-worklet'; await addModule(...values); this.testStage = 'worklet-loaded';
              };
            }
            async resume() { this.testStage = 'resuming'; await super.resume(); this.testStage = 'resumed'; }
            async close() { this.testStage = 'closing'; await super.close(); this.testStage = 'closed'; }
          };
          navigator.mediaDevices.getUserMedia = async () => {
            // Keep the synthetic device alive across sessions, like a physical microphone.
            // Closing and immediately recreating its AudioContext can stall WebKit resume().
            if (!window.liveTestContext) {
              window.liveTestContext = new AudioContext();
              window.liveTestDestination = liveTestContext.createMediaStreamDestination();
              const tone = liveTestContext.createOscillator(); tone.connect(liveTestDestination); tone.start();
            }
            await liveTestContext.resume();
            window.liveTestStream = new MediaStream(liveTestDestination.stream.getAudioTracks().map(track => track.clone()));
            return liveTestStream;
          };
          document.getElementById('asrLiveStart').click(); true
          """)
        try await waitFor("live listening", "document.getElementById('asrLiveControls').dataset.state === 'listening'")
        try await waitFor("live input meter receives real samples", "Number(document.querySelector('#asrLiveControls [role=meter]').getAttribute('aria-valuenow')) > -40 && !document.querySelector('#asrLiveControls .recording-input-meter').hidden")
        try require(try await js("document.getElementById('asrModel').disabled") as? Bool == true, "Model can change during a live session")
        try await waitFor("words during recording", "document.getElementById('asrLiveDraft').textContent.includes('Live words') && !document.getElementById('asrLiveStop').hidden")
        _ = try await js("document.getElementById('asrLiveControls').scrollIntoView({behavior:'instant', block:'center'}); true")
        try await checkLayout("live-transcription")
        try await capture("live-transcription-listening")
        _ = try await js("document.getElementById('asrLiveStop').click(); true")
        try await waitFor("live transcript saved", "document.getElementById('asrLiveControls').dataset.state === 'saved' && document.getElementById('transcriptTitle').textContent.startsWith('Live recording')")
        try require(try await js("liveTestStream.getTracks().every(track => track.readyState === 'ended')") as? Bool == true,
                    "Stopping live transcription did not release the microphone")
        try require(try await js("document.querySelector('#asrLiveControls .recording-input-meter').hidden") as? Bool == true,
                    "Stopping live transcription left the input meter active")
        _ = try await js("document.getElementById('transcriptEditor').scrollIntoView({behavior:'instant', block:'start'}); true")
        try await capture("live-transcription-saved")
        _ = try await js("document.getElementById('asrLiveStart').click(); true")
        try await waitFor("second live session", "document.getElementById('asrLiveControls').dataset.state === 'listening'")
        try await waitFor("second session audio", "document.getElementById('asrLiveDraft').textContent.includes('Live words')")
        workspace.selectView("clone")
        try await waitFor("leaving stops microphone", "liveTestStream.getTracks().every(track => track.readyState === 'ended')")
        try await waitFor("leaving saves transcript", "document.getElementById('asrLiveControls').dataset.state === 'saved'")
        workspace.selectView("asr")
        for model in ["whisper", "moonshine-en", "moonshine-zh"] {
            _ = try await js("document.getElementById('asrModel').value = '\(model)'; document.getElementById('asrModel').dispatchEvent(new Event('change')); document.getElementById('asrLiveStart').click(); true")
            try await waitFor("\(model) live words", "document.getElementById('asrLiveControls').dataset.state === 'listening' && document.getElementById('asrLiveDraft').textContent.includes('Live words')")
            _ = try await js("document.getElementById('asrLiveStop').click(); true")
            try await waitFor("\(model) saved", "document.getElementById('asrLiveControls').dataset.state === 'saved'")
        }
        _ = try await js("""
          navigator.mediaDevices.getUserMedia = () => new Promise(resolve => window.resolveLivePermission = resolve);
          document.getElementById('asrLiveStart').click(); true
          """)
        try await waitFor("pending live permission", "typeof window.resolveLivePermission === 'function'")
        _ = try await js("document.getElementById('asrLiveStop').click(); true")
        try await waitFor("cancel pending start", "document.getElementById('asrLiveControls').dataset.state === 'idle'")
        _ = try await js("window.lateLiveTrackStops = 0; resolveLivePermission({getTracks: () => [{stop: () => window.lateLiveTrackStops++}]}); true")
        try await waitFor("late microphone released", "window.lateLiveTrackStops === 1")
        _ = try await js("liveTestDestination.stream.getTracks().forEach(track => track.stop()); liveTestContext.close(); window.AudioContext = window.liveOriginalAudioContext; navigator.mediaDevices.getUserMedia = window.liveOriginalGetUserMedia; document.getElementById('asrFileMode').click(); true")
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
        try await waitFor("four transcription choices", "document.getElementById('asrModel').options.length === 4")
        _ = try await js("document.getElementById('asrPrompt').value = 'Remembered names'; document.getElementById('asrModel').value = 'moonshine-zh'; document.getElementById('asrModel').dispatchEvent(new Event('change')); true")
        try require(try await js("document.getElementById('asrLanguage').value === 'zh' && document.getElementById('asrLanguage').disabled && !document.getElementById('asrPrompt').disabled") as? Bool == true, "Mandarin model has incompatible options")
        _ = try await js("document.getElementById('asrModel').value = 'nemotron'; document.getElementById('asrModel').dispatchEvent(new Event('change')); true")
        try require(try await js("document.getElementById('asrPrompt').disabled && document.getElementById('asrPrompt').value === 'Remembered names' && !document.getElementById('asrLanguage').disabled") as? Bool == true, "Model change erased hints or kept incompatible controls")
        _ = try await js("document.getElementById('asrModel').scrollIntoView({behavior:'instant', block:'center'}); true")
        try await capture("asr-model-selection")
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
        _ = try await js("document.getElementById('asrFocusEditor').click(); true")
        try require(try await js("document.getElementById('asrSetup').hidden && !document.getElementById('transcriptEditor').hidden && document.activeElement.id === 'asrFocusEditor'") as? Bool == true,
                    "Focus editor must retain the editor and keyboard focus")
        try await capture("asr-editor-focused")
        _ = try await js("document.getElementById('asrFocusEditor').click(); true")
        try require(try await js("!document.getElementById('asrSetup').hidden && document.getElementById('asrFocusEditor').getAttribute('aria-pressed') === 'false'") as? Bool == true,
                    "Focus editor did not restore import and library")
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
        _ = try await js("document.getElementById('dubTimelineZoomIn').click(); document.getElementById('dubTimelineZoomIn').click(); true")
        try await waitFor("timeline zoom", "document.getElementById('dubTimelineViewport').scrollWidth > document.getElementById('dubTimelineViewport').clientWidth * 1.5")
        _ = try await js("(() => { const viewport = document.getElementById('dubTimelineViewport'); viewport.focus(); viewport.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowRight', bubbles:true})); return true; })()")
        try await waitFor("timeline keyboard scrolling", "document.getElementById('dubTimelineViewport').scrollLeft > 0")
        _ = try await js("""
          (() => { const viewport = document.getElementById('dubTimelineViewport');
          const shell = document.getElementById('dubWaveformShell');
          const x = viewport.getBoundingClientRect().left + viewport.clientWidth / 2;
          window.expectedTimelineSeek = (x - shell.getBoundingClientRect().left) / shell.getBoundingClientRect().width * 3;
          shell.dispatchEvent(new MouseEvent('click', {clientX:x, bubbles:true})); return true; })()
          """)
        try await waitFor("zoomed timeline seek", "Math.abs(document.getElementById('dubSourceAudio').currentTime - expectedTimelineSeek) < .05")
        try await capture("dub-timeline-zoom")
        _ = try await js("document.getElementById('dubTimelineFit').click(); true")
        try await waitFor("timeline fit", "document.getElementById('dubTimelineViewport').scrollWidth <= document.getElementById('dubTimelineViewport').clientWidth + 1")
        try require(try await js("Math.abs(document.getElementById('dubSourceAudio').currentTime - expectedTimelineSeek) < .05") as? Bool == true,
                    "Fitting the timeline changed the playhead")
        _ = try await js("document.getElementById('dubFocusEditor').click(); true")
        try require(try await js("document.getElementById('dubSetup').hidden && !document.getElementById('dubEditor').hidden") as? Bool == true,
                    "Dubbing focus mode hid the editor")
        try await capture("dub-editor-focused")
        _ = try await js("document.getElementById('dubFocusEditor').click(); true")
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
        _ = try await js("document.getElementById('asrModel').value = 'whisper'; document.getElementById('asrModel').dispatchEvent(new Event('change')); document.getElementById('asrPrompt').value = 'UI_TEST_FAILURE'; true")
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
        _ = try await js("document.getElementById('asrModel').value = 'moonshine-zh'; document.getElementById('asrModel').dispatchEvent(new Event('change')); window.beforeHistoryReload = true; true")
        workspace.webView.reload()
        try await waitFor("draft after reload", "!window.beforeHistoryReload && document.getElementById('targetText')?.value === 'Desktop draft recovery test.'")
        try await waitFor("selected model survives reload", "document.getElementById('asrModel').value === 'moonshine-zh' && document.getElementById('asrLanguage').value === 'zh'")
        try await runHistoryChecks()
        try await runLiveTranscriptionChecks()
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
