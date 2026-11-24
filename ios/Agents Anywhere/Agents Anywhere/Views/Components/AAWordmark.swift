import SwiftUI

struct AAWordmark: View {
    let fontSize: CGFloat

    var body: some View {
        Text(verbatim: "云大师\u{2009}")
            .font(.system(size: fontSize, weight: .medium))
            .tracking(0)
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: true)
            .frame(height: fontSize)
    }
}
