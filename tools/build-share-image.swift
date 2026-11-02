// Compose the existing public logo and approved dashboard capture; no private inputs.
import AppKit
let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let output = root.appendingPathComponent("docs/assets/freeqnap-share-v1.png")
let bitmap = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:1200,pixelsHigh:630,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep:bitmap)
NSColor(calibratedRed:0.043,green:0.035,blue:0.051,alpha:1).setFill()
NSRect(x:0,y:0,width:1200,height:630).fill()
let glow = NSGradient(starting:NSColor(calibratedRed:0.28,green:0.08,blue:0.15,alpha:1),ending:NSColor(calibratedRed:0.043,green:0.035,blue:0.051,alpha:1))!
glow.draw(in:NSRect(x:0,y:430,width:1200,height:200),angle:0)
let logo = NSImage(contentsOf:root.appendingPathComponent("docs/assets/freeqnap.svg"))!
logo.draw(in:NSRect(x:42,y:508,width:92,height:92))
func text(_ value:String,_ x:CGFloat,_ y:CGFloat,_ size:CGFloat,_ color:NSColor,_ weight:NSFont.Weight = .regular){
 (value as NSString).draw(at:NSPoint(x:x,y:y),withAttributes:[.font:NSFont.systemFont(ofSize:size,weight:weight),.foregroundColor:color])
}
text("FreeQNAP",154,548,44,.white,.bold)
text("Your hardware. Your NAS. Your memories.",156,516,20,NSColor(calibratedWhite:0.77,alpha:1))
text("STORAGE  ·  BACKUPS  ·  PRIVATE ICLOUD PHOTO ARCHIVE",44,473,15,NSColor(calibratedRed:0.98,green:0.47,blue:0.61,alpha:1),.semibold)
let frame = NSBezierPath(roundedRect:NSRect(x:40,y:28,width:1120,height:425),xRadius:12,yRadius:12)
NSColor(calibratedRed:0.4,green:0.22,blue:0.3,alpha:1).setFill();frame.fill()
let screenshot = NSImage(contentsOf:root.appendingPathComponent("docs/assets/screenshots/overview.png"))!
NSGraphicsContext.saveGraphicsState()
NSBezierPath(roundedRect:NSRect(x:43,y:31,width:1114,height:419),xRadius:10,yRadius:10).addClip()
// Preserve the full screenshot width and crop only the lower edge to fit the card.
let height = 1114 * screenshot.size.height / screenshot.size.width
screenshot.draw(in:NSRect(x:43,y:450-height,width:1114,height:height))
NSGraphicsContext.restoreGraphicsState()
NSGraphicsContext.restoreGraphicsState()
try bitmap.representation(using:.png,properties:[:])!.write(to:output)
print(output.path)
