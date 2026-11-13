# Login retry behavior

Provider login flows are bounded sessions. A rejected, expired or incomplete confirmation is a failure, not a connected account. The UI offers a fresh attempt with a fresh login key. Cancelling a pending attempt stops that session; it is not a provider logout.

Codes are sent through masked input or stdin rather than command-line arguments. Use the native provider CLI and complete browser consent yourself. A profile busy with another native operation remains busy; a retry must preserve account and worker locks.

The controlled login tests cover start, input, cancellation, rejection and retry. Run the Rust login tests and frontend `LoginView` tests described in [validation](validation.md). Actual provider consent and platform-specific keychain behavior require separate opt-in acceptance on the executing machine.
