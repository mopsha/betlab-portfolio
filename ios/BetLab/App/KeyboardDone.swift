import UIKit

/// A Done bar above every number pad in the app (Nov 6, Mike: "there's no enter option so I can't get rid of the number pad
/// on my screen"). iOS's number and decimal pads have no Return key, and 27 fields across 12 screens had nothing to close
/// them. Installed once at launch: when any text field begins editing with a pad that has no Return key, it gets a bar
/// with Done, which ends editing. Fields with a Return key are left alone.
enum KeyboardDone {
    private static var observer: NSObjectProtocol?
    private static let pads: Set<UIKeyboardType> = [.numberPad, .decimalPad, .phonePad, .asciiCapableNumberPad]
    private static let tag = 0xD0E

    static func install() {
        guard observer == nil else { return }
        observer = NotificationCenter.default.addObserver(forName: UITextField.textDidBeginEditingNotification, object: nil, queue: .main) { n in
            // SwiftUI puts its own empty accessory host on its fields, so "none set" can't be the test; the app has no
            // keyboard toolbars of its own (no ToolbarItem placement .keyboard), so replacing it is safe
            guard let f = n.object as? UITextField, pads.contains(f.keyboardType), f.inputAccessoryView?.tag != tag else { return }
            f.inputAccessoryView = bar(for: f)
            f.reloadInputViews()
        }
    }

    private static func bar(for f: UITextField) -> UIToolbar {
        let t = UIToolbar(frame: CGRect(x: 0, y: 0, width: 320, height: 44))
        let done = UIBarButtonItem(systemItem: .done, primaryAction: UIAction { [weak f] _ in f?.resignFirstResponder() })
        t.items = [UIBarButtonItem(systemItem: .flexibleSpace), done]
        t.sizeToFit()
        t.tag = tag
        return t
    }
}
