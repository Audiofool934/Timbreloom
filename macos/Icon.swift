// Build-time vector artwork. This executable is not included in the app.
import AppKit

let directory = URL(fileURLWithPath: CommandLine.arguments[1])
for size in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = size * scale
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
        let context = NSGraphicsContext.current!.cgContext
        context.scaleBy(x: CGFloat(pixels) / 1024, y: CGFloat(pixels) / 1024)
        NSGraphicsContext.saveGraphicsState()
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.22)
        shadow.shadowBlurRadius = 28
        shadow.shadowOffset = NSSize(width: 0, height: -12)
        shadow.set()
        NSColor(srgbRed: 0.085, green: 0.105, blue: 0.08, alpha: 1).setFill()
        let tile = NSBezierPath(roundedRect: NSRect(x: 72, y: 72, width: 880, height: 880), xRadius: 196, yRadius: 196)
        tile.fill()
        NSGraphicsContext.restoreGraphicsState()
        NSColor.white.withAlphaComponent(0.12).setStroke()
        tile.lineWidth = 2
        tile.stroke()
        NSColor(srgbRed: 0.85, green: 1, blue: 0.34, alpha: 1).setFill()
        for (i, height) in [160.0, 300, 470, 300, 160].enumerated() {
            NSBezierPath(roundedRect: NSRect(x: 282 + Double(i) * 100, y: (1024 - height) / 2,
                width: 60, height: height), xRadius: 30, yRadius: 30).fill()
        }
        NSGraphicsContext.restoreGraphicsState()
        let name = "icon_\(size)x\(size)\(scale == 2 ? "@2x" : "").png"
        try bitmap.representation(using: .png, properties: [:])!.write(to: directory.appendingPathComponent(name))
    }
}

if CommandLine.arguments.count > 2 {
    let names = ["square.and.arrow.down", "arrow.right", "arrow.clockwise", "plus", "xmark",
                 "play.fill", "pause.fill", "chevron.right", "waveform", "text.alignleft", "rectangle.stack", "checkmark.circle"]
    var symbols: [String: String] = [:]
    for name in names {
        guard let image = NSImage(systemSymbolName: name, accessibilityDescription: nil)?
            .withSymbolConfiguration(NSImage.SymbolConfiguration(pointSize: 48, weight: .regular)),
            let tiff = image.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff),
            let png = bitmap.representation(using: .png, properties: [:]) else { fatalError("Cannot render \(name)") }
        symbols[name] = "data:image/png;base64," + png.base64EncodedString()
    }
    let data = try JSONEncoder().encode(symbols)
    try data.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
}
