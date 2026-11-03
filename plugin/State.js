// What the bar and the panel show, from what the command printed.
//
// The plugin holds no rules: the command decides every finding and the result.
// This file only reads its --json document and exit code, and refuses one that
// doesn't add up, so a check that didn't run is never shown as clear.
//
// It is plain JavaScript with no QML in it. The QML imports it, and the tests run
// it under node on the command's own documents.

var SCHEMA_VERSION = 1
var CHECKS = ["bindings", "packages", "commands", "plugins", "edits"]
var EXIT_CODES = { clear: 0, noUpdate: 0, attention: 1, failed: 2, incomplete: 3 }
var STATE_WORDS = { ranInPart: "ran in part", didNotRun: "didn't run" }
// Longer text from stderr is cut, so a runaway line can't fill the panel.
var MOST_REASON = 400
// Hours between checks: 6 by default, 0 for only when asked, and at most a week.
var DEFAULT_HOURS = 6
var MOST_HOURS = 168
// What the panel's "Check every" offers.
var OFFERED_HOURS = [0, 1, 6, 12, 24]
// The first check waits this long, so the network is up after login.
var FIRST_CHECK_MS = 2 * 60 * 1000
// "Open report" and each newer release's "Check" run the command in this.
var LAUNCHER = "omarchy-launch-floating-terminal-with-presentation"

// A view is everything the bar and the panel show. Each state fills in its part.
function view(state, fields) {
  var base = {
    state: state,       // notChecked, quiet, attention or unknown
    mark: "",           // beside the icon: the count, "?", "…" or nothing
    colour: "muted",    // muted, text or warning: a theme role, not a colour
    tooltip: "",
    summary: "",        // the panel's first line
    problem: "",        // why it couldn't check, or ""
    installed: "",
    release: "",
    channel: "",
    attention: [],      // findings that need attention and aren't reviewed
    limits: [],         // each check that didn't run in full: check and words
    unknowns: [],       // each unknown finding
    notes: [],
    reviewed: 0,
    newer: [],          // newer releases on other channels, with noUpdate
    newerProblem: ""
  }
  for (var key in fields) base[key] = fields[key]
  return base
}

function plural(count, one, many) {
  return count + " " + (count === 1 ? one : many)
}

function lastLine(text) {
  var lines = String(text || "").split("\n")
  for (var i = lines.length - 1; i >= 0; i--) {
    var line = lines[i].trim()
    if (line !== "") return line.length > MOST_REASON ? line.slice(0, MOST_REASON) + "…" : line
  }
  return ""
}

function isText(value) {
  return typeof value === "string"
}

// Before the first check. With checks only when asked, nothing is on its way.
function notChecked(onlyWhenAsked) {
  return view("notChecked", {
    mark: "…",
    tooltip: onlyWhenAsked ? "Not checked yet" : "Checking…",
    summary: onlyWhenAsked ? "Not checked yet. Check now to compare with the next release." : "Checking…"
  })
}

// It couldn't check. why says what happened, and stays on screen.
function cantCheck(release, why, fields) {
  var all = {
    mark: "?",
    colour: "text",
    tooltip: (release ? "Couldn't check " + release : "Couldn't check") + "\n" + why,
    summary: release ? "Couldn't check " + release : "Couldn't check",
    problem: why
  }
  for (var key in fields) all[key] = fields[key]
  return view("unknown", all)
}

// A replacement bar gives its widgets no service, so nothing runs the command.
function noService() {
  return cantCheck("", "This bar gives the widget no service to run the check. Omarchy's own bar does.")
}

// The command's output couldn't be read. The last line of stderr says why, if anything does.
function unreadable(why, stderr) {
  var said = lastLine(stderr)
  return cantCheck("", said ? why + " It said: " + said : why)
}

// Every finding of one level, in the document's order.
function level(findings, name, reviewed) {
  return findings.filter(function(f) { return f.level === name && f.reviewed === reviewed })
}

// Why a report can't be shown as it says, or "" when it adds up. Only what the
// document holds is compared, so a clear result can never hide a check that didn't run.
function reportProblem(doc) {
  if (!doc.target || !isText(doc.target.name)) return "It has no release."
  if (!doc.checks || typeof doc.checks !== "object") return "It has no checks."
  if (!Array.isArray(doc.findings)) return "It has no findings."
  for (var i = 0; i < CHECKS.length; i++) {
    var check = doc.checks[CHECKS[i]]
    if (!check || ["ran", "ranInPart", "didNotRun"].indexOf(check.state) === -1)
      return "It doesn't say whether " + CHECKS[i] + " ran."
  }
  for (var j = 0; j < doc.findings.length; j++) {
    var f = doc.findings[j]
    if (!f || ["attention", "note", "unknown"].indexOf(f.level) === -1 || !isText(f.title)
        || typeof f.reviewed !== "boolean")
      return "Finding " + (j + 1) + " can't be read."
  }
  var open = level(doc.findings, "attention", false).length
  var unknown = level(doc.findings, "unknown", false).length
  var limited = CHECKS.some(function(name) { return doc.checks[name].state !== "ran" })
  if (doc.result === "attention" && open === 0) return "It says attention, with nothing that needs it."
  if (doc.result !== "attention" && open > 0) return "It says " + doc.result + ", with findings that need attention."
  if (doc.result === "clear" && (unknown > 0 || limited)) return "It says clear, but a check didn't run in full."
  if (doc.result === "incomplete" && unknown === 0 && !limited) return "It says incomplete, but every check ran."
  return ""
}

// A report: clear, attention or incomplete.
function report(doc) {
  var release = doc.target.name
  var attention = level(doc.findings, "attention", false)
  var limits = CHECKS.filter(function(name) { return doc.checks[name].state !== "ran" })
    .map(function(name) { return { check: name, words: STATE_WORDS[doc.checks[name].state] } })
  var fields = {
    installed: isText(doc.installed) ? doc.installed : "",
    release: release,
    channel: isText(doc.channel) ? doc.channel : "",
    attention: attention,
    limits: limits,
    unknowns: doc.findings.filter(function(f) { return f.level === "unknown" }),
    notes: doc.findings.filter(function(f) { return f.level === "note" }),
    reviewed: doc.findings.filter(function(f) { return f.reviewed }).length
  }
  if (doc.result === "attention") {
    var needs = plural(attention.length, "thing needs", "things need") + " attention"
    fields.mark = String(attention.length)
    fields.colour = "warning"
    fields.tooltip = release + ": " + needs
    fields.summary = release + ": " + needs
    return view("attention", fields)
  }
  if (doc.result === "incomplete") {
    var names = limits.map(function(l) { return l.check })
    var why = names.length > 0
      ? "Some checks didn't run in full: " + names.join(", ") + "."
      : "Some things couldn't be checked."
    return cantCheck(release, why + " Nothing else needs attention.", fields)
  }
  fields.tooltip = release + ": nothing needs attention"
  fields.summary = release + ": nothing needs attention"
  return view("quiet", fields)
}

// A newer release on another channel. Checking it opens its report in a terminal,
// and downloads it first unless the command said it is in the cache.
function newerRelease(n) {
  var cached = n.cached === true
  return {
    tag: n.tag,
    channel: n.channel,
    cached: cached,
    line: "Newer on the " + n.channel + " channel: " + n.tag,
    download: cached ? "It is in the cache, so nothing downloads." : "Checking it downloads it first, about 200 MB."
  }
}

function upToDate(doc) {
  var newer = Array.isArray(doc.newer) ? doc.newer.filter(function(n) {
    return n && isText(n.tag) && isText(n.channel)
  }).map(newerRelease) : []
  var installed = "Omarchy " + doc.target.name + " is up to date"
  return view("quiet", {
    tooltip: installed,
    summary: installed,
    installed: isText(doc.installed) ? doc.installed : "",
    release: doc.target.name,
    channel: isText(doc.channel) ? doc.channel : "",
    newer: newer,
    newerProblem: doc.newer === null && isText(doc.newerProblem) ? doc.newerProblem : ""
  })
}

// One run of the command: whether it started, its exit code, stdout and stderr.
function fromRun(run) {
  if (!run || !run.started) return unreadable("The bundled command couldn't start.", run ? run.stderr : "")
  var doc
  try {
    doc = JSON.parse(String(run.stdout || ""))
  } catch (e) {
    return unreadable("Its output wasn't one JSON document.", run.stderr)
  }
  if (!doc || typeof doc !== "object" || Array.isArray(doc))
    return unreadable("Its output wasn't one JSON document.", run.stderr)
  if (doc.schemaVersion !== SCHEMA_VERSION)
    return unreadable("It printed schema version " + String(doc.schemaVersion) + ", and this plugin reads "
      + SCHEMA_VERSION + ".", run.stderr)
  if (!Object.prototype.hasOwnProperty.call(EXIT_CODES, doc.result))
    return unreadable("It printed a result this plugin doesn't know.", run.stderr)
  if (EXIT_CODES[doc.result] !== run.exitCode)
    return unreadable("It exited " + run.exitCode + ", which doesn't go with the result " + doc.result + ".",
      run.stderr)
  if (doc.result === "failed") {
    var reason = isText(doc.reason) && doc.reason !== "" ? doc.reason : lastLine(run.stderr)
    return cantCheck("", reason || "It failed, and didn't say why.")
  }
  if (doc.result === "noUpdate") {
    if (!doc.target || !isText(doc.target.name)) return unreadable("It has no release.", run.stderr)
    return upToDate(doc)
  }
  var problem = reportProblem(doc)
  if (problem) return unreadable("Its document doesn't add up. " + problem, run.stderr)
  return report(doc)
}

// ---------- How often it checks ----------

// The widget's setting as the service uses it: 0, or 1 to 168 hours, rounded.
// Anything else, such as text, true or 500, is the default.
function hoursFrom(value) {
  if (typeof value !== "number" && !(isText(value) && value.trim() !== "")) return DEFAULT_HOURS
  var hours = Math.round(Number(value))
  return isFinite(hours) && hours >= 0 && hours <= MOST_HOURS ? hours : DEFAULT_HOURS
}

function hoursLabel(hours) {
  return hours === 0 ? "Only when asked" : hours + " h"
}

// The panel's choices, for the shell's ButtonGroup. A value set by hand that isn't
// offered, such as 3, is kept among them in order, so what is in effect is shown.
function intervalChoices(hours) {
  var all = OFFERED_HOURS.slice()
  if (all.indexOf(hours) === -1) all.push(hours)
  all.sort(function(a, b) { return a - b })
  return all.map(function(h) {
    return {
      value: String(h),
      label: hoursLabel(h),
      tooltip: h === 0 ? "Only when you check, as for a metered connection"
        : h === 1 ? "Check every hour" : "Check every " + h + " hours"
    }
  })
}

// The widget's entry in shell.json with one setting changed, the rest as they were.
function withSetting(settings, id, key, value) {
  var entry = { id: id }
  if (settings && typeof settings === "object")
    for (var k in settings) if (k !== "id") entry[k] = settings[k]
  entry[key] = value
  return entry
}

// When the next check is due, in ms since the epoch, or null when it checks only
// when asked. The first is 2 minutes after loading, then every hours after the last
// one started. A changed setting counts from the same start, so it applies at once.
function nextCheckAt(hours, lastStartedAt, loadedAt) {
  if (hours === 0) return null
  return lastStartedAt > 0 ? lastStartedAt + hours * 3600 * 1000 : loadedAt + FIRST_CHECK_MS
}

// ---------- The terminal ----------

function shellQuote(value) {
  return "'" + String(value).replace(/'/g, "'\\''") + "'"
}

// The line the bar's run() hands to bash. The launcher joins its arguments and gives
// them to a second bash -c, so the command is quoted once for that shell, and the
// whole of it again for the first. A path or tag with a space reaches it intact.
function terminalLine(command, args) {
  var words = [command].concat(args || []).map(shellQuote)
  return LAUNCHER + " " + shellQuote(words.join(" "))
}
