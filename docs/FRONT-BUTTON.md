# Front-button behavior and requested shutdown tune

The accepted QNAP button controller reports a sustained power-button press after
about two seconds through MCU `@CV`; it does not expose individual quick press and
release edges. The installed held-button policy continues to request a normal
clean shutdown. RESET continues to request an ordinary reboot. Neither erases
configuration. The final power-off hook removes power only after filesystem and
RAID shutdown. Check Settings → General & power for the installed policy.

Five **quick** presses cannot currently be counted reliably from that accepted
interface. The fixed short-beep MCU command also does not provide a validated
pitch parameter, and this unit exposes no accepted audio-output device. Issuing
unidentified MCU or GPIO writes could affect cooling, power or other hardware;
none are introduced here. No five-tap option is falsely offered as enabled.

The owner-requested tune is preserved as a platform-neutral note/timing
specification in `hardware/ts431xeu/shutdown-melody.json`: 116 BPM, 0.82
articulation, the exact requested notes and rests. It is disabled. No private
application code is imported. It has not been played on this NAS.

To finish this hardware feature:

1. With the owner present and healthy/idle storage, passively observe quick taps
   and determine whether an independent raw button GPIO or documented MCU event
   exposes every press/release. Preserve the existing held-button escape path.
2. Validate a pitch-capable output path, potentially optional USB audio with a
   speaker. The existing fixed-tone buzzer alone cannot reproduce the tune.
3. Test debouncing, five-tap timing, incomplete/late sequences, startup-held input,
   duplicate events, unavailable sound and clean-shutdown fallback in isolation.
4. Only then enable the feature, document the accepted hardware path and perform
   an owner-observed orderly shutdown/cold-start with data checks.

`system.button-status` reports these capabilities and limits to administrators
and specifically authorized agents. Software status is not physical acceptance.
