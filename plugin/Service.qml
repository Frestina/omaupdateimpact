import QtQuick
import Quickshell
import Quickshell.Io
import "State.js" as State

// The only part of the plugin that runs the command. The shell loads one service
// however many monitors there are, so a check runs once, not once per bar.
//
// It runs the bundled bin/omaupdateimpact with --json, never one on PATH, and keeps
// the last result in memory. It writes nothing itself: "Mark reviewed" runs the
// command with --ack, which writes the reviewed file. The command decides every
// finding; State.js only reads what it printed.
Item {
  id: root

  // Injected by the shell after it creates the service.
  property string omarchyPath: ""
  property var shell: null
  property var manifest: null

  // The command beside this folder, found from this file's own path.
  readonly property string command: decodeURIComponent(
    Qt.resolvedUrl("../bin/omaupdateimpact").toString().replace(/^file:\/\//, ""))

  // What the bar and the panel show. See State.js.
  property var view: State.notChecked(false)
  property bool running: false
  // What the running process is for: "check", or "ack" for "Mark reviewed".
  property string runKind: "check"
  // Why the last "Mark reviewed" wrote nothing, or "".
  property string ackProblem: ""
  // Where --ack keeps reviews, for the panel to name.
  readonly property string reviewedFile: State.reviewedFile(Quickshell.env("XDG_CONFIG_HOME"))
  // Whether omarchy-agent-prompt is on PATH, so "Ask agent" can show. Looked up once.
  property bool agentReady: false
  // When the last check finished, or null before the first.
  property var checkedAt: null

  // Hours between checks, handed over by the widget. 0 checks only when asked.
  property int checkEveryHours: State.DEFAULT_HOURS
  readonly property real loadedAt: Date.now()
  // When the last check started, in ms, or 0 before the first.
  property real lastStartedAt: 0

  // Per run: a command that can't start only drops running, with no exit code.
  property bool procStarted: false
  property int procExitCode: -1

  // The widget's setting, kept to 0 or 1 to 168 hours. Anything else is the default.
  // A new value applies at once: the next check is due that long after the last began.
  function setCheckEveryHours(value) {
    var hours = State.hoursFrom(value)
    if (hours === checkEveryHours) return
    checkEveryHours = hours
    if (!running && !checkedAt) view = State.notChecked(hours === 0)
    schedule()
  }

  // Check now. A check already running isn't started twice.
  function check() {
    if (running) return
    lastStartedAt = Date.now()
    start("check", [root.command, "--json"])
    schedule()
  }

  // Mark one finding reviewed, for the release the bar shows. The panel asks first.
  // A run already going isn't started twice.
  function ack(id) {
    if (running || !view.release) return
    start("ack", [root.command].concat(State.ackArgs(id, view.release)))
  }

  function start(kind, command) {
    running = true
    runKind = kind
    procStarted = false
    procExitCode = -1
    proc.command = command
    proc.running = true
  }

  function finish() {
    running = false
    var run = {
      started: procStarted,
      exitCode: procExitCode,
      stdout: out.text,
      stderr: errOut.text
    }
    if (runKind === "ack") {
      // A failed --ack wrote nothing: the last result stays, with its reason.
      const after = State.afterAck(run, view)
      ackProblem = after.problem
      if (!after.kept) {
        view = after.view
        checkedAt = new Date()
      }
    } else {
      ackProblem = ""
      checkedAt = new Date()
      view = State.fromRun(run)
    }
    schedule()
  }

  // The next check: two minutes after loading, then every checkEveryHours after
  // the last one started. "Check again" starts the wait over.
  function schedule() {
    var due = State.nextCheckAt(checkEveryHours, lastStartedAt, loadedAt)
    if (due === null) {
      timer.stop()
      return
    }
    timer.interval = Math.max(1000, due - Date.now())
    timer.restart()
  }

  Component.onCompleted: {
    schedule()
    agentLookup.running = true
  }

  // command -v in a login shell, as the shell's execArgv starts the agent.
  Process {
    id: agentLookup
    command: State.AGENT_LOOKUP
    onExited: function(exitCode) { root.agentReady = exitCode === 0 }
  }

  Timer {
    id: timer
    repeat: false
    // A check still running when the time comes reschedules when it ends.
    onTriggered: if (!root.running) root.check()
  }

  // Both streams end and exited fires before running drops, so finish() sees
  // the whole of this run's output.
  Process {
    id: proc
    onStarted: root.procStarted = true
    onExited: function(exitCode) { root.procExitCode = exitCode }
    onRunningChanged: if (!running && root.running) root.finish()
    stdout: StdioCollector { id: out; waitForEnd: true }
    stderr: StdioCollector { id: errOut; waitForEnd: true }
  }

  // omarchy-shell io.github.frestina.omaupdateimpact check: the same as "Check again".
  IpcHandler {
    target: "io.github.frestina.omaupdateimpact"
    function check(): void { root.check() }
  }
}
