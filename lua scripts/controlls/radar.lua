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
end