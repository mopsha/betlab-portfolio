import SwiftUI

/// Sign in with email and password, or leave the password empty to get a 6-digit code by email
/// (the web app's login page, without Google for now).
struct LoginView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var email = ""
    @State private var password = ""
    @State private var code = ""
    @State private var codeSent = false
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form { Group {
                Section {
                    TextField("Email", text: $email)
                        .textContentType(.username)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    if !codeSent {
                        SecureField("Password (or leave empty for a code)", text: $password)
                            .textContentType(.password)
                    }
                } footer: {
                    Text("Only the invited account can sign in.")
                }

                if codeSent {
                    Section {
                        TextField("6-digit code", text: $code)
                            .textContentType(.oneTimeCode)
                            .keyboardType(.numberPad)
                    } footer: {
                        Text("We emailed a code to \(email). Codes last an hour and work once.")
                    }
                }

                if let error {
                    Section { Text(error).foregroundStyle(.red) }
                }

                Section {
                    Button(action: submit) {
                        HStack {
                            Text(codeSent ? "Sign in with code" : password.isEmpty ? "Email me a code" : "Sign in")
                            if busy { Spacer(); ProgressView() }
                        }
                    }
                    .disabled(busy || email.isEmpty || (codeSent && code.filter(\.isNumber).count < 6))
                    if codeSent {
                        Button("Use a password instead") { codeSent = false; code = ""; error = nil }
                    }
                }
            }.themedRows() }.themedList()
            .navigationTitle("BetLab")
        }
    }

    private func submit() {
        busy = true
        error = nil
        let address = email.trimmingCharacters(in: .whitespaces).lowercased()
        Task {
            defer { busy = false }
            do {
                if codeSent {
                    try await auth.verify(email: address, code: code.filter(\.isNumber))
                } else if password.isEmpty {
                    try await auth.sendCode(email: address)
                    codeSent = true
                } else {
                    try await auth.signIn(email: address, password: password)
                }
            } catch {
                self.error = codeSent ? "That code didn't work. Send a new one."
                    : password.isEmpty ? "Couldn't send the email. Check the address (it must be the invited one)."
                    : "That email and password don't match. Leave the password empty to get a code by email."
            }
        }
    }
}
