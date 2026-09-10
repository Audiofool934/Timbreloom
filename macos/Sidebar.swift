import AppKit

struct WorkspaceMode {
    let id: String
    let title: String
    let symbol: String
    let caption: String
    static let all = [
        WorkspaceMode(id: "clone", title: "声音克隆", symbol: "waveform", caption: "让文字拥有你的声音"),
        WorkspaceMode(id: "vc", title: "原声换色", symbol: "waveform.path", caption: "保留表演，改变音色"),
        WorkspaceMode(id: "asr", title: "本地转录", symbol: "text.bubble", caption: "听见声音，留下文字"),
        WorkspaceMode(id: "dub", title: "配音项目", symbol: "rectangle.stack", caption: "声音与画面的工作台"),
    ]
}

private final class ModeLabel: NSTextField {
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
}

final class ModeButton: NSButton {
    private let titleLabel = ModeLabel(labelWithString: "")
    private let captionLabel = ModeLabel(labelWithString: "")
    private let shortcutLabel = ModeLabel(labelWithString: "")
    var selected = false { didSet { updateLabels(); needsDisplay = true } }
    override var title: String { didSet { titleLabel.stringValue = title } }
    var caption = "" { didSet { captionLabel.stringValue = caption } }
    var shortcut = "" { didSet { shortcutLabel.stringValue = shortcut } }
    private var hovering = false
    private var hoverTracking: NSTrackingArea?
    override var isFlipped: Bool { true }
    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        for label in [titleLabel, captionLabel, shortcutLabel] {
            label.translatesAutoresizingMaskIntoConstraints = false
            label.setAccessibilityElement(false)
            addSubview(label)
        }
        captionLabel.font = .systemFont(ofSize: 10)
        shortcutLabel.font = .monospacedSystemFont(ofSize: 10, weight: .regular)
        NSLayoutConstraint.activate([
            titleLabel.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 39),
            titleLabel.topAnchor.constraint(equalTo: topAnchor, constant: 9),
            titleLabel.trailingAnchor.constraint(lessThanOrEqualTo: shortcutLabel.leadingAnchor, constant: -6),
            captionLabel.leadingAnchor.constraint(equalTo: titleLabel.leadingAnchor),
            captionLabel.topAnchor.constraint(equalTo: topAnchor, constant: 30),
            captionLabel.trailingAnchor.constraint(lessThanOrEqualTo: trailingAnchor, constant: -10),
            shortcutLabel.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -10),
            shortcutLabel.topAnchor.constraint(equalTo: topAnchor, constant: 11),
        ])
        updateLabels()
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    private func updateLabels() {
        let primary = NSColor(srgbRed: 0.19, green: 0.24, blue: 0.15, alpha: 1)
        let secondary = selected ? primary.withAlphaComponent(0.7) : NSColor.secondaryLabelColor
        titleLabel.font = .systemFont(ofSize: 13, weight: selected ? .semibold : .medium)
        titleLabel.textColor = primary
        captionLabel.textColor = secondary
        shortcutLabel.textColor = secondary.withAlphaComponent(0.65)
    }
    override func updateTrackingAreas() {
        if let hoverTracking { removeTrackingArea(hoverTracking) }
        let tracking = NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeInKeyWindow, .inVisibleRect], owner: self)
        addTrackingArea(tracking)
        hoverTracking = tracking
        super.updateTrackingAreas()
    }
    override func mouseEntered(with event: NSEvent) { hovering = true; needsDisplay = true }
    override func mouseExited(with event: NSEvent) { hovering = false; needsDisplay = true }
    override func draw(_ dirtyRect: NSRect) {
        let shape = NSBezierPath(roundedRect: bounds.insetBy(dx: 1, dy: 1), xRadius: 9, yRadius: 9)
        if selected {
            NSColor(srgbRed: 0.84, green: 0.92, blue: 0.69, alpha: 0.85).setFill()
            shape.fill()
            NSColor(srgbRed: 0.65, green: 0.74, blue: 0.51, alpha: 0.24).setStroke()
            shape.stroke()
        } else if hovering || isHighlighted {
            NSColor.labelColor.withAlphaComponent(isHighlighted ? 0.08 : 0.04).setFill()
            shape.fill()
        }
        image?.draw(in: NSRect(x: 13, y: 17, width: 18, height: 18), from: .zero,
                    operation: .sourceOver, fraction: selected ? 0.9 : 0.65, respectFlipped: true, hints: nil)
    }
    override var focusRingMaskBounds: NSRect { bounds.insetBy(dx: 1, dy: 1) }
    override func drawFocusRingMask() {
        NSBezierPath(roundedRect: focusRingMaskBounds, xRadius: 9, yRadius: 9).fill()
    }
}

@MainActor
final class Sidebar: NSViewController {
    var onSelect: ((String) -> Void)?
    var onRetry: (() -> Void)?
    var onModels: (() -> Void)?
    private var buttons: [ModeButton] = []
    private let status = NSTextField(wrappingLabelWithString: "正在连接本地引擎")
    private let dot = NSImageView()
    private let retry = NSButton(title: "重新连接", target: nil, action: nil)

    override func loadView() {
        let backdrop = NSVisualEffectView()
        backdrop.material = .sidebar
        backdrop.blendingMode = .behindWindow
        backdrop.wantsLayer = true
        backdrop.layer?.cornerRadius = 16
        backdrop.layer?.cornerCurve = .continuous
        backdrop.layer?.masksToBounds = true
        view = backdrop
        let brand = NSTextField(labelWithString: "TIMBRELOOM")
        brand.font = .systemFont(ofSize: 11, weight: .bold)
        brand.textColor = .secondaryLabelColor
        let name = NSTextField(labelWithString: "声音工作台")
        name.font = .systemFont(ofSize: 21, weight: .semibold)
        let caption = NSTextField(labelWithString: "在这台 Mac 上，编织声音。")
        caption.font = .systemFont(ofSize: 11)
        caption.textColor = .secondaryLabelColor
        let header = NSStackView(views: [brand, name, caption])
        header.orientation = .vertical
        header.alignment = .leading
        header.spacing = 9
        place(header, top: 27, leading: 22, trailing: 16)

        let label = NSTextField(labelWithString: "工作空间")
        label.font = .systemFont(ofSize: 11, weight: .medium)
        label.textColor = .tertiaryLabelColor
        place(label, top: 138, leading: 24, trailing: 16)
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.distribution = .fillEqually
        stack.spacing = 4
        place(stack, top: 157, leading: 12, trailing: 12)
        for (index, mode) in WorkspaceMode.all.enumerated() {
            let button = ModeButton(title: mode.title, target: self, action: #selector(selectMode(_:)))
            button.image = NSImage(systemSymbolName: mode.symbol, accessibilityDescription: nil)
            button.caption = mode.caption
            button.shortcut = "⌘\(index + 1)"
            button.focusRingType = .exterior
            button.imagePosition = .imageLeading
            button.imageHugsTitle = true
            button.alignment = .left
            button.bezelStyle = .regularSquare
            button.isBordered = false
            button.font = .systemFont(ofSize: 13, weight: .medium)
            button.contentTintColor = .labelColor
            button.tag = index
            button.toolTip = "\(mode.caption) · ⌘\(index + 1)"
            button.setAccessibilityLabel(mode.title)
            stack.addArrangedSubview(button)
            button.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
            button.heightAnchor.constraint(equalToConstant: 58).isActive = true
            buttons.append(button)
        }
        let local = NSTextField(labelWithString: "本地引擎")
        local.font = .systemFont(ofSize: 11, weight: .medium)
        local.textColor = .secondaryLabelColor
        status.font = .systemFont(ofSize: 11)
        status.textColor = .secondaryLabelColor
        status.maximumNumberOfLines = 3
        status.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        dot.image = NSImage(systemSymbolName: "circle.fill", accessibilityDescription: nil)
        dot.contentTintColor = .systemOrange
        dot.widthAnchor.constraint(equalToConstant: 7).isActive = true
        dot.heightAnchor.constraint(equalToConstant: 7).isActive = true
        let line = NSStackView(views: [dot, local])
        line.spacing = 7
        retry.target = self
        retry.action = #selector(reconnect)
        retry.controlSize = .small
        retry.isHidden = true
        let divider = NSBox()
        divider.boxType = .separator
        let hint = NSTextField(labelWithString: "⌘O 导入    ⌘↩ 开始处理")
        hint.font = .systemFont(ofSize: 10)
        hint.textColor = .tertiaryLabelColor
        let models = NSButton(title: "模型管理", target: self, action: #selector(manageModels))
        models.bezelStyle = .rounded
        models.controlSize = .small
        models.toolTip = "选择、下载和管理本地模型 · ⌘,"
        let footer = NSStackView(views: [line, status, retry, models, divider, hint])
        footer.orientation = .vertical
        footer.alignment = .leading
        footer.spacing = 9
        footer.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(footer)
        NSLayoutConstraint.activate([
            footer.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24),
            footer.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -20),
            footer.bottomAnchor.constraint(equalTo: view.bottomAnchor, constant: -23),
        ])
    }

    private func place(_ child: NSView, top: CGFloat, leading: CGFloat, trailing: CGFloat) {
        child.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(child)
        NSLayoutConstraint.activate([
            child.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: leading),
            child.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -trailing),
            child.topAnchor.constraint(equalTo: view.topAnchor, constant: top),
        ])
    }

    func select(_ id: String) {
        for button in buttons {
            button.selected = WorkspaceMode.all[button.tag].id == id
            button.setAccessibilityValue(button.selected ? "已选择" : "")
        }
    }
    func setStatus(_ text: String, state: String) {
        status.stringValue = text
        status.toolTip = text
        dot.contentTintColor = state == "error" ? .systemRed : state == "loading" ? .systemOrange : state == "missing" ? .secondaryLabelColor : .systemGreen
        retry.isHidden = state != "error"
    }
    @objc private func selectMode(_ sender: NSButton) { onSelect?(WorkspaceMode.all[sender.tag].id) }
    @objc private func reconnect() { onRetry?() }
    @objc private func manageModels() { onModels?() }
}
