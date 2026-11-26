#!/usr/bin/env python3
"""BlueZ 5.82 read-only per-controller queries via a synchronized PTY session.

bluetoothctl has no -i option. Avoid piping select/query/quit at once:
the select operation is asynchronous and subsequent commands can be dispatched
before it takes effect. Confirm select before sending the query.
"""
import os
import pty
import re
import select
import signal
import subprocess
import time

MAC = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ERROR = re.compile(r"(?:Failed to |Error: |Invalid command|No default controller)", re.I)
PROMPT = re.compile(r"\[[^\]\r\n]{1,100}\]>\s*$")


class BluezCommandError(RuntimeError):
    pass


def validate(controller, command):
    if not MAC.fullmatch(controller):
        raise ValueError("Invalid controller MAC")
    parts = command.split()
    if not parts or parts[0] not in ("devices", "info"):
        raise ValueError("Only devices/info inspection supported")
    if parts[0] == "devices":
        if len(parts) not in (1, 2) or (
                len(parts) == 2 and parts[1] not in (
                    "Connected", "Paired", "Bonded", "Trusted")):
            raise ValueError("Invalid devices filter")
    elif len(parts) != 2 or not MAC.fullmatch(parts[1]):
        raise ValueError("Invalid info address")
    # Reconstruct from validated tokens: never pass newlines/commands to shell.
    if command != " ".join(parts):
        raise ValueError("Non-canonical command string")


def clean(raw):
    # BlueZ readline can reprint prompts using CR and terminal clear sequences.
    return ANSI.sub("", raw.decode("utf-8", errors="replace")).replace("\r", "\n")


def response_ready(output, command):
    """A command is finished only when the NEXT prompt follows its echo."""
    marker = re.search(r"(?:^|\n)\[[^\]\n]{1,100}\]>\s*"+
                       re.escape(command)+r"\s*(?:\n|$)", output)
    if marker is None:
        return False
    return bool(PROMPT.search(output[marker.end():]))


def selected(controller, command, timeout=15):
    """Execute read-only query after *confirmed* adapter selection.

    No global adapter change survives the short-lived bluetoothctl process.
    """
    validate(controller, command)
    master, slave = pty.openpty()
    proc = None
    try:
        proc = subprocess.Popen(["bluetoothctl"], stdin=slave, stdout=slave,
                                stderr=slave, start_new_session=True,
                                close_fds=True)
        os.close(slave)
        slave = -1
        deadline = time.monotonic()+timeout
        chunks = []

        def collect_until(predicate, stage):
            text = ""
            while time.monotonic() < deadline:
                if predicate(text):
                    return text
                readable, _, _ = select.select([master], [], [],
                                               min(.2, max(.01, deadline-time.monotonic())))
                if readable:
                    try:
                        data = os.read(master, 8192)
                    except OSError:
                        break
                    if not data:
                        break
                    chunks.append(data)
                    text = clean(b"".join(chunks)[-65536:])
                    if ERROR.search(text):
                        raise BluezCommandError(stage+": "+text[-600:])
                if proc.poll() is not None:
                    break
            raise BluezCommandError(stage+" timeout or exited: "+text[-500:])

        # Wait for BlueZ to be ready before selecting the controller.
        collect_until(lambda text: bool(PROMPT.search(text)), "initial BlueZ prompt")
        chunks.clear()
        os.write(master, ("select "+controller+"\n").encode("ascii"))
        # Selection acknowledgement, not just the echoed select command.
        confirmation = re.compile(r"(?:^|\n)Controller\s+"+
                                  re.escape(controller)+r"(?:\s|$)", re.I)
        collect_until(lambda text: bool(confirmation.search(text) and
                                       PROMPT.search(text)), "controller selection")
        chunks.clear()
        os.write(master, (command+"\n").encode("ascii"))
        result = collect_until(lambda text: response_ready(text,command),
                               "device query")
        return result
    finally:
        if proc is not None and proc.poll() is None:
            try:
                os.write(master, b"quit\n")
                proc.wait(timeout=1.5)
            except (OSError, subprocess.TimeoutExpired):
                proc.terminate()
                try:
                    proc.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=1)
        if slave >= 0:
            os.close(slave)
        os.close(master)
