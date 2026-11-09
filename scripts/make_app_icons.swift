// Draws ios/BetLab/app_icons.json into the asset catalog as alternate app icons (see make_app_icons.py). Opaque 1024 PNGs,
// as Apple requires, with no packages: CoreGraphics and CoreText only.
import AppKit
import ImageIO
import UniformTypeIdentifiers

struct Icon: Decodable { let id: String, bg: String, fg: String, tag: String; let stripe: String? }

func color(_ h: String) -> CGColor {
    let v = Int(h, radix: 16) ?? 0
    return CGColor(red: CGFloat((v >> 16) & 255) / 255, green: CGFloat((v >> 8) & 255) / 255, blue: CGFloat(v & 255) / 255, alpha: 1)
}

func text(_ s: String, size: CGFloat, centerY: CGFloat, fill: CGColor, in c: CGContext) {
    let font = CTFontCreateWithName("Helvetica-Bold" as CFString, size, nil)
    let attr = NSAttributedString(string: s, attributes: [.font: font, .foregroundColor: fill])
    let line = CTLineCreateWithAttributedString(attr)
    let b = CTLineGetImageBounds(line, c)
    c.textPosition = CGPoint(x: 512 - b.midX, y: centerY - b.midY)
    CTLineDraw(line, c)
}

let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let icons = try JSONDecoder().decode([Icon].self, from: Data(contentsOf: root.appendingPathComponent("ios/BetLab/app_icons.json")))
let assets = root.appendingPathComponent("ios/BetLab/Assets.xcassets")
let contents = #"{ "images" : [ { "filename" : "icon.png", "idiom" : "universal", "platform" : "ios", "size" : "1024x1024" } ], "info" : { "author" : "xcode", "version" : 1 } }"#
for i in icons {
    let c = CGContext(data: nil, width: 1024, height: 1024, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                      bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    c.setFillColor(color(i.bg)); c.fill(CGRect(x: 0, y: 0, width: 1024, height: 1024))
    if let s = i.stripe { c.setFillColor(color(s)); c.fill(CGRect(x: 0, y: 0, width: 1024, height: 90)) }
    if i.tag.isEmpty {
        text("B", size: 640, centerY: 512, fill: color(i.fg), in: c)
    } else {
        text("B", size: 560, centerY: 590, fill: color(i.fg), in: c)
        text(i.tag, size: 170, centerY: 220, fill: color(i.fg), in: c)
    }
    let dir = assets.appendingPathComponent("\(i.id).appiconset")
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    try contents.write(to: dir.appendingPathComponent("Contents.json"), atomically: true, encoding: .utf8)
    let dest = CGImageDestinationCreateWithURL(dir.appendingPathComponent("icon.png") as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(dest, c.makeImage()!, nil)
    guard CGImageDestinationFinalize(dest) else { fatalError(i.id) }
}
print("drew", icons.count)
