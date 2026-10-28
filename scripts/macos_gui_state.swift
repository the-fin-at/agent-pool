// Headful acceptance preflight; reports no user identity or other app content.
import CoreGraphics
import Foundation
let session = CGSessionCopyCurrentDictionary() as? [String: Any] ?? [:]
let locked = (session["CGSSessionScreenIsLocked"] as? NSNumber)?.boolValue ?? false
let console = (session["kCGSSessionOnConsoleKey"] as? NSNumber)?.boolValue ?? false
let data = try JSONSerialization.data(withJSONObject: ["screen_locked":locked,"console_session":console], options: [.sortedKeys])
print(String(data:data,encoding:.utf8)!)
