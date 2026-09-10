import AppKit
import WebKit

private struct DownloadTransfer {
    let temporary: URL
    let destination: URL
}

@MainActor
final class WebWorkspace: NSViewController, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler, WKDownloadDelegate {
    let backend: Backend
    let fileDialogs: FileDialogs
    private(set) var webView: WKWebView!
    private(set) var ready = false
    private(set) var selectedView: String
    var onMessage: (([String: Any]) -> Void)?
    var onRetry: (() -> Void)?
    var onReady: (() -> Void)?
    var revealExport: (URL) -> Void = { NSWorkspace.shared.activateFileViewerSelecting([$0]) }
    private var loaded = false
    private let surface = NSView()
    private let overlay = NSView()
    private let loadingTitle = NSTextField(labelWithString: "正在打开你的工作台")
    private let loadingDetail = NSTextField(wrappingLabelWithString: "连接本地音频引擎，模型将在需要时加载。")
    private let spinner = NSProgressIndicator()
    private let retryButton = NSButton(title: "重试", target: nil, action: nil)
    private let logButton = NSButton(title: "查看连接详情", target: nil, action: nil)
    private var transfers: [ObjectIdentifier: DownloadTransfer] = [:]
    private var downloads: [ObjectIdentifier: WKDownload] = [:]
    var downloading: Bool { !downloads.isEmpty }

    init(backend: Backend, initialView: String, fileDialogs: FileDialogs? = nil) {
        self.backend = backend
        self.fileDialogs = fileDialogs ?? NativeFileDialogs()
        self.selectedView = initialView
        super.init(nibName: nil, bundle: nil)
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func loadView() {
        view = NSView()
        surface.wantsLayer = true
        surface.layer?.backgroundColor = NSColor(srgbRed: 0.957, green: 0.961, blue: 0.945, alpha: 1).cgColor
        surface.layer?.cornerRadius = 16
        surface.layer?.cornerCurve = .continuous
        surface.layer?.masksToBounds = true
        surface.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(surface)
        NSLayoutConstraint.activate([
            surface.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            surface.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            surface.topAnchor.constraint(equalTo: view.topAnchor),
            surface.bottomAnchor.constraint(equalTo: view.bottomAnchor),
        ])
        overlay.wantsLayer = true
        overlay.layer?.backgroundColor = surface.layer?.backgroundColor
        fill(overlay)
        spinner.style = .spinning
        spinner.isDisplayedWhenStopped = false
        spinner.controlSize = .regular
        spinner.startAnimation(nil)
        let symbol = NSImageView(image: NSImage(systemSymbolName: "waveform", accessibilityDescription: nil)!)
        symbol.contentTintColor = NSColor(srgbRed: 0.32, green: 0.39, blue: 0.22, alpha: 1)
        symbol.symbolConfiguration = NSImage.SymbolConfiguration(pointSize: 40, weight: .light)
        loadingTitle.font = .systemFont(ofSize: 22, weight: .semibold)
        loadingDetail.font = .systemFont(ofSize: 13)
        loadingDetail.textColor = .secondaryLabelColor
        loadingDetail.alignment = .center
        retryButton.target = self
        retryButton.action = #selector(retry)
        logButton.target = self
        logButton.action = #selector(openLog)
        retryButton.isHidden = true
        logButton.isHidden = true
        let actions = NSStackView(views: [retryButton, logButton])
        let stack = NSStackView(views: [symbol, loadingTitle, loadingDetail, spinner, actions])
        stack.orientation = .vertical
        stack.spacing = 18
        stack.translatesAutoresizingMaskIntoConstraints = false
        overlay.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: overlay.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: overlay.centerYAnchor, constant: -24),
            stack.widthAnchor.constraint(lessThanOrEqualToConstant: 420),
            stack.widthAnchor.constraint(lessThanOrEqualTo: overlay.widthAnchor, constant: -64),
        ])
    }

    private func initializeWebView() {
        guard webView == nil else { return }
        StartupTrace.mark("webview_initialization_started")
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        config.mediaTypesRequiringUserActionForPlayback = []
        config.preferences.javaScriptCanOpenWindowsAutomatically = false
        let options: [String: Any] = ["version": 1, "initialView": selectedView, "symbols": desktopSymbols()]
        let json = String(data: try! JSONSerialization.data(withJSONObject: options), encoding: .utf8)!
        config.userContentController.addUserScript(WKUserScript(
            source: "window.timbreloomDesktop = Object.freeze(\(json));",
            injectionTime: .atDocumentStart, forMainFrameOnly: true))
        config.userContentController.add(self, name: "timbreloom")
        webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.underPageBackgroundColor = NSColor(srgbRed: 0.96, green: 0.965, blue: 0.95, alpha: 1)
        webView.allowsBackForwardNavigationGestures = false
        webView.allowsMagnification = false
        webView.isInspectable = ProcessInfo.processInfo.environment["TIMBRELOOM_INSPECT"] == "1"
        fill(webView, below: overlay)
        surface.layoutSubtreeIfNeeded()
        StartupTrace.mark("webview_created")
    }

    // Packaged apps use build-time symbols, keeping rasterization off the startup path.
    private func desktopSymbols() -> [String: String] {
        if let url = Bundle.main.url(forResource: "DesktopSymbols", withExtension: "json"),
           let data = try? Data(contentsOf: url),
           let symbols = try? JSONDecoder().decode([String: String].self, from: data) {
            return symbols
        }
        // The standalone WebKit test harness has no app resource bundle.
        let names = ["square.and.arrow.down", "arrow.right", "arrow.clockwise", "plus", "xmark",
                     "play.fill", "pause.fill", "chevron.right", "waveform", "text.alignleft", "rectangle.stack", "checkmark.circle"]
        var result: [String: String] = [:]
        for name in names {
            guard let image = NSImage(systemSymbolName: name, accessibilityDescription: nil)?
                .withSymbolConfiguration(NSImage.SymbolConfiguration(pointSize: 48, weight: .regular)),
                let tiff = image.tiffRepresentation,
                let bitmap = NSBitmapImageRep(data: tiff),
                let png = bitmap.representation(using: .png, properties: [:]) else { continue }
            result[name] = "data:image/png;base64," + png.base64EncodedString()
        }
        return result
    }

    private func fill(_ child: NSView, below sibling: NSView? = nil) {
        child.translatesAutoresizingMaskIntoConstraints = false
        if let sibling { surface.addSubview(child, positioned: .below, relativeTo: sibling) }
        else { surface.addSubview(child) }
        NSLayoutConstraint.activate([
            child.leadingAnchor.constraint(equalTo: surface.leadingAnchor),
            child.trailingAnchor.constraint(equalTo: surface.trailingAnchor),
            child.topAnchor.constraint(equalTo: surface.topAnchor),
            child.bottomAnchor.constraint(equalTo: surface.bottomAnchor),
        ])
    }

    func loadWorkspace() {
        guard !loaded else { return }
        _ = view
        initializeWebView()
        loaded = true
        webView.load(URLRequest(url: backend.baseURL))
    }
    func showError(_ message: String) {
        guard !ready else { return }
        overlay.isHidden = false
        spinner.stopAnimation(nil)
        loadingTitle.stringValue = "暂时无法打开工作台"
        loadingDetail.stringValue = message
        retryButton.isHidden = false
        logButton.isHidden = false
    }
    @objc private func retry() {
        loaded = false
        loadingTitle.stringValue = "正在重新连接"
        loadingDetail.stringValue = "你的音色和项目仍然保存在本机。"
        spinner.startAnimation(nil)
        retryButton.isHidden = true
        logButton.isHidden = true
        onRetry?()
    }
    @objc private func openLog() { NSWorkspace.shared.open(backend.logURL) }

    func selectView(_ id: String) {
        selectedView = id
        if ready { command("selectView", argument: id) }
    }
    func command(_ name: String, argument: String? = nil) {
        guard ready, ["selectView", "openFile", "primaryAction", "save", "openModels"].contains(name) else { return }
        let args = argument.map { String(data: try! JSONEncoder().encode($0), encoding: .utf8)! } ?? ""
        webView.evaluateJavaScript("window.timbreloomCommands?.\(name)(\(args))", completionHandler: nil)
    }
    func hasUnsavedChanges() async -> Bool {
        guard ready else { return false }
        return (try? await webView.evaluateJavaScript("window.timbreloomCommands?.hasUnsavedChanges()")) as? Bool ?? true
    }

    private func local(_ url: URL?) -> Bool {
        guard let url else { return false }
        return url.scheme == "http" && url.host == "127.0.0.1" && url.port == backend.baseURL.port
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, local(message.frameInfo.request.url),
              let payload = message.body as? [String: Any] else { return }
        if payload["type"] as? String == "view", let id = payload["view"] as? String,
           ["clone", "vc", "asr", "dub"].contains(id) {
            selectedView = id
        }
        if payload["type"] as? String == "ready" {
            ready = true
            overlay.isHidden = true
            spinner.stopAnimation(nil)
            command("selectView", argument: selectedView)
            onReady?()
        }
        onMessage?(payload)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if local(url) {
            if navigationAction.shouldPerformDownload { decisionHandler(.download) }
            else if url.path == "/" { decisionHandler(.allow) }
            else if navigationAction.navigationType == .linkActivated { decisionHandler(.download) }
            else { decisionHandler(.cancel) }
        } else {
            if navigationAction.navigationType == .linkActivated && ["https", "http"].contains(url.scheme ?? "") {
                NSWorkspace.shared.open(url)
            }
            decisionHandler(.cancel)
        }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(navigationResponse.canShowMIMEType ? .allow : .download)
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled {
            loaded = false
            showError(error.localizedDescription)
        }
    }
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        ready = false
        loaded = false
        loadWorkspace()
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        guard local(frame.request.url), let window = view.window else { completionHandler(nil); return }
        fileDialogs.open(in: window, multiple: parameters.allowsMultipleSelection,
                         kind: selectedView == "dub" ? .project : selectedView == "clone" ? .reference : .media,
                         completion: completionHandler)
    }
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                 initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType,
                 decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        decisionHandler(local(frame.request.url) && type == .microphone ? .prompt : .deny)
    }
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        guard let window = view.window else { completionHandler(); return }
        let alert = NSAlert()
        alert.messageText = "Timbreloom"
        alert.informativeText = message
        alert.addButton(withTitle: "好")
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        guard let window = view.window else { completionHandler(false); return }
        let alert = NSAlert()
        alert.messageText = "确认操作"
        alert.informativeText = message
        alert.addButton(withTitle: "取消")
        alert.addButton(withTitle: "继续")
        alert.beginSheetModal(for: window) { response in completionHandler(response == .alertSecondButtonReturn) }
    }
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        downloads[ObjectIdentifier(download)] = download
        download.delegate = self
    }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        downloads[ObjectIdentifier(download)] = download
        download.delegate = self
    }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        guard let window = view.window else { completionHandler(nil); return }
        fileDialogs.save(in: window, filename: suggestedFilename) { [weak self] destination in
            guard let self else { completionHandler(nil); return }
            guard let destination else {
                self.downloads.removeValue(forKey: ObjectIdentifier(download))
                completionHandler(nil)
                return
            }
            do {
                let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
                let temporary = directory.appendingPathComponent(destination.lastPathComponent)
                self.transfers[ObjectIdentifier(download)] = DownloadTransfer(temporary: temporary, destination: destination)
                completionHandler(temporary)
            } catch {
                self.downloads.removeValue(forKey: ObjectIdentifier(download))
                self.showDownloadError(error)
                completionHandler(nil)
            }
        }
    }
    func downloadDidFinish(_ download: WKDownload) {
        let id = ObjectIdentifier(download)
        downloads.removeValue(forKey: id)
        guard let transfer = transfers.removeValue(forKey: id) else { return }
        do {
            if FileManager.default.fileExists(atPath: transfer.destination.path) {
                _ = try FileManager.default.replaceItemAt(transfer.destination, withItemAt: transfer.temporary)
            } else { try FileManager.default.moveItem(at: transfer.temporary, to: transfer.destination) }
            try? FileManager.default.removeItem(at: transfer.temporary.deletingLastPathComponent())
            revealExport(transfer.destination)
        } catch { showDownloadError(error) }
    }
    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        let id = ObjectIdentifier(download)
        downloads.removeValue(forKey: id)
        if let transfer = transfers.removeValue(forKey: id) {
            try? FileManager.default.removeItem(at: transfer.temporary.deletingLastPathComponent())
        }
        if (error as NSError).code != NSURLErrorCancelled { showDownloadError(error) }
    }
    func download(_ download: WKDownload, willPerformHTTPRedirection response: HTTPURLResponse,
                  newRequest request: URLRequest, decisionHandler: @escaping (WKDownload.RedirectPolicy) -> Void) {
        decisionHandler(local(request.url) ? .allow : .cancel)
    }
    private func showDownloadError(_ error: Error) {
        guard let window = view.window else { return }
        let alert = NSAlert()
        alert.messageText = "文件未能导出"
        alert.informativeText = error.localizedDescription
        alert.beginSheetModal(for: window)
    }
}
