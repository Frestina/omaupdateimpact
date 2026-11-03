pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Ui
import "State.js" as State

// The bar icon and its panel. It runs nothing itself: the service checks, and this
// shows the service's view. Each monitor has its own copy; they share the service.
//
// Left click opens the panel. Its two buttons check again and open the report in a
// terminal. No button changes the system.
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
  readonly property int checkEveryHours: Number(root.setting("checkEveryHours", 6))

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

  // The same bundled command, as text, in the launcher Omarchy's update row uses.
  function openReport() {
    if (!root.host) return
    var command = root.service ? root.service.command : ""
    if (command === "") return
    root.close()
    root.host.run("omarchy-launch-floating-terminal-with-presentation " + Util.shellQuote(command))
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

  onOpenedChanged: if (!opened) notesOpen = false

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
            delegate: Selectable {
              required property var modelData
              text: "Newer on the " + modelData.channel + " channel: " + modelData.tag
              color: root.muted
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
            }
          }

          // ---------- Reviewed, a count ----------
          Text {
            visible: root.view.reviewed > 0
            width: parent.width
            textFormat: Text.PlainText
            text: State.plural(root.view.reviewed, "finding", "findings") + " reviewed with --ack."
            wrapMode: Text.Wrap
            color: root.muted
            font.family: root.fontFamily
            font.pixelSize: root.fonts.caption
          }
        }
      }
    }
  }
}
