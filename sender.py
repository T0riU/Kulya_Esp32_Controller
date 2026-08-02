import network
import espnow
import time
from machine import Pin, ADC

try:
    import ujson as json
except ImportError:
    import json


CONFIG_PATH = "config.json"
DEFAULT_CONFIG = {
    "robot_mac": "AA:AA:AA:AA:AA:AA",
    "pins": {
        "button1": 12, "button2": 14, "button3": 27,
        "button4": 26, "button5": 25,
        "joystick_x": 35, "joystick_y": 34, "joystick_sw": 32,
    },
}

NUM_LEGS = 6
J_MODES = ["tilt", "shift", "steer", "sides"]

HEIGHT_PRESETS = [
    {"name": "low",      "height": 80,  "raise": 40, "spread": 105},
    {"name": "standard", "height": 120, "raise": 55, "spread": 110},
    {"name": "high",     "height": 150, "raise": 80, "spread": 85},
]

JOY_X_RAW_MIN, JOY_X_RAW_MAX = 110, 3650
JOY_Y_RAW_MIN, JOY_Y_RAW_MAX = -250, 4195
JOY_DEADZONE = 4

BUTTON_DEBOUNCE_MS = 200
JOYSTICK_SEND_INTERVAL_MS = 50   # 20 Hz
MAIN_LOOP_POLL_MS = 10           # how often buttons are sampled


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
def load_config():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        print("Config loaded from", CONFIG_PATH)
        return cfg
    except Exception as e:
        print("WARN: could not read {} ({}) - using built-in defaults. "
              "Edit config.json to set your pins/MAC.".format(CONFIG_PATH, e))
        return DEFAULT_CONFIG


def mac_str_to_bytes(mac_str: str) -> bytes:
    return bytes(int(part, 16) for part in mac_str.split(":"))


# ---------------------------------------------------------------------------
# Robot link (ESP-NOW)
# ---------------------------------------------------------------------------
class RobotLink:
    """Owns the ESP-NOW peer and sends text commands, matching the
    'gait:X;' style protocol the BLE GUI controller also speaks."""

    def __init__(self, mac_str: str):
        self.wifi = network.WLAN(network.STA_IF)
        self.wifi.active(True)

        self.esp = espnow.ESPNow()
        self.esp.active(True)

        self.peer = mac_str_to_bytes(mac_str)
        self.esp.add_peer(self.peer)
        time.sleep_ms(50)

    def send(self, text: str):
        try:
            self.esp.send(self.peer, text, False)
            print("->", text)
        except Exception as e:
            print("send error:", e)


# ---------------------------------------------------------------------------
# Debounced, edge-triggered button
# ---------------------------------------------------------------------------
class DebouncedButton:
    """Active-low button on an internal pull-up. poll() returns True
    exactly once per physical press (rising->falling edge), after the
    signal has been stable for debounce_ms. Holding the button down does
    not fire repeatedly - it only fires again after a release + a new
    press."""

    def __init__(self, pin_num: int, debounce_ms: int = BUTTON_DEBOUNCE_MS):
        self.pin = Pin(pin_num, Pin.IN, Pin.PULL_UP)
        self.debounce_ms = debounce_ms
        self._stable_state = 1          # 1 = released (pull-up idle)
        self._pending_state = 1
        self._last_change_ms = time.ticks_ms()

    def poll(self) -> bool:
        raw = self.pin.value()
        now = time.ticks_ms()

        if raw != self._pending_state:
            # signal is moving - restart the debounce timer
            self._pending_state = raw
            self._last_change_ms = now
            return False

        if time.ticks_diff(now, self._last_change_ms) < self.debounce_ms:
            return False  # not settled yet

        if self._pending_state != self._stable_state:
            self._stable_state = self._pending_state
            return self._stable_state == 0  # fire only on the press edge

        return False


# ---------------------------------------------------------------------------
# Joystick (analog X/Y, same read/map/deadzone principle as before)
# ---------------------------------------------------------------------------
class Joystick:
    def __init__(self, pin_x: int, pin_y: int):
        self.x_axis = ADC(Pin(pin_x))
        self.x_axis.atten(ADC.ATTN_11DB)
        self.y_axis = ADC(Pin(pin_y))
        self.y_axis.atten(ADC.ATTN_11DB)

    @staticmethod
    def _map(x, in_min, in_max, out_min, out_max):
        return int((x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)

    def read(self):
        x_raw = self.x_axis.read()
        y_raw = self.y_axis.read()

        jx = self._map(x_raw, JOY_X_RAW_MIN, JOY_X_RAW_MAX, -100, 100)
        jy = self._map(y_raw, JOY_Y_RAW_MIN, JOY_Y_RAW_MAX, 100, -100)

        if abs(jx) < JOY_DEADZONE:
            jx = 0
        if abs(jy) < JOY_DEADZONE:
            jy = 0
        return jx, jy


# ---------------------------------------------------------------------------
# Simple wrap-around cycler, used for height presets / leg indices / J_mode
# ---------------------------------------------------------------------------
class Cycler:
    def __init__(self, values):
        self.values = values
        self.index = 0

    def next(self):
        value = self.values[self.index]
        self.index = (self.index + 1) % len(self.values)
        return value


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    cfg = load_config()
    pins = cfg.get("pins", DEFAULT_CONFIG["pins"])
    robot_mac = cfg.get("robot_mac", DEFAULT_CONFIG["robot_mac"])

    robot = RobotLink(robot_mac)
    joystick = Joystick(pins["joystick_x"], pins["joystick_y"])

    btn_roll = DebouncedButton(pins["button1"])
    btn_height = DebouncedButton(pins["button2"])
    btn_wave = DebouncedButton(pins["button3"])
    btn_dance = DebouncedButton(pins["button4"])
    btn_ce = DebouncedButton(pins["button5"])
    btn_joy_sw = DebouncedButton(pins["joystick_sw"])

    height_cycler = Cycler(HEIGHT_PRESETS)
    wave_leg_cycler = Cycler(list(range(NUM_LEGS)))
    dance_leg_cycler = Cycler(list(range(NUM_LEGS)))
    jmode_cycler = Cycler(J_MODES)
    ce_expanded = True

    last_joy_value = (None, None)
    last_joy_send_ms = time.ticks_ms()

    print("Kulya RC remote - setting up initial robot state")
    robot.send("gait:WALK;")
    time.sleep_ms(50)
    robot.send("J_mode:steer;")

    while True:
        if btn_roll.poll():
            robot.send("gait:ROLL;")

        if btn_height.poll():
            preset = height_cycler.next()
            robot.send("height:{};".format(preset["height"]))
            robot.send("raise:{};".format(preset["raise"]))
            robot.send("spread:{};".format(preset["spread"]))

        if btn_wave.poll():
            leg = wave_leg_cycler.next()
            robot.send("gait:WAVE;leg_num:{};".format(leg))

        if btn_dance.poll():
            leg = dance_leg_cycler.next()
            robot.send("gait:DANCE;leg_num:{};".format(leg))

        if btn_ce.poll():
            if ce_expanded:
                robot.send("gait:CE;")
                robot.send("ce_value:5;")
            else:
                robot.send("ce_value:100;")
                robot.send("gait:WALK;")
            ce_expanded = not ce_expanded

        if btn_joy_sw.poll():
            mode = jmode_cycler.next()
            robot.send("J_mode:{};".format(mode))

        now = time.ticks_ms()
        if time.ticks_diff(now, last_joy_send_ms) >= JOYSTICK_SEND_INTERVAL_MS:
            jx, jy = joystick.read()
            if (jx, jy) != last_joy_value:
                robot.send("J_XY:{}|{}".format(jx, jy))
                last_joy_value = (jx, jy)
            last_joy_send_ms = now

        time.sleep_ms(MAIN_LOOP_POLL_MS)


main()