// SPDX-FileCopyrightText: 2026 Ben Balter
// SPDX-License-Identifier: MIT

// What the board and the phone say to each other. The board's side, and the
// protocol's description, is firmware/remote.py; keep the two in step.
//
// In short: the board sends newline-terminated JSON over the Nordic UART
// Service (NUS), split into Bluetooth-sized pieces, and the phone writes
// plain-text commands back.

import Foundation

/// The Bluetooth identifiers the board advertises. NUS is a de facto standard,
/// so apps like nRF Connect can talk to the board too.
public enum NUS {
    public static let service = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
    /// The phone writes commands here (the board's "receive").
    public static let rx = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
    /// The board notifies messages here (the board's "transmit").
    public static let tx = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
    /// The name the board advertises.
    public static let name = "Furby Show"
}

/// The built show: who's in it, its scenes and each Furby's clips.
public struct Plan: Codable, Equatable, Sendable {
    public var order: [String]
    public var scenes: [[String]]
    public var greetings: [[String]]
    public var clips: [String: [String]]

    public init(order: [String], scenes: [[String]], greetings: [[String]], clips: [String: [String]]) {
        self.order = order
        self.scenes = scenes
        self.greetings = greetings
        self.clips = clips
    }

    /// A scene as one line, the way the board logs it: "pink.boo -> blue.what".
    public static func describe(_ scene: [String]) -> String {
        scene.joined(separator: " -> ")
    }
}

/// The show right now. Optional fields may be missing from an older board.
public struct Status: Codable, Equatable, Sendable {
    /// Seconds since the board started.
    public var up: Int
    /// The Furbies in power-up order.
    public var order: [String]
    /// The Furbies connected now.
    public var on: [String]
    /// The next Furby to power up, if any is missing.
    public var waiting: String?
    /// True when a missing Furby hasn't turned up for a while (the LED flickers).
    public var stuck: Bool
    /// True during a scene.
    public var playing: Bool
    /// Scenes played since the board started.
    public var scenes: Int
    /// Free memory on the board, in KB.
    public var freeKB: Int?
    /// Why the board last started.
    public var reset: String?

    enum CodingKeys: String, CodingKey {
        case up, order, on, waiting, stuck, playing, scenes, reset
        case freeKB = "free_kb"
    }
}

/// One message from the board.
public enum Message: Equatable, Sendable {
    case hello(Plan)
    case errors([String])
    case log(line: String, isError: Bool)
    case status(Status)
    case ack(command: String, ok: Bool, error: String?)
    /// A message this app doesn't know yet (a newer board), kept rather than failing.
    case unknown(String)

    /// Decode one line of the board's JSON.
    public static func decode(_ line: String) throws -> Message {
        let data = Data(line.utf8)
        let kind = try JSONDecoder().decode(Kind.self, from: data).t
        switch kind {
        case "hello":
            return .hello(try JSONDecoder().decode(Hello.self, from: data).plan)
        case "errors":
            return .errors(try JSONDecoder().decode(Errors.self, from: data).lines)
        case "log":
            let log = try JSONDecoder().decode(Log.self, from: data)
            return .log(line: log.line, isError: log.error)
        case "status":
            return .status(try JSONDecoder().decode(Status.self, from: data))
        case "ack":
            let ack = try JSONDecoder().decode(Ack.self, from: data)
            return .ack(command: ack.cmd, ok: ack.ok, error: ack.error)
        default:
            return .unknown(kind)
        }
    }

    // The shapes of each message on the wire.
    private struct Kind: Decodable { let t: String }
    private struct Hello: Decodable { let plan: Plan }
    private struct Errors: Decodable { let lines: [String] }
    private struct Log: Decodable { let line: String; let error: Bool }
    private struct Ack: Decodable { let cmd: String; let ok: Bool; let error: String? }
}

/// Joins the board's Bluetooth notifications back into whole lines.
///
/// A notification carries at most about 180 bytes, so a long message (the
/// plan, say) arrives in several pieces; a line is complete at its newline.
public struct LineAssembler: Sendable {
    private var buffer = Data()

    public init() {}

    /// Add one notification; returns any lines it completed, oldest first.
    public mutating func append(_ chunk: Data) -> [String] {
        buffer.append(chunk)
        var lines: [String] = []
        while let newline = buffer.firstIndex(of: UInt8(ascii: "\n")) {
            let line = buffer[buffer.startIndex..<newline]
            buffer.removeSubrange(buffer.startIndex...newline)
            if let text = String(data: line, encoding: .utf8), !text.isEmpty {
                lines.append(text)
            }
        }
        return lines
    }

    /// Forget a half-received line, e.g. after the connection drops.
    public mutating func reset() {
        buffer.removeAll()
    }
}

/// Something the phone asks the board to do.
public enum Command: Equatable, Sendable {
    /// Play a greeting now, as the board's button does.
    case greet
    /// Play the plan's scene at this index next.
    case scene(Int)
    /// Play one clip next, e.g. "pink.cackle".
    case clip(String)
    /// Send the status now.
    case status

    /// The text the board reads.
    public var text: String {
        switch self {
        case .greet: "greet"
        case .scene(let index): "scene \(index)"
        case .clip(let name): "clip \(name)"
        case .status: "status"
        }
    }

    /// The bytes to write to the board's RX characteristic.
    public var data: Data { Data(text.utf8) }
}
