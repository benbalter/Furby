// SPDX-FileCopyrightText: 2026 Ben Balter
// SPDX-License-Identifier: MIT

import SwiftUI

/// The app's entry point. `@main` tells Swift to start here; SwiftUI then
/// shows the first `Scene`, a window holding `ContentView`.
@main
struct FurbyRemoteApp: App {
    /// One connection to the board for the whole app. `@State` keeps it alive
    /// for as long as the app runs and hands the same instance to every view.
    @State private var board = BoardLink()

    var body: some Scene {
        WindowGroup {
            ContentView(board: board)
        }
    }
}
