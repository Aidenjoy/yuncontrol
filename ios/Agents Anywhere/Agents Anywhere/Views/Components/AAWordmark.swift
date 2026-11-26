import SwiftUI

/// Displays the shared cloud brand mark alongside the product name.
struct AAWordmark: View {
    let fontSize: CGFloat

    var body: some View {
        HStack(spacing: 8) {
            Image("login-logo-light-mode").resizable().scaledToFit()
                .frame(width: fontSize, height: fontSize)
                .accessibilityHidden(true)
            Text(verbatim: "云大师Agent\u{2009}")
                .font(.system(size: fontSize, weight: .medium))
                .tracking(0)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: true)
                .frame(height: fontSize)
        }
    }
}
