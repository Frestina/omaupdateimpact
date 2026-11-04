import QtQuick
import Quickshell
import Quickshell.Io
import "State.js" as State

// The only part of the plugin that runs the command. The shell loads one service
// however many monitors there are, so a check runs once, not once per bar.
//
// It runs the bundled bin/omaupdateimpact with --json, never one on PATH, and keeps
// the last result in memory, with each newer release's report checked in the panel,
// by its tag, until the shell restarts.
// It writes nothing itself: "Mark reviewed" runs the command with --ack, which writes
// the reviewed file. The command decides every finding; State.js only reads what it
// printed.
Item {
  id: root

  // Injected by the shell after it creates the service.
  property string omarchyPath: ""
  property var shell: null
  property var manifest: null

  // The command beside this folder, found from this file's own path.
  readonly property string command: decodeURIComponent(
    Qt.resolvedUrl("../bin/omaupdateimpact").toString().replace(/^file:\/\//, ""))

  // The user's own result, the newer releases' reports checked in the panel, the one
  // it shows, and the run going. See State.js. The bar reads only the user's own.
  property var held: State.held(false)
  readonly property var view: State.bar(held).view
  readonly property bool running: held.job !== null
  // A run for the user's own release, so the bar's tooltip says "Checking…".
  readonly property bool barRunning: State.bar(held).running
  // What the panel shows: a chosen report while it shows one, else the user's own.
  readonly property var panel: State.panel(held)
  // Where --ack keeps reviews, for the panel to name.
  readonly property string reviewedFile: State.reviewedFile(Quickshell.env("XDG_CONFIG_HOME"))
  // Whether omarchy-agent-prompt is on PATH, so "Ask agent" can show. Looked up once.
  property bool agentReady: false

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
    held = State.waiting(held, hours === 0)
    schedule()
  }

  // Check the user's own release now. A check already running isn't started twice.
  function check() {
    if (start(State.startCheck(held))) lastStartedAt = Date.now()
    schedule()
  }

  // A newer release's report, for the panel only. It never changes the bar.
  function checkRelease(tag, cached) {
    start(State.startChosen(held, tag, cached))
  }

  // "Show": a kept report on a newer release, with nothing run.
  function show(tag) {
    held = State.show(held, tag)
  }

  // Mark one finding reviewed, for the report the panel shows. The panel asks first.
  // A run already going isn't started twice.
  function ack(id) {
    start(State.startAck(held, id))
  }

  // Back to the user's own result, from "Back" or a closed panel. Chosen reports are
  // kept, and a run on one goes on.
  function back() {
    held = State.back(held)
  }

  // Runs the bundled command with the step's arguments, if it has any.
  function start(next) {
    held = next.held
    if (next.args === null) return false
    procStarted = false
    procExitCode = -1
    proc.command = [root.command].concat(next.args)
    proc.running = true
    return true
  }

  function finish() {
    held = State.finished(held, {
      started: procStarted,
      exitCode: procExitCode,
      stdout: out.text,
      stderr: errOut.text
    }, Date.now())
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
