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
end