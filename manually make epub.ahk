#Persistent

; Variables to control loop state
isLooping := false

; Hotkey to trigger the loop
q::
    ; Toggle the loop on or off
    isLooping := !isLooping

    ; If loop is active, start it
    while isLooping {
        ; Perform the actions
        MouseClick
        Sleep, 500
        Send, {Enter}
        Sleep, 500
        Send, ^w ; Ctrl + W
        Sleep, 500
    }
return
