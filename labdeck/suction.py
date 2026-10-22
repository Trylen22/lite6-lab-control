"""Verified Lite 6 suction output transitions, independent of arm motion.

Manufacturer states: ON=(DO0=1, DO1=0), OFF/release=(DO0=0, DO1=1).
Live trials found the SDK's paired command could acknowledge ON yet leave both
outputs low. Check readback; if necessary, apply ordered individual writes while
stationary, verifying each bit before the next. Never treat an ACK as a seal.
"""

import time


def checked_vacuum(arm, enabled, wait=False, timeout=2, sync=False, sleep=time.sleep):
    """SDK-like return code; output faults raise, missing attachment returns 41."""

    def read(result):
        code, payload = result
        if code != 0:
            raise RuntimeError(f"Suction read failed: {code}")
        return payload

    def idle():
        if read(arm.get_state()) != 2 or read(arm.get_err_warn_code()) != [0, 0]:
            raise RuntimeError("Suction transition requires healthy stationary arm")

    expected = [1, 0, 0, 0, 0] if enabled else [0, 1, 0, 0, 0]
    idle()
    current = read(arm.get_tgpio_output_digital())
    if current[2:] != [0, 0, 0]:
        raise RuntimeError("Unexpected other tool outputs; no tool rewrite")
    # An explicit OFF request reasserts release even when readback already
    # matches. An already-ON seal is preserved without pulsing the outputs.
    if current != expected or not enabled:
        code = arm.set_vacuum_gripper(enabled, wait=False, sync=sync)
        if code != 0:
            return code
        for _ in range(5):
            sleep(0.1)
            idle()
            current = read(arm.get_tgpio_output_digital())
            if current == expected:
                break
        else:
            # Explicit verification prevents a lost/late paired update from
            # silently authorizing contact movement. Clear the opposing line
            # first, then assert the requested line; both-high is never a goal.
            sequence = [(1, 0), (0, 1)] if enabled else [(0, 0), (1, 1)]
            for channel, state in sequence:
                idle()
                code = arm.set_tgpio_digital(channel, state, sync=False)
                if code != 0:
                    return code
                for _ in range(10):
                    sleep(0.1)
                    idle()
                    current = read(arm.get_tgpio_output_digital())
                    if current[channel] == state:
                        break
                else:
                    raise RuntimeError("Individual suction output failed readback")
            current = read(arm.get_tgpio_output_digital())
            if current != expected:
                raise RuntimeError("Final suction output pair not verified")
    if wait:
        # The outputs indicate pump/valve commands; DI0 independently indicates
        # the observed vacuum seal. Require BOTH before allowing any lift.
        for _ in range(max(1, round(timeout * 10))):
            idle()
            if read(arm.get_tgpio_output_digital()) != expected:
                raise RuntimeError("Suction outputs changed while waiting for seal")
            if read(arm.get_tool_digital_input())[0] == int(enabled):
                return 0
            sleep(0.1)
        return 41
    return 0
