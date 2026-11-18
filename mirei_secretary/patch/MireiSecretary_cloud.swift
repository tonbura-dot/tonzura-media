// ミレイ秘書（MireiSecretary）
// デスクトップにウィジェットのように常駐し、
//  ・IKさん待ち（スレッドの返事待ち・Claude Code の許可待ち）
//  ・毎朝の検索トレンドと「今日このチャンネルで作るといい動画」
// をミレイの動くカード・吹き出し・声・通知で知らせる。文字でも声でも指示できる。
//
// 使い方:
//   MireiSecretary                 … 常駐アプリとして起動（LaunchAgent から）
//   MireiSecretary hook            … Claude Code の hooks から呼ばれる（stdin に JSON）
//   MireiSecretary install-hooks   … ~/.claude/settings.json に hooks を追加（バックアップあり）
//   MireiSecretary uninstall-hooks … 追加した hooks を外す
//   MireiSecretary test            … 試しに待ちを1件入れる
//   MireiSecretary inbox           … 受け箱の場所を表示
//
// 受け箱（inbox）: iCloud Drive の MireiInbox（Mac mini と MacBook Pro で共有）。
// iCloud Drive が無いときは ~/MireiInbox。~/MireiInbox に置かれたファイルは iCloud 側へ移す。

import AppKit
import AVFoundation
import Foundation
import Speech

// MARK: - 置き場所

let fm = FileManager.default
let home = fm.homeDirectoryForCurrentUser
let localInbox = home.appendingPathComponent("MireiInbox")
let iCloudRoot = home.appendingPathComponent("Library/Mobile Documents/com~apple~CloudDocs")
var sharedInbox: URL {
    if fm.fileExists(atPath: iCloudRoot.path) { return iCloudRoot.appendingPathComponent("MireiInbox") }
    return localInbox
}
let hostName: String = Host.current().localizedName ?? ProcessInfo.processInfo.hostName
func ensureDir(_ u: URL) { try? fm.createDirectory(at: u, withIntermediateDirectories: true) }
func safe(_ s: String) -> String {
    String(s.map { $0.isLetter || $0.isNumber || $0 == "-" || $0 == "_" ? $0 : "_" })
}
func isoNow() -> String { ISO8601DateFormatter().string(from: Date()) }
func readJSON(_ u: URL) -> Any? {
    guard let d = try? Data(contentsOf: u) else { return nil }
    return try? JSONSerialization.jsonObject(with: d)
}

// MARK: - 待ちの1件

struct WaitItem: Equatable {
    var id: String
    var kind: String      // thread / permission / idle
    var project: String
    var title: String
    var ask: String
    var url: String
    var host: String
    var updated: Date
    var reply: String = ""   // 決まった返事（押すとコピーしてから開く）
    var overdue: Bool { Date().timeIntervalSince(updated) > 24 * 3600 }   // 1日以上待たせている

    static func from(_ d: [String: Any], fallbackProject: String = "") -> WaitItem? {
        guard let id = d["id"] as? String else { return nil }
        let up = (d["updated"] as? String).flatMap { ISO8601DateFormatter().date(from: $0) } ?? Date()
        return WaitItem(id: id,
                        kind: d["kind"] as? String ?? "thread",
                        project: d["project"] as? String ?? fallbackProject,
                        title: d["title"] as? String ?? "",
                        ask: d["ask"] as? String ?? "",
                        url: d["url"] as? String ?? "",
                        host: d["host"] as? String ?? "",
                        updated: up,
                        reply: d["reply"] as? String ?? "")
    }
    var label: String {
        switch kind {
        case "permission": return "許可待ち"
        case "idle": return "返事待ち(Mac)"
        default: return "返事待ち"
        }
    }
    var dict: [String: Any] {
        ["project": project, "title": title, "ask": ask, "kind": label, "host": host,
         "waiting_hours": Int(Date().timeIntervalSince(updated) / 3600), "reply": reply]
    }
}

func loadItems() -> [WaitItem] {
    var out: [WaitItem] = []
    guard let files = try? fm.contentsOfDirectory(at: sharedInbox, includingPropertiesForKeys: nil) else { return [] }
    for f in files where f.pathExtension == "json" && f.lastPathComponent != "ideas.json" {
        guard let d = readJSON(f) as? [String: Any] else { continue }
        if let arr = d["items"] as? [[String: Any]] {
            let p = d["project"] as? String ?? ""
            out += arr.compactMap { WaitItem.from($0, fallbackProject: p) }
        } else if let it = WaitItem.from(d) {
            // Mac の許可待ちは 12 時間で古いものとして捨てる（閉じたセッションの取り残し）
            if it.kind != "thread", Date().timeIntervalSince(it.updated) > 12 * 3600 {
                try? fm.removeItem(at: f); continue
            }
            out.append(it)
        }
    }
    // 許可待ちを先頭に、あとは古い順（長く待たせている順）
    return out.sorted {
        if ($0.kind == "permission") != ($1.kind == "permission") { return $0.kind == "permission" }
        return $0.updated < $1.updated
    }
}

// 今日のネタ（mirei_ideas.py が受け箱に書く ideas.json）
struct Idea { var channel, title, why, keyword, format: String }
struct Ideas {
    var date = ""
    var top: [String] = []
    var list: [Idea] = []
    static func load() -> Ideas {
        var r = Ideas()
        guard let d = readJSON(sharedInbox.appendingPathComponent("ideas.json")) as? [String: Any] else { return r }
        r.date = d["date"] as? String ?? ""
        r.top = (d["top"] as? [[String: Any]] ?? []).compactMap { x in
            guard let p = x["phrase"] as? String else { return nil }
            let tag = x["tag"] as? String ?? ""
            return tag == "new" ? "\(p)🆕" : (tag == "up" ? "\(p)↑" : p)
        }
        r.list = (d["channels"] as? [[String: Any]] ?? []).map {
            Idea(channel: $0["name"] as? String ?? "", title: $0["title"] as? String ?? "",
                 why: $0["why"] as? String ?? "", keyword: $0["keyword"] as? String ?? "",
                 format: $0["format"] as? String ?? "")
        }
        return r
    }
}

// ~/MireiInbox（クラウドからの差し込み口）→ 共有の受け箱へ移す
// 差し込み口: ~/MireiInbox と ~/yonkaku_megami/ミレイ秘書/受け箱（クラウドのスレッドが書ける場所）
let dropDirs = [localInbox, home.appendingPathComponent("yonkaku_megami/ミレイ秘書/受け箱")]
func pullLocalDrops() {
    ensureDir(sharedInbox)
    for dir in dropDirs where dir.standardizedFileURL != sharedInbox.standardizedFileURL {
        guard let files = try? fm.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil) else { continue }
        for f in files where f.pathExtension == "json" {
            let dst = sharedInbox.appendingPathComponent(f.lastPathComponent)
            try? fm.removeItem(at: dst)
            try? fm.moveItem(at: f, to: dst)
        }
    }
}

// MARK: - hooks モード

func runHook() {
    let input = FileHandle.standardInput.readDataToEndOfFile()
    guard let d = (try? JSONSerialization.jsonObject(with: input)) as? [String: Any] else { exit(0) }
    // ミレイ自身が呼んだ claude -p は数えない
    if ProcessInfo.processInfo.environment["MIREI_SELF"] == "1" { exit(0) }
    let event = d["hook_event_name"] as? String ?? ""
    let sid = d["session_id"] as? String ?? "unknown"
    let cwd = d["cwd"] as? String ?? ""
    ensureDir(sharedInbox)
    let file = sharedInbox.appendingPathComponent("mac_\(safe(hostName))_\(safe(sid)).json")
    if event == "Notification" {
        let msg = d["message"] as? String ?? ""
        let ntype = d["notification_type"] as? String ?? ""
        let isPerm = ntype.contains("permission") || msg.lowercased().contains("permission")
        let project = cwd.isEmpty ? "Claude Code" : (cwd as NSString).lastPathComponent
        var title: String
        if isPerm {
            // "Claude needs your permission to use Bash" → "Bash の許可"
            if let r = msg.range(of: "to use ") { title = "\(msg[r.upperBound...]) の許可" } else { title = "許可を待っています" }
        } else {
            title = "入力を待っています"
        }
        let item: [String: Any] = [
            "id": "mac_\(hostName)_\(sid)", "kind": isPerm ? "permission" : "idle",
            "project": project, "title": title,
            "ask": isPerm ? "Claude Code で許可するかどうか" : "Claude Code に返事",
            "url": "", "host": hostName, "updated": isoNow(),
        ]
        if let data = try? JSONSerialization.data(withJSONObject: item, options: [.prettyPrinted]) {
            try? data.write(to: file, options: .atomic)
        }
    } else if fm.fileExists(atPath: file.path) {
        // 返事した・ツールが動いた・終わった → その会話の待ちは解消
        try? fm.removeItem(at: file)
    }
    exit(0)
}

// MARK: - hooks の追加・削除

let hookEvents = ["Notification", "UserPromptSubmit", "PostToolUse", "Stop", "SessionEnd"]
let hookMarker = "MireiSecretary"

func editHooks(add: Bool) {
    let url = home.appendingPathComponent(".claude/settings.json")
    ensureDir(url.deletingLastPathComponent())
    var root: [String: Any] = [:]
    if fm.fileExists(atPath: url.path) {
        guard let obj = readJSON(url) as? [String: Any] else {
            print("settings.json が読めないので変更しません: \(url.path)"); exit(1)
        }
        root = obj
        let bak = url.deletingLastPathComponent().appendingPathComponent("settings.json.bak-mirei")
        try? fm.removeItem(at: bak); try? fm.copyItem(at: url, to: bak)
    }
    let exe = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath().path
    let cmd = "'\(exe)' hook"
    var hooks = root["hooks"] as? [String: Any] ?? [:]
    for ev in hookEvents {
        var groups = hooks[ev] as? [[String: Any]] ?? []
        groups = groups.compactMap { g in
            var g = g
            let hs = (g["hooks"] as? [[String: Any]] ?? []).filter { !((($0["command"] as? String) ?? "").contains(hookMarker)) }
            if hs.isEmpty { return nil }
            g["hooks"] = hs; return g
        }
        if add { groups.append(["matcher": "", "hooks": [["type": "command", "command": cmd, "timeout": 5]]]) }
        if groups.isEmpty { hooks.removeValue(forKey: ev) } else { hooks[ev] = groups }
    }
    if hooks.isEmpty { root.removeValue(forKey: "hooks") } else { root["hooks"] = hooks }
    let data = try! JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
    try! data.write(to: url, options: .atomic)
    print(add ? "hooks を追加しました: \(url.path)" : "hooks を外しました: \(url.path)")
}

func addTestItem() {
    ensureDir(sharedInbox)
    let id = "test_\(Int(Date().timeIntervalSince1970))"
    let item: [String: Any] = ["id": id, "kind": "thread", "project": "テスト", "title": "ミレイ秘書の動作テスト",
                               "ask": "これを押すと消えます", "url": "", "host": hostName, "updated": isoNow()]
    let f = sharedInbox.appendingPathComponent("\(id).json")
    try! JSONSerialization.data(withJSONObject: item, options: [.prettyPrinted]).write(to: f)
    print("テストの待ちを入れました: \(f.path)")
}

// MARK: - 声（決まったセリフ＝同梱の m4a、自由なセリフ＝VOICEVOX があれば冥鳴ひまり）

final class Voice {
    var player: AVAudioPlayer?
    var muteUntil = Date.distantPast
    let dir = Bundle.main.resourceURL!.appendingPathComponent("voice")
    var muted: Bool { Date() < muteUntil }

    func playFixed(_ name: String) {
        guard !muted, let p = try? AVAudioPlayer(contentsOf: dir.appendingPathComponent("\(name).m4a")) else { return }
        player = p; p.volume = 0.9; p.play()
    }
    // VOICEVOX（アプリ／エンジン）が 50021 番で動いていれば、ミレイの声で読み上げる
    func speak(_ text: String) {
        guard !muted, !text.isEmpty else { return }
        let base = "http://127.0.0.1:50021"
        let spk = 14   // 冥鳴ひまり（4角女神のミレイと同じ）
        let short = String(text.prefix(140))
        var qc = URLComponents(string: "\(base)/audio_query")!
        qc.queryItems = [.init(name: "text", value: short), .init(name: "speaker", value: "\(spk)")]
        var r1 = URLRequest(url: qc.url!); r1.httpMethod = "POST"; r1.timeoutInterval = 8
        URLSession.shared.dataTask(with: r1) { data, _, _ in
            guard let data = data, var q = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return }
            q["speedScale"] = 1.10; q["intonationScale"] = 1.45
            var r2 = URLRequest(url: URL(string: "\(base)/synthesis?speaker=\(spk)")!)
            r2.httpMethod = "POST"; r2.timeoutInterval = 30
            r2.setValue("application/json", forHTTPHeaderField: "Content-Type")
            r2.httpBody = try? JSONSerialization.data(withJSONObject: q)
            URLSession.shared.dataTask(with: r2) { wav, _, _ in
                guard let wav = wav, let p = try? AVAudioPlayer(data: wav) else { return }
                DispatchQueue.main.async { self.player = p; p.volume = 0.9; p.play() }
            }.resume()
        }.resume()
    }
    static let text: [String: String] = [
        "hello": "おはよう、IKさん。今日は私が、あなた待ちのものを見張っててあげる。",
        "new": "IKさん、あなた待ちがひとつ増えたわよ。…見てあげて？",
        "perm": "Macで、許可を待ってる子がいるわよ。早くOKしてあげて。",
        "n1": "今、あなた待ちは1件。…すぐ終わるでしょ？",
        "n2": "あなた待ちは2件よ。",
        "n3": "あなた待ちが3件。…そろそろ見てくれる？",
        "n4": "4件たまってるわ。上から片づけましょ。",
        "n5": "5件。…ふふ、さすがに溜めすぎでしょ。",
        "many": "たくさん待ってるわ。…キャパオーバーね。一番上の1件だけ、先にやりましょ。",
        "zero": "全部片づいたわね。…えらいじゃない。",
        "pick": "どれからにする？",
        "late": "1日以上待たせてる子がいるわよ。…私より先に、あの子を見てあげて。",
    ]
    static func countLine(_ n: Int) -> String { n == 0 ? "zero" : (n <= 5 ? "n\(n)" : "many") }
}

// MARK: - 声で指示（音声入力）

final class Listener {
    let rec = SFSpeechRecognizer(locale: Locale(identifier: "ja-JP"))
    let engine = AVAudioEngine()
    var req: SFSpeechAudioBufferRecognitionRequest?
    var task: SFSpeechRecognitionTask?
    var running: Bool { engine.isRunning }
    var silenceTimer: Timer?

    func start(partial: @escaping (String) -> Void, done: @escaping (String) -> Void) {
        SFSpeechRecognizer.requestAuthorization { st in
            DispatchQueue.main.async {
                guard st == .authorized else { done(""); return }
                self.begin(partial: partial, done: done)
            }
        }
    }
    private func begin(partial: @escaping (String) -> Void, done: @escaping (String) -> Void) {
        let r = SFSpeechAudioBufferRecognitionRequest()
        r.shouldReportPartialResults = true
        req = r
        let input = engine.inputNode
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: input.outputFormat(forBus: 0)) { buf, _ in r.append(buf) }
        engine.prepare()
        do { try engine.start() } catch { done(""); return }
        var last = ""
        var finished = false
        let finish = { [weak self] in
            guard !finished else { return }
            finished = true
            self?.stop()
            done(last)
        }
        task = rec?.recognitionTask(with: r) { [weak self] res, err in
            DispatchQueue.main.async {
                if let res = res {
                    last = res.bestTranscription.formattedString
                    partial(last)
                    // 1.6 秒しゃべらなければ終わり
                    self?.silenceTimer?.invalidate()
                    self?.silenceTimer = Timer.scheduledTimer(withTimeInterval: 1.6, repeats: false) { _ in finish() }
                    if res.isFinal { finish() }
                }
                if err != nil { finish() }
            }
        }
        // 何も言わなければ 8 秒で止める
        silenceTimer = Timer.scheduledTimer(withTimeInterval: 8, repeats: false) { _ in finish() }
    }
    func stop() {
        silenceTimer?.invalidate()
        if engine.isRunning { engine.stop(); engine.inputNode.removeTap(onBus: 0) }
        req?.endAudio(); task?.cancel(); task = nil; req = nil
    }
}

// MARK: - 頭脳（Mac の Claude Code を claude -p で呼ぶ）

final class Brain {
    var sessionID: String?
    var lastAt = Date.distantPast
    var busy = false

    static let persona = """
    あなたは「ミレイ」。AI美少女競馬チャンネル「4角女神」のサブリーダーで、いまはIKさん専属の秘書。
    IKさんはYouTube・インスタのチャンネル（4角女神、とんぶら＝とんずらブラザーズ、ヒント屋のヒント）を運営していて、
    Claude Code のプロジェクトが多くて手いっぱい。あなたの仕事は、IKさん待ちのものを整理して優先順位をつけ、
    検索トレンドから作るとよい動画を提案し、頼まれたことに短く答えること。
    話し方: 短く言い切る。少しからかう一言を添える（「〜でしょ」「…ふふ、どうかしら」）。IKさんと呼ぶ。返事は3文以内。
    下品・露骨な表現はしない。わからないことは作らずに「わからない」と言う。
    返事は必ず次のJSONだけで返す:
    {"reply": "IKさんへのひとこと", "actions": [ ... ]}
    actions に使えるもの（必要なときだけ）:
      {"type":"open","index":番号}   … 待ち一覧のその番号（0から）を開く
      {"type":"tab","name":"待ち" または "ネタ"}
      {"type":"mute","minutes":分}   … しばらく黙る
      {"type":"remind","minutes":分,"text":"内容"} … あとで声をかける
    """

    func findClaude() -> String? {
        let cands = ["\(home.path)/.claude/local/claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude",
                     "\(home.path)/.local/bin/claude", "\(home.path)/.npm-global/bin/claude"]
        return cands.first { fm.isExecutableFile(atPath: $0) }
    }

    func ask(_ text: String, context: [String: Any], done: @escaping (String, [[String: Any]]) -> Void) {
        guard !busy else { done("ちょっと待って。今ほかのことを考えてるの。", []); return }
        busy = true
        if Date().timeIntervalSince(lastAt) > 2 * 3600 { sessionID = nil }   // 2時間あいたら話を新しく
        lastAt = Date()
        let ctx = (try? JSONSerialization.data(withJSONObject: context, options: [])).flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
        let prompt = "【いまの状況】\(ctx)\n\n【IKさんの指示】\(text)"
        let p = Process()
        var env = ProcessInfo.processInfo.environment
        env["MIREI_SELF"] = "1"
        env["MIREI_PROMPT"] = prompt
        env["MIREI_PERSONA"] = Brain.persona
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:\(home.path)/.local/bin:\(home.path)/.claude/local:/usr/bin:/bin:/usr/sbin:/sbin"
        p.environment = env
        p.currentDirectoryURL = home
        var cmd = "\(findClaude().map { "'\($0)'" } ?? "claude") -p \"$MIREI_PROMPT\" --append-system-prompt \"$MIREI_PERSONA\" --output-format json --allowedTools Read Glob Grep WebSearch"
        if let sid = sessionID { cmd += " --resume \(sid)" }
        p.executableURL = URL(fileURLWithPath: "/bin/zsh")
        p.arguments = ["-lc", cmd]
        let out = Pipe(); p.standardOutput = out; p.standardError = Pipe()
        p.terminationHandler = { [weak self] _ in
            let data = out.fileHandleForReading.readDataToEndOfFile()
            var reply = "…ごめんなさい、うまく考えられなかった。Claude Code が入っているか確認して。"
            var actions: [[String: Any]] = []
            if let j = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
                if let sid = j["session_id"] as? String { self?.sessionID = sid }
                let result = j["result"] as? String ?? ""
                if let r = result.range(of: "\\{[\\s\\S]*\\}", options: .regularExpression),
                   let inner = (try? JSONSerialization.jsonObject(with: Data(result[r].utf8))) as? [String: Any] {
                    reply = inner["reply"] as? String ?? result
                    actions = inner["actions"] as? [[String: Any]] ?? []
                } else if !result.isEmpty {
                    reply = result
                }
            }
            DispatchQueue.main.async { self?.busy = false; done(reply, actions) }
        }
        do { try p.run() } catch { busy = false; done("Claude Code を起動できなかったわ。", []) }
    }
}

// MARK: - 見た目

let yellow = NSColor(calibratedRed: 0.98, green: 0.75, blue: 0.18, alpha: 1)

final class KeyPanel: NSPanel {
    override var canBecomeKey: Bool { true }
}

final class ClickView: NSView {
    var onClick: (() -> Void)?
    var onRightClick: ((NSEvent) -> Void)?
    override func mouseDown(with e: NSEvent) {
        // ドラッグで移動。動かなかったらクリックとして扱う（performDrag は mouseUp まで戻らない）
        let before = window?.frame.origin ?? .zero
        window?.performDrag(with: e)
        let after = window?.frame.origin ?? .zero
        if abs(after.x - before.x) < 3 && abs(after.y - before.y) < 3 { onClick?() }
    }
    override func rightMouseDown(with e: NSEvent) { onRightClick?(e) }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

final class RowView: NSView {
    var action: (() -> Void)?
    override func mouseDown(with e: NSEvent) { }   // 親（ドラッグ）に渡さない
    override func mouseUp(with e: NSEvent) { action?() }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .pointingHand) }
}

final class InputField: NSTextField {
    var onFocus: (() -> Void)?
    override func mouseDown(with e: NSEvent) { onFocus?(); super.mouseDown(with: e) }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

final class Widget: NSObject, NSTextFieldDelegate {
    let W: CGFloat = 320, VIDEO_H: CGFloat = 270, TAB_H: CGFloat = 30, LIST_H: CGFloat = 150, INPUT_H: CGFloat = 46
    var H: CGFloat { VIDEO_H + TAB_H + LIST_H + INPUT_H }
    var window: KeyPanel!
    var player: AVQueuePlayer!
    var looper: AVPlayerLooper?
    var bubble: NSTextField!
    var bubbleBox: NSView!
    var badge: NSTextField!
    var listStack: NSStackView!
    var tabs: NSSegmentedControl!
    var input: InputField!
    var mic: NSButton!
    var currentClip = ""
    var tab = 0   // 0=待ち 1=ネタ
    var onOpen: ((WaitItem) -> Void)?
    var onIdea: ((Idea) -> Void)?
    var onMenu: (() -> Void)?
    var onTapMirei: (() -> Void)?
    var onSend: ((String) -> Void)?
    var onMic: (() -> Void)?
    var lastItems: [WaitItem] = []
    var lastIdeas = Ideas()

    func build() {
        let saved = UserDefaults.standard.string(forKey: "origin").map { NSPointFromString($0) }
        let scr = NSScreen.main!.visibleFrame
        let origin = saved ?? NSPoint(x: scr.maxX - W - 24, y: scr.maxY - H - 24)
        window = KeyPanel(contentRect: NSRect(origin: origin, size: NSSize(width: W, height: H)),
                          styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.hidesOnDeactivate = false
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenNone]
        setDesktopLevel(true)

        let root = ClickView(frame: NSRect(x: 0, y: 0, width: W, height: H))
        root.wantsLayer = true
        root.layer?.cornerRadius = 26
        root.layer?.masksToBounds = true
        root.layer?.backgroundColor = NSColor(calibratedWhite: 0.62, alpha: 1).cgColor
        root.onClick = { [weak self] in self?.onTapMirei?() }
        root.onRightClick = { [weak self] _ in self?.onMenu?() }
        window.contentView = root

        let lowerH = TAB_H + LIST_H + INPUT_H

        // ミレイの動画（上）
        player = AVQueuePlayer()
        player.isMuted = true
        let vl = AVPlayerLayer(player: player)
        vl.videoGravity = .resizeAspectFill
        vl.frame = NSRect(x: 0, y: lowerH - 20, width: W, height: VIDEO_H + 20)
        root.layer?.addSublayer(vl)
        play("idle")

        // 件数バッジ（右上）
        badge = NSTextField(labelWithString: "0")
        badge.font = .systemFont(ofSize: 22, weight: .heavy)
        badge.alignment = .center
        badge.textColor = .black
        badge.drawsBackground = true
        badge.backgroundColor = yellow
        badge.wantsLayer = true
        badge.layer?.cornerRadius = 22
        badge.layer?.masksToBounds = true
        badge.frame = NSRect(x: W - 58, y: H - 58, width: 44, height: 44)
        root.addSubview(badge)

        // 吹き出し（動画の下寄り）
        bubbleBox = NSView(frame: NSRect(x: 12, y: lowerH + 8, width: W - 24, height: 86))
        bubbleBox.wantsLayer = true
        bubbleBox.layer?.backgroundColor = NSColor(calibratedWhite: 1, alpha: 0.93).cgColor
        bubbleBox.layer?.cornerRadius = 16
        bubbleBox.layer?.borderColor = yellow.cgColor
        bubbleBox.layer?.borderWidth = 3
        bubble = NSTextField(wrappingLabelWithString: "")
        bubble.font = .systemFont(ofSize: 13.5, weight: .bold)
        bubble.textColor = NSColor(calibratedWhite: 0.1, alpha: 1)
        bubble.frame = NSRect(x: 12, y: 6, width: W - 48, height: 74)
        bubbleBox.addSubview(bubble)
        bubbleBox.isHidden = true
        root.addSubview(bubbleBox)

        // 下半分（すりガラス）
        let glass = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: W, height: lowerH))
        glass.material = .hudWindow
        glass.blendingMode = .withinWindow
        glass.state = .active
        root.addSubview(glass)

        tabs = NSSegmentedControl(labels: ["あなた待ち", "今日のネタ"], trackingMode: .selectOne,
                                  target: self, action: #selector(tabChanged))
        tabs.selectedSegment = 0
        tabs.frame = NSRect(x: 12, y: lowerH - TAB_H + 2, width: W - 24, height: 24)
        glass.addSubview(tabs)

        listStack = NSStackView(frame: NSRect(x: 10, y: INPUT_H + 4, width: W - 20, height: LIST_H - 8))
        listStack.orientation = .vertical
        listStack.alignment = .leading
        listStack.spacing = 4
        listStack.distribution = .gravityAreas
        glass.addSubview(listStack)

        // 指示の入力欄＋マイク
        input = InputField(frame: NSRect(x: 12, y: 10, width: W - 70, height: 26))
        input.placeholderString = "ミレイに指示（Enterで送る）"
        input.font = .systemFont(ofSize: 13)
        input.bezelStyle = .roundedBezel
        input.focusRingType = .none
        input.delegate = self
        input.target = self
        input.action = #selector(send)
        input.onFocus = { [weak self] in
            NSApp.activate(ignoringOtherApps: true)
            self?.window.makeKey()
        }
        glass.addSubview(input)

        mic = NSButton(title: "🎤", target: self, action: #selector(micTapped))
        mic.bezelStyle = .rounded
        mic.font = .systemFont(ofSize: 16)
        mic.frame = NSRect(x: W - 54, y: 7, width: 44, height: 32)
        mic.toolTip = "押して話す（もう一度押すと止める）"
        glass.addSubview(mic)

        window.orderFrontRegardless()
        NotificationCenter.default.addObserver(forName: NSWindow.didMoveNotification, object: window, queue: .main) { [weak self] _ in
            guard let o = self?.window.frame.origin else { return }
            UserDefaults.standard.set(NSStringFromPoint(o), forKey: "origin")
        }
    }

    @objc func tabChanged() { tab = tabs.selectedSegment; redraw() }
    func setTab(_ t: Int) { tab = t; tabs.selectedSegment = t; redraw() }
    @objc func send() {
        let t = input.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        input.stringValue = ""
        onSend?(t)
    }
    @objc func micTapped() { onMic?() }
    func setListening(_ on: Bool) {
        mic.title = on ? "⏹" : "🎤"
        if on { input.placeholderString = "聞いてるわ…" } else { input.placeholderString = "ミレイに指示（Enterで送る）" }
    }

    func setDesktopLevel(_ desktop: Bool) {
        // デスクトップ（壁紙とアイコンの上、ふつうのウインドウの下）＝ウィジェットと同じ高さ
        window.level = desktop ? NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.desktopIconWindow)) + 1) : .floating
    }

    func clipURL(_ name: String) -> URL { Bundle.main.resourceURL!.appendingPathComponent("clips/\(name).mp4") }

    func play(_ name: String) {
        guard name != currentClip, fm.fileExists(atPath: clipURL(name).path) else { return }
        currentClip = name
        player.removeAllItems()
        looper = AVPlayerLooper(player: player, templateItem: AVPlayerItem(url: clipURL(name)))
        player.play()
    }

    var bubbleToken = UUID()
    func say(_ text: String, seconds: Double = 10) {
        guard !text.isEmpty else { return }
        bubble.stringValue = text
        bubbleBox.isHidden = false
        let token = UUID(); bubbleToken = token
        DispatchQueue.main.asyncAfter(deadline: .now() + max(seconds, Double(text.count) * 0.18)) { [weak self] in
            if self?.bubbleToken == token { self?.bubbleBox.isHidden = true }
        }
    }

    func row(_ text: String, tip: String, strong: Bool, alert: Bool = false, action: @escaping () -> Void) -> NSView {
        let row = RowView(frame: NSRect(x: 0, y: 0, width: W - 20, height: 26))
        row.wantsLayer = true
        row.layer?.cornerRadius = 8
        row.layer?.backgroundColor = alert ? NSColor(calibratedRed: 0.85, green: 0.15, blue: 0.15, alpha: 0.55).cgColor
                                           : NSColor(calibratedWhite: 1, alpha: strong ? 0.16 : 0.08).cgColor
        let t = NSTextField(labelWithString: text)
        t.font = .systemFont(ofSize: 12, weight: .semibold)
        t.textColor = .white
        t.lineBreakMode = .byTruncatingTail
        t.frame = NSRect(x: 8, y: 4, width: W - 36, height: 18)
        row.addSubview(t)
        row.toolTip = tip
        row.action = action
        row.translatesAutoresizingMaskIntoConstraints = false
        row.widthAnchor.constraint(equalToConstant: W - 20).isActive = true
        row.heightAnchor.constraint(equalToConstant: 26).isActive = true
        return row
    }
    func note(_ s: String) -> NSView {
        let t = NSTextField(labelWithString: s)
        t.font = .systemFont(ofSize: 11)
        t.textColor = NSColor(calibratedWhite: 1, alpha: 0.75)
        t.lineBreakMode = .byTruncatingTail
        t.translatesAutoresizingMaskIntoConstraints = false
        t.widthAnchor.constraint(equalToConstant: W - 24).isActive = true
        return t
    }

    func show(_ items: [WaitItem], _ ideas: Ideas) {
        lastItems = items; lastIdeas = ideas
        badge.stringValue = "\(items.count)"
        badge.backgroundColor = items.isEmpty ? NSColor(calibratedWhite: 0.85, alpha: 1) : yellow
        tabs.setLabel(items.isEmpty ? "あなた待ち なし" : "あなた待ち \(items.count)件", forSegment: 0)
        redraw()
        play(items.isEmpty ? "happy" : (items.count >= 4 || items.contains { $0.overdue } ? "arms" : "idle"))
    }

    func redraw() {
        listStack.arrangedSubviews.forEach { $0.removeFromSuperview() }
        if tab == 0 {
            if lastItems.isEmpty { listStack.addArrangedSubview(note("　いまIKさん待ちはないわ。")) }
            for it in lastItems.prefix(4) {
                let dot = it.overdue ? "⚠" : (it.kind == "permission" ? "●" : "○")
                let copy = it.reply.isEmpty ? "" : "　📋"
                listStack.addArrangedSubview(row("\(dot) [\(it.project)] \(it.title)\(copy)",
                    tip: "\(it.label)：\(it.ask)\(it.reply.isEmpty ? "" : "\n押すと「\(it.reply)」をコピーして開く")\(it.host.isEmpty ? "" : "（\(it.host)）")",
                    strong: it.kind == "permission", alert: it.overdue) { [weak self] in self?.onOpen?(it) })
            }
            if lastItems.count > 4 { listStack.addArrangedSubview(note("　ほか \(lastItems.count - 4) 件（右クリックで全部）")) }
        } else {
            let id = lastIdeas
            if id.list.isEmpty { listStack.addArrangedSubview(note("　今日のネタはまだ。毎朝7時すぎに届くわ。")) }
            for i in id.list.prefix(3) {
                listStack.addArrangedSubview(row("[\(i.channel)] \(i.title)", tip: "\(i.why)（検索語：\(i.keyword)・\(i.format)）",
                                                 strong: true) { [weak self] in self?.onIdea?(i) })
            }
            if !id.top.isEmpty { listStack.addArrangedSubview(note("　伸びてる検索：" + id.top.prefix(6).joined(separator: "・"))) }
        }
    }
}

// MARK: - 本体

final class App: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let widget = Widget()
    let voice = Voice()
    let listener = Listener()
    let brain = Brain()
    var status: NSStatusItem!
    var items: [WaitItem] = []
    var ideas = Ideas()
    var known = Set<String>()
    var first = true
    var lastNag = Date()
    var nagMinutes: Double { let v = UserDefaults.standard.double(forKey: "nagMinutes"); return v > 0 ? v : 60 }

    func applicationDidFinishLaunching(_ n: Notification) {
        ensureDir(sharedInbox); ensureDir(localInbox)
        widget.build()
        widget.onOpen = { [weak self] it in self?.open(it) }
        widget.onIdea = { [weak self] i in self?.talk("\(i.channel)なら「\(i.title)」。\(i.why)") }
        widget.onMenu = { [weak self] in self?.popMenu() }
        widget.onTapMirei = { [weak self] in self?.tapMirei() }
        widget.onSend = { [weak self] t in self?.instruct(t) }
        widget.onMic = { [weak self] in self?.toggleMic() }

        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        status.button?.title = "ミ 0"
        status.menu = NSMenu()
        status.menu?.delegate = self

        refresh()
        let hour = Calendar.current.component(.hour, from: Date())
        if hour >= 5 && hour < 11 { say("hello") }
        Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in self?.refresh() }
    }

    // 決まったセリフ
    func say(_ key: String) { voice.playFixed(key); widget.say(Voice.text[key] ?? "") }
    // 自由なセリフ（VOICEVOX があれば声、無ければ吹き出しだけ）
    func talk(_ text: String) { voice.speak(text); widget.say(text) }

    func refresh() {
        pullLocalDrops()
        let now = loadItems()
        let newIdeas = Ideas.load()
        let added = now.filter { !known.contains($0.id) }
        let wasEmpty = items.isEmpty
        let ideasChanged = newIdeas.date != ideas.date && !newIdeas.date.isEmpty
        items = now; ideas = newIdeas
        widget.show(items, ideas)
        status.button?.title = items.isEmpty ? "ミ ✓" : "ミ \(items.count)"
        if !first {
            if let p = added.first(where: { $0.kind == "permission" }) {
                say("perm"); notify("許可待ち：\(p.project)", p.title)
            } else if let a = added.first {
                say("new"); notify("あなた待ち：\(a.project)", "\(a.title)\n\(a.ask)")
            } else if items.isEmpty && !wasEmpty {
                say("zero")
            }
            if !added.isEmpty { lastNag = Date() }
            if ideasChanged, let i = ideas.list.first {
                talk("今日のネタ、届いたわよ。\(i.channel)なら「\(i.title)」がおすすめ。")
                notify("今日のネタ", ideas.list.map { "[\($0.channel)] \($0.title)" }.joined(separator: "\n"))
            }
        }
        // ほったらかしにしていると、間をあけて件数を教える
        if !items.isEmpty && Date().timeIntervalSince(lastNag) > nagMinutes * 60 {
            lastNag = Date()
            if let o = items.first(where: { $0.overdue }) {
                say("late"); widget.say("1日以上待たせてる子がいるわよ。[\(o.project)] \(o.title)。…私より先に、あの子を見てあげて。")
            } else { say(Voice.countLine(items.count)) }
        }
        known = Set(now.map { $0.id })
        first = false
    }

    func tapMirei() {
        if widget.tab == 1, let i = ideas.list.first { talk("今日のおすすめは、\(i.channel)の「\(i.title)」。") }
        else { say(Voice.countLine(items.count)) }
    }

    // MARK: 指示

    func context() -> [String: Any] {
        let f = DateFormatter(); f.locale = Locale(identifier: "ja_JP"); f.dateFormat = "yyyy/MM/dd(E) HH:mm"
        return [
            "now": f.string(from: Date()),
            "mac": hostName,
            "waiting": items.enumerated().map { ["index": $0.offset].merging($0.element.dict) { a, _ in a } },
            "today_ideas": ideas.list.map { ["channel": $0.channel, "title": $0.title, "why": $0.why, "keyword": $0.keyword] },
            "rising_searches": ideas.top,
        ]
    }

    func instruct(_ text: String) {
        // すぐできることは自分でやる
        if text.contains("黙") || text.contains("静かに") { voice.muteUntil = Date().addingTimeInterval(3600); widget.say("…わかった。1時間だまってるわ。"); return }
        if text == "ネタ" || text.contains("今日のネタ") && text.count < 10 { widget.setTab(1); tapMirei(); return }
        widget.say("考えてるわ…", seconds: 60)
        widget.play("idle")
        brain.ask(text, context: context()) { [weak self] reply, actions in
            guard let self = self else { return }
            self.talk(reply)
            for a in actions { self.perform(a) }
        }
    }

    func perform(_ a: [String: Any]) {
        switch a["type"] as? String ?? "" {
        case "open":
            if let i = a["index"] as? Int, i >= 0, i < items.count { open(items[i]) }
        case "tab":
            widget.setTab((a["name"] as? String ?? "") == "ネタ" ? 1 : 0)
        case "mute":
            voice.muteUntil = Date().addingTimeInterval(Double(a["minutes"] as? Int ?? 60) * 60)
        case "remind":
            let m = Double(a["minutes"] as? Int ?? 30)
            let t = a["text"] as? String ?? "時間よ。"
            DispatchQueue.main.asyncAfter(deadline: .now() + m * 60) { [weak self] in
                self?.talk("IKさん、\(t)"); self?.notify("リマインド", t)
            }
        default: break
        }
    }

    func toggleMic() {
        if listener.running { listener.stop(); widget.setListening(false); return }
        widget.setListening(true)
        voice.player?.stop()
        listener.start(partial: { [weak self] s in self?.widget.input.stringValue = s }) { [weak self] s in
            guard let self = self else { return }
            self.widget.setListening(false)
            let t = s.trimmingCharacters(in: .whitespaces)
            self.widget.input.stringValue = ""
            if t.isEmpty { self.widget.say("…聞こえなかったわ。もう一回？") } else { self.instruct(t) }
        }
    }

    // MARK: 開く・通知・メニュー

    func open(_ it: WaitItem) {
        if !it.reply.isEmpty {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(it.reply, forType: .string)
            widget.say("返事の「\(it.reply)」をコピーしたわ。開いたら貼って送るだけよ。")
        }
        if let u = URL(string: it.url), !it.url.isEmpty {
            NSWorkspace.shared.open(u)
        } else {
            // Mac の許可待ち → Claude アプリ（なければターミナル）を前に出す
            for id in ["com.anthropic.claudefordesktop", "com.apple.Terminal", "com.googlecode.iterm2"] {
                if let app = NSWorkspace.shared.urlForApplication(withBundleIdentifier: id) {
                    NSWorkspace.shared.openApplication(at: app, configuration: .init()); break
                }
            }
        }
        if it.id.hasPrefix("test_") { try? fm.removeItem(at: sharedInbox.appendingPathComponent("\(it.id).json")) }
    }

    func notify(_ title: String, _ body: String) {
        let esc: (String) -> String = { $0.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"") }
        NSAppleScript(source: "display notification \"\(esc(body))\" with title \"ミレイ秘書\" subtitle \"\(esc(title))\"")?.executeAndReturnError(nil)
    }

    func buildMenu(_ m: NSMenu) {
        m.removeAllItems()
        if items.isEmpty { m.addItem(withTitle: "あなた待ちはありません", action: nil, keyEquivalent: "") }
        for (i, it) in items.enumerated() {
            let mi = NSMenuItem(title: "\(it.kind == "permission" ? "●" : "○") [\(it.project)] \(it.title) — \(it.ask)",
                                action: #selector(menuOpen(_:)), keyEquivalent: "")
            mi.tag = i; mi.target = self; mi.toolTip = it.host
            m.addItem(mi)
        }
        if !ideas.list.isEmpty {
            m.addItem(.separator())
            m.addItem(withTitle: "今日のネタ", action: nil, keyEquivalent: "")
            for i in ideas.list { m.addItem(withTitle: "　[\(i.channel)] \(i.title)", action: nil, keyEquivalent: "") }
        }
        m.addItem(.separator())
        let front = NSMenuItem(title: "いつも手前に出す", action: #selector(toggleFront(_:)), keyEquivalent: "")
        front.target = self; front.state = UserDefaults.standard.bool(forKey: "front") ? .on : .off
        m.addItem(front)
        let mute = NSMenuItem(title: voice.muted ? "声を戻す" : "1時間だまる", action: #selector(toggleMute), keyEquivalent: "")
        mute.target = self; m.addItem(mute)
        let inbox = NSMenuItem(title: "受け箱のフォルダを開く", action: #selector(openInbox), keyEquivalent: "")
        inbox.target = self; m.addItem(inbox)
        m.addItem(NSMenuItem(title: "ミレイ秘書を終了", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
    }
    func menuNeedsUpdate(_ menu: NSMenu) { buildMenu(menu) }

    func popMenu() {
        let m = NSMenu(); buildMenu(m)
        m.popUp(positioning: nil, at: NSPoint(x: 20, y: widget.H - widget.VIDEO_H), in: widget.window.contentView!)
    }

    @objc func menuOpen(_ s: NSMenuItem) { if s.tag < items.count { open(items[s.tag]) } }
    @objc func toggleFront(_ s: NSMenuItem) {
        let v = !UserDefaults.standard.bool(forKey: "front")
        UserDefaults.standard.set(v, forKey: "front")
        widget.setDesktopLevel(!v)
    }
    @objc func toggleMute() { voice.muteUntil = voice.muted ? .distantPast : Date().addingTimeInterval(3600) }
    @objc func openInbox() { NSWorkspace.shared.open(sharedInbox) }
}

// MARK: - 入口

let args = CommandLine.arguments
switch args.count > 1 ? args[1] : "" {
case "hook": runHook()
case "install-hooks": editHooks(add: true); exit(0)
case "uninstall-hooks": editHooks(add: false); exit(0)
case "test": addTestItem(); exit(0)
case "inbox": print(sharedInbox.path); exit(0)
default:
    let app = NSApplication.shared
    let delegate = App()
    app.delegate = delegate
    app.setActivationPolicy(.accessory)   // Dock に出さない常駐
    if UserDefaults.standard.bool(forKey: "front") { DispatchQueue.main.async { delegate.widget.setDesktopLevel(false) } }
    app.run()
}
