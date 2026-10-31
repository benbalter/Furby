// SPDX-FileCopyrightText: 2026 Ben Balter
// SPDX-License-Identifier: MIT

import Foundation
import Testing

@testable import FurbyRemoteKit

// The JSON here is what firmware/remote.py sends (see its tests in test_furby.py).

@Test func joinsChunksIntoLines() {
    var assembler = LineAssembler()
    #expect(assembler.append(Data("{\"t\":\"lo".utf8)) == [])
    #expect(assembler.append(Data("g\"}\n{\"t\":".utf8)) == ["{\"t\":\"log\"}"])
    #expect(assembler.append(Data("\"ack\"}\n\n".utf8)) == ["{\"t\":\"ack\"}"])  // and skips empty lines
    assembler.reset()
    #expect(assembler.append(Data("x\n".utf8)) == ["x"])
}

@Test func decodesHello() throws {
    let line = #"{"t": "hello", "plan": {"order": ["pink", "blue"], "scenes": [["pink.a", "blue.b"]], "greetings": [], "clips": {"pink": ["a"], "blue": ["b"]}}}"#
    let message = try Message.decode(line)
    #expect(message == .hello(Plan(order: ["pink", "blue"], scenes: [["pink.a", "blue.b"]], greetings: [],
                                   clips: ["pink": ["a"], "blue": ["b"]])))
}

@Test func decodesStatusLogErrorsAndAck() throws {
    let status = #"{"t": "status", "up": 31, "order": ["pink", "blue"], "on": ["pink"], "waiting": "blue", "stuck": false, "playing": true, "scenes": 4, "free_kb": 7900, "reset": "power-on"}"#
    guard case .status(let s) = try Message.decode(status) else { Issue.record("not a status"); return }
    #expect(s.on == ["pink"] && s.waiting == "blue" && s.playing && s.freeKB == 7900)

    // A board from before free_kb or reset existed still decodes
    let old = #"{"t": "status", "up": 1, "order": [], "on": [], "waiting": null, "stuck": true, "playing": false, "scenes": 0}"#
    guard case .status(let o) = try Message.decode(old) else { Issue.record("not a status"); return }
    #expect(o.freeKB == nil && o.waiting == nil && o.stuck)

    #expect(try Message.decode(#"{"t": "log", "line": "[  40] Blue dropped.", "error": true}"#)
            == .log(line: "[  40] Blue dropped.", isError: true))
    #expect(try Message.decode(#"{"t": "errors", "lines": ["a", "b"]}"#) == .errors(["a", "b"]))
    #expect(try Message.decode(#"{"t": "ack", "cmd": "clip pink.zzz", "ok": false, "error": "No clip pink.zzz in this show"}"#)
            == .ack(command: "clip pink.zzz", ok: false, error: "No clip pink.zzz in this show"))
    #expect(try Message.decode(#"{"t": "later"}"#) == .unknown("later"))
}

@Test func commandText() {
    #expect(Command.greet.text == "greet")
    #expect(Command.scene(3).text == "scene 3")
    #expect(Command.clip("pink.cackle").data == Data("clip pink.cackle".utf8))
    #expect(Plan.describe(["pink.boo", "blue.what"]) == "pink.boo -> blue.what")
}
