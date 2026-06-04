#!/usr/bin/env python3
"""
tms_tui.py - Terminal UI for the TMS controller.

Dependencies:
    pip install "textual>=0.60" pyserial

Run:
    python app.py                    # pick port interactively
    python app.py --port /dev/ttyACM0
    python app.py --port COM3 --divider 100 --max-adc 614
    python app.py --list             # list available serial ports and exit

Keybindings (see footer):
    c   charge / uncharge       a   arm / unarm
    f   FIRE                    r   reset
    s   status query            p   pick port
    d   disconnect              q   quit

Platform notes:
    - Linux/macOS: works in any modern terminal.
    - Windows: works in Windows Terminal, PowerShell, and the newer
      Command Prompt. Use the Cascadia Mono or similar font for block
      characters in the sparkline. WSL is not required.
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
from collections import deque
from datetime import datetime

import serial
import serial.tools.list_ports

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Label, ListItem, ListView, RichLog, Static

BAUD = 115200
SPARK_BLOCKS = " ▁▂▃▄▅▆▇█"
SPARK_WIDTH = 32
HISTORY_LEN = 100  # 10 s at 10 Hz telemetry


# ======================================================================
# Serial bridge (background read thread, main-thread writes)
# ======================================================================

class SerialBridge:
    def __init__(self) -> None:
        self.ser: serial.Serial | None = None
        self.rx_queue: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def is_open(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def open(self, port_name: str) -> None:
        if self.is_open():
            self.close()
        # Default pyserial config. No DTR/RTS toggling.
        # R4 Minima uses native USB CDC so opening does not reset the MCU.
        self.ser = serial.Serial(port_name, BAUD, timeout=0.1)
        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        t = self._thread
        self._thread = None
        if t and t.is_alive():
            t.join(timeout=0.5)
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def send(self, cmd: str) -> None:
        if not self.is_open():
            return
        try:
            self.ser.write((cmd + "\n").encode("ascii"))
        except Exception as e:
            self.rx_queue.put(f"__WRITE_ERROR__:{e}")

    def _read_loop(self) -> None:
        buf = ""
        while not self._stop.is_set():
            try:
                data = self.ser.read(256) if self.ser else b""
            except Exception as e:
                self.rx_queue.put(f"__READ_ERROR__:{e}")
                return
            if not data:
                continue
            buf += data.decode("ascii", errors="replace")
            while True:
                nl = buf.find("\n")
                if nl < 0:
                    break
                line = buf[:nl].rstrip("\r")
                buf = buf[nl + 1:]
                if line:
                    self.rx_queue.put(line)


# ======================================================================
# Helpers
# ======================================================================

def parse_kv(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tok in s.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    return out


def sparkline(values: list[int], width: int, vmax: int) -> str:
    if width <= 0:
        return ""
    if not values or vmax <= 0:
        return " " * width
    n = len(values)
    if n >= width:
        step = n / width
        chunks = [values[int(i * step):int((i + 1) * step)] for i in range(width)]
    else:
        chunks = [[] for _ in range(width - n)] + [[v] for v in values]
    out = []
    top = len(SPARK_BLOCKS) - 1
    for c in chunks:
        if not c:
            out.append(" ")
            continue
        avg = sum(c) / len(c)
        ratio = min(1.0, avg / vmax)
        out.append(SPARK_BLOCKS[int(ratio * top)])
    return "".join(out)


def ts() -> str:
    now = datetime.now()
    return now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"


# ======================================================================
# Port picker modal
# ======================================================================

class PortPicker(ModalScreen[str]):
    CSS = """
    PortPicker { align: center middle; }
    #pp-wrap {
        width: 70;
        max-width: 90%;
        height: auto;
        background: $panel;
        border: thick $accent;
        padding: 1 2;
    }
    #pp-title { content-align: center middle; margin-bottom: 1; }
    #pp-list { height: auto; max-height: 12; }
    #pp-hint { color: $text-muted; margin-top: 1; content-align: center middle; }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "cancel"),
        Binding("enter", "select", "connect", priority=True),
    ]

    def compose(self) -> ComposeResult:
        ports = list(serial.tools.list_ports.comports())
        items: list[ListItem] = []
        if not ports:
            items.append(ListItem(Label("[dim](no serial ports found)[/dim]"), name=""))
        else:
            for p in ports:
                desc = (p.description or "").strip()
                lbl = f"{p.device}  [dim]{desc}[/dim]" if desc else p.device
                items.append(ListItem(Label(lbl), name=p.device))
        yield Vertical(
            Label("[b]Select serial port[/b]", id="pp-title"),
            ListView(*items, id="pp-list"),
            Label("[dim]↑↓ move  enter connect  esc cancel[/dim]", id="pp-hint"),
            id="pp-wrap",
        )

    def on_mount(self) -> None:
        self.query_one("#pp-list", ListView).focus()

    def action_dismiss(self) -> None:
        self.dismiss(None)

    def action_select(self) -> None:
        lv = self.query_one("#pp-list", ListView)
        item = lv.highlighted_child
        name = getattr(item, "name", None) if item is not None else None
        if name:
            self.dismiss(name)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        name = getattr(event.item, "name", None)
        if name:
            self.dismiss(name)


# ======================================================================
# Main screen
# ======================================================================

class MainScreen(Screen):
    CSS = """
    Screen { background: $surface; }

    #top {
        height: 1;
        padding: 0 1;
        background: $primary-background;
        color: $text;
    }

    #main-row { height: 13; }

    #voltage-box {
        border: round $accent;
        width: 60%;
        padding: 0 1;
    }

    #state-box {
        border: round $accent;
        width: 40%;
        padding: 0 1;
    }

    #log-box {
        border: round $accent;
        height: 1fr;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("c", "charge", "charge"),
        Binding("a", "arm", "arm"),
        Binding("f", "fire", "FIRE"),
        Binding("r", "reset", "reset"),
        Binding("s", "status", "status"),
        Binding("p", "pick_port", "port"),
        Binding("d", "disconnect", "disconn"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, bridge: SerialBridge, divider: float, vref: float, max_adc: int,
                 avg_window: int) -> None:
        super().__init__()
        self.bridge = bridge
        self.divider = divider
        self.vref = vref
        self.max_adc = max_adc
        self.avg_window = max(1, avg_window)
        self.history: deque[int] = deque(maxlen=max(HISTORY_LEN, self.avg_window))
        # telemetry state
        self.tele_adc = 0
        self.tele_t_ms = 0
        self.tele_ok = False
        self.tele_chg = False
        self.tele_arm = False
        self.tele_hw = False
        self.connected = False
        self.port_name = ""

    def compose(self) -> ComposeResult:
        yield Static(id="top")
        with Horizontal(id="main-row"):
            yield Static(id="voltage-box")
            yield Static(id="state-box")
        yield RichLog(id="log-box", markup=True, max_lines=500)
        yield Footer()

    def on_mount(self) -> None:
        self.render_top()
        self.render_voltage()
        self.render_state()
        self.write_log("[dim]Ready. Press [b]p[/b] to pick a port.[/dim]")
        self.set_interval(0.05, self.drain_queue)

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------

    def render_top(self) -> None:
        top = self.query_one("#top", Static)
        if self.connected:
            top.update(
                f"[b]TMS CTRL[/b]  │  [green]● CONNECTED[/green]  "
                f"{self.port_name} @ {BAUD}  │  "
                f"divider={self.divider:g}  max_adc={self.max_adc}"
            )
        else:
            top.update(
                "[b]TMS CTRL[/b]  │  [red]○ DISCONNECTED[/red]  │  "
                "press [b]p[/b] to pick port"
            )

    def render_voltage(self) -> None:
        box = self.query_one("#voltage-box", Static)
        if not self.connected:
            box.update(
                "[b]VOLTAGE[/b]\n"
                "\n"
                "  [dim]— disconnected —[/dim]\n"
            )
            return
        v_pin = (self.tele_adc / 1023.0) * self.vref
        v_bus = v_pin * self.divider
        pct = (self.tele_adc / self.max_adc * 100.0) if self.max_adc else 0.0
        # moving average over the last N ADC samples
        window = list(self.history)[-self.avg_window:]
        n_avg = len(window)
        if n_avg > 0:
            avg_adc = sum(window) / n_avg
            v_bus_avg = (avg_adc / 1023.0) * self.vref * self.divider
            avg_str = f"{v_bus_avg:>8.1f}"
        else:
            avg_str = "     ---"
        ms = self.tele_t_ms
        tstr = f"{ms // 60000:02d}:{(ms // 1000) % 60:02d}.{ms % 1000:03d}"
        # sparkline colour reflects overvoltage proximity
        if pct >= 100:
            spark_col = "red"
        elif pct >= 80:
            spark_col = "yellow"
        else:
            spark_col = "cyan"
        spark = sparkline(list(self.history), SPARK_WIDTH, self.max_adc)
        v_bus_col = "red bold" if pct >= 100 else ("yellow bold" if pct >= 80 else "cyan bold")
        box.update(
            f"[b]VOLTAGE[/b]\n"
            f"  Bus    [{v_bus_col}]{v_bus:>8.1f}[/{v_bus_col}] V\n"
            f"  Bus μ  [cyan]{avg_str}[/cyan] V  [dim](N={n_avg}/{self.avg_window})[/dim]\n"
            f"  Pin    [cyan]{v_pin:>8.3f}[/cyan] V\n"
            f"  ADC    [cyan]{self.tele_adc:>4d}[/cyan] / 1023\n"
            f"  %Max   [cyan]{pct:>5.1f}[/cyan] %\n"
            f"  t+     [dim]{tstr}[/dim]\n"
            f"\n"
            f"  [{spark_col}]{spark}[/{spark_col}]"
        )

    def render_state(self) -> None:
        box = self.query_one("#state-box", Static)
        if not self.connected:
            box.update(
                "[b]STATE[/b]\n"
                "\n"
                "  [dim]— disconnected —[/dim]\n"
            )
            return

        def row(label: str, val: str, colour: str) -> str:
            return f"  {label:<10} [{colour}]{val}[/{colour}]"

        hw_col = "red bold" if self.tele_hw else "green"
        arm_col = "yellow bold" if self.tele_arm else "dim"
        chg_col = "yellow bold" if self.tele_chg else "dim"
        ok_col = "green" if self.tele_ok else "dim"

        lines = [
            "[b]STATE[/b]",
            "",
            row("CHARGE OK", "READY"   if self.tele_ok  else "OFF",    ok_col),
            row("CHARGING",  "ACTIVE"  if self.tele_chg else "IDLE",   chg_col),
            row("ARMED",     "ARMED"   if self.tele_arm else "SAFE",   arm_col),
            row("HW STOP",   "TRIPPED" if self.tele_hw  else "CLEAR",  hw_col),
            "",
            "  [dim]" + ("⚠ FIRE READY" if (self.tele_arm and not self.tele_ok and not self.tele_hw) else "") + "[/dim]",
        ]
        box.update("\n".join(lines))

    def write_log(self, rich_msg: str) -> None:
        log = self.query_one("#log-box", RichLog)
        log.write(f"[dim]{ts()}[/dim]  {rich_msg}")

    # ------------------------------------------------------------------
    # serial plumbing
    # ------------------------------------------------------------------

    def drain_queue(self) -> None:
        for _ in range(80):
            try:
                line = self.bridge.rx_queue.get_nowait()
            except queue.Empty:
                break
            if line.startswith("__READ_ERROR__"):
                self.write_log(f"[red]Read error: {line.split(':', 1)[1]}[/red]")
                self._mark_disconnected()
                continue
            if line.startswith("__WRITE_ERROR__"):
                self.write_log(f"[red]Write error: {line.split(':', 1)[1]}[/red]")
                continue
            self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        # Telemetry
        if line.startswith("T "):
            kv = parse_kv(line[2:])
            self._apply_kv(kv)
            self.history.append(self.tele_adc)
            self.render_voltage()
            self.render_state()
            return
        # Status response
        if line.startswith("STATUS "):
            kv = parse_kv(line[7:])
            self._apply_kv(kv)
            self.render_voltage()
            self.render_state()
            self.write_log(f"[cyan]{line}[/cyan]")
            return
        # Events
        up = line.upper()
        if any(x in up for x in ("OVERVOLT", "HW_STOP", "ERROR", "DENIED", "BLOCKED")):
            self.write_log(f"[red]{line}[/red]")
        elif any(x in up for x in ("ARMED", "UNARM", "UNCHARG")):
            self.write_log(f"[yellow]{line}[/yellow]")
        elif any(x in up for x in ("BOOT", "FIRED", "CHARGING", "RESET_OK")):
            self.write_log(f"[green]{line}[/green]")
        else:
            self.write_log(line)

    def _apply_kv(self, kv: dict[str, str]) -> None:
        try:
            if "adc" in kv: self.tele_adc = int(kv["adc"])
            if "t"   in kv: self.tele_t_ms = int(kv["t"])
            if "ok"  in kv: self.tele_ok  = (kv["ok"]  == "1")
            if "chg" in kv: self.tele_chg = (kv["chg"] == "1")
            if "arm" in kv: self.tele_arm = (kv["arm"] == "1")
            if "hw"  in kv: self.tele_hw  = (kv["hw"]  == "1")
        except ValueError:
            pass

    def try_connect(self, port: str) -> None:
        try:
            self.bridge.open(port)
            self.connected = True
            self.port_name = port
            self.render_top()
            self.render_voltage()
            self.render_state()
            self.write_log(f"[green]Connected to {port} @ {BAUD}[/green]")
        except Exception as e:
            self.write_log(f"[red]Connect failed: {e}[/red]")

    def _mark_disconnected(self) -> None:
        self.bridge.close()
        self.connected = False
        self.tele_adc = 0
        self.tele_ok = self.tele_chg = self.tele_arm = self.tele_hw = False
        self.history.clear()
        self.render_top()
        self.render_voltage()
        self.render_state()

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------

    def action_pick_port(self) -> None:
        def done(port: str | None) -> None:
            if port:
                self.try_connect(port)
        self.app.push_screen(PortPicker(), done)

    def _need_connected(self) -> bool:
        if not self.connected:
            self.write_log("[yellow]not connected[/yellow]")
            return False
        return True

    def action_charge(self) -> None:
        if not self._need_connected(): return
        cmd = "UNCHARGE" if self.tele_chg else "CHARGE"
        self.bridge.send(cmd)
        self.write_log(f"[cyan]> {cmd}[/cyan]")

    def action_arm(self) -> None:
        if not self._need_connected(): return
        cmd = "UNARM" if self.tele_arm else "ARM"
        self.bridge.send(cmd)
        self.write_log(f"[cyan]> {cmd}[/cyan]")

    def action_fire(self) -> None:
        if not self._need_connected(): return
        self.bridge.send("FIRE")
        self.write_log("[cyan]> FIRE[/cyan]")

    def action_reset(self) -> None:
        if not self._need_connected(): return
        self.bridge.send("RESET")
        self.write_log("[cyan]> RESET[/cyan]")

    def action_status(self) -> None:
        if not self._need_connected(): return
        self.bridge.send("STATUS")

    def action_disconnect(self) -> None:
        if self.connected:
            self._mark_disconnected()
            self.write_log("[yellow]disconnected[/yellow]")

    def action_quit(self) -> None:
        self.app.exit()


# ======================================================================
# App
# ======================================================================

class TMSApp(App):
    TITLE = "TMS CTRL"

    def __init__(self, divider: float, vref: float, max_adc: int, avg_window: int,
                 port: str | None) -> None:
        super().__init__()
        self.bridge = SerialBridge()
        self.divider = divider
        self.vref = vref
        self.max_adc = max_adc
        self.avg_window = avg_window
        self.initial_port = port

    def on_mount(self) -> None:
        main = MainScreen(self.bridge, self.divider, self.vref, self.max_adc, self.avg_window)
        self.install_screen(main, name="main")
        self.push_screen("main")
        if self.initial_port:
            main.try_connect(self.initial_port)


# ======================================================================
# Entry point
# ======================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="TMS controller TUI")
    ap.add_argument("--port", help="Serial port (e.g. /dev/ttyACM0 or COM3). If omitted, pick in UI.")
    ap.add_argument("--divider", type=float, default=100.0,
                    help="Voltage divider ratio V_bus / V_pin (default 100)")
    ap.add_argument("--vref", type=float, default=5.0,
                    help="ADC reference voltage (default 5.0)")
    ap.add_argument("--max-adc", type=int, default=614,
                    help="Firmware MAX_ADC trip point (for display and sparkline scale)")
    ap.add_argument("--avg-window", type=int, default=10,
                    help="Number of recent ADC samples to average for Bus μ (default 10, ~1 s at 10 Hz)")
    ap.add_argument("--list", action="store_true",
                    help="List available serial ports and exit")
    args = ap.parse_args()

    if args.list:
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            print("(no serial ports found)")
            return 0
        for p in ports:
            desc = p.description or ""
            print(f"{p.device:<20}  {desc}")
        return 0

    app = TMSApp(
        divider=args.divider,
        vref=args.vref,
        max_adc=args.max_adc,
        avg_window=args.avg_window,
        port=args.port,
    )
    try:
        app.run()
    finally:
        app.bridge.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
