// SPDX-FileCopyrightText: 2026 Ben Balter
// SPDX-License-Identifier: MIT

import FurbyRemoteKit
import SwiftUI

/// The app's one screen: who's connected, buttons to play things, errors and the log.
///
/// A SwiftUI view is a description of the screen, not the screen itself: `body`
/// runs again whenever something it reads changes (here, anything on `board`),
/// and SwiftUI updates only what's different.
struct ContentView: View {
    let board: BoardLink

    var body: some View {
        NavigationStack {
            List {
                connectionSection
                if let status = board.status { furbiesSection(status) }
                if board.state == .connected { playSection }
                if let plan = board.plan { scenesSection(plan); clipsSection(plan) }
                errorsSection
                logSection
            }
            .navigationTitle("Furby Show")
            .refreshable { board.send(.status) }  // pull down to ask for the status now
        }
    }

    // MARK: Sections

    private var connectionSection: some View {
        Section {
            HStack {
                Circle().fill(connectionColor).frame(width: 10, height: 10)
                Text(connectionText)
                Spacer()
                if board.state != .connected {
                    Button("Retry") { board.reconnect() }
                }
            }
            if let reply = board.lastReply {
                Text(reply).font(.footnote).foregroundStyle(.secondary)
            }
        }
    }

    private func furbiesSection(_ status: Status) -> some View {
        Section("Furbies") {
            ForEach(status.order, id: \.self) { name in
                HStack {
                    Image(systemName: status.on.contains(name) ? "checkmark.circle.fill" : "circle.dashed")
                        .foregroundStyle(status.on.contains(name) ? .green : .orange)
                    Text(name.capitalized)
                    Spacer()
                    Text(furbyNote(name, status)).foregroundStyle(.secondary)
                }
            }
            LabeledContent("Now", value: status.playing ? "Playing a scene" : "Between scenes")
            LabeledContent("Scenes played", value: "\(status.scenes)")
            LabeledContent("Up", value: Duration.seconds(status.up).formatted(.units(allowed: [.hours, .minutes])))
            if let free = status.freeKB { LabeledContent("Free memory", value: "\(free) KB") }
        }
    }

    private var playSection: some View {
        Section {
            Button {
                board.send(.greet)
            } label: {
                Label("Greet", systemImage: "hand.wave.fill").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
    }

    private func scenesSection(_ plan: Plan) -> some View {
        Section("Scenes") {
            // enumerated() pairs each scene with its index, which is what the board wants
            ForEach(Array(plan.scenes.enumerated()), id: \.offset) { index, scene in
                Button(Plan.describe(scene)) { board.send(.scene(index)) }
                    .disabled(board.state != .connected)
            }
        }
    }

    private func clipsSection(_ plan: Plan) -> some View {
        Section("Clips") {
            ForEach(plan.order, id: \.self) { name in
                DisclosureGroup(name.capitalized) {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 100))], spacing: 8) {
                        ForEach(plan.clips[name] ?? [], id: \.self) { clip in
                            Button(clip) { board.send(.clip("\(name).\(clip)")) }
                                .buttonStyle(.bordered)
                                .disabled(board.state != .connected)
                        }
                    }
                }
            }
        }
    }

    private var errorsSection: some View {
        Section("Errors") {
            if board.errors.isEmpty {
                Text("None").foregroundStyle(.secondary)
            }
            ForEach(Array(board.errors.prefix(10).enumerated()), id: \.offset) { _, line in
                Text(line).font(.caption.monospaced()).foregroundStyle(.red)
            }
        }
    }

    private var logSection: some View {
        Section {
            NavigationLink("Full log (\(board.log.count) lines)") { LogView(board: board) }
            ForEach(Array(board.log.suffix(5).reversed().enumerated()), id: \.offset) { _, line in
                Text(line).font(.caption.monospaced())
            }
        } header: {
            Text("Latest")
        }
    }

    // MARK: Helpers

    private var connectionText: String {
        switch board.state {
        case .bluetoothOff: "Bluetooth is off"
        case .scanning: "Looking for the board…"
        case .connecting: "Connecting…"
        case .connected: "Connected to the board"
        case .unavailable(let why): why
        }
    }

    private var connectionColor: Color {
        switch board.state {
        case .connected: .green
        case .scanning, .connecting: .orange
        default: .red
        }
    }

    private func furbyNote(_ name: String, _ status: Status) -> String {
        if status.on.contains(name) { return "connected" }
        if status.waiting == name { return status.stuck ? "not found yet" : "power up next" }
        return "waiting"
    }
}

/// The whole log, newest at the bottom, following new lines as they come in.
struct LogView: View {
    let board: BoardLink

    var body: some View {
        ScrollViewReader { proxy in
            List(Array(board.log.enumerated()), id: \.offset) { index, line in
                Text(line)
                    .font(.caption.monospaced())
                    .foregroundStyle(line.contains("Couldn't") || line.contains("dropped") ? .red : .primary)
                    .id(index)
            }
            .onChange(of: board.log.count) { _, count in
                withAnimation { proxy.scrollTo(count - 1, anchor: .bottom) }
            }
        }
        .navigationTitle("Log")
        .navigationBarTitleDisplayMode(.inline)
    }
}
