import AppKit

final class WorkspaceSplitView: NSSplitView {
    weak var sidebarItem: NSSplitViewItem?
    override var dividerThickness: CGFloat { sidebarItem?.isCollapsed == true ? 0 : 12 }
    override func drawDivider(in rect: NSRect) {}
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, NSToolbarDelegate {
    let backend = Backend()
    let sidebar = Sidebar()
    let split = NSSplitViewController()
    var workspace: WebWorkspace!
    var window: NSWindow!
    private var terminating = false
    private let started = ProcessInfo.processInfo.systemUptime
    private var mode = "clone"
    private let toolbarTitle = NSTextField(labelWithString: "")
    private let importButton = NSButton(title: "导入文件", target: nil, action: nil)
    private var workspaceMenu: NSMenu?

    func applicationDidFinishLaunching(_ notification: Notification) {
        StartupTrace.mark("application_did_finish_launching")
        NSApp.appearance = NSAppearance(named: .aqua)
        mode = UserDefaults.standard.string(forKey: "workspaceMode") ?? "clone"
        if !WorkspaceMode.all.contains(where: { $0.id == mode }) { mode = "clone" }
        workspace = WebWorkspace(backend: backend, initialView: mode)
        split.splitView = WorkspaceSplitView()
        split.splitView.isVertical = true
        split.splitView.dividerStyle = .thin
        // Own the pane geometry; system sidebar items add another inset on newer macOS.
        let side = NSSplitViewItem(viewController: sidebar)
        (split.splitView as? WorkspaceSplitView)?.sidebarItem = side
        side.minimumThickness = 218
        side.maximumThickness = 280
        side.canCollapse = true
        split.addSplitViewItem(side)
        split.addSplitViewItem(NSSplitViewItem(viewController: workspace))
        split.splitView.autosaveName = "TimbreloomSidebar"
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: min(1260, screen.width - 80),
                                            height: min(850, screen.height - 70)),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        // Inset both panes below the toolbar so their rounded surfaces share a baseline.
        let content = NSViewController()
        content.view = NSView()
        content.view.wantsLayer = true
        content.view.layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor
        content.addChild(split)
        split.view.translatesAutoresizingMaskIntoConstraints = false
        content.view.addSubview(split.view)
        NSLayoutConstraint.activate([
            split.view.leadingAnchor.constraint(equalTo: content.view.leadingAnchor, constant: 12),
            split.view.trailingAnchor.constraint(equalTo: content.view.trailingAnchor, constant: -12),
            split.view.topAnchor.constraint(equalTo: content.view.topAnchor, constant: 12),
            split.view.bottomAnchor.constraint(equalTo: content.view.bottomAnchor, constant: -12),
        ])
        window.contentViewController = content
        window.title = "Timbreloom"
        window.subtitle = "本机声音工作台"
        window.titleVisibility = .hidden
        window.toolbarStyle = .unified
        window.minSize = NSSize(width: 920, height: 640)
        window.isReleasedWhenClosed = false
        window.delegate = self
        let toolbar = NSToolbar(identifier: "TimbreloomToolbar")
        toolbar.delegate = self
        toolbar.displayMode = .iconOnly
        window.toolbar = toolbar
        // Assigning contentViewController can adopt its initial zero-sized view.
        window.setContentSize(NSSize(width: min(1260, screen.width - 80), height: min(800, screen.height - 100)))
        window.center()
        window.setFrameUsingName("TimbreloomMainWindow")
        // Ignore a stale invalid frame from an interrupted first launch.
        if window.frame.width < 920 || window.frame.height < 640 {
            window.setContentSize(NSSize(width: 1100, height: 760))
            window.center()
        }
        window.setFrameAutosaveName("TimbreloomMainWindow")
        split.splitView.setPosition(230, ofDividerAt: 0)
        buildMenus()
        sidebar.onSelect = { [weak self] mode in self?.select(mode) }
        sidebar.onRetry = { [weak self] in self?.backend.start() }
        sidebar.onModels = { [weak self] in self?.showModels() }
        workspace.onRetry = { [weak self] in self?.backend.start() }
        workspace.onMessage = { [weak self] payload in
            guard let self else { return }
            if payload["type"] as? String == "view", let mode = payload["view"] as? String {
                self.mode = mode
                self.sidebar.select(mode)
                self.updateWorkspaceChrome()
                UserDefaults.standard.set(mode, forKey: "workspaceMode")
            } else if payload["type"] as? String == "status" {
                self.sidebar.setStatus(payload["label"] as? String ?? "", state: payload["state"] as? String ?? "idle")
            }
        }
        workspace.onReady = { [weak self] in
            guard let self else { return }
            StartupTrace.mark("workspace_ready")
            NSLog("Timbreloom workspace ready in %.3f s", ProcessInfo.processInfo.systemUptime - self.started)
        }
        backend.onReady = { [weak self] in
            self?.sidebar.setStatus("本地引擎已连接", state: "idle")
            self?.workspace.loadWorkspace()
        }
        backend.onError = { [weak self] message in
            self?.sidebar.setStatus(message, state: "error")
            self?.workspace.showError(message)
        }
        sidebar.select(mode)
        updateWorkspaceChrome()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        NSLog("Timbreloom window shown in %.3f s", ProcessInfo.processInfo.systemUptime - started)
        StartupTrace.mark("window_shown")
        backend.start()
    }

    func select(_ id: String) {
        guard WorkspaceMode.all.contains(where: { $0.id == id }) else { return }
        mode = id
        sidebar.select(id)
        updateWorkspaceChrome()
        workspace.selectView(id)
        UserDefaults.standard.set(id, forKey: "workspaceMode")
    }
    private func updateWorkspaceChrome() {
        guard let selection = WorkspaceMode.all.first(where: { $0.id == mode }) else { return }
        toolbarTitle.stringValue = selection.title
        window.title = "\(selection.title) · Timbreloom"
        let names = ["clone": "导入录音", "vc": "导入媒体", "asr": "导入媒体", "dub": "导入项目"]
        importButton.title = names[mode] ?? "导入文件"
        importButton.toolTip = "\(importButton.title) · ⌘O"
        importButton.setAccessibilityLabel(importButton.title)
        importButton.sizeToFit()
        if let item = window.toolbar?.items.first(where: { $0.itemIdentifier.rawValue == "open" }) {
            item.label = importButton.title
            item.toolTip = importButton.toolTip
        }
        for item in workspaceMenu?.items ?? [] where item.action == #selector(selectMenu(_:)) {
            item.state = WorkspaceMode.all[item.tag].id == mode ? .on : .off
        }
    }
    @objc func selectMenu(_ item: NSMenuItem) { select(WorkspaceMode.all[item.tag].id) }
    @objc func openFile() { window.makeKeyAndOrderFront(nil); workspace.command("openFile") }
    @objc func generate() { workspace.command("primaryAction") }
    @objc func save() { workspace.command("save") }
    @objc func showLibrary() { NSWorkspace.shared.open(backend.dataRoot) }
    @objc func showModels() { showWindow(); workspace.command("openModels") }
    @objc func showLog() { NSWorkspace.shared.open(backend.logURL) }
    @objc func showWindow() { window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    @objc func toggleSidebar() {
        guard let side = split.splitViewItems.first else { return }
        side.animator().isCollapsed = !side.isCollapsed
    }
    @objc func showHelp() { NSWorkspace.shared.open(backend.root.appendingPathComponent("docs/macos-app.md")) }
    @objc func showLicenses() {
        if let resources = Bundle.main.resourceURL {
            NSWorkspace.shared.open(resources.appendingPathComponent("ThirdPartyNotices"))
        }
    }
    @objc func about() {
        NSApp.orderFrontStandardAboutPanel(options: [
            .applicationName: "Timbreloom", .applicationVersion: "1.1.0", .version: "Mac 本机版",
            .credits: NSAttributedString(string: "在这台 Mac 上，编织声音。\n声音克隆 · 原声换色 · 本地转录 · 配音项目"),
        ])
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showWindow()
        return true
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !terminating else { return .terminateLater }
        terminating = true
        Task {
            let dirty = await workspace.hasUnsavedChanges()
            let state = try? await backend.runtime()
            let busy = state?.busy ?? (backend.process?.isRunning == true)
            if dirty || busy || workspace.downloading {
                showWindow()
                let alert = NSAlert()
                alert.messageText = state == nil ? "确认退出工作台？" : busy ? "仍有任务在运行" : workspace.downloading ? "文件仍在导出" : "结束这次工作？"
                var reasons = [String]()
                if busy {
                    reasons.append(backend.process == nil
                        ? "终端启动的服务会继续运行。"
                        : "退出会中断当前处理；下次打开会恢复可恢复的任务，换色任务可在记录中重试。模型下载会保留进度，可手动继续。关闭窗口则会继续在后台运行。")
                }
                if dirty { reasons.append("文字草稿已保留；尚未保存的项目修改、录音和本次选取的文件可能需要重新准备。") }
                if workspace.downloading { reasons.append("尚未完成的文件导出将中断。") }
                alert.informativeText = reasons.joined(separator: "\n\n")
                alert.addButton(withTitle: "继续工作")
                alert.addButton(withTitle: "退出 Timbreloom")
                alert.beginSheetModal(for: window) { [weak self] response in
                    let quit = response == .alertSecondButtonReturn
                    if quit { self?.backend.stop() } else { self?.terminating = false }
                    NSApp.reply(toApplicationShouldTerminate: quit)
                }
            } else {
                backend.stop()
                NSApp.reply(toApplicationShouldTerminate: true)
            }
        }
        return .terminateLater
    }
    func applicationWillTerminate(_ notification: Notification) { backend.stop() }

    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [.init("sidebar"), .sidebarTrackingSeparator, .flexibleSpace, .init("title"), .init("open"), .init("library")]
    }
    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [.init("sidebar"), .sidebarTrackingSeparator, .init("title"), .flexibleSpace, .init("open"), .init("library")]
    }
    func toolbar(_ toolbar: NSToolbar, itemForItemIdentifier id: NSToolbarItem.Identifier,
                 willBeInsertedIntoToolbar flag: Bool) -> NSToolbarItem? {
        if id == .sidebarTrackingSeparator {
            return NSTrackingSeparatorToolbarItem(identifier: id, splitView: split.splitView, dividerIndex: 0)
        }
        if id.rawValue == "sidebar" {
            let item = NSToolbarItem(itemIdentifier: id)
            item.image = NSImage(systemSymbolName: "sidebar.left", accessibilityDescription: "显示或隐藏侧栏")
            item.label = "侧栏"
            item.toolTip = "显示或隐藏侧栏 · ⌃⌘S"
            item.target = self
            item.action = #selector(toggleSidebar)
            return item
        }
        let item = NSToolbarItem(itemIdentifier: id)
        if id.rawValue == "title" {
            toolbarTitle.font = .systemFont(ofSize: 13, weight: .semibold)
            toolbarTitle.textColor = .secondaryLabelColor
            item.view = toolbarTitle
        } else {
            let open = id.rawValue == "open"
            item.label = open ? "导入文件" : "打开资料库"
            item.toolTip = open ? "导入文件 (⌘O)" : "在 Finder 中打开资料库"
            item.image = NSImage(systemSymbolName: open ? "square.and.arrow.down" : "folder", accessibilityDescription: item.label)
            if open {
                importButton.image = item.image
                importButton.imagePosition = .imageLeading
                importButton.bezelStyle = .rounded
                importButton.font = .systemFont(ofSize: 12, weight: .medium)
                importButton.target = self
                importButton.action = #selector(openFile)
                item.view = importButton
            }
            item.target = self
            item.action = open ? #selector(openFile) : #selector(showLibrary)
        }
        return item
    }

    private func buildMenus() {
        let main = NSMenu()
        func menu(_ name: String) -> NSMenu {
            let item = NSMenuItem(title: name, action: nil, keyEquivalent: "")
            let submenu = NSMenu(title: name)
            item.submenu = submenu
            main.addItem(item)
            return submenu
        }
        @discardableResult
        func item(_ menu: NSMenu, _ title: String, _ action: Selector, _ key: String = "", target: AnyObject? = nil) -> NSMenuItem {
            let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
            item.target = target
            menu.addItem(item)
            return item
        }
        let app = menu("Timbreloom")
        item(app, "关于 Timbreloom", #selector(about), target: self)
        item(app, "模型管理…", #selector(showModels), ",", target: self)
        app.addItem(.separator())
        item(app, "隐藏 Timbreloom", #selector(NSApplication.hide(_:)), "h")
        item(app, "显示全部", #selector(NSApplication.unhideAllApplications(_:)))
        app.addItem(.separator())
        item(app, "退出 Timbreloom", #selector(NSApplication.terminate(_:)), "q")
        let file = menu("文件")
        item(file, "导入文件…", #selector(openFile), "o", target: self)
        item(file, "保存修改", #selector(save), "s", target: self)
        item(file, "开始生成 / 转录", #selector(generate), "\r", target: self)
        file.addItem(.separator())
        item(file, "在 Finder 中打开资料库", #selector(showLibrary), target: self)
        item(file, "关闭窗口", #selector(NSWindow.performClose(_:)), "w")
        let edit = menu("编辑")
        item(edit, "撤销", Selector(("undo:")), "z")
        let redo = item(edit, "重做", Selector(("redo:")), "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        edit.addItem(.separator())
        item(edit, "剪切", #selector(NSText.cut(_:)), "x")
        item(edit, "复制", #selector(NSText.copy(_:)), "c")
        item(edit, "粘贴", #selector(NSText.paste(_:)), "v")
        item(edit, "全选", #selector(NSText.selectAll(_:)), "a")
        let view = menu("工作空间")
        workspaceMenu = view
        for (index, mode) in WorkspaceMode.all.enumerated() {
            item(view, mode.title, #selector(selectMenu(_:)), String(index + 1), target: self).tag = index
        }
        view.addItem(.separator())
        let toggle = item(view, "显示 / 隐藏侧栏", #selector(toggleSidebar), "s", target: self)
        toggle.keyEquivalentModifierMask = [.command, .control]
        let windows = menu("窗口")
        item(windows, "显示工作台", #selector(showWindow), "0", target: self)
        item(windows, "最小化", #selector(NSWindow.performMiniaturize(_:)), "m")
        item(windows, "缩放", #selector(NSWindow.performZoom(_:)))
        NSApp.windowsMenu = windows
        let help = menu("帮助")
        item(help, "Timbreloom 使用说明", #selector(showHelp), target: self)
        if backend.embedded { item(help, "第三方许可", #selector(showLicenses), target: self) }
        item(help, "打开运行日志", #selector(showLog), target: self)
        NSApp.helpMenu = help
        NSApp.mainMenu = main
    }
}

@main
struct TimbreloomApp {
    @MainActor
    static func main() {
        StartupTrace.mark("process_entry")
        let application = NSApplication.shared
        let delegate = AppDelegate()
        application.delegate = delegate
        application.setActivationPolicy(.regular)
        application.run()
        withExtendedLifetime(delegate) {}
    }
}
