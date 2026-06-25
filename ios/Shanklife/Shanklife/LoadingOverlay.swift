import SwiftUI

struct BlockingProgressOverlay: ViewModifier {
    let isPresented: Bool
    let message: String

    func body(content: Content) -> some View {
        ZStack {
            content
                .disabled(isPresented)

            if isPresented {
                Color.black.opacity(0.18)
                    .ignoresSafeArea()

                VStack(spacing: 14) {
                    ProgressView()
                        .controlSize(.large)
                    Text(message)
                        .font(.headline)
                }
                .padding(.horizontal, 28)
                .padding(.vertical, 22)
                .background(.regularMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .shadow(radius: 18)
            }
        }
        .animation(.easeInOut(duration: 0.18), value: isPresented)
    }
}

extension View {
    func blockingProgress(_ isPresented: Bool, message: String) -> some View {
        modifier(BlockingProgressOverlay(isPresented: isPresented, message: message))
    }
}

struct OptionMenuRow<Value: Hashable>: View {
    let title: String
    let options: [(label: String, value: Value?)]
    @Binding var selection: Value?

    var body: some View {
        Menu {
            ForEach(Array(options.enumerated()), id: \.offset) { _, option in
                Button {
                    selection = option.value
                } label: {
                    if selection == option.value {
                        Label(option.label, systemImage: "checkmark")
                    } else {
                        Text(option.label)
                    }
                }
            }
        } label: {
            HStack {
                Text(title)
                    .foregroundStyle(.primary)
                Spacer()
                Text(selectedLabel)
                    .foregroundStyle(.secondary)
                Image(systemName: "chevron.up.chevron.down")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var selectedLabel: String {
        options.first { $0.value == selection }?.label ?? "-"
    }
}
