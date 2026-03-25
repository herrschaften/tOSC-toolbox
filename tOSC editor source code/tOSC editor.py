"""
TouchOSC Address + Script Editor
Scans a .tosc file for RADAR, XY, GRID, ENCODER controls,
rewrites their OSC messages, and pastes scripts.
"""

import copy
from tkinter import filedialog
import xml.etree.ElementTree as ET
import zlib

# ── Scripts ──────────────────────────────────────────────────────────────────

SCRIPT_ROOT = """\
local g_controlMap = {}
local g_buffer = {}
local g_lastReceiveTime = nil
local g_threshold = 100
local g_velocity = {}

function init()
    local function sortByRow(items)
        table.sort(items, function(a, b)
            return a.frame.y < b.frame.y
        end)
        local rows = {}
        for i = 1, #items do
            local cf = items[i].frame
            local placed = false
            for r = 1, #rows do
                local row = rows[r]
                if cf.y < row.maxY and cf.y + cf.h > row.minY then
                    table.insert(row.items, items[i])
                    if cf.y < row.minY then row.minY = cf.y end
                    if cf.y + cf.h > row.maxY then row.maxY = cf.y + cf.h end
                    placed = true
                    break
                end
            end
            if not placed then
                table.insert(rows, {
                    minY = cf.y,
                    maxY = cf.y + cf.h,
                    items = { items[i] }
                })
            end
        end
        table.sort(rows, function(a, b)
            return a.minY < b.minY
        end)
        for r = 1, #rows do
            table.sort(rows[r].items, function(a, b)
                return a.frame.x < b.frame.x
            end)
        end
        local sorted = {}
        for r = 1, #rows do
            for i = 1, #rows[r].items do
                table.insert(sorted, rows[r].items[i])
            end
        end
        return sorted
    end

    local function pingControl(child)
        for i = 1, #child.messages.OSC do
            local data = child.messages.OSC[i]:data()
            local address = data[1]
            local argument = data[2]
            -- disable send on radar y message
            if child.type == ControlType.RADAR and i == 2 then
                child.messages.OSC[i].send = false
            end
            sendOSC(data)
            g_controlMap[address] = {
                control = child,
                key = argument,
                type = child.type,
                msgIndex = i
            }
        end
    end

    local function processContainer(container)
        local children = {}
        for i = 1, #container.children do
            local child = container.children[i]
            if child.type ~= ControlType.LABEL then
                table.insert(children, child)
            end
        end
        local sorted = sortByRow(children)
        for i = 1, #sorted do
            local child = sorted[i]
            if child.type == ControlType.GRID then
                if #child.children > 0 then
                    pingControl(child.children[1])
                end
            elseif #child.children > 0 then
                processContainer(child)
            else
                pingControl(child)
            end
        end
    end

    processContainer(self)
end

function update()
    local now = getMillis()

    -- advance velocity for all encoders and radar y that have one, even after buffer is cleared
    for path, vel in pairs(g_velocity) do
        local entry = g_controlMap[path]
        if entry then
            if math.abs(vel) > 0.0001 then
                if entry.type == ControlType.ENCODER then
                    local current = entry.control.values.x
                    entry.control.values.x = (current + vel) % 1.0
                elseif entry.type == ControlType.RADAR and entry.msgIndex == 2 then
                    local current = entry.control.values.y
                    entry.control.values.y = (current + vel) % 1.0
                end
                g_velocity[path] = vel * 0.75
            else
                g_velocity[path] = nil
            end
        end
    end

    if g_lastReceiveTime == nil then return end
    if next(g_buffer) == nil then return end
    if now - g_lastReceiveTime < g_threshold then
        -- while receiving, update velocity toward target each frame
        for path, entry in pairs(g_buffer) do
            local target, current, axis
            if entry.type == ControlType.ENCODER then
                target = entry.value % 1.0
                current = entry.control.values.x
                axis = 'x'
            elseif entry.type == ControlType.RADAR and entry.msgIndex == 2 then
                target = entry.value % 1.0
                current = entry.control.values.y
                axis = 'y'
            end
            if axis then
                local delta = target - current
                if delta > 0.5 then delta = delta - 1.0
                elseif delta < -0.5 then delta = delta + 1.0
                end
                local vel = g_velocity[path] or 0
                vel = vel * 0.6 + delta * 0.4
                g_velocity[path] = vel
                if axis == 'x' then
                    entry.control.values.x = (current + vel) % 1.0
                else
                    entry.control.values.y = (current + vel) % 1.0
                end
            end
        end
        return
    end

    -- threshold passed, flush buffer
    for path, entry in pairs(g_buffer) do
        local value = entry.value
        if entry.type == ControlType.RADAR and entry.msgIndex == 2 then
            -- don't snap display, let velocity carry it
            sendOSC(path, value)
            entry.control:notify('presetRecall', value)
            entry.control:notify('receiving', false)
        elseif entry.type == ControlType.ENCODER then
            -- don't snap display here, let velocity carry it
            -- but do send OSC and notify the encoder script
            sendOSC(path, value)
            entry.control:notify('presetRecall', value)
            entry.control:notify('receiving', false)
        else
            sendOSC(path, value)
        end
    end
    g_buffer = {}
    g_lastReceiveTime = nil
end

function onReceiveOSC(message, connections)
    local path = message[1]
    local arguments = message[2]
    if not arguments or #arguments == 0 then return end
    local entry = g_controlMap[path]
    if not entry then return end
    -- notify radar y and encoder controls to go silent
    if entry.type == ControlType.RADAR and entry.msgIndex == 2 then
        entry.control:notify('receiving', true)
    elseif entry.type == ControlType.ENCODER then
        entry.control:notify('receiving', true)
    end
    g_buffer[path] = {
        value = arguments[1].value,
        control = entry.control,
        type = entry.type,
        msgIndex = entry.msgIndex
    }
    g_lastReceiveTime = getMillis()
end"""

SCRIPT_RADAR = """\
local prev = 0
local accumulated = 0
self.messages.OSC[2].send = false
self.messages.OSC[2].receive = false
function onValueChanged(key)
    if key == 'y' and not receiving then
        local curr = self.values.y
        local delta = curr - prev
        if delta > 0.5 then
            delta = delta - 1.0
        elseif delta < -0.5 then
            delta = delta + 1.0
        end
        accumulated = accumulated + delta
        prev = curr
        local path = self.messages.OSC[2]:data()[1]
        sendOSC(path, accumulated)
    end
end
function onReceiveNotify(key, value)
    if key == 'receiving' then
        receiving = value
    elseif key == 'presetRecall' then
        accumulated = value
        prev = self.values.y
    end
end"""

SCRIPT_ENCODER = """\
local prev = 0
local accumulated = 0
self.messages.OSC[1].receive = false
self.messages.OSC[1].send = false
function onValueChanged(key)
    if key == 'x' and not receiving then
        local curr = self.values.x
        local delta = curr - prev
        if delta > 0.5 then
            delta = delta - 1.0
        elseif delta < -0.5 then
            delta = delta + 1.0
        end
        accumulated = accumulated + delta
        prev = curr
        local path = self.messages.OSC[1]:data()[1]
        sendOSC(path, accumulated)
    end
end
function onReceiveNotify(key, value)
    if key == 'receiving' then
        receiving = value
    elseif key == 'presetRecall' then
        accumulated = value
        prev = self.values.x
    end
end"""


def set_script(node, script_text):
    """Set or replace the script property on a node."""
    props = node.find("properties")
    if props is None:
        props = ET.SubElement(node, "properties")
    for prop in props.findall("property"):
        key = prop.find("key")
        if key is not None and key.text == "script":
            props.remove(prop)
    prop = ET.SubElement(props, "property", attrib={"type": "s"})
    ET.SubElement(prop, "key").text = "script"
    ET.SubElement(prop, "value").text = script_text


def clear_script(node):
    """Remove script property from a node if present."""
    props = node.find("properties")
    if props is None:
        return
    for prop in props.findall("property"):
        key = prop.find("key")
        if key is not None and key.text == "script":
            props.remove(prop)
            return

# ── OSC message builders ────────────────────────────────────────────────────

def make_partial(ptype, conversion, value, scale_min="0", scale_max="1"):
    p = ET.Element("partial")
    ET.SubElement(p, "type").text = ptype
    ET.SubElement(p, "conversion").text = conversion
    ET.SubElement(p, "value").text = value
    ET.SubElement(p, "scaleMin").text = scale_min
    ET.SubElement(p, "scaleMax").text = scale_max
    return p

def make_osc_message(path_partials, arg_partial, trigger_var):
    """Build a full <osc> XML element matching TouchOSC's actual format."""
    osc = ET.Element("osc")
    ET.SubElement(osc, "enabled").text = "1"
    ET.SubElement(osc, "send").text = "1"
    ET.SubElement(osc, "receive").text = "1"
    ET.SubElement(osc, "feedback").text = "0"
    ET.SubElement(osc, "noDuplicates").text = "0"        # FIX: was missing
    ET.SubElement(osc, "connections").text = "1111111111" # FIX: was "0000000001"

    triggers = ET.SubElement(osc, "triggers")
    trigger = ET.SubElement(triggers, "trigger")
    ET.SubElement(trigger, "var").text = trigger_var
    ET.SubElement(trigger, "condition").text = "ANY"

    path = ET.SubElement(osc, "path")
    for p in path_partials:
        path.append(p)

    arguments = ET.SubElement(osc, "arguments")
    arguments.append(arg_partial)

    return osc


def build_xy_radar_messages():
    """Two messages for XY and RADAR: /name/x and /name/y"""
    messages = []
    for axis in ("x", "y"):
        path_partials = [
            make_partial("CONSTANT", "STRING", "/"),
            make_partial("PROPERTY", "STRING", "name"),
            make_partial("CONSTANT", "STRING", axis),
        ]
        arg = make_partial("VALUE", "FLOAT", axis)
        messages.append(make_osc_message(path_partials, arg, axis))
    return messages


def build_grid_messages():
    """One message for GRID: /parent.name, INDEX arg starting at 1"""
    path_partials = [
        make_partial("CONSTANT", "STRING", "/"),
        make_partial("PROPERTY", "STRING", "parent.name"),
    ]
    arg = make_partial("INDEX", "INTEGER", None, scale_min="1", scale_max="2")
    return [make_osc_message(path_partials, arg, "x")]


# ── Core processing ─────────────────────────────────────────────────────────

OSC_TYPES  = {"BUTTON", "TEXT", "FADER", "XY", "RADIAL", "ENCODER", "RADAR", "RADIO", "GRID", "PAGER"}
ALL_TYPES  = {"BOX", "BUTTON", "LABEL", "TEXT", "FADER", "XY", "RADIAL",
              "ENCODER", "RADAR", "RADIO", "GROUP", "PAGER", "GRID"}
UI_TO_TYPE = {
    "Box":"BOX","Button":"BUTTON","Label":"LABEL","Text":"TEXT",
    "Fader":"FADER","XY":"XY","Radial":"RADIAL","Encoder":"ENCODER",
    "Radar":"RADAR","Radio":"RADIO","Group":"GROUP","Pager":"PAGER","Grid":"GRID",
}
TYPE_TO_UI = {v: k for k, v in UI_TO_TYPE.items()}

def get_name(node):
    props = node.find("properties")
    if props is not None:
        for prop in props.findall("property"):
            key = prop.find("key")
            if key is not None and key.text == "name":
                val = prop.find("value")
                return val.text if val is not None else "?"
    return "?"

def clear_all_scripts(node):
    """Recursively clear scripts from all nodes."""
    clear_script(node)
    children = node.find("children")
    if children is not None:
        for child in children.findall("node"):
            clear_all_scripts(child)

def process_node(node, log, scripts, preset_data=None):
    """Recursively walk nodes, apply OSC rewrites and scripts."""
    preset_data = preset_data or {}
    control_type = node.attrib.get("type", "").upper()
    count = 0

    if control_type in ALL_TYPES:
        name    = get_name(node)
        ui_name = TYPE_TO_UI.get(control_type, control_type)

        if control_type in OSC_TYPES:
            messages_el = node.find("messages")
            if messages_el is None:
                messages_el = ET.SubElement(node, "messages")

            preset = preset_data.get(ui_name)
            if preset:
                for osc in messages_el.findall("osc"):
                    messages_el.remove(osc)
                for osc in preset["messages_xml"].findall("osc"):
                    messages_el.append(copy.deepcopy(osc))
            else:
                if control_type in ("RADAR", "XY"):
                    for osc in messages_el.findall("osc"):
                        messages_el.remove(osc)
                    for msg in build_xy_radar_messages():
                        messages_el.append(msg)
                elif control_type == "GRID":
                    for osc in messages_el.findall("osc"):
                        messages_el.remove(osc)
                    for msg in build_grid_messages():
                        messages_el.append(msg)

        script = scripts.get(ui_name, "").strip()        
                     
        if script:
            set_script(node, script)

        parts = []
        if control_type in OSC_TYPES:
            src = "preset" if preset_data.get(ui_name) else "default"
            parts.append(f"OSC ({src})")
        if script:
            parts.append("script")
        if parts:
            log(f"  [{control_type:<8}] '{name}' → {', '.join(parts)}")
            count += 1

    if control_type != "GRID":
        children = node.find("children")
        if children is not None:
            for child in children.findall("node"):
                count += process_node(child, log, scripts, preset_data)

    return count


def run_on_file(path, log, scripts, preset_data=None):
    preset_data = preset_data or {}
    log(f"Loading: {path}")
    with open(path, "rb") as f:
        raw = zlib.decompress(f.read())

    root = ET.fromstring(raw)

    log("Clearing all existing scripts...")
    for child in root:
        if child.tag == "node":
            clear_all_scripts(child)

    root_node = root.find("node")
    if root_node is not None:
        script = scripts.get("Root", "").strip()
        if script:
            set_script(root_node, script)
            log(f"  [ROOT]    '{get_name(root_node)}' → root script")

    log("Processing controls...")
    total = 0
    for child in root:
        if child.tag == "node":
            total += process_node(child, log, scripts, preset_data)

    new_xml = ET.tostring(root, encoding="UTF-8", xml_declaration=False)
    with open(path, "wb") as f:
        f.write(zlib.compress(new_xml))

    log(f"\nDone. {total} control(s) modified. Saved to: {path}")


# ── UI ───────────────────────────────────────────────────────────────────────

import copy
import customtkinter as ctk
from tkinter import filedialog

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def make_editor(parent):
    """Return (frame, textbox). CTkTextbox with rounded corners."""
    textbox = ctk.CTkTextbox(
        parent,
        font=FONT,
        fg_color=C_RAISED,
        text_color=C_FG,
        corner_radius=10,
        wrap="word",
        activate_scrollbars=True,
        scrollbar_button_color=C_RAISED,
        scrollbar_button_hover_color=C_ACCENT,
    )
    return textbox, textbox


ALL_CONTROLS = [
    "Root", "Button", "Text", "Fader", "XY", "Radial",
    "Encoder", "Radar", "Radio", "Grid", "Pager",
    "Label", "Box", "Group",
]

DEFAULT_SCRIPTS = {
    "Root":    SCRIPT_ROOT,
    "Radar":   SCRIPT_RADAR,
    "Encoder": SCRIPT_ENCODER,
}

HAS_OSC = {"Button", "Text", "Fader", "XY", "Radial", "Encoder",
           "Radar", "Radio", "Grid", "Pager"}
MULTI_MSG = {"XY", "Radar"}

DEFAULT_ADDRS = {
    "Button":  ["/name"],
    "Text":    ["/name"],
    "Fader":   ["/name"],
    "XY":      ["/namex", "/namey"],
    "Radial":  ["/name"],
    "Encoder": ["/name"],
    "Radar":   ["/namex", "/namey"],
    "Radio":   ["/name"],
    "Grid":    ["/parent.name"],
    "Pager":   ["/name"],
}
DEFAULT_ARGS = {
    "Button":  ["x"],
    "Text":    ["x"],
    "Fader":   ["x"],
    "XY":      ["x", "y"],
    "Radial":  ["x"],
    "Encoder": ["x"],
    "Radar":   ["x", "y"],
    "Radio":   ["x"],
    "Grid":    ["index"],
    "Pager":   ["page"],
}

HAS_DEFAULT_OSC    = {"XY", "Radar", "Grid"}
HAS_DEFAULT_SCRIPT = {"Root", "Radar", "Encoder"}

UI_TO_TYPE = {
    "Box":"BOX","Button":"BUTTON","Label":"LABEL","Text":"TEXT",
    "Fader":"FADER","XY":"XY","Radial":"RADIAL","Encoder":"ENCODER",
    "Radar":"RADAR","Radio":"RADIO","Group":"GROUP","Pager":"PAGER","Grid":"GRID",
}
TYPE_TO_UI = {v: k for k, v in UI_TO_TYPE.items()}

# ── Design tokens ────────────────────────────────────────────────────────────
C_BG      = "#1a1a1a"
C_RAISED  = "#2e2e2e"
C_FG      = "#e0e0e0"
C_FG_DIM  = "#888888"
C_ACCENT  = "#fbe017"

FONT      = ("Cascadia Code", 13)
FONT_BOLD = ("Cascadia Code", 13, "bold")


def load_tosc(path):
    with open(path, "rb") as f:
        return ET.fromstring(zlib.decompress(f.read()))


def extract_preset_messages(preset_path):
    """Return dict: ui_name → (messages_element, address_strings, arg_strings)"""
    root = load_tosc(preset_path)
    found = {}

    def walk(node):
        ct = node.attrib.get("type", "").upper()
        ui = TYPE_TO_UI.get(ct)
        if ui and ui not in found:
            msgs = node.find("messages")
            if msgs is not None and msgs.find("osc") is not None:
                addresses, args = [], []
                for osc in msgs.findall("osc"):
                    path_el = osc.find("path")
                    addr = ""
                    if path_el is not None:
                        for p in path_el.findall("partial"):
                            ptype = p.findtext("type","")
                            val   = p.findtext("value","") or ""
                            if ptype == "CONSTANT":
                                addr += val
                            elif ptype == "PROPERTY":
                                addr += f"<{val}>"
                            elif ptype == "INDEX":
                                addr += "<index>"
                            elif ptype == "VALUE":
                                addr += f"<{val}>"
                    arg_el = osc.find("arguments")
                    arg_str = ""
                    if arg_el is not None:
                        parts = []
                        for p in arg_el.findall("partial"):
                            ptype = p.findtext("type","")
                            conv  = p.findtext("conversion","")
                            val   = p.findtext("value","") or ""
                            if ptype == "VALUE":
                                parts.append(f"<{val}> ({conv})")
                            elif ptype == "INDEX":
                                parts.append(f"<index> ({conv})")
                            elif ptype == "CONSTANT":
                                parts.append(f"{val} ({conv})")
                        arg_str = ", ".join(parts)
                    addresses.append(addr)
                    args.append(arg_str)
                # extract script if present
                script = ""
                props = node.find("properties")
                if props is not None:
                    for prop in props.findall("property"):
                        key = prop.find("key")
                        if key is not None and key.text == "script":
                            val = prop.find("value")
                            script = val.text if val is not None and val.text else ""
                found[ui] = {
                    "messages_xml": copy.deepcopy(msgs),
                    "addresses":    addresses,
                    "args":         args,
                    "script":       script,
                }
        children = node.find("children")
        if children is not None:
            for child in children.findall("node"):
                walk(child)

    # extract script from root node
    root_node = root.find("node")
    if root_node is not None:
        script = ""
        props = root_node.find("properties")
        if props is not None:
            for prop in props.findall("property"):
                key = prop.find("key")
                if key is not None and key.text == "script":
                    val = prop.find("value")
                    script = val.text if val is not None and val.text else ""
        found["Root"] = {"messages_xml": None, "addresses": [], "args": [], "script": script}

    for child in root:
        if child.tag == "node":
            walk(child)
    return found


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("")
        self.geometry("920x700")
        self.minsize(780, 540)
        self.configure(fg_color=C_BG)

        import sys, os
        def resource_path(p):
            base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
            return os.path.join(base, p)
        self.after(200, lambda: self.iconbitmap(resource_path("icon.ico")))

        self.target_files  = []
        self.preset_data   = {}
        self.selected_ctrl = ctk.StringVar(value="Root")
        self.code_views    = {}
        self._dot_vars     = {}
        self._sidebar_btns = {}
        self._copy_timer   = None
        self._run_log      = []

        self._build()
        self._select_control("Root")
        self.after(150, self._update_all_dots)

    def _build(self):
        top = ctk.CTkFrame(self, fg_color=C_BG, corner_radius=0, height=64)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)
        ctk.CTkButton(top, text="Select Preset File", width=170, height=40,
                      font=FONT_BOLD, fg_color=C_ACCENT, hover_color=C_FG, text_color=C_BG,
                      command=self._browse_preset).pack(side="left", padx=(16,8), pady=12)
        ctk.CTkButton(top, text="Select Files", width=140, height=40,
                      font=FONT_BOLD, fg_color=C_ACCENT, hover_color=C_FG, text_color=C_BG,
                      command=self._browse_targets).pack(side="left", pady=12)

        bottom = ctk.CTkFrame(self, fg_color=C_BG, corner_radius=0, height=64)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)
        self.run_btn = ctk.CTkButton(bottom, text="RUN", width=120, height=40,
                                     font=FONT_BOLD, fg_color=C_ACCENT, hover_color=C_FG, text_color=C_BG,
                                     command=self._run)
        self.run_btn.pack(side="left", padx=16, pady=12)
        self.copy_btn = ctk.CTkButton(bottom, text="Copy to Clipboard", width=170, height=40,
                                      font=FONT_BOLD, fg_color=C_ACCENT, hover_color=C_FG, text_color=C_BG,
                                      command=self._copy_script)
        self.copy_btn.pack(side="right", padx=16, pady=10)

        main = ctk.CTkFrame(self, fg_color=C_BG)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(main, fg_color=C_BG, corner_radius=0, width=185)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.pack_propagate(False)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(0, weight=1)
        sidebar.rowconfigure(1, weight=0)

        nav = ctk.CTkScrollableFrame(
            sidebar, fg_color=C_BG,
            scrollbar_button_color=C_RAISED,
            scrollbar_button_hover_color=C_ACCENT)
        nav.grid(row=0, column=0, sticky="nsew")
        nav.columnconfigure(0, weight=1)

        for i, ctrl in enumerate(ALL_CONTROLS):
            btn = ctk.CTkButton(
                nav, text=ctrl, anchor="w",
                fg_color="transparent", hover_color=C_RAISED,
                text_color=C_FG, font=FONT,
                corner_radius=6, height=36,
                command=lambda c=ctrl: self._select_control(c))
            btn.grid(row=i, column=0, sticky="ew")
            self._sidebar_btns[ctrl] = btn
            self._dot_vars[ctrl] = btn

        bottom_side = ctk.CTkFrame(sidebar, fg_color=C_BG, corner_radius=0)
        bottom_side.grid(row=1, column=0, sticky="ew")

        ctk.CTkLabel(bottom_side, text="Selected Files",
                     font=FONT, text_color=C_FG_DIM).pack(
                     anchor="w", padx=12, pady=(10,2))
        self.files_box = ctk.CTkTextbox(bottom_side, height=72, font=FONT,
                                        fg_color=C_RAISED, state="disabled",
                                        activate_scrollbars=True)
        self.files_box.pack(fill="x", padx=8, pady=(0,4))

        ctk.CTkLabel(bottom_side, text="Preset File",
                     font=FONT, text_color=C_FG_DIM).pack(
                     anchor="w", padx=12, pady=(6,2))
        self.preset_lbl = ctk.CTkLabel(bottom_side, text="—",
                                       font=FONT, text_color=C_FG_DIM,
                                       wraplength=162, anchor="w")
        self.preset_lbl.pack(anchor="w", padx=12, pady=(0,10))

        right = ctk.CTkFrame(main, fg_color=C_BG, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self.addr_frame = ctk.CTkFrame(right, fg_color="transparent")
        self.addr_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        self.addr_frame.columnconfigure(0, weight=1)
        right.rowconfigure(0, minsize=10)

        for ctrl in ALL_CONTROLS:
            script = DEFAULT_SCRIPTS.get(ctrl, "")
            frame, text = make_editor(right)
            frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 12))
            frame.grid_remove()
            if script:
                text.insert("1.0", script)
            self.code_views[ctrl] = (frame, text)

    def _select_control(self, ctrl):
        self.selected_ctrl.set(ctrl)
        for name, btn in self._sidebar_btns.items():
            btn.configure(fg_color=C_RAISED if name == ctrl else "transparent")
        for frame, _ in self.code_views.values():
            frame.grid_remove()
        self.code_views[ctrl][0].grid()
        self._rebuild_addr_fields(ctrl)

    def _rebuild_addr_fields(self, ctrl):
        for w in self.addr_frame.winfo_children():
            w.destroy()

        if ctrl not in HAS_OSC:
            self.addr_frame.grid_remove()
            return
        self.addr_frame.grid()

        preset    = self.preset_data.get(ctrl)
        def_addrs = DEFAULT_ADDRS.get(ctrl, [""])
        def_args  = DEFAULT_ARGS.get(ctrl, [""])
        n_msgs    = len(preset["addresses"]) if preset else len(def_addrs)
        addresses = preset["addresses"] if preset else def_addrs
        args      = preset["args"]      if preset else def_args

        is_preset = bool(preset)
        for i in range(n_msgs):
            addr      = addresses[i] if i < len(addresses) else "—"
            arg       = args[i]      if i < len(args)      else "—"

            row1 = ctk.CTkFrame(self.addr_frame, fg_color="transparent")
            row1.grid(row=i*2,   column=0, sticky="ew", pady=(0,2))
            row1.columnconfigure(1, weight=1)

            ctk.CTkLabel(row1, text="Address",
                         width=100, font=FONT,
                         text_color=C_FG_DIM, anchor="w").grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(row1, text=addr or "—",
                         font=FONT, text_color=C_FG,
                         fg_color=C_RAISED, corner_radius=6,
                         anchor="w", padx=10).grid(row=0, column=1, sticky="ew", ipady=4)

            row2 = ctk.CTkFrame(self.addr_frame, fg_color="transparent")
            row2.grid(row=i*2+1, column=0, sticky="ew", pady=(0,6))
            row2.columnconfigure(1, weight=1)

            ctk.CTkLabel(row2, text="Argument",
                         width=100, font=FONT,
                         text_color=C_FG_DIM, anchor="w").grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(row2, text=arg or "—",
                         font=FONT, text_color=C_FG,
                         fg_color=C_RAISED, corner_radius=6,
                         anchor="w", padx=10).grid(row=0, column=1, sticky="ew", ipady=4)

    def _update_dot(self, ctrl):
        has_content = bool(self.code_views[ctrl][1].get("1.0", "end-1c").strip())
        btn = self._dot_vars[ctrl]
        btn.configure(text_color=C_ACCENT if has_content else C_FG)

    def _update_all_dots(self):
        for ctrl in ALL_CONTROLS:
            self._update_dot(ctrl)

    def _browse_targets(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("TouchOSC files","*.tosc"),("All files","*.*")])
        if paths:
            self.target_files = list(paths)
            self.files_box.configure(state="normal")
            self.files_box.delete("1.0","end")
            for p in self.target_files:
                name = p.replace("\\","/").split("/")[-1]
                self.files_box.insert("end", name + "\n")
            self.files_box.configure(state="disabled")

    def _browse_preset(self):
        path = filedialog.askopenfilename(
            filetypes=[("TouchOSC files","*.tosc"),("All files","*.*")])
        if path:
            try:
                self.preset_data = extract_preset_messages(path)
                name = path.replace("\\","/").split("/")[-1]
                self.preset_lbl.configure(text=name, text_color=C_FG)
                # clear all editors then fill from preset
                for ctrl in ALL_CONTROLS:
                    _, textbox = self.code_views[ctrl]
                    textbox.delete("1.0", "end")
                for ctrl, data in self.preset_data.items():
                    if ctrl in self.code_views and data.get("script"):
                        _, textbox = self.code_views[ctrl]
                        textbox.insert("1.0", data["script"])
                self._update_all_dots()
                self._rebuild_addr_fields(self.selected_ctrl.get())
            except Exception as e:
                import tkinter.messagebox as mb
                mb.showerror("Preset Error", str(e))

    def _copy_script(self):
        ctrl = self.selected_ctrl.get()
        content = self.code_views[ctrl][1].get("1.0","end-1c")
        self.clipboard_clear()
        self.clipboard_append(content)
        self.copy_btn.configure(text="Copied!")
        if self._copy_timer:
            self.after_cancel(self._copy_timer)
        self._copy_timer = self.after(
            1500, lambda: self.copy_btn.configure(text="Copy to Clipboard"))

    def _set_run_status(self, text, color=None):
        self.run_btn.configure(text=text)
        if color:
            self.run_btn.configure(text_color=color)

    def _log(self, msg):
        self._run_log.append(msg)
        self.update_idletasks()

    def _run(self):
        if not self.target_files:
            self.run_btn.configure(text="No files selected")
            self.after(2000, lambda: self.run_btn.configure(text="RUN", text_color=C_BG))
            return

        self._run_log = []
        self.run_btn.configure(text="Running…", text_color=C_BG)
        self.update_idletasks()

        scripts = {ctrl: self.code_views[ctrl][1].get("1.0","end-1c")
                   for ctrl in ALL_CONTROLS}
        errors = []
        for path in self.target_files:
            try:
                run_on_file(path, self._log, scripts, self.preset_data)
            except Exception as e:
                errors.append(str(e))

        if errors:
            self.run_btn.configure(text=f"{len(errors)} error(s)", text_color="#f38ba8")
            self.after(3000, lambda: self.run_btn.configure(text="RUN", text_color=C_BG))
        else:
            n = len(self.target_files)
            self.run_btn.configure(text=f"{n} file{'s' if n>1 else ''} done", text_color="#a6e3a1")
            self.after(3000, lambda: self.run_btn.configure(text="RUN", text_color=C_BG))


if __name__ == "__main__":
    App().mainloop()