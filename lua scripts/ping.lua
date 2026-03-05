local g_controlMap = {}
local g_buffer = {}
local g_lastReceiveTime = nil
local g_threshold = 100

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
    if g_lastReceiveTime == nil then return end
    if next(g_buffer) == nil then return end
    local now = getMillis()
    if now - g_lastReceiveTime < g_threshold then return end
    for path, entry in pairs(g_buffer) do
        local value = entry.value
        -- for radar y, wrap value to 0-1 for display and notify control with raw value
        if entry.type == ControlType.RADAR and entry.msgIndex == 2 then
            entry.control.values.y = value % 1.0
            sendOSC(path, value)
            entry.control:notify('presetRecall', value)
            entry.control:notify('receiving', false)
        elseif entry.type == ControlType.ENCODER then
            entry.control.values.x = value % 1.0
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
end