// Runs plugin/State.js under node, as the plugin's QML imports it, for tests/test_plugin.py.
// Reads a list of {"call": name, "args": [...]} on stdin and prints what each returns, as JSON.
// {"get": name} gives a constant instead.
"use strict"

const fs = require("fs")
const path = require("path")
const vm = require("vm")

const file = path.join(__dirname, "..", "plugin", "State.js")
const state = vm.createContext({})
vm.runInContext(fs.readFileSync(file, "utf8"), state, { filename: file })
const calls = JSON.parse(fs.readFileSync(0, "utf8"))
process.stdout.write(JSON.stringify(calls.map((c) => ("get" in c ? state[c.get] : state[c.call](...c.args)))))
