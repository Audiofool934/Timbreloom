// Build-time icon sizes from the approved artwork. This executable is not included in the app.
import AppKit

let directory = URL(fileURLWithPath: CommandLine.arguments[1])
guard CommandLine.arguments.count > 3,
      let artwork = NSImage(contentsOfFile: CommandLine.arguments[3]) else {
    fatalError("Provide the approved app icon artwork as the third argument")
}
for size in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = size * scale
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
        NSGraphicsContext.current!.imageInterpolation = .high
        artwork.draw(in: NSRect(x: 0, y: 0, width: pixels, height: pixels),
                     from: .zero, operation: .copy, fraction: 1)
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
