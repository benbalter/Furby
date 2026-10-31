// SPDX-FileCopyrightText: 2026 Ben Balter
// SPDX-License-Identifier: MIT

// @preconcurrency: CoreBluetooth predates Swift 6's data-race checks. Its objects
// only ever come to us on the main queue (see init), so that's safe here.
@preconcurrency import CoreBluetooth
import FurbyRemoteKit
import Observation
import UIKit
import UserNotifications

/// The Bluetooth link to the show's board, and everything it has told us.
///
/// CoreBluetooth works by delegation: we ask it to do something (scan, connect,
/// discover services) and it calls us back later on a delegate method. The
/// order is always: power on → scan → connect → discover the service → discover
/// its characteristics → subscribe to TX. Each step's callback starts the next.
///
/// `@Observable` makes SwiftUI redraw any view that reads a property here when
/// that property changes. `@MainActor` keeps every change on the main thread,
/// which SwiftUI requires; the central manager is created on the main queue so
/// its callbacks arrive there too.
@Observable
@MainActor
final class BoardLink: NSObject {
    enum State: Equatable {
        case bluetoothOff, scanning, connecting, connected
        case unavailable(String)
    }

    private(set) var state: State = .bluetoothOff
    private(set) var plan: Plan?
    private(set) var status: Status?
    private(set) var log: [String] = []
    private(set) var errors: [String] = []
    /// The board's answer to the last command, shown briefly.
    private(set) var lastReply: String?

    static let logLimit = 500
    static let errorLimit = 50

    private var central: CBCentralManager!
    private var board: CBPeripheral?
    private var rx: CBCharacteristic?
    private var assembler = LineAssembler()
    private let serviceID = CBUUID(string: NUS.service)
    private let rxID = CBUUID(string: NUS.rx)
    private let txID = CBUUID(string: NUS.tx)

    override init() {
        super.init()
        // queue: .main means callbacks arrive on the main thread (see above).
        central = CBCentralManager(delegate: self, queue: .main)
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    /// Ask the board to do something. Does nothing until we're connected.
    func send(_ command: Command) {
        guard let board, let rx else { return }
        board.writeValue(command.data, for: rx, type: .withResponse)
    }

    /// Drop the connection and look again, e.g. after moving closer to the porch.
    func reconnect() {
        if let board { central.cancelPeripheralConnection(board) }
        startScanning()
    }

    private func startScanning() {
        guard central.state == .poweredOn else { return }
        state = .scanning
        // Only boards advertising the show's service turn up.
        central.scanForPeripherals(withServices: [serviceID])
    }

    /// Handle one complete line from the board.
    private func handle(_ line: String) {
        let message: Message
        do {
            message = try Message.decode(line)
        } catch {
            append(log: "(couldn't read: \(line))")
            return
        }
        switch message {
        case .hello(let plan):
            self.plan = plan
            log.removeAll()  // the board resends its backlog next
        case .errors(let lines):
            errors = lines.reversed()
        case .log(let line, let isError):
            append(log: line)
            if isError {
                errors.insert(line, at: 0)
                errors = Array(errors.prefix(Self.errorLimit))
                alertIfInBackground(line)
            }
        case .status(let status):
            self.status = status
        case .ack(let command, let ok, let error):
            lastReply = ok ? "✓ \(command)" : "✗ \(command): \(error ?? "failed")"
        case .unknown:
            break  // a newer board; nothing to show yet
        }
    }

    private func append(log line: String) {
        log.append(line)
        if log.count > Self.logLimit { log.removeFirst(log.count - Self.logLimit) }
    }

    /// With the app in the background, an error (a Furby dropped, say) buzzes the phone.
    private func alertIfInBackground(_ line: String) {
        guard UIApplication.shared.applicationState != .active else { return }
        let content = UNMutableNotificationContent()
        content.title = "Furby show"
        // Drop the "[   123] " timestamp the board puts on every line
        content.body = line.split(separator: "]", maxSplits: 1).last.map { $0.trimmingCharacters(in: .whitespaces) } ?? line
        content.sound = .default
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}

// MARK: - CoreBluetooth callbacks
//
// These are `nonisolated` because CoreBluetooth's protocols don't know about
// the main actor. We told it to call us on the main queue, so
// `MainActor.assumeIsolated` is safe: it just tells Swift what we already know.

extension BoardLink: CBCentralManagerDelegate {
    nonisolated func centralManagerDidUpdateState(_ central: CBCentralManager) {
        MainActor.assumeIsolated {
            switch central.state {
            case .poweredOn: startScanning()
            case .unauthorized: state = .unavailable("Allow Bluetooth for Furby Remote in Settings")
            case .unsupported: state = .unavailable("This device has no Bluetooth LE")
            default: state = .bluetoothOff
            }
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                                    advertisementData: [String: Any], rssi RSSI: NSNumber) {
        MainActor.assumeIsolated {
            central.stopScan()
            board = peripheral  // keep a reference, or iOS drops the connection
            peripheral.delegate = self
            state = .connecting
            central.connect(peripheral)
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        MainActor.assumeIsolated {
            assembler.reset()
            peripheral.discoverServices([serviceID])
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral,
                                    error: Error?) {
        MainActor.assumeIsolated { startScanning() }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral,
                                    error: Error?) {
        MainActor.assumeIsolated {
            rx = nil
            append(log: "(lost the board; reconnecting when it's back in range)")
            // A pending connect never times out: iOS completes it whenever the
            // board shows up again, even with the app in the background.
            state = .connecting
            central.connect(peripheral)
        }
    }
}

extension BoardLink: CBPeripheralDelegate {
    nonisolated func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        MainActor.assumeIsolated {
            guard let service = peripheral.services?.first(where: { $0.uuid == serviceID }) else { return }
            peripheral.discoverCharacteristics([rxID, txID], for: service)
        }
    }

    nonisolated func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService,
                                error: Error?) {
        MainActor.assumeIsolated {
            for characteristic in service.characteristics ?? [] {
                if characteristic.uuid == rxID { rx = characteristic }
                // Subscribing makes the board start talking: hello, errors, the backlog.
                if characteristic.uuid == txID { peripheral.setNotifyValue(true, for: characteristic) }
            }
            state = .connected
        }
    }

    nonisolated func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic,
                                error: Error?) {
        MainActor.assumeIsolated {
            guard let chunk = characteristic.value else { return }
            for line in assembler.append(chunk) { handle(line) }
        }
    }
}
