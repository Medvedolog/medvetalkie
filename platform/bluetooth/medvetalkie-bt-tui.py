#!/usr/bin/env python3
"""MedveTalkie Bluetooth bench TUI: zero third-party Python dependencies.

Keys: 1/2 adapter, S timed BR/EDR scan, R refresh, arrows device selection,
I device details, C connect, P pair (explicit), H audio diagnostics,
L full log, Q quit. Does not alter display, network or system configuration.
"""
import curses
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

HEADSET = "41:42:63:27:E7:3A"
MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")
SPIN = "|/-\\"
COLOR_OK, COLOR_WARN, COLOR_ERR, COLOR_TITLE = 1, 2, 3, 4


def run(argv, timeout=15, env=None):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, errors="replace",
                           timeout=timeout, env=env, check=False)
        output = (p.stdout + ("\n" + p.stderr if p.stderr else "")).strip()
        return p.returncode, output[:12000]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, str(exc)


def controllers():
    code, output = run(["bluetoothctl", "list"], 8)
    if code:
        return [], output
    found = []
    for line in output.splitlines():
        m = re.search(r"Controller\s+(" + MAC.pattern + r")\s+(.+)", line)
        if m:
            found.append({"mac": m.group(1).upper(), "name": m.group(2)})
    return found, ""


def discovered(controller):
    # Display cache is per selected adapter when supported by bluetoothctl.
    args = ["bluetoothctl", "-i", controller, "devices"]
    code, output = run(args, 10)
    if code:
        return [], output
    found = []
    for line in output.splitlines():
        m = re.search(r"Device\s+(" + MAC.pattern + r")(?:\s+(.*))?$", line)
        if m:
            mac = m.group(1).upper()
            found.append({"mac": mac, "name": (m.group(2) or "Без имени").strip()})
    found.sort(key=lambda item: (item["mac"] != HEADSET, item["name"].casefold()))
    return found, ""


def has_profile(text):
    return ("Handsfree" in text or "Headset" in text or
            "0000111e-" in text or "00001108-" in text)


def short_info(text):
    allowed = ("Name:", "Alias:", "Icon:", "Paired:", "Bonded:", "Trusted:",
               "Connected:", "UUID:", "RSSI:", "Class:")
    return [line.strip() for line in text.splitlines()
            if line.strip().startswith(allowed)][:28]


def audio_check():
    user = os.environ.get("MT_AUDIO_USER", "medvetalkie")
    try:
        import pwd
        uid = pwd.getpwnam(user).pw_uid
    except (KeyError, ImportError):
        return "Нет пользователя %s" % user
    runtime = "/run/user/%d" % uid
    lines = ["Audio user: %s, UID=%d" % (user, uid)]
    for path in (runtime + "/pipewire-0", runtime + "/pulse/native"):
        lines.append("%s: %s" % (path, "OK" if os.path.exists(path) else "ОТСУТСТВУЕТ"))
    if os.geteuid() == 0:
        command = ["runuser", "-u", user, "--", "env",
                   "XDG_RUNTIME_DIR=" + runtime,
                   "PULSE_SERVER=unix:" + runtime + "/pulse/native",
                   "pactl", "list", "cards"]
    elif os.environ.get("USER") == user:
        command = ["pactl", "list", "cards"]
    else:
        return "\n".join(lines + ["Запустите TUI через sudo для проверки аудиосессии."])
    code, output = run(command, 12)
    if code:
        return "\n".join(lines + ["pactl: " + output])
    subset = [line.strip() for line in output.splitlines()
              if ("bluez_card." in line or "Active Profile:" in line or
                  "headset-head-unit" in line or "handsfree" in line.lower())]
    lines += subset[:35] or ["Нет Bluetooth-карт PipeWire (или нет подключённых гарнитур)."]
    lines.append("Профиль/Connected не доказывает наличие SCO и звука.")
    return "\n".join(lines)


class Bench:
    def __init__(self):
        self.adapters = []
        self.adapter = 0
        self.devices = []
        self.selected = 0
        self.logs = []
        self.full_log = False
        self.notice = "R — обновить; S — поиск BR/EDR; Q — выход"
        self.busy = ""
        self.started = 0.0
        self.results = queue.Queue()
        self._thread = None
        self.last_refresh = 0.0
        self.pending_pair = None

    def addlog(self, message):
        stamp = time.strftime("%H:%M:%S")
        self.logs.extend("%s  %s" % (stamp, line) for line in str(message).splitlines())
        self.logs = self.logs[-160:]

    def work(self, label, fn):
        if self._thread is not None and self._thread.is_alive():
            self.notice = "Операция уже выполняется: " + self.busy
            return
        self.busy = label
        self.started = time.monotonic()
        def task():
            try:
                result = fn()
                self.results.put((label, result, None))
            except Exception as exc:
                self.results.put((label, None, str(exc)))
        self._thread = threading.Thread(target=task, daemon=True)
        self._thread.start()

    def update(self):
        while True:
            try:
                label, result, error = self.results.get_nowait()
            except queue.Empty:
                break
            self.busy = ""
            if error:
                self.notice = "Ошибка: " + error
                self.addlog(self.notice)
                continue
            kind, data = result
            if kind == "refresh":
                adapters, devices, messages = data
                old = self.current_mac()
                self.adapters = adapters
                self.adapter = next((i for i, a in enumerate(adapters)
                                     if a["mac"] == old), 0)
                self.devices = devices
                self.selected = min(self.selected, max(0, len(devices)-1))
                self.notice = "Обновлено: %d контроллер(ов), %d устройств" % (
                    len(adapters), len(devices))
                if messages:
                    self.addlog(messages)
                self.last_refresh = time.monotonic()
            elif kind == "scan":
                code, output = data
                self.addlog("Сканирование BR/EDR: exit=%s\n%s" % (code, output))
                self.notice = "Поиск завершён. Нажмите R для обновления списка."
                self.refresh()
            else:
                code, output = data
                self.addlog("%s: exit=%s\n%s" % (label, code, output))
                self.notice = label + (" — выполнено" if code == 0 else " — ошибка; L — журнал")
                if kind in ("connect", "pair"):
                    self.refresh()

    def current_mac(self):
        if self.adapters and self.adapter < len(self.adapters):
            return self.adapters[self.adapter]["mac"]
        return None

    def selected_device(self):
        return self.devices[self.selected] if self.devices else None

    def refresh(self):
        old = self.current_mac()
        def task():
            adapters, err = controllers()
            controller = old if old and any(a["mac"] == old for a in adapters) else (
                adapters[0]["mac"] if adapters else None)
            devices, err2 = discovered(controller) if controller else ([], "BlueZ: нет контроллеров")
            return "refresh", (adapters, devices, err + "\n" + err2)
        self.work("Обновление устройств", task)

    def command(self, kind):
        mac = self.current_mac()
        device = self.selected_device()
        if not mac:
            self.notice = "Контроллер не выбран"
            return
        if kind == "scan":
            self.work("Поиск BR/EDR (~12 с)", lambda: (
                "scan", run(["bluetoothctl", "-i", mac, "--timeout", "12",
                             "scan", "bredr"], 17)))
        elif kind in ("info", "connect", "pair"):
            if not device:
                self.notice = "Сначала обнаружьте устройство"
                return
            addr = device["mac"]
            # Never remove bond or trust a device implicitly.
            if kind == "pair":
                self.pending_pair = addr
                self.notice = "Подтвердить PAIR %s? Y — да, N — отмена" % addr
                return
            self.work("%s %s" % (kind.upper(), addr), lambda: (
                kind, run(["bluetoothctl", "-i", mac, kind, addr],
                          45 if kind == "pair" else 20)))
        elif kind == "audio":
            self.work("Диагностика PipeWire", lambda: ("audio", (0, audio_check())))

    @staticmethod
    def put(win, y, x, value, attr=0):
        h, w = win.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        try:
            win.addnstr(y, x, str(value), max(0, w-x-1), attr)
        except curses.error:
            pass

    def draw(self, win):
        win.erase()
        h, w = win.getmaxyx()
        if h < 18 or w < 64:
            self.put(win, 0, 1, "Увеличьте терминал до 64×18")
            win.refresh()
            return
        spinner = SPIN[int(time.monotonic()*8) % len(SPIN)]
        title = " MedveTalkie | Bluetooth Bench | OPi Zero 3 "
        self.put(win, 0, 1, title, curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        self.put(win, 1, 1, "Наблюдение / тестирование. HFP ≠ проверенный SCO/PCM.",
                 curses.A_DIM)
        self.put(win, 2, 1, "Контроллеры BlueZ:", curses.A_BOLD)
        for i, a in enumerate(self.adapters[:2]):
            flag = "►" if i == self.adapter else " "
            self.put(win, 3+i, 2, "%s [%d] %s  %s" %
                     (flag, i+1, a["mac"], a["name"]),
                     curses.color_pair(COLOR_OK if i == self.adapter else COLOR_TITLE))
        if not self.adapters:
            self.put(win, 3, 2, "Контроллеры не обнаружены", curses.color_pair(COLOR_ERR))
        self.put(win, 6, 1, "Устройства в кэше BlueZ: %d" % len(self.devices), curses.A_BOLD)
        if not self.full_log:
            available = max(3, h-15)
            start = max(0, self.selected-available+1)
            for i in range(start, min(len(self.devices), start+available)):
                device = self.devices[i]
                prefix = "►" if i == self.selected else " "
                color = COLOR_OK if device["mac"] == HEADSET else COLOR_TITLE
                self.put(win, 7+i-start, 2, "%s %-17s %s" %
                         (prefix, device["mac"], device["name"]),
                         curses.color_pair(color) | (curses.A_BOLD if i == self.selected else 0))
            if not self.devices:
                self.put(win, 7, 2, "Пусто. S — поиск Classic, затем R — обновить.",
                         curses.color_pair(COLOR_WARN))
        else:
            self.put(win, 7, 1, "ЖУРНАЛ (L — вернуться)", curses.A_BOLD)
            for i, entry in enumerate(self.logs[-max(1,h-16):]):
                self.put(win, 8+i, 2, entry)
        if self.busy:
            elapsed = time.monotonic()-self.started
            status = "%s %s  %.1f с" % (spinner, self.busy, elapsed)
            self.put(win, h-7, 1, status, curses.color_pair(COLOR_WARN) | curses.A_BOLD)
            bar_width = max(8, min(38, w-8))
            step = int(elapsed*5) % bar_width
            self.put(win, h-6, 1, "[" + "".join("█" if j in
                     (step, (step+1)%bar_width, (step+2)%bar_width) else "·"
                     for j in range(bar_width)) + "]", curses.color_pair(COLOR_WARN))
        else:
            self.put(win, h-7, 1, self.notice, curses.color_pair(COLOR_OK))
        self.put(win, h-4, 1, "1/2 адаптер   ↑↓ выбор   S поиск   R обновить   I информация")
        self.put(win, h-3, 1, "C подключить  P сопрячь  H PipeWire  L журнал  Q выход")
        self.put(win, h-2, 1, "При ошибке profile-unavailable: H → L; без удаления bond.",
                 curses.A_DIM)
        win.refresh()

    def main(self, win):
        curses.curs_set(0)
        win.nodelay(True)
        win.keypad(True)
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            for ident, color in ((COLOR_OK, curses.COLOR_GREEN),
                                 (COLOR_WARN, curses.COLOR_YELLOW),
                                 (COLOR_ERR, curses.COLOR_RED),
                                 (COLOR_TITLE, curses.COLOR_CYAN)):
                curses.init_pair(ident, color, -1)
        self.refresh()
        while True:
            self.update()
            self.draw(win)
            key = win.getch()
            if self.pending_pair is not None:
                target = self.pending_pair
                self.pending_pair = None
                if key in (ord("y"), ord("Y")):
                    self.work("PAIR %s" % target, lambda: (
                        "pair", run(["bluetoothctl", "-i", self.current_mac(),
                                     "pair", target], 45)))
                else:
                    self.notice = "Сопряжение отменено"
                time.sleep(0.07)
                continue
            if key in (ord("q"), ord("Q"), 27):
                return
            elif key in (ord("1"), ord("2")):
                index = key-ord("1")
                if index < len(self.adapters):
                    self.adapter = index
                    self.devices = []
                    self.selected = 0
                    self.refresh()
            elif key in (curses.KEY_DOWN, ord("j")):
                self.selected = min(max(0,len(self.devices)-1),self.selected+1)
            elif key in (curses.KEY_UP, ord("k")):
                self.selected = max(0,self.selected-1)
            elif key in (ord("s"), ord("S")):
                self.command("scan")
            elif key in (ord("r"), ord("R")):
                self.refresh()
            elif key in (ord("i"), ord("I")):
                self.command("info")
            elif key in (ord("c"), ord("C")):
                self.command("connect")
            elif key in (ord("p"), ord("P")):
                self.command("pair")
            elif key in (ord("h"), ord("H")):
                self.command("audio")
            elif key in (ord("l"), ord("L")):
                self.full_log = not self.full_log
            time.sleep(0.07)


def main():
    if not shutil.which("bluetoothctl"):
        sys.exit("Bluetoothctl is missing: install bluez.")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.exit("Run in an interactive SSH terminal (TTY).")
    curses.wrapper(Bench().main)


if __name__ == "__main__":
    main()
