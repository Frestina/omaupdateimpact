pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Ui
import "State.js" as State

// The bar icon and its panel. It runs nothing itself: the service checks, and this
// shows the service's view. Each monitor has its own copy; they share the service.
//
// Left click opens the panel. Its buttons check again, and open a report in a
// terminal: the user's own release, or a newer one on another channel. "Mark
// reviewed" asks first, then has the service run the command with --ack. "Ask agent"
// hands a finding, or the whole report, to the user's own coding agent. The only
// other thing it changes is its own setting, how often it checks, when one is chosen.
Panel {
  id: root
  moduleName: "io.github.frestina.omaupdateimpact"
  // The service answers IPC on the plugin's id, so the widget takes none.
  ipcTarget: ""

  // The bar's facade and the shell's style groups, read untyped: their members
  // differ between bars and Omarchy versions, and each is checked before use.
  readonly property var host: root.bar
  readonly property var fonts: Style.font
  readonly property var service: root.host && root.host.shell && typeof root.host.shell.serviceFor === "function"
    ? root.host.shell.serviceFor(root.moduleName) : null
  // Without a service nothing runs the command, and that is shown, never hidden.
  readonly property var view: root.service && root.service.view ? root.service.view : State.noService()
  readonly property bool running: !!root.service && root.service.running === true
  readonly property int checkEveryHours: State.hoursFrom(root.setting("checkEveryHours", State.DEFAULT_HOURS))

  // Theme roles: text, muted text and the warning colour. Muted text is the text
  // colour faded, as the shell fades its own quiet widgets: the theme's muted
  // colour is too dark to read on some popups, such as nord's and matte-black's.
  readonly property color foreground: root.host ? root.host.foreground : Color.foreground
  readonly property color muted: Util.alpha(root.foreground, 0.6)
  readonly property color warning: root.host ? root.host.urgent : Color.urgent
  readonly property string fontFamily: root.host ? root.host.fontFamily : root.fonts.family
  readonly property bool vertical: root.host ? root.host.vertical === true : false

  readonly property var barStyle: Style.bar
  readonly property real barIconSlot: root.barStyle.iconSlot
  property bool notesOpen: false
  // The id of the finding whose "Mark reviewed?" is open, or "".
  property string confirming: ""
  // "Ask agent" shows only when omarchy-agent-prompt is on PATH.
  readonly property bool agentReady: !!root.service && root.service.agentReady === true
  readonly property string ackProblem: root.service && typeof root.service.ackProblem === "string"
    ? root.service.ackProblem : ""

  readonly property string glyph: "󰚰"
  readonly property string tooltipText: root.view.tooltip + (root.running && root.view.state !== "notChecked" ? "\nChecking…" : "")

  // Every monitor's copy hands the same setting over, so the service sees it once.
  function handOver() {
    if (root.service && typeof root.service.setCheckEveryHours === "function")
      root.service.setCheckEveryHours(root.checkEveryHours)
  }
  onServiceChanged: handOver()
  onCheckEveryHoursChanged: handOver()

  function checkAgain() {
    if (root.service && typeof root.service.check === "function") root.service.check()
  }

  // The same bundled command, in the launcher Omarchy's update row uses. With a tag,
  // the report on that release. It only opens a terminal: the service's state, and so
  // the bar, stay on the user's own channel.
  function openReport(args) {
    if (!root.host) return
    var command = root.service ? root.service.command : ""
    if (command === "") return
    root.close()
    root.host.run(State.terminalLine(command, args || []))
  }

  // The finding was seen and accepted: the service runs --ack for it, and its
  // document replaces the last result. Only after Yes on "Mark reviewed?".
  function markReviewed(id) {
    root.confirming = ""
    if (root.service && typeof root.service.ack === "function") root.service.ack(id)
  }

  // One finding, or the whole report when finding is null, to the user's own agent.
  // The prompt is one argument, so no shell reads its text. See State.agentPrompt.
  function askAgent(finding) {
    if (!root.agentReady) return
    root.close()
    Util.execArgv(State.agentCommand(State.agentPrompt(root.view, finding, root.service.command)))
  }

  // Saves the choice on the widget's own entry in shell.json, as the clock panel saves
  // its own. Applied here first so the choice shows on the click; the write comes back
  // through the bar as the same value, and every copy hands it to the service.
  function setCheckEvery(value) {
    var hours = State.hoursFrom(value)
    if (hours === root.checkEveryHours) return
    var entry = State.withSetting(root.settings, root.moduleName, "checkEveryHours", hours)
    root.settings = entry
    var shell = root.host ? root.host.shell : null
    if (shell && typeof shell.updateEntryInline === "function") shell.updateEntryInline(root.moduleName, entry)
  }

  function checkedText() {
    var at = root.service ? root.service.checkedAt : null
    if (!at) return ""
    var today = new Date().toDateString() === at.toDateString()
    return "checked " + (today ? Qt.formatTime(at, "HH:mm") : Qt.formatDateTime(at, "d MMM, HH:mm"))
  }

  function headerLine() {
    var parts = []
    if (root.view.installed !== "") parts.push("installed " + root.view.installed)
    if (root.view.channel !== "") parts.push(root.view.channel + " channel")
    var checked = root.checkedText()
    if (checked !== "") parts.push(checked)
    if (root.running) parts.push("checking…")
    return parts.join(" · ")
  }

  function iconColour(role) {
    if (role === "warning") return root.warning
    var text = root.host ? root.host.barForeground : Color.foreground
    return role === "text" ? text : Util.alpha(text, 0.45)
  }

  onOpenedChanged: if (!opened) {
    notesOpen = false
    confirming = ""
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    // Horizontal bars show the mark beside the icon; vertical ones under it, as a badge.
    text: root.view.mark !== "" && !root.vertical ? root.glyph + " " + root.view.mark : root.glyph
    slotSize: root.barIconSlot * (root.view.mark.length > 0 && !root.vertical ? 1.3 + 0.3 * root.view.mark.length : 1)
    foreground: root.iconColour(root.view.colour)
    useActiveColor: false
    tooltipText: root.opened ? "" : root.tooltipText
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.LeftButton) root.toggle()
    }

    Text {
      visible: root.vertical && root.view.mark !== ""
      anchors.right: parent.right
      anchors.bottom: parent.bottom
      textFormat: Text.PlainText
      text: root.view.mark
      color: root.iconColour(root.view.colour)
      font.family: root.fontFamily
      font.pixelSize: root.fonts.caption
      font.bold: true
    }
  }

  // Selectable text, so a fix or an id can be copied. Plain text always.
  component Selectable: TextEdit {
    width: parent ? parent.width : implicitWidth
    readOnly: true
    selectByMouse: true
    textFormat: TextEdit.PlainText
    wrapMode: TextEdit.Wrap
    color: root.foreground
    selectionColor: Style.selectionFill
    selectedTextColor: root.foreground
    font.family: root.fontFamily
    font.pixelSize: root.fonts.bodySmall
  }

  component Heading: PanelSectionHeader {
    foreground: root.foreground
    fontFamily: root.fontFamily
  }

  // "Ask agent" for one finding, or for the whole report when finding is null.
  component AgentButton: Button {
    id: agentButton
    property var about: null
    visible: root.agentReady
    iconText: "󰚩"
    text: "Ask agent"
    tooltipText: agentButton.about ? "Ask your coding agent about this finding" : "Ask your coding agent about the report"
    foreground: root.foreground
    fontFamily: root.fontFamily
    fontSize: root.fonts.bodySmall
    onClicked: root.askAgent(agentButton.about)
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(420))
    contentHeight: panel.fittedContentHeight(body.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onMoveRequested: function(dx, dy) {
        if (dy !== 0) flick.contentY = Math.max(0, Math.min(flick.contentY + dy * Style.space(48),
                                                            flick.contentHeight - flick.height))
      }
      onTextKey: function(t) {
        if (t === "r" || t === "R") root.checkAgain()
      }

      Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: body.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: body
          width: flick.width
          spacing: Style.space(10)

          // ---------- What was compared, and when ----------
          Row {
            width: parent.width
            spacing: Style.space(12)

            Text {
              id: heroGlyph
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: root.glyph
              color: root.iconColour(root.view.colour)
              font.family: root.fontFamily
              font.pixelSize: root.fonts.display
            }

            Column {
              width: parent.width - heroGlyph.width - parent.spacing
              spacing: Style.space(2)

              Text {
                width: parent.width
                textFormat: Text.PlainText
                text: root.view.summary
                wrapMode: Text.Wrap
                color: root.view.colour === "warning" ? root.warning : root.foreground
                font.family: root.fontFamily
                font.pixelSize: root.fonts.title
                font.bold: true
              }

              Text {
                width: parent.width
                visible: text !== ""
                textFormat: Text.PlainText
                text: root.headerLine()
                wrapMode: Text.Wrap
                color: root.muted
                font.family: root.fontFamily
                font.pixelSize: root.fonts.caption
              }
            }
          }

          Row {
            spacing: Style.space(6)

            Button {
              iconText: "󰑐"
              text: root.running ? "Checking…" : "Check again"
              tooltipText: "Compare with the release now (r)"
              enabled: !!root.service && !root.running
              iconSpinning: root.running
              foreground: root.foreground
              fontFamily: root.fontFamily
              fontSize: root.fonts.bodySmall
              onClicked: root.checkAgain()
            }

            Button {
              iconText: "󰆍"
              text: "Open report"
              tooltipText: "The full report in a terminal"
              enabled: !!root.service && !!root.bar
              foreground: root.foreground
              fontFamily: root.fontFamily
              fontSize: root.fonts.bodySmall
              onClicked: root.openReport()
            }

            AgentButton {
              visible: root.agentReady && root.view.hasReport
            }
          }

          // ---------- Why it couldn't check ----------
          Selectable {
            visible: root.view.problem !== ""
            text: root.view.problem
            font.pixelSize: root.fonts.body
          }

          // ---------- Up to date, and newer releases elsewhere ----------
          Repeater {
            model: root.view.newer
            delegate: Column {
              id: newer
              required property var modelData
              width: body.width
              spacing: Style.space(3)

              Row {
                width: parent.width
                spacing: Style.space(8)

                Button {
                  id: checkNewer
                  anchors.verticalCenter: parent.verticalCenter
                  iconText: "󰆍"
                  text: "Check"
                  tooltipText: "The report on " + newer.modelData.tag + " in a terminal"
                  enabled: !!root.service && !!root.bar
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  fontSize: root.fonts.bodySmall
                  onClicked: root.openReport([newer.modelData.tag])
                }

                Selectable {
                  anchors.verticalCenter: parent.verticalCenter
                  width: parent.width - checkNewer.width - parent.spacing
                  text: newer.modelData.line
                }
              }

              Selectable {
                text: newer.modelData.download
                color: root.muted
                font.pixelSize: root.fonts.caption
              }
            }
          }

          Selectable {
            visible: root.view.newerProblem !== ""
            text: root.view.newerProblem
            color: root.muted
          }

          // ---------- Needs attention, never collapsed ----------
          PanelSeparator { visible: root.view.attention.length > 0; foreground: root.foreground }
          Heading {
            visible: root.view.attention.length > 0
            text: "NEEDS ATTENTION"
          }

          // Why the last "Mark reviewed" wrote nothing. The last result stays.
          Selectable {
            visible: root.ackProblem !== ""
            text: root.ackProblem
          }

          Repeater {
            model: root.view.attention
            delegate: Column {
              id: finding
              required property var modelData
              width: body.width
              spacing: Style.space(3)

              Selectable {
                text: finding.modelData.title + (finding.modelData.detail ? " " + finding.modelData.detail : "")
                color: root.warning
                font.pixelSize: root.fonts.body
                font.bold: true
              }
              Selectable {
                visible: !!finding.modelData.reason
                text: finding.modelData.reason
                  ? "Why: " + finding.modelData.reason.text + " (" + finding.modelData.reason.reference + ")" : ""
              }
              Selectable {
                visible: finding.modelData.fix !== ""
                text: "Fix: " + finding.modelData.fix
              }
              Selectable {
                text: finding.modelData.evidence.join("\n") + "\n[" + finding.modelData.id + "]"
                color: root.muted
                font.pixelSize: root.fonts.caption
              }

              Row {
                visible: root.confirming !== finding.modelData.id
                spacing: Style.space(6)

                Button {
                  iconText: "󰄬"
                  text: "Mark reviewed"
                  tooltipText: "Seen it, and it's fine: it won't count for " + root.view.release + " again"
                  enabled: !!root.service && !root.running
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  fontSize: root.fonts.bodySmall
                  onClicked: root.confirming = finding.modelData.id
                }

                AgentButton { about: finding.modelData }
              }

              // In place, and nothing is written until Yes.
              Row {
                visible: root.confirming === finding.modelData.id
                spacing: Style.space(6)

                Text {
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  text: "Mark reviewed?"
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: root.fonts.bodySmall
                }

                Button {
                  text: "Yes"
                  tooltipText: "Run --ack " + finding.modelData.id + " for " + root.view.release
                  enabled: !!root.service && !root.running
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  fontSize: root.fonts.bodySmall
                  onClicked: root.markReviewed(finding.modelData.id)
                }

                Button {
                  text: "No"
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  fontSize: root.fonts.bodySmall
                  onClicked: root.confirming = ""
                }
              }
            }
          }

          // ---------- Couldn't check, never collapsed ----------
          PanelSeparator {
            visible: root.view.limits.length + root.view.unknowns.length > 0
            foreground: root.foreground
          }
          Heading {
            visible: root.view.limits.length + root.view.unknowns.length > 0
            text: "COULDN'T CHECK"
          }

          Repeater {
            model: root.view.limits
            delegate: Selectable {
              required property var modelData
              text: modelData.check + ": " + modelData.words
            }
          }

          Repeater {
            model: root.view.unknowns
            delegate: Column {
              id: unknown
              required property var modelData
              width: body.width
              spacing: Style.space(2)

              Selectable {
                text: unknown.modelData.title + (unknown.modelData.detail ? " " + unknown.modelData.detail : "")
              }
              Selectable {
                text: unknown.modelData.evidence.join("\n")
                color: root.muted
                font.pixelSize: root.fonts.caption
              }
              AgentButton { about: unknown.modelData }
            }
          }

          // ---------- Notes, collapsed ----------
          PanelSeparator { visible: root.view.notes.length > 0; foreground: root.foreground }
          Button {
            visible: root.view.notes.length > 0
            iconText: root.notesOpen ? "󰅀" : "󰅂"
            text: State.plural(root.view.notes.length, "note", "notes")
            tooltipText: root.notesOpen ? "Hide the notes" : "Show the notes"
            foreground: root.foreground
            fontFamily: root.fontFamily
            fontSize: root.fonts.bodySmall
            onClicked: root.notesOpen = !root.notesOpen
          }

          Repeater {
            model: root.notesOpen ? root.view.notes : []
            delegate: Column {
              id: note
              required property var modelData
              width: body.width
              spacing: Style.space(2)

              Selectable {
                text: note.modelData.title + (note.modelData.detail ? " " + note.modelData.detail : "")
              }
              Selectable {
                text: note.modelData.evidence.join("\n")
                color: root.muted
                font.pixelSize: root.fonts.caption
              }
              AgentButton { about: note.modelData }
            }
          }

          // ---------- Reviewed, a count, and the file that undoes one ----------
          Selectable {
            visible: root.view.reviewed > 0
            text: State.reviewedLine(root.view.reviewed,
              root.service ? root.service.reviewedFile : State.reviewedFile(""))
            color: root.muted
            font.pixelSize: root.fonts.caption
          }

          // ---------- How often it checks, the one setting ----------
          PanelSeparator { foreground: root.foreground }
          Text {
            width: parent.width
            textFormat: Text.PlainText
            text: "Check every"
            color: root.muted
            font.family: root.fontFamily
            font.pixelSize: root.fonts.caption
          }
          ButtonGroup {
            options: State.intervalChoices(root.checkEveryHours)
            value: String(root.checkEveryHours)
            focusable: false
            spacing: Style.space(4)
            foreground: root.foreground
            fontFamily: root.fontFamily
            fontSize: root.fonts.bodySmall
            onChanged: function(value) { root.setCheckEvery(value) }
          }
        }
      }
    }
  }
}
