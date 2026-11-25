#!/usr/bin/env python3
"""MedveTalkie Bluetooth Manager: arrow/Enter-driven SSH menu. Stdlib only."""
import curses
import importlib.util
import os
import pty
import queue
import re
import select
import shutil
import signal
import subprocess
import threading
import time
import wave
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
MAC_PATTERN = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")
BLUEZ_LINE = re.compile(r"Device\s+("+MAC_PATTERN.pattern+r")\s*(.*)")
ACTIONS = [
    ("Обновить список", "refresh"), ("Поиск устройств BR/EDR · 12 с", "scan"),
    ("Подключить гарнитуру", "connect"), ("Отключить гарнитуру", "disconnect"),
    ("Сопряжение / ввод PIN", "pair"), ("Доверять устройству", "trust"),
    ("Профиль A2DP · музыка", "a2dp-sink"),
    ("Профиль HFP · mSBC", "headset-head-unit"),
    ("Профиль HFP · CVSD", "headset-head-unit-cvsd"),
    ("Записать голос · 6 с", "record"), ("Прослушать последнюю запись", "play"),
    ("Duplex · 10 с", "duplex"), ("Duplex + HCI-трасса", "trace"),
    ("Громкость динамика −10%", "sink-"), ("Громкость динамика +10%", "sink+"),
    ("Усиление микрофона −10%", "source-"), ("Усиление микрофона +10%", "source+"),
    ("Сведения об устройстве", "info"), ("Журнал операций", "logs"),
]
PROFILES = ("a2dp-sink", "headset-head-unit", "headset-head-unit-cvsd")


def command(argv, timeout=20):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, errors="replace",
                           timeout=timeout)
        return p.returncode, (p.stdout+"\n"+p.stderr).strip()[:6000]
    except (OSError, subprocess.TimeoutExpired) as e:
        return 124, str(e)


def invoke_user(program, *args):
    """Use the existing headless PipeWire session; never start another daemon."""
    import pwd
    name = os.environ.get("MT_AUDIO_USER", "medvetalkie")
    uid = pwd.getpwnam(name).pw_uid
    env = ["XDG_RUNTIME_DIR=/run/user/%d" % uid,
           "PULSE_SERVER=unix:/run/user/%d/pulse/native" % uid]
    if os.geteuid() == 0:
        return ["runuser", "-u", name, "--", "env", *env, program, *args]
    if os.geteuid() != uid:
        raise RuntimeError("Нужен sudo или пользователь "+name)
    return ["env", *env, program, *args]


def parse_devices(text):
    found = {}
    for line in text.splitlines():
        m = BLUEZ_LINE.search(line)
        if m:
            found[m.group(1).upper()] = (m.group(2).strip() or "(без имени)")
    return [{"mac":mac,"name":name} for mac,name in sorted(found.items(), key=lambda x:x[1].lower())]


def percent(text):
    match = re.search(r"\b(\d+)\s*%", text)
    return int(match.group(1)) if match else None


def parse_profile(cards, mac):
    section = next((part for part in cards.split("Card #")
                    if "Name: bluez_card."+mac.replace(":","_") in part), "")
    m = re.search(r"Active Profile:\s*(\S+)", section)
    return m.group(1) if m else "нет Bluetooth-карты"


def audio_devices(mac):
    slug = mac.replace(":","_")
    code, sinks = command(invoke_user("pactl","list","short","sinks"))
    if code: raise RuntimeError(sinks)
    code, sources = command(invoke_user("pactl","list","short","sources"))
    if code: raise RuntimeError(sources)
    sink = next((line.split()[1] for line in sinks.splitlines()
                 if len(line.split())>1 and line.split()[1].startswith("bluez_output."+slug+".")), None)
    source = next((line.split()[1] for line in sources.splitlines()
                   if len(line.split())>1 and line.split()[1].lower().startswith("bluez_input."+mac.lower())), None)
    return sink, source


def interact_bluetooth(controller, verb, device, answer_fn, event_fn, seconds=60):
    """Run bluetoothctl with a real PTY: handles PIN, passkey and yes/no agent prompts."""
    master, slave = pty.openpty()
    proc = subprocess.Popen(["bluetoothctl","-i",controller], stdin=slave,
                            stdout=slave, stderr=slave, start_new_session=True, close_fds=True)
    os.close(slave)
    buffer = ""
    sent = False
    deadline = time.monotonic()+seconds
    transcript = []
    try:
        os.write(master,b"agent KeyboardDisplay\n")
        os.write(master,b"default-agent\n")
        os.write(master,(verb+" "+device+"\n").encode())
        while time.monotonic()<deadline:
            if proc.poll() is not None: break
            readable, _, _ = select.select([master],[],[],.25)
            if not readable: continue
            try: data=os.read(master,4096)
            except OSError: break
            if not data: break
            chunk=re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", data.decode(errors="replace"))
            buffer=(buffer+chunk)[-10000:]
            transcript.append(chunk)
            event_fn(chunk)
            lower=buffer.lower()
            # Prompt may be displayed without a trailing newline.
            prompt = re.search(r"(?:Enter PIN code|Enter passkey|Confirm passkey|Request confirmation|Authorize service|Accept pairing|Confirm value|Passkey:|PIN code:)[^\r\n]{0,130}", buffer, re.I)
            if prompt:
                question=prompt.group(0)
                answer=answer_fn(question)
                if answer is None:
                    event_fn("\nОтменено пользователем\n")
                    break
                os.write(master,(answer+"\n").encode())
                buffer=""
            if any(x in lower for x in ("pairing successful","connection successful",
                                         "successful disconnected","successful disconnected",
                                         "trust succeeded","failed to", "not available",
                                         "authenticationfailed", "authentication failed")):
                # Give the agent a moment to report final status.
                time.sleep(.2)
                break
    finally:
        if proc.poll() is None:
            try: os.write(master,b"quit\n")
            except OSError: pass
            try: proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try: proc.wait(timeout=2)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        os.close(master)
    return "".join(transcript)[-6000:]


class Manager:
    def __init__(self, screen):
        self.s=screen
        self.page="devices"
        self.focus=0
        self.controllers=[]
        self.adapter=0
        self.devices=[]
        self.device_index=0
        self.menu_index=0
        self.log=[]
        self.note="Стрелки — выбор; Tab — панель; Enter — действие"
        self.messages=queue.Queue()
        self.pending=None
        self.running=""
        self.started=0
        self.last_wav={}
        self.status={}
        self._thread=None
        self.job("Обновление",self.refresh)

    def job(self, name, fn):
        if self._thread and self._thread.is_alive():
            self.note="Операция выполняется: "+self.running
            return
        self.running=name
        self.started=time.monotonic()
        def worker():
            try: self.messages.put(("done",name,fn(),None))
            except Exception as e: self.messages.put(("done",name,None,str(e)))
        self._thread=threading.Thread(target=worker,daemon=True)
        self._thread.start()

    def logline(self, text):
        self.log.extend(("%s %s"%(datetime.now().strftime("%H:%M:%S"),line))
                        for line in str(text).splitlines() if line.strip())
        self.log=self.log[-250:]

    def refresh(self):
        code,out=command(["bluetoothctl","list"])
        if code: raise RuntimeError(out)
        controllers=[]
        for line in out.splitlines():
            m=re.search(r"Controller\s+("+MAC_PATTERN.pattern+r")",line)
            if m: controllers.append(m.group(1).upper())
        selected=self.controller()
        target=selected if selected in controllers else (controllers[0] if controllers else None)
        devices=[]
        if target:
            code,out=command(["bluetoothctl","-i",target,"devices"])
            if code: raise RuntimeError(out)
            devices=parse_devices(out)
        self.messages.put(("inventory",controllers,target,devices))
        return "Обнаружено контроллеров: %d; устройств: %d"%(len(controllers),len(devices))

    def controller(self):
        return self.controllers[self.adapter] if self.adapter<len(self.controllers) else None

    def device(self):
        return self.devices[self.device_index] if self.device_index<len(self.devices) else None

    def bt(self, verb):
        control=self.controller()
        device=self.device()
        if not control or not device: raise RuntimeError("Нужны контроллер и выбранное устройство")
        return interact_bluetooth(control,verb,device["mac"],self.ask_agent,
                                 lambda v:self.messages.put(("log",v)),70 if verb=="pair" else 22)

    def ask_agent(self, prompt):
        response=queue.Queue(maxsize=1)
        self.messages.put(("agent",prompt,response))
        try: return response.get(timeout=80)
        except queue.Empty: return None

    def profile(self, name):
        mac=self.device()["mac"]
        code, out=command(invoke_user("pactl","set-card-profile",
                         "bluez_card."+mac.replace(":","_"),name))
        if code: raise RuntimeError(out)
        return "Профиль выбран: "+name

    def gain(self, target, increment):
        mac=self.device()["mac"]
        sink,source=audio_devices(mac)
        endpoint=sink if target=="sink" else source
        if not endpoint: raise RuntimeError("Устройство PipeWire отсутствует")
        cmd="get-sink-volume" if target=="sink" else "get-source-volume"
        code,out=command(invoke_user("pactl",cmd,endpoint))
        if code: raise RuntimeError(out)
        current=percent(out)
        if current is None: raise RuntimeError("Не удалось прочитать усиление: "+out)
        desired=min(150 if target=="source" else 100,max(0,current+increment))
        cmd="set-sink-volume" if target=="sink" else "set-source-volume"
        code,out=command(invoke_user("pactl",cmd,endpoint,"%d%%"%desired))
        if code: raise RuntimeError(out)
        return "%s: %d%% → %d%%"%(target,current,desired)

    def record(self):
        mac=self.device()["mac"]
        sink,source=audio_devices(mac)
        if not source: raise RuntimeError("Нужен режим HFP с микрофоном")
        stamp=time.strftime("%Y%m%d-%H%M%S")
        path="/tmp/medvetalkie-"+mac.replace(":","-")+"-"+stamp+".wav"
        # parecord runs in the service user account; unique /tmp path.
        args=invoke_user("parecord","--device="+source,
                         "--file-format=wav","--rate=16000","--channels=1",
                         "--format=s16le",path)
        p=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            p.wait(timeout=6)
        except subprocess.TimeoutExpired:
            p.terminate()
            try: p.wait(timeout=2)
            except subprocess.TimeoutExpired: p.kill();p.wait(timeout=2)
        if not Path(path).exists() or Path(path).stat().st_size<1000:
            raise RuntimeError("Запись не создана: "+p.stderr.read().decode(errors="replace")[:300])
        self.messages.put(("lastwav",mac,path))
        return "Запись 5–6 с: "+path

    def play(self):
        mac=self.device()["mac"]
        path=self.last_wav.get(mac)
        if not path or not Path(path).exists():
            raise RuntimeError("Сначала выполните запись для этой гарнитуры")
        sink,_=audio_devices(mac)
        if not sink: raise RuntimeError("Нет выхода PipeWire для гарнитуры")
        code,out=command(invoke_user("paplay","--device="+sink,path),25)
        if code: raise RuntimeError(out)
        return "Воспроизведено: "+path

    def duplex(self, trace):
        spec=importlib.util.spec_from_file_location("mt_audio_bench",ROOT/"bt_audio_bench.py")
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result=module.execute(self.device()["mac"],seconds=10,monitor=trace)
        self.messages.put(("lastwav",self.device()["mac"],result["recording"]))
        return ("Duplex: "+result["profile"]+"\n"
                "Запись: "+result["recording"]+"\n"
                "Peak: %s dBFS; RMS: %s dBFS; clipped: %s\n"%(result["metrics"]["peak_dbfs"],
                                  result["metrics"]["rms_dbfs"],result["metrics"]["clipped"])
                +("HCI: "+result.get("btmon","") if trace else ""))

    def choose(self, action):
        if action=="logs": self.page="logs"; return
        if action=="refresh": self.job("Обновление",self.refresh);return
        if action=="scan":
            c=self.controller()
            if not c:self.note="Нет адаптера";return
            def scan():
                code,out=command(["bluetoothctl","-i",c,"--timeout","12","scan","bredr"],17)
                self.messages.put(("log",out))
                self.refresh()
                return "Поиск завершён; код "+str(code)
            self.job("Сканирование",scan);return
        if not self.device():self.note="Выберите устройство";return
        if action in ("connect","disconnect","pair","trust"):
            self.pending=("confirm",action)
            self.note="Подтвердите действие Enter или отмените Esc"
        elif action in PROFILES:
            self.job("Смена профиля",lambda:self.profile(action))
        elif action=="record": self.job("Запись",self.record)
        elif action=="play": self.job("Воспроизведение",self.play)
        elif action in ("duplex","trace"):
            self.pending=("confirm",action)
            self.note="10 секунд аудиотеста — Enter подтвердить; Esc отменить"
        elif action.startswith(("sink","source")):
            target="sink" if action.startswith("sink") else "source"
            self.job("Громкость",lambda:self.gain(target,10 if action.endswith("+") else -10))
        elif action=="info":
            c=self.controller(); mac=self.device()["mac"]
            self.job("Сведения",lambda:command(["bluetoothctl","-i",c,"info",mac])[1])
            self.page="logs"

    def confirmed(self, action):
        if action in ("connect","disconnect","pair","trust"):
            self.job(action,lambda:self.bt(action))
        elif action in ("duplex","trace"):
            self.job(action,lambda:self.duplex(action=="trace"))

    def drain(self):
        while not self.messages.empty():
            data=self.messages.get_nowait()
            if data[0]=="inventory":
                _,controllers,target,devices=data
                current=self.device()
                self.controllers=controllers
                self.adapter=controllers.index(target) if target in controllers else 0
                old_mac=current["mac"] if current else None
                self.devices=devices
                self.device_index=next((i for i,d in enumerate(devices) if d["mac"]==old_mac),0)
            elif data[0]=="done":
                _,label,result,error=data
                self.running=""
                self.note=("%s: ошибка %s"%(label,error) if error else str(result or label))[:150]
                self.logline(self.note)
            elif data[0]=="log":self.logline(data[1])
            elif data[0]=="lastwav":self.last_wav[data[1]]=data[2]
            elif data[0]=="agent":
                self.pending=("agent",data[1],data[2])
                self.note="Bluetooth запрос: "+data[1]

    def get_input(self, title, hidden=False):
        h,w=self.s.getmaxyx()
        curses.echo() if not hidden else curses.noecho()
        curses.curs_set(1)
        self.s.nodelay(False)
        try:
            self.s.move(h-3,1)
            self.s.clrtoeol()
            self.put(h-3,1,title)
            self.s.refresh()
            result=self.s.getstr(h-2,2,32).decode(errors="replace").strip()
        finally:
            self.s.nodelay(True)
            curses.noecho()
            curses.curs_set(0)
        return result

    def put(self,y,x,value,attr=0):
        h,w=self.s.getmaxyx()
        if 0<=y<h and x<w:
            try:self.s.addnstr(y,x,str(value),max(0,w-x-1),attr)
            except curses.error:pass

    def draw(self):
        self.s.erase()
        h,w=self.s.getmaxyx()
        if h<21 or w<84:
            self.put(0,0,"Нужен терминал не меньше 84 × 21");self.s.refresh();return
        self.put(0,2,"MEDVETALKIE  /  BLUETOOTH MANAGER",curses.color_pair(4)|curses.A_BOLD)
        self.put(1,2,"Контроллер: "+str(self.controller() or "нет")+"   [PgUp / PgDn для смены]",curses.color_pair(4))
        self.put(2,2,"Tab: панель  ↑↓: выбор  Enter: действие  Esc: назад  Q: выход",curses.A_DIM)
        self.put(4,2,"УСТРОЙСТВА",curses.A_BOLD)
        self.put(4,37,"ДЕЙСТВИЯ",curses.A_BOLD)
        height=h-12
        first=max(0,self.device_index-height+1)
        for i,d in enumerate(self.devices[first:first+height],first):
            text="%s %-17s"%(d["name"][:13],d["mac"])
            attr=curses.A_REVERSE if self.focus==0 and i==self.device_index else 0
            self.put(5+i-first,2,text[:33],attr)
        if not self.devices:self.put(5,2,"Не найдены. Выберите Поиск.",curses.color_pair(3))
        start=max(0,self.menu_index-height+1)
        for i,(label,_) in enumerate(ACTIONS[start:start+height],start):
            attr=curses.A_REVERSE if self.focus==1 and i==self.menu_index else 0
            self.put(5+i-start,37,label[:w-40],attr)
        device=self.device()
        self.put(h-7,2,"ВЫБРАНО: "+(device["name"]+" "+device["mac"] if device else "нет"),curses.color_pair(2))
        if self.running:
            self.put(h-6,2,"◐ "+self.running+" %.1f с"%(time.monotonic()-self.started),curses.color_pair(3))
        if self.pending:
            self.put(h-5,2,"ЗАПРОС: "+self.note,curses.color_pair(3)|curses.A_BOLD)
        else:
            self.put(h-5,2,self.note,curses.color_pair(2))
        self.put(h-3,2,"Посл. запись: "+str(self.last_wav.get(device["mac"],"—") if device else "—"),curses.A_DIM)
        self.s.refresh()

    def show_logs(self):
        self.s.erase()
        h,w=self.s.getmaxyx()
        self.put(0,2,"ЖУРНАЛ  /  Esc — назад",curses.A_BOLD)
        for i,line in enumerate(self.log[-max(1,h-3):]):
            self.put(i+2,1,line)
        self.s.refresh()

    def loop(self):
        self.s.keypad(True);self.s.nodelay(True)
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        for num,color in ((2,curses.COLOR_GREEN),(3,curses.COLOR_YELLOW),(4,curses.COLOR_CYAN)):
            curses.init_pair(num,color,-1)
        while True:
            self.drain()
            self.show_logs() if self.page=="logs" else self.draw()
            key=self.s.getch()
            if key==-1: time.sleep(.07);continue
            if self.pending and self.pending[0]=="agent":
                _,prompt,answer=self.pending
                self.pending=None
                if key==27: answer.put(None)
                else:
                    val=self.get_input(prompt+"  (Enter = подтвердить)")
                    if re.search(r"confirm|authoriz|accept",prompt,re.I):
                        val=val or "yes"
                    answer.put(val or None)
                continue
            if self.pending and self.pending[0]=="confirm":
                action=self.pending[1];self.pending=None
                if key in (10,13,curses.KEY_ENTER):self.confirmed(action)
                else:self.note="Отменено"
                continue
            if key in (ord("q"),ord("Q")):break
            if key==27:self.page="devices";continue
            if self.page=="logs":continue
            if key in (9,curses.KEY_BTAB,curses.KEY_LEFT,curses.KEY_RIGHT):
                self.focus=1-self.focus
            elif key in (curses.KEY_PPAGE,ord("[")):
                self.adapter=max(0,self.adapter-1)
                self.devices=[];self.device_index=0;self.job("Обновление",self.refresh)
            elif key in (curses.KEY_NPAGE,ord("]")):
                self.adapter=min(max(0,len(self.controllers)-1),self.adapter+1)
                self.devices=[];self.device_index=0;self.job("Обновление",self.refresh)
            elif key in (curses.KEY_UP,ord("k")):
                if self.focus==0:self.device_index=max(0,self.device_index-1)
                else:self.menu_index=max(0,self.menu_index-1)
            elif key in (curses.KEY_DOWN,ord("j")):
                if self.focus==0:self.device_index=min(max(0,len(self.devices)-1),self.device_index+1)
                else:self.menu_index=min(len(ACTIONS)-1,self.menu_index+1)
            elif key in (10,13,curses.KEY_ENTER):
                if self.focus==0:self.focus=1
                else:self.choose(ACTIONS[self.menu_index][1])


def main():
    if not shutil.which("bluetoothctl"):
        raise SystemExit("Не установлен bluez / bluetoothctl")
    if not os.isatty(0):raise SystemExit("Нужна настоящая SSH/TTY сессия")
    curses.wrapper(lambda stdscr:Manager(stdscr).loop())


if __name__=="__main__":
    main()
