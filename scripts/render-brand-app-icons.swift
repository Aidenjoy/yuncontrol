import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

// Flatten the shared artwork onto opaque canvases required by iOS app icons.
let root = URL(fileURLWithPath: CommandLine.arguments[1])
let sourceURL = root.appendingPathComponent("desktop-workbench/build/icon-mac-source.png")
guard let source = CGImageSourceCreateWithURL(sourceURL as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    fatalError("Missing source icon")
}
func writeIcon(_ relative: String, dark: Bool) throws {
    let size = 1024
    guard let space = CGColorSpace(name: CGColorSpace.sRGB),
          let context = CGContext(data: nil, width: size, height: size, bitsPerComponent: 8,
                                  bytesPerRow: size * 4, space: space,
                                  bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else {
        fatalError("Cannot create RGB icon canvas")
    }
    context.setFillColor(CGColor(gray: dark ? 0.06 : 1, alpha: 1))
    context.fill(CGRect(x: 0, y: 0, width: size, height: size))
    context.interpolationQuality = .high
    context.draw(image, in: CGRect(x: 96, y: 96, width: 832, height: 832))
    guard let output = context.makeImage(),
          let destination = CGImageDestinationCreateWithURL(root.appendingPathComponent(relative) as CFURL,
                                                           UTType.png.identifier as CFString, 1, nil) else {
        fatalError("Cannot encode app icon")
    }
    CGImageDestinationAddImage(destination, output, nil)
    guard CGImageDestinationFinalize(destination) else { fatalError("Cannot write app icon") }
}
try writeIcon("logo/ios-light-iOS-Default-1024@1x.png", dark: false)
try writeIcon("logo/ios-dark-iOS-Default-1024@1x.png", dark: true)
let appIcons = "ios/Agents Anywhere/Agents Anywhere/Assets.xcassets/AppIcon.appiconset/"
try writeIcon(appIcons + "ios-dark-iOS-Dark-1024@1x.png", dark: false)
try writeIcon(appIcons + "ios-dark-iOS-TintedLight-1024@1x.png", dark: false)
