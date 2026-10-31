// swift-tools-version: 6.0
// SPDX-FileCopyrightText: 2026 Ben Balter
// SPDX-License-Identifier: MIT

// The phone remote's protocol, kept apart from the app so it builds and tests
// with just the command-line tools (`swift test`), on a Mac or in CI, with no
// iPhone, simulator or Xcode project involved.
import PackageDescription

let package = Package(
    name: "FurbyRemoteKit",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "FurbyRemoteKit", targets: ["FurbyRemoteKit"])],
    targets: [
        .target(name: "FurbyRemoteKit"),
        .testTarget(name: "FurbyRemoteKitTests", dependencies: ["FurbyRemoteKit"]),
    ]
)
