-- ============================================================
-- ROOT LAYOUT + RENAME + STYLE + LABEL SCRIPT
-- Place this script on the document root.
-- Requires a pool of pre-placed LABEL controls as children of root.
-- ============================================================

-- ── LAYOUT CONFIG ────────────────────────────────────────────
local gap               = 5     -- spacing between controls inside a group
local groupPad          = 4     -- padding of group borders around controlls

-- ── LABEL CONFIG ────────────────────────────────────────────
local createLabels      = true  -- false to turn off
local createGroupLabels = true   

local labelPad          = 5     -- gap above controls
local textSize          = 10
local textColor         = Color(1, 1, 1, 1)
local cellLabelColor    = Color(0, 0, 0, 1)

-- ── TYPE SHORT NAMES ─────────────────────────────────────────
local function getShortAndKey(child)
    local t = child.type
    if     t == ControlType.FADER   then return "Fad", "FADER"
    elseif t == ControlType.BUTTON  then
        if child.buttonType == ButtonType.MOMENTARY then return "Mom", "BUTTON"
        else return "Tog", "BUTTON" end
    elseif t == ControlType.XY      then return "Xy",  "XY"
    elseif t == ControlType.RADIAL  then return "Rad", "RADIAL"
    elseif t == ControlType.ENCODER then return "Enc", "ENCODER"
    elseif t == ControlType.RADAR   then return "Rdr", "RADAR"
    elseif t == ControlType.RADIO   then return "Rdo", "RADIO"
    elseif t == ControlType.GRID    then return "Grd", "GRID"
    elseif t == ControlType.TEXT    then return "Txt", "TEXT"
    elseif t == ControlType.BOX     then return "Box", "BOX"
    elseif t == ControlType.PAGER   then return "Pgr", "PAGER"
    else return "Unk", "UNKNOWN" end
end

-- ── STYLE COPY ───────────────────────────────────────────────
local function hasGridColor(ctrl)
    local t = ctrl.type
    return t == ControlType.FADER  or t == ControlType.XY     or
           t == ControlType.RADIAL or t == ControlType.ENCODER or
           t == ControlType.RADAR
end

local function copyStyle(source, target)
    target.color        = source.color
    target.background   = source.background
    target.outline      = source.outline
    target.outlineStyle = source.outlineStyle
    target.cornerRadius = source.cornerRadius
    if hasGridColor(source) and hasGridColor(target) then
        target.gridColor = source.gridColor
    end
end

-- ── LABEL POOL SETUP ─────────────────────────────────────────
-- Reset grid/step tags so those labels re-enter the fresh pool
local allLabels = root:findAllByType(ControlType.LABEL, true)
for i = 1, #allLabels do
    local lbl = allLabels[i]
    if lbl.tag == "inuse_grid" or lbl.tag == "inuse_step" then
        lbl.tag = ""
    end
end

-- Split root-level labels into used (inuse_main) and fresh pools
local usedLabels  = {}
local freshLabels = {}
for i = 1, #root.children do
    local child = root.children[i]
    if child.type == ControlType.LABEL then
        if child.tag == "inuse_main" then
            table.insert(usedLabels, child)
        elseif child.tag ~= "inuse_grid" and child.tag ~= "inuse_step" then
            table.insert(freshLabels, child)
        end
    end
end

-- Track which used labels have been reclaimed this run
local usedLabelClaimed = {}

-- Try to reclaim an already-placed label near a global frame position.
-- "above" match: label sits just above the frame (within margin)
-- "overlap" match: label overlaps the frame (for inside labels)
local function reclaimLabel(gx, gy, gw, gh, mode)
    local margin = labelPad + 20
    for i = 1, #usedLabels do
        if not usedLabelClaimed[i] then
            local lbl = usedLabels[i]
            local lf  = lbl.frame
            local match = false
            if mode == "above" then
                -- label should be horizontally aligned and just above
                match = math.abs(lf.x - gx) < margin
                    and lf.y >= gy - lf.h - margin - 10
                    and lf.y <= gy + margin
            elseif mode == "overlap" then
                -- label overlaps the control frame
                match = lf.x < gx + gw and lf.x + lf.w > gx
                    and lf.y < gy + gh  and lf.y + lf.h > gy
            end
            if match then
                usedLabelClaimed[i] = true
                return lbl
            end
        end
    end
    return nil
end

local freshIndex = 0
local function nextFreshLabel()
    freshIndex = freshIndex + 1
    if freshIndex > #freshLabels then
        print("WARNING: ran out of fresh labels at index " .. freshIndex)
        return nil
    end
    return freshLabels[freshIndex]
end

-- Get a label: try to reclaim an existing one first, else use fresh pool
local function getLabel(gx, gy, gw, gh, mode)
    local lbl = reclaimLabel(gx, gy, gw, gh, mode)
    if lbl then return lbl end
    return nextFreshLabel()
end

-- ── LABEL STYLING ────────────────────────────────────────────
local function styleLabel(lbl)
    lbl.textSize    = textSize
    lbl.textColor   = textColor
    lbl.background  = false
    lbl.outline     = false
    lbl.interactive = false
    lbl.tag         = "inuse_main"
    lbl.orientation = Orientation.NORTH
    lbl.textAlignH  = AlignH.CENTER
    lbl.textAlignV  = AlignV.MIDDLE
end

local function styleCellLabel(lbl)
    lbl.textSize    = textSize
    lbl.textColor   = textColor
    lbl.background  = true
    lbl.color       = cellLabelColor
    lbl.outline     = false
    lbl.interactive = false
    lbl.orientation = Orientation.NORTH
    lbl.textAlignH  = AlignH.CENTER
    lbl.textAlignV  = AlignV.MIDDLE
end

-- ── LABEL PLACEMENT ──────────────────────────────────────────
-- All functions take global canvas coordinates (gx, gy, gw, gh).

local function placeLabelAbove(name, gx, gy, gw, gh)
    local lbl = getLabel(gx, gy, gw, gh, "above")
    if not lbl then return end
    local lf = lbl.frame
    lf.x = gx
    lf.y = gy - lf.h - labelPad
    lf.w = gw
    lbl.frame = lf
    lbl.values.text = name
    lbl.name = name .. "_label"
    styleLabel(lbl)
    lbl.textAlignH = AlignH.LEFT
end

local function placeLabelInside(name, gx, gy, gw, gh, centered)
    local lbl = getLabel(gx, gy, gw, gh, "overlap")
    if not lbl then return end
    local lf = lbl.frame
    lf.x = gx + labelPad
    lf.y = gy + labelPad
    lf.w = gw - labelPad * 2
    lbl.frame = lf
    lbl.values.text = name
    lbl.name = name .. "_label"
    styleLabel(lbl)
    if centered then
        lbl.textAlignH = AlignH.CENTER
        lbl.textAlignV = AlignV.MIDDLE
    else
        lbl.textAlignH = AlignH.LEFT
        lbl.textAlignV = AlignV.TOP
    end
end

-- ── CELL / STEP LABELS ───────────────────────────────────────
-- ox, oy = global canvas origin of the control's parent group

local function placeGridCellLabels(ctrl, ox, oy)
    local cf    = ctrl.frame
    local count = #ctrl.children
    local gridCols = math.floor(math.sqrt(count) + 0.5)
    local gridRows = gridCols
    if gridCols < 1 then return end
    local cellW = cf.w / gridCols
    local cellH = cf.h / gridRows
    for row = 0, gridRows - 1 do
        for col = 0, gridCols - 1 do
            local n   = row * gridCols + col + 1
            local cgx = ox + cf.x + col * cellW
            local cgy = oy + cf.y + row * cellH
            local lbl = getLabel(cgx, cgy, cellW, cellH, "overlap")
            if lbl then
                local lblW = cellW * 0.5
                local lblH = cellH * 0.5
                local clf  = lbl.frame
                clf.x = cgx + (cellW - lblW) / 2
                clf.y = cgy + (cellH - lblH) / 2
                clf.w = lblW
                clf.h = lblH
                lbl.frame = clf
                lbl.values.text = tostring(n)
                lbl.name = ctrl.name .. "_c" .. n
                styleCellLabel(lbl)
                lbl.tag = "inuse_grid"
            end
        end
    end
end

local function placeRadioStepLabels(ctrl, ox, oy)
    local cf    = ctrl.frame
    local steps = ctrl.steps
    local isVert = (ctrl.orientation == Orientation.NORTH or
                    ctrl.orientation == Orientation.SOUTH)
    for s = 0, steps - 1 do
        local sgx, sgy, sgw, sgh
        if isVert then
            local cellH = cf.h / steps
            sgx = ox + cf.x
            sgy = oy + cf.y + s * cellH
            sgw = cf.w
            sgh = cellH
        else
            local cellW = cf.w / steps
            sgx = ox + cf.x + s * cellW
            sgy = oy + cf.y
            sgw = cellW
            sgh = cf.h
        end
        local lbl = getLabel(sgx, sgy, sgw, sgh, "overlap")
        if lbl then
            local sf = lbl.frame
            sf.x = sgx + (sgw - sgw * 0.5) / 2
            sf.y = sgy + (sgh - sgh * 0.5) / 2
            sf.w = sgw * 0.5
            sf.h = sgh * 0.5
            lbl.frame = sf
            lbl.values.text = tostring(s + 1)
            lbl.name = ctrl.name .. "_s" .. (s + 1)
            styleCellLabel(lbl)
            lbl.tag = "inuse_step"
        end
    end
end

-- ── LABEL A SINGLE CONTROL ───────────────────────────────────
-- ox, oy = global canvas origin of this control's parent (0,0 for root controls)
local function labelControl(ctrl, ox, oy)
    ox = ox or 0
    oy = oy or 0
    local t  = ctrl.type
    local cf = ctrl.frame
    local gx = ox + cf.x
    local gy = oy + cf.y

    if t == ControlType.GRID then
        placeLabelAbove(ctrl.name, gx, gy, cf.w, cf.h)
        placeGridCellLabels(ctrl, ox, oy)

    elseif t == ControlType.RADIO then
        placeLabelAbove(ctrl.name, gx, gy, cf.w, cf.h)
        placeRadioStepLabels(ctrl, ox, oy)

    elseif t == ControlType.XY or t == ControlType.RADAR then
        placeLabelInside(ctrl.name, gx, gy, cf.w, cf.h, false)

    elseif t == ControlType.ENCODER or t == ControlType.RADIAL then
        local lbl = getLabel(gx, gy, cf.w, cf.h, "overlap")
        if lbl then
            local lf = lbl.frame
            lf.x = gx
            lf.y = gy + (cf.h - cf.h * 0.5) / 2
            lf.w = cf.w
            lf.h = cf.h * 0.5
            lbl.frame = lf
            lbl.values.text = ctrl.name
            lbl.name = ctrl.name .. "_label"
            styleLabel(lbl)
            lbl.textAlignH = AlignH.CENTER
            lbl.textAlignV = AlignV.MIDDLE
        end

    elseif t == ControlType.FADER then
        local lbl = getLabel(gx, gy, cf.w, cf.h, "overlap")
        if lbl then
            local lf = lbl.frame
            if cf.w >= cf.h then
                -- Horizontal: 50% height, centered vertically, full width
                lf.x = gx
                lf.y = gy + (cf.h - cf.h * 0.5) / 2
                lf.w = cf.w
                lf.h = cf.h * 0.5
            else
                -- Vertical: 50% width, centered horizontally, full height, rotated
                lf.x = gx + (cf.w - cf.w * 0.5) / 2
                lf.y = gy
                lf.w = cf.w * 0.5
                lf.h = cf.h
            end
            lbl.frame = lf
            lbl.values.text = ctrl.name
            lbl.name = ctrl.name .. "_label"
            styleLabel(lbl)
            if cf.w < cf.h then
                lbl.orientation = Orientation.WEST
            end
            lbl.textAlignH = AlignH.CENTER
        end

    else
        -- Default: label above
        placeLabelAbove(ctrl.name, gx, gy, cf.w, cf.h)
    end
end

-- ── IS A GROUP? ──────────────────────────────────────────────
local function isGroup(ctrl)
    return #ctrl.children > 0
        and ctrl.type ~= ControlType.GRID
        and ctrl.type ~= ControlType.LABEL
end

-- ── PROCESS A GROUP ──────────────────────────────────────────
local function processGroup(group, globalMaster)
    local groupName = group.name

    -- Collect non-label, non-excluded children
    local controls = {}
    for i = 1, #group.children do
        local child = group.children[i]
        if child.type ~= ControlType.LABEL and child.tag ~= "none" then
            table.insert(controls, child)
        end
    end

    if #controls == 0 then return end

    -- Sort by x (group-local coords)
    table.sort(controls, function(a, b)
        return a.frame.x < b.frame.x
    end)

    -- Layout: place children left-to-right starting at groupPad
    local nextX = groupPad
    for i = 1, #controls do
        local child = controls[i]
        local f = child.frame
        f.x   = nextX
        f.y   = groupPad
        nextX = f.x + f.w + gap
        child.frame = f
    end

    -- Style copy from global master
    if globalMaster then
        for i = 1, #controls do
            copyStyle(globalMaster, controls[i])
        end
    end

    -- Rename
    local counters = {}
    for i = 1, #controls do
        local child = controls[i]
        local short, key = getShortAndKey(child)
        counters[key] = (counters[key] or 0) + 1
        local newName = groupName .. short .. counters[key]
        print("Renaming: " .. child.name .. " -> " .. newName)
        child.name = newName
    end

    -- Resize group: width = total span + right pad, height = tallest child + pad*2
    local maxH = 0
    for i = 1, #controls do
        local f = controls[i].frame
        if f.h > maxH then maxH = f.h end
    end
    local totalW = nextX - gap + groupPad  -- back off last gap, add right pad
    local totalH = maxH + groupPad * 2

    local gf = group.frame
    gf.w = totalW
    gf.h = totalH
    group.frame = gf

    -- Label children using group's global canvas position as offset
    if createLabels then
        for i = 1, #controls do
            labelControl(controls[i], gf.x, gf.y)
        end
        -- Label the group itself above its frame
        if createGroupLabels then
            placeLabelAbove(groupName, gf.x, gf.y, gf.w, gf.h)
        end
    end

    print("Group '" .. groupName .. "' done: " .. #controls ..
          " controls, frame " .. gf.x .. "," .. gf.y ..
          " " .. gf.w .. "x" .. gf.h)
end

-- ── FIND GLOBAL MASTER ───────────────────────────────────────
local globalMaster = nil
for i = 1, #root.children do
    local child = root.children[i]
    if child.tag == "master" then
        globalMaster = child
        break
    end
end

if globalMaster then
    print("Master found: " .. globalMaster.name)
else
    print("WARNING: no master-tagged control found at root — style copy skipped")
end

-- ── MAIN ─────────────────────────────────────────────────────
local processed = 0

for i = 1, #root.children do
    local child = root.children[i]
    if child.type == ControlType.LABEL then
        -- skip: label pool
    elseif child.tag == "none" then
        -- skip: manually excluded
    elseif isGroup(child) then
        processGroup(child, globalMaster)
        processed = processed + 1
    else
        -- Direct root control: style + label, no rename
        if globalMaster and child ~= globalMaster then
            copyStyle(globalMaster, child)
        end
        if createLabels then
            labelControl(child, 0, 0)
        end
        processed = processed + 1
    end
end

print("Done. Processed " .. processed .. " top-level items. Used " ..
      freshIndex .. " fresh labels.")