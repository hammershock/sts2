import Foundation
import AppKit
import ScreenCaptureKit
import CoreGraphics
import CoreVideo
import ImageIO
import UniformTypeIdentifiers

func savePNG(_ image: CGImage, to url: URL) throws {
    guard let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        throw NSError(domain: "sts2.sck", code: 1, userInfo: [NSLocalizedDescriptionKey: "Cannot create image destination"])
    }
    CGImageDestinationAddImage(destination, image, nil)
    if !CGImageDestinationFinalize(destination) {
        throw NSError(domain: "sts2.sck", code: 2, userInfo: [NSLocalizedDescriptionKey: "Cannot finalize PNG"])
    }
}

@main
struct Main {
    static func main() async {
        _ = NSApplication.shared
        do {
            let args = CommandLine.arguments
            guard args.count >= 2 else {
                throw NSError(domain: "sts2.sck", code: 64, userInfo: [NSLocalizedDescriptionKey: "Usage: sck_capture_window <output> [owner]"])
            }
            let outputPath = args[1]
            let owner = args.count >= 3 ? args[2] : "Slay the Spire 2"
            let content = try await SCShareableContent.current
            guard let window = content.windows
                .filter({ $0.owningApplication?.applicationName == owner })
                .filter({ $0.windowLayer == 0 && $0.frame.width >= 320 && $0.frame.height >= 240 })
                .max(by: { $0.frame.width * $0.frame.height < $1.frame.width * $1.frame.height })
            else {
                throw NSError(domain: "sts2.sck", code: 3, userInfo: [NSLocalizedDescriptionKey: "Window not found"])
            }

            let filter = SCContentFilter(desktopIndependentWindow: window)
            let config = SCStreamConfiguration()
            config.width = Int(window.frame.width * 2.0)
            config.height = Int(window.frame.height * 2.0)
            config.pixelFormat = kCVPixelFormatType_32BGRA
            config.showsCursor = false
            config.scalesToFit = true
            config.ignoreShadowsSingleWindow = true
            config.ignoreGlobalClipSingleWindow = true

            let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
            let url = URL(fileURLWithPath: outputPath)
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try savePNG(image, to: url)
            print("{\"window_id\":\(window.windowID),\"width\":\(image.width),\"height\":\(image.height),\"on_screen\":\(window.isOnScreen),\"active\":\(window.isActive)}")
        } catch {
            fputs("\(error)\n", stderr)
            exit(1)
        }
    }
}
