import AppKit

@MainActor
enum StartupTrace {
    private static let start = ProcessInfo.processInfo.systemUptime
    private static var events: [[String: Any]] = []
    static func mark(_ stage: String) {
        let baseline = start
        events.append(["stage": stage, "seconds": ProcessInfo.processInfo.systemUptime - baseline])
        let file = ProcessInfo.processInfo.environment["TIMBRELOOM_STARTUP_TRACE"].map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/Timbreloom/startup-latest.json")
        let directory = file.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let payload: [String: Any] = ["pid": ProcessInfo.processInfo.processIdentifier,
            "recorded_at": ISO8601DateFormatter().string(from: Date()), "events": events]
        if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: file, options: .atomic)
        }
    }
}

struct RuntimeState: Decodable {
    let app: String
    let project_root: String
    let data_root: String
    let busy: Bool
}

enum DesktopError: LocalizedError {
    case message(String)
    var errorDescription: String? {
        switch self { case .message(let text): return text }
    }
}

@MainActor
final class Backend {
    let root: URL
    let dataRoot: URL
    let baseURL: URL
    let logURL: URL
    let embedded: Bool
    private(set) var process: Process?
    private var logHandle: FileHandle?
    private var connecting = false
    private var stopping = false
    private var monitor: Timer?
    private var activity: NSObjectProtocol?
    private var workBusy = false
    private let session: URLSession
    var onReady: (() -> Void)?
    var onError: ((String) -> Void)?

    init() {
        let env = ProcessInfo.processInfo.environment
        embedded = Bundle.main.object(forInfoDictionaryKey: "TimbreloomEmbeddedRuntime") as? Bool == true
            && env["TIMBRELOOM_PROJECT_ROOT"] == nil
        let path = env["TIMBRELOOM_PROJECT_ROOT"]
            ?? (embedded ? Bundle.main.resourceURL?.appendingPathComponent("backend").path
                : Bundle.main.object(forInfoDictionaryKey: "TimbreloomProjectRoot") as? String) ?? ""
        root = URL(fileURLWithPath: path).standardizedFileURL.resolvingSymlinksInPath()
        let defaultData = embedded
            ? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Timbreloom/data")
            : root.appendingPathComponent("data")
        dataRoot = URL(fileURLWithPath: env["TIMBRELOOM_DATA_DIR"] ?? defaultData.path)
            .standardizedFileURL.resolvingSymlinksInPath()
        let port = Int(env["TIMBRELOOM_PORT"] ?? "7865") ?? 7865
        baseURL = URL(string: "http://127.0.0.1:\(port)")!
        logURL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/Timbreloom/desktop.log")
        let config = URLSessionConfiguration.ephemeral
        config.connectionProxyDictionary = [:]
        config.timeoutIntervalForRequest = 1
        config.timeoutIntervalForResource = 2
        session = URLSession(configuration: config)
    }

    func runtime() async throws -> RuntimeState {
        let (data, response) = try await session.data(from: baseURL.appendingPathComponent("api/runtime"))
        guard (response as? HTTPURLResponse)?.statusCode == 200,
              let state = try? JSONDecoder().decode(RuntimeState.self, from: data),
              state.app == "timbreloom",
              URL(fileURLWithPath: state.project_root).resolvingSymlinksInPath() == root.resolvingSymlinksInPath(),
              URL(fileURLWithPath: state.data_root).resolvingSymlinksInPath() == dataRoot.resolvingSymlinksInPath() else {
            throw DesktopError.message("本地端口已被另一服务占用。请关闭该服务后重试。")
        }
        workBusy = state.busy
        updateActivity()
        return state
    }

    func start() {
        guard !connecting, !stopping else { return }
        connecting = true
        updateActivity()
        Task {
            defer { connecting = false; updateActivity() }
            do {
                do {
                    _ = try await runtime()
                    ready()
                    return
                } catch let error as DesktopError {
                    throw error
                } catch { /* A refused connection is expected on a cold start. */ }
                if process?.isRunning != true { try launch() }
                let deadline = Date().addingTimeInterval(30)
                while Date() < deadline && !stopping {
                    try await Task.sleep(nanoseconds: 150_000_000)
                    guard process?.isRunning == true else {
                        throw DesktopError.message("本地引擎未能启动。请打开运行日志查看原因，或重试连接。")
                    }
                    do {
                        _ = try await runtime()
                        ready()
                        return
                    } catch let error as DesktopError { throw error }
                    catch { continue }
                }
                if !stopping { throw DesktopError.message("启动超过 30 秒。可以重试，或打开运行日志查看原因。") }
            } catch { if !stopping { onError?(error.localizedDescription) } }
        }
    }

    private func ready() {
        onReady?()
        if monitor == nil {
            monitor = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    guard let self, !self.stopping, !self.connecting else { return }
                    do { _ = try await self.runtime() }
                    catch { self.onError?("本地服务连接已断开，正在重新连接。"); self.start() }
                }
            }
            monitor?.tolerance = 2
        }
    }

    private func updateActivity() {
        if !stopping && (connecting || workBusy) {
            if activity == nil {
                activity = ProcessInfo.processInfo.beginActivity(options: .userInitiated,
                    reason: "Timbreloom 正在准备或处理本地音频")
            }
        } else if let current = activity {
            ProcessInfo.processInfo.endActivity(current)
            activity = nil
        }
    }

    private func launch() throws {
        let python = root.appendingPathComponent(".venv/bin/python")
        guard FileManager.default.isExecutableFile(atPath: python.path),
              FileManager.default.fileExists(atPath: root.appendingPathComponent("app.py").path) else {
            throw DesktopError.message(embedded ? "应用内的本地引擎不完整，请重新安装 Timbreloom。"
                : "找不到项目或 Python 环境。此本机版依赖 \(root.path)，请恢复该目录后重试。")
        }
        try FileManager.default.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        // Keep one previous log without unbounded growth. Logs contain no environment dump.
        if let size = (try? logURL.resourceValues(forKeys: [.fileSizeKey]))?.fileSize, size > 2_000_000 {
            let previous = logURL.deletingLastPathComponent().appendingPathComponent("desktop.previous.log")
            if FileManager.default.fileExists(atPath: previous.path) {
                _ = try FileManager.default.replaceItemAt(previous, withItemAt: logURL)
            } else { try FileManager.default.moveItem(at: logURL, to: previous) }
        }
        if !FileManager.default.fileExists(atPath: logURL.path) {
            FileManager.default.createFile(atPath: logURL.path, contents: nil,
                                           attributes: [.posixPermissions: 0o600])
        }
        logHandle = try FileHandle(forWritingTo: logURL)
        try logHandle?.seekToEnd()
        let child = Process()
        child.executableURL = python
        child.currentDirectoryURL = root
        child.arguments = ["-m", "timbreloom.desktop_server", "--port", String(baseURL.port!),
                           "--parent", String(ProcessInfo.processInfo.processIdentifier)]
        var env = ProcessInfo.processInfo.environment
        if embedded {
            env["PATH"] = root.appendingPathComponent("runtime/media/bin").path + ":/usr/bin:/bin:/usr/sbin:/sbin"
            env["TIMBRELOOM_EMBEDDED"] = "1"
            env["TIMBRELOOM_MODELS_DIR"] = env["TIMBRELOOM_MODELS_DIR"]
                ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Timbreloom/models").path
            env["TIMBRELOOM_H264_ENCODER"] = "h264_videotoolbox"
            let cache = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Caches/Timbreloom")
            try FileManager.default.createDirectory(at: cache, withIntermediateDirectories: true)
            env["HF_HOME"] = cache.appendingPathComponent("huggingface").path
            env["NUMBA_CACHE_DIR"] = cache.appendingPathComponent("numba").path
            env["MPLCONFIGDIR"] = cache.appendingPathComponent("matplotlib").path
            env["HF_HUB_OFFLINE"] = "1"
            env["TRANSFORMERS_OFFLINE"] = "1"
            env.removeValue(forKey: "PYTHONHOME")
            env.removeValue(forKey: "PYTHONPATH")
        } else {
            env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        }
        env["TIMBRELOOM_PRELOAD"] = "0"
        env["TIMBRELOOM_DATA_DIR"] = dataRoot.path
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        child.environment = env
        child.standardOutput = logHandle
        child.standardError = logHandle
        child.standardInput = FileHandle.nullDevice
        try child.run()
        process = child
    }

    func stop() {
        stopping = true
        updateActivity()
        monitor?.invalidate()
        // A service started in Terminal belongs to Terminal, not this window.
        if process?.isRunning == true { process?.terminate() }
        try? logHandle?.close()
    }
}
