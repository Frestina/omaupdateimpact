pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Ui
import "State.js" as State

// The bar icon and its panel. It runs nothing itself: the service checks, and this
// shows the service's view. Each monitor has its own copy; they share the service.
//
// Left click opens the panel, always on the user's own result. Its buttons check
// again, open the report in a terminal, and check a newer release, whose report shows
// in the panel and is kept until the shell restarts. The bar follows only the user's
// own channel. Each finding starts closed, and a click anywhere on its title row opens
// it. Worth knowing lists its notes by group, each group closed. "Mark reviewed" has
// the service run the command with --ack at once, and "Undo" under Reviewed with
// --unack, as each undoes the other. "Ask agent" hands a finding, or the whole report,
// to the user's own coding agent. The only other thing it changes is its own setting,
// how often it checks, when one is chosen.
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
  // The bar shows the user's own result only, and the panel what the service says it
  // shows: a newer release's report while one is chosen.
  readonly property var shown: root.service && root.service.panel ? root.service.panel : null
  readonly property var barView: root.service && root.service.view ? root.service.view : State.noService()
  readonly property var view: root.shown ? root.shown.view : State.noService()
  // A run for the user's own release, for the bar; one for what the panel shows; any run.
  readonly property bool barRunning: !!root.service && root.service.barRunning === true
  readonly property bool running: !!root.shown && root.shown.running === true
  readonly property bool busy: !!root.shown && root.shown.busy === true
  // The tag of the release chosen by hand, or "" for the user's own.
  readonly property string chosen: root.shown ? root.shown.chosen : ""
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
  // Worth knowing's groups, as the document names them, with "Other" last.
  readonly property var noteGroups: State.noteGroups(root.view.notes)
  // The findings opened by a click on their title. Each starts closed, in every
  // section, and they close again with the panel or another report.
  property var openFindings: ({})
  // "Ask agent" shows only when omarchy-agent-prompt is on PATH.
  readonly property bool agentReady: !!root.service && root.service.agentReady === true
  readonly property string ackProblem: root.shown && typeof root.shown.ackProblem === "string"
    ? root.shown.ackProblem : ""
  readonly property string undoProblem: root.shown && typeof root.shown.undoProblem === "string"
    ? root.shown.undoProblem : ""

  readonly property string glyph: "󰚰"
  readonly property string tooltipText: root.barView.tooltip
    + (root.barRunning && root.barView.state !== "notChecked" ? "\nChecking…" : "")

  // Every monitor's copy hands the same setting over, so the service sees it once.
  function handOver() {
    if (root.service && typeof root.service.setCheckEveryHours === "function")
      root.service.setCheckEveryHours(root.checkEveryHours)
  }
  onServiceChanged: handOver()
  onCheckEveryHoursChanged: handOver()

  // The user's own release only. On a chosen report, "Back" takes its place, and r
  // does nothing.
  function checkAgain() {
    if (root.chosen !== "") return
    if (root.service && typeof root.service.check === "function") root.service.check()
  }

  // A newer release's report, here in the panel. The bar stays on the user's channel.
  function checkRelease(release) {
    if (root.service && typeof root.service.checkRelease === "function")
      root.service.checkRelease(release.tag, release.cached)
  }

  // A kept report on a newer release, or the run on it still going. Nothing runs.
  function showRelease(release) {
    if (root.service && typeof root.service.show === "function") root.service.show(release.tag)
  }

  // Back to the user's own result. Closing the panel does the same. Chosen reports are
  // kept, and a check of one goes on.
  function goBack() {
    if (root.service && typeof root.service.back === "function") root.service.back()
  }

  function isOpen(finding) {
    return State.isOpen(root.openFindings, finding)
  }

  function toggleFinding(finding) {
    root.openFindings = State.toggled(root.openFindings, finding)
  }

  // The same bundled command, in the launcher Omarchy's update row uses, on the
  // release the panel shows. It only opens a terminal. The line is made before the
  // panel closes, as closing goes back to the user's own result.
  function openReport() {
    if (!root.host) return
    var command = root.service ? root.service.command : ""
    if (command === "") return
    var line = State.terminalLine(command, root.chosen !== "" ? [root.chosen] : [])
    root.close()
    root.host.run(line)
  }

  // The finding was seen and accepted: the service runs --ack for it, and its
  // document replaces the last result. "Undo" takes it back, so nothing asks first.
  function markReviewed(id) {
    if (root.service && typeof root.service.ack === "function") root.service.ack(id)
  }

  // "Undo" under Reviewed: the service runs --unack for it, and the finding counts again.
  function undoReview(id) {
    if (root.service && typeof root.service.unack === "function") root.service.unack(id)
  }

  // One finding, or the whole report when finding is null, to the user's own agent.
  // The prompt is one argument, so no shell reads its text. See State.agentPrompt.
  // The prompt is made before the panel closes, as closing goes back to the user's own.
  function askAgent(finding) {
    if (!root.agentReady) return
    var argv = State.agentCommand(State.agentPrompt(root.view, finding, root.service.command, root.chosen))
    root.close()
    Util.execArgv(argv)
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
    if (!root.shown || root.shown.at === null) return ""
    var at = new Date(root.shown.at)
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
    openFindings = {}
    goBack()
  }
  // Another report: its findings start closed too.
  onChosenChanged: {
    notesOpen = false
    openFindings = {}
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    // Horizontal bars show the mark beside the icon; vertical ones under it, as a badge.
    // From Omarchy 4.5.0 the mark goes in labelText, as the battery's percentage
    // does: the shell fits all of text into one icon's box, so a mark there
    // would shrink the glyph with it. An older shell has no labelText and draws
    // text at its own size, so there the mark stays in text. Assigning
    // labelText where it does not exist would fail the whole icon, hence the
    // check.
    readonly property string sideMark: !root.vertical ? root.barView.mark : ""
    readonly property bool hasLabel: "labelText" in button
    text: sideMark !== "" && !hasLabel ? root.glyph + " " + sideMark : root.glyph
    Component.onCompleted: {
      if (hasLabel) button.labelText = Qt.binding(function() { return button.sideMark })
    }
    slotSize: root.barIconSlot * (sideMark !== "" ? 1.1 + 0.5 * sideMark.length : 1)
    foreground: root.iconColour(root.barView.colour)
    useActiveColor: false
    tooltipText: root.opened ? "" : root.tooltipText
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.LeftButton) root.toggle()
    }

    Text {
      visible: root.vertical && root.barView.mark !== ""
      anchors.right: parent.right
      anchors.bottom: parent.bottom
      textFormat: Text.PlainText
      text: root.barView.mark
      color: root.iconColour(root.barView.colour)
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

  // A row that opens: a finding's title, a group of notes, or Worth knowing. A click
  // anywhere on it opens it or closes it, and it lights up under the pointer with the
  // theme's hover colour. Its arrow sits on the right, in the text colour, a size
  // larger than the title, and turns down when it opens.
  component OpenRow: Item {
    id: openRow
    property string text: ""
    property bool opened: false
    property color colour: root.foreground
    property bool strong: false
    signal activated()
    readonly property real pad: Style.space(4)
    width: parent ? parent.width : implicitWidth
    implicitHeight: Math.max(arrow.implicitHeight, rowText.implicitHeight) + 2 * openRow.pad

    Rectangle {
      anchors.fill: parent
      radius: Style.cornerRadius
      color: rowMouse.containsMouse ? Style.hoverFillFor(root.foreground, Color.accent) : "transparent"
      Behavior on color { ColorAnimation { duration: 120 } }
    }

    Text {
      id: rowText
      x: openRow.pad
      width: arrow.x - x - Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: openRow.text
      wrapMode: Text.Wrap
      color: openRow.colour
      font.family: root.fontFamily
      font.pixelSize: root.fonts.body
      font.bold: openRow.strong
    }

    Text {
      id: arrow
      x: parent.width - width - openRow.pad
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: "󰅂"
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: root.fonts.title
      rotation: openRow.opened ? 90 : 0
      Behavior on rotation { NumberAnimation { duration: 120 } }
    }

    MouseArea {
      id: rowMouse
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: openRow.activated()
    }
  }

  // A finding's title. A click opens the rest of it, or closes it.
  component FindingTitle: OpenRow {
    id: findingTitle
    property var about: null
    text: findingTitle.about ? findingTitle.about.title : ""
    opened: root.isOpen(findingTitle.about)
    onActivated: root.toggleFinding(findingTitle.about)
  }

  // The rest of an open finding: its detail, its items one per line, why, fix,
  // evidence and id, all selectable.
  component FindingBody: Column {
    id: findingBody
    property var about: null
    readonly property var f: findingBody.about || ({})
    readonly property var items: Array.isArray(findingBody.f.items) ? findingBody.f.items : []
    width: parent ? parent.width : implicitWidth
    spacing: Style.space(3)

    Selectable {
      visible: !!findingBody.f.detail
      text: findingBody.f.detail || ""
    }
    Selectable {
      visible: findingBody.items.length > 0
      text: findingBody.items.join("\n")
    }
    Selectable {
      visible: !!findingBody.f.reason
      text: findingBody.f.reason
        ? "Why: " + findingBody.f.reason.text + " (" + findingBody.f.reason.reference + ")" : ""
    }
    Selectable {
      visible: !!findingBody.f.fix
      text: "Fix: " + (findingBody.f.fix || "")
    }
    Selectable {
      text: (Array.isArray(findingBody.f.evidence) && findingBody.f.evidence.length > 0
        ? findingBody.f.evidence.join("\n") + "\n" : "") + "[" + (findingBody.f.id || "") + "]"
      color: root.muted
      font.pixelSize: root.fonts.caption
    }
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

          // ---------- A release chosen by hand, which the bar doesn't follow ----------
          Selectable {
            visible: root.chosen !== ""
            text: root.shown ? root.shown.chosenLine : ""
            color: root.muted
          }

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
                text: root.view.progress
                wrapMode: Text.Wrap
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: root.fonts.bodySmall
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
              visible: root.chosen === ""
              iconText: "󰑐"
              text: root.running ? "Checking…" : "Check again"
              tooltipText: "Compare with the release now (r)"
              enabled: !!root.service && !root.busy
              iconSpinning: root.running
              foreground: root.foreground
              fontFamily: root.fontFamily
              fontSize: root.fonts.bodySmall
              onClicked: root.checkAgain()
            }

            Button {
              visible: root.chosen !== ""
              iconText: "󰁍"
              text: "Back"
              tooltipText: "Your own release's result. This check goes on."
              foreground: root.foreground
              fontFamily: root.fontFamily
              fontSize: root.fonts.bodySmall
              onClicked: root.goBack()
            }

            // A chosen check looks as busy as one of the user's own: the same turning icon.
            Button {
              visible: root.chosen !== "" && root.running
              iconText: "󰑐"
              text: "Checking…"
              tooltipText: "Checking " + root.chosen + ". Closing the panel doesn't stop it."
              enabled: false
              iconSpinning: root.running
              foreground: root.foreground
              fontFamily: root.fontFamily
              fontSize: root.fonts.bodySmall
            }

            Button {
              iconText: "󰆍"
              text: "Open report"
              tooltipText: root.chosen !== "" ? "The report on " + root.chosen + " in a terminal"
                : "The full report in a terminal"
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

          // ---------- Up to date: what is coming next on another channel ----------
          Repeater {
            model: root.shown ? root.shown.newer : []
            delegate: Column {
              id: newer
              required property var modelData
              width: body.width
              spacing: Style.space(3)

              Selectable {
                text: newer.modelData.line
                font.pixelSize: root.fonts.body
                font.bold: true
              }
              Selectable {
                text: newer.modelData.about
                color: root.muted
              }
              // Before it is checked, whether checking downloads it; after, what it found.
              Selectable {
                visible: !newer.modelData.kept
                text: newer.modelData.download
                color: root.muted
                font.pixelSize: root.fonts.caption
              }
              Selectable {
                visible: newer.modelData.kept
                text: newer.modelData.found
                color: root.iconColour(newer.modelData.foundColour)
              }

              Row {
                spacing: Style.space(6)

                Button {
                  visible: !newer.modelData.kept
                  iconText: "󰑐"
                  text: "Check it"
                  tooltipText: "The report on " + newer.modelData.tag + ", here. The bar stays on your channel."
                  enabled: !!root.service && !root.busy
                  iconSpinning: newer.modelData.running
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  fontSize: root.fonts.bodySmall
                  onClicked: root.checkRelease(newer.modelData)
                }

                // Opens the kept report, or the check of it still going. Nothing runs.
                Button {
                  visible: newer.modelData.kept
                  iconText: "󰈈"
                  text: "Show"
                  tooltipText: "The report on " + newer.modelData.tag + ", as last checked"
                  enabled: !!root.service
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  fontSize: root.fonts.bodySmall
                  onClicked: root.showRelease(newer.modelData)
                }

                Button {
                  visible: newer.modelData.kept
                  iconText: "󰑐"
                  text: newer.modelData.running ? "Checking…" : "Check again"
                  tooltipText: "Check " + newer.modelData.tag + " again, here"
                  enabled: !!root.service && !root.busy
                  iconSpinning: newer.modelData.running
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  fontSize: root.fonts.bodySmall
                  onClicked: root.checkRelease(newer.modelData)
                }
              }
            }
          }

          Selectable {
            visible: root.view.newerProblem !== ""
            text: root.view.newerProblem
            color: root.muted
          }

          // ---------- Needs attention, never collapsed: every title shows ----------
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

              FindingTitle {
                about: finding.modelData
                colour: root.warning
                strong: true
              }

              Column {
                visible: root.isOpen(finding.modelData)
                width: parent.width
                spacing: Style.space(3)

                FindingBody { about: finding.modelData }

                // At once: "Undo" under Reviewed takes it back.
                Row {
                  spacing: Style.space(6)

                  Button {
                    iconText: "󰄬"
                    text: "Mark reviewed"
                    tooltipText: "Seen it, and it's fine: it won't count for " + root.view.release
                      + " again. Undo is under Reviewed."
                    enabled: !!root.service && !root.busy
                    foreground: root.foreground
                    fontFamily: root.fontFamily
                    fontSize: root.fonts.bodySmall
                    onClicked: root.markReviewed(finding.modelData.id)
                  }

                  AgentButton { about: finding.modelData }
                }
              }
            }
          }

          // ---------- Couldn't check, never collapsed: every title shows ----------
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
              spacing: Style.space(3)

              FindingTitle { about: unknown.modelData }

              Column {
                visible: root.isOpen(unknown.modelData)
                width: parent.width
                spacing: Style.space(3)

                FindingBody { about: unknown.modelData }
                AgentButton { about: unknown.modelData }
              }
            }
          }

          // ---------- Worth knowing, the notes, collapsed, in their groups ----------
          // Opening it lists each group with its count, closed, in the document's
          // order. Opening a group lists its notes, each one line until it opens.
          PanelSeparator { visible: root.view.notes.length > 0; foreground: root.foreground }
          OpenRow {
            visible: root.view.notes.length > 0
            text: "Worth knowing: " + State.plural(root.view.notes.length, "note", "notes")
            strong: true
            opened: root.notesOpen
            onActivated: root.notesOpen = !root.notesOpen
          }

          Repeater {
            model: root.notesOpen ? root.noteGroups : []
            delegate: Column {
              id: group
              required property var modelData
              width: body.width
              spacing: Style.space(3)

              OpenRow {
                text: group.modelData.line
                opened: root.isOpen(group.modelData)
                onActivated: root.toggleFinding(group.modelData)
              }

              // Its notes, a step in, so they read as the group's.
              Column {
                visible: root.isOpen(group.modelData)
                x: Style.space(12)
                width: parent.width - x
                spacing: Style.space(3)

                Repeater {
                  model: root.isOpen(group.modelData) ? group.modelData.notes : []
                  delegate: Column {
                    id: note
                    required property var modelData
                    width: parent ? parent.width : 0
                    spacing: Style.space(3)

                    FindingTitle { about: note.modelData }

                    Column {
                      visible: root.isOpen(note.modelData)
                      width: parent.width
                      spacing: Style.space(3)

                      FindingBody { about: note.modelData }
                      AgentButton { about: note.modelData }
                    }
                  }
                }
              }
            }
          }

          // ---------- Reviewed, each with "Undo", and the file they are kept in ----------
          PanelSeparator { visible: root.view.reviewed.length > 0; foreground: root.foreground }
          Heading {
            visible: root.view.reviewed.length > 0
            text: "REVIEWED"
          }

          // Why the last "Undo" wrote nothing. The last result stays.
          Selectable {
            visible: root.undoProblem !== ""
            text: root.undoProblem
          }

          Repeater {
            model: root.view.reviewed
            delegate: Column {
              id: reviewed
              required property var modelData
              width: body.width
              spacing: Style.space(3)

              FindingTitle { about: reviewed.modelData }

              Column {
                visible: root.isOpen(reviewed.modelData)
                width: parent.width
                spacing: Style.space(3)

                FindingBody { about: reviewed.modelData }

                Row {
                  spacing: Style.space(6)

                  Button {
                    iconText: "󰕌"
                    text: "Undo"
                    tooltipText: "It counts for " + root.view.release + " again"
                    enabled: !!root.service && !root.busy
                    foreground: root.foreground
                    fontFamily: root.fontFamily
                    fontSize: root.fonts.bodySmall
                    onClicked: root.undoReview(reviewed.modelData.id)
                  }

                  AgentButton { about: reviewed.modelData }
                }
              }
            }
          }

          Selectable {
            visible: root.view.reviewed.length > 0
            text: State.reviewedLine(root.view.release,
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
