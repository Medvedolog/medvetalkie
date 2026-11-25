#!/usr/bin/env python3
"""Controller-scoped BlueZ 5.82 CLI, without nonexistent bluetoothctl -i option."""
import re
import subprocess

MAC = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ERROR = re.compile(r"(?:^|\n)(?:Failed to |Error: |Invalid command|No default controller)", re.I)


class BluezCommandError(RuntimeError):
    pass


def selected(controller, command, timeout=12, runner=subprocess.run):
    """Run select + query in ONE bluetoothctl session, not separate processes.

    stdin accepts sequential bluetoothctl commands (as confirmed by BlueZ docs).
    Only allow the non-mutating inventory/info subset to avoid CLI injection.
    """
    if not MAC.fullmatch(controller):
        raise ValueError("Invalid controller MAC")
    parts = command.split()
    if not parts or parts[0] not in ("devices", "info"):
        raise ValueError("Only devices/info inspection supported")
    if parts[0] == "devices":
        if len(parts) not in (1, 2) or (
             len(parts) == 2 and parts[1] not in ("Connected", "Paired", "Bonded", "Trusted")):
            raise ValueError("Invalid devices filter")
    elif len(parts) != 2 or not MAC.fullmatch(parts[1]):
        raise ValueError("Invalid info address")
    try:
        result = runner(["bluetoothctl"], input="select "+controller+"\n"+
                        command+"\nquit\n", text=True, capture_output=True,
                        errors="replace", timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BluezCommandError(str(exc)) from exc
    output = ANSI.sub("", (result.stdout or "")+"\n"+(result.stderr or ""))
    if result.returncode:
        raise BluezCommandError(output.strip()[:400] or ("bluetoothctl exit "+str(result.returncode)))
    if ERROR.search(output):
        raise BluezCommandError(output.strip()[:400])
    # The selected adapter should appear in output; if not, a "devices"
    # result might actually belong to another controller.
    if not re.search(r"Controller\s+"+re.escape(controller)+r"\b", output, re.I):
        raise BluezCommandError("Controller selection was not confirmed for "+controller+
                                ": "+output.strip()[:300])
    return output
