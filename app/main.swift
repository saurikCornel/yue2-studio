// YuE2 Studio — envoltorio nativo (WKWebView) del backend local de mlx-Yue.
// Arranca server.py si no está corriendo, espera el puerto y muestra la UI.
import Cocoa
import WebKit

func infoValue(_ key: String) -> String? {
    Bundle.main.object(forInfoDictionaryKey: key) as? String
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var server: Process?
    var startedByUs = false
    var logHandle: FileHandle?
    var retries = 0

    var studioDir: String { infoValue("StudioDir") ?? NSString(string: "~/Projects/yue2-studio").expandingTildeInPath }
    var port: Int { Int(infoValue("StudioPort") ?? "8787") ?? 8787 }
    var projectDir: String {
        let cfg = URL(fileURLWithPath: studioDir).appendingPathComponent("config.json")
        if let data = try? Data(contentsOf: cfg),
           let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let project = obj["project"] as? String { return NSString(string: project).expandingTildeInPath }
        return NSString(string: "~/Projects/mlx-Yue").expandingTildeInPath
    }
    var consoleURL: URL { URL(fileURLWithPath: studioDir).appendingPathComponent("server.log") }

    // MARK: ciclo de vida
    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        let config = WKWebViewConfiguration()
        config.mediaTypesRequiringUserActionForPlayback = []
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")
        webView = WKWebView(frame: .zero, configuration: config)
        webView.setValue(false, forKey: "drawsBackground")

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1240, height: 840),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "YuE2 Studio"
        window.titlebarAppearsTransparent = true
        window.minSize = NSSize(width: 960, height: 640)
        window.appearance = NSAppearance(named: .darkAqua)
        window.backgroundColor = NSColor(calibratedRed: 0.039, green: 0.039, blue: 0.047, alpha: 1)
        window.contentView = webView
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        if healthy() {
            loadUI()
        } else {
            startServer()
            waitForServer()
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        guard startedByUs, let proc = server, proc.isRunning else { return }
        proc.terminate()
        let deadline = Date().addingTimeInterval(4)
        while proc.isRunning && Date() < deadline { usleep(120_000) }
        if proc.isRunning { kill(proc.processIdentifier, SIGKILL) }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    // MARK: servidor
    func healthy() -> Bool {
        guard let url = URL(string: "http://127.0.0.1:\(port)/api/health") else { return false }
        var request = URLRequest(url: url)
        request.timeoutInterval = 1.5
        var ok = false
        let sem = DispatchSemaphore(value: 0)
        URLSession.shared.dataTask(with: request) { _, response, _ in
            if let http = response as? HTTPURLResponse, http.statusCode == 200 { ok = true }
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 3)
        return ok
    }

    func startServer() {
        let script = URL(fileURLWithPath: studioDir).appendingPathComponent("server.py")
        guard FileManager.default.fileExists(atPath: script.path) else {
            presentError("No encuentro \(script.path). Recompilá la app con build_app.sh.")
            return
        }
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        proc.arguments = [script.path]
        var env = ProcessInfo.processInfo.environment
        env["YUE2_STUDIO_PORT"] = String(port)
        env["PYTHONUNBUFFERED"] = "1"
        proc.environment = env
        let logPath = consoleURL.path
        FileManager.default.createFile(atPath: logPath, contents: nil)
        logHandle = FileHandle(forWritingAtPath: logPath)
        proc.standardOutput = logHandle
        proc.standardError = logHandle
        do {
            try proc.run()
            server = proc
            startedByUs = true
        } catch {
            presentError("No pude arrancar el backend: \(error.localizedDescription)")
        }
    }

    func waitForServer() {
        if healthy() { loadUI(); return }
        retries += 1
        if retries > 120 {
            presentError("El backend no respondió en 60 s. Mirá la consola (menú → Ver consola del backend).")
            return
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in self?.waitForServer() }
    }

    func loadUI() {
        guard let url = URL(string: "http://127.0.0.1:\(port)/") else { return }
        webView.load(URLRequest(url: url))
    }

    func presentError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "YuE2 Studio"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.runModal()
    }

    // MARK: menú
    func buildMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Acerca de YuE2 Studio", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Recargar interfaz", action: #selector(reloadUI), keyEquivalent: "r")
        appMenu.addItem(withTitle: "Reiniciar backend", action: #selector(restartBackend), keyEquivalent: "R")
        appMenu.addItem(withTitle: "Ver consola del backend", action: #selector(openConsole), keyEquivalent: "l")
        appMenu.addItem(withTitle: "Abrir outputs en Finder", action: #selector(openOutputs), keyEquivalent: "o")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Salir de YuE2 Studio", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)

        let editItem = NSMenuItem()
        let edit = NSMenu(title: "Edición")
        edit.addItem(withTitle: "Cortar", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copiar", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Pegar", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Seleccionar todo", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        main.addItem(editItem)

        NSApp.mainMenu = main
    }

    @objc func reloadUI() { webView.reload() }

    @objc func restartBackend() {
        if let proc = server, proc.isRunning { proc.terminate() }
        server = nil
        startedByUs = false
        retries = 0
        startServer()
        waitForServer()
    }

    @objc func openConsole() {
        if !FileManager.default.fileExists(atPath: consoleURL.path) {
            FileManager.default.createFile(atPath: consoleURL.path, contents: nil)
        }
        NSWorkspace.shared.open(consoleURL)
    }

    @objc func openOutputs() {
        let outputs = URL(fileURLWithPath: projectDir).appendingPathComponent("outputs")
        NSWorkspace.shared.open(outputs)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
