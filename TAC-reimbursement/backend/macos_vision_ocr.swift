import Foundation
import Vision
import AppKit
import PDFKit

func cgImageFromImageFile(_ url: URL) -> CGImage? {
    guard let image = NSImage(contentsOf: url) else { return nil }
    var rect = CGRect(origin: .zero, size: image.size)
    return image.cgImage(forProposedRect: &rect, context: nil, hints: nil)
}

func cgImageFromPDF(_ url: URL) -> CGImage? {
    guard let document = PDFDocument(url: url), let page = document.page(at: 0) else { return nil }
    let bounds = page.bounds(for: .mediaBox)
    let scale: CGFloat = 2.0
    let image = NSImage(size: NSSize(width: bounds.width * scale, height: bounds.height * scale))
    image.lockFocus()
    guard let context = NSGraphicsContext.current?.cgContext else {
        image.unlockFocus()
        return nil
    }
    context.setFillColor(NSColor.white.cgColor)
    context.fill(CGRect(x: 0, y: 0, width: bounds.width * scale, height: bounds.height * scale))
    context.saveGState()
    context.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: context)
    context.restoreGState()
    image.unlockFocus()
    var rect = CGRect(origin: .zero, size: image.size)
    return image.cgImage(forProposedRect: &rect, context: nil, hints: nil)
}

if CommandLine.arguments.count < 2 {
    fputs("Usage: macos_vision_ocr.swift <image-or-pdf>\n", stderr)
    exit(2)
}

let url = URL(fileURLWithPath: CommandLine.arguments[1])
let fileExtension = url.pathExtension.lowercased()
let cgImage = fileExtension == "pdf" ? cgImageFromPDF(url) : cgImageFromImageFile(url)

guard let image = cgImage else {
    fputs("Could not load image/PDF for OCR\n", stderr)
    exit(3)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["ja-JP", "en-US"]

let handler = VNImageRequestHandler(cgImage: image, options: [:])
do {
    try handler.perform([request])
    let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    print(lines.joined(separator: "\n"))
} catch {
    fputs("Vision OCR failed: \(error)\n", stderr)
    exit(4)
}
