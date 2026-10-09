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
    "channel": 6,
    "dance_count": 10,
    "height_presets": [
        {"name": "very_low",  "height": 58,  "raise": 17, "spread": 172},
        {"name": "low",       "height": 87,  "raise": 33, "spread": 150},
        {"name": "standard",  "height": 115, "raise": 50, "spread": 130},
        {"name": "high",      "height": 143, "raise": 67, "spread": 110},
        {"name": "very_high", "height": 172, "raise": 83, "spread": 90},
    ],
    "pins": {
        "button1": 12, "button2": 14, "button3": 27,
        "button4": 26, "button5": 25,
        "joystick_x": 35, "joystick_y": 34, "joystick_sw": 32,
    },
}

NUM_LEGS = 6
J_MODES = ["tilt", "shift", "steer", "sides"]

JOY_X_RAW_MIN, JOY_X_RAW_MAX = 110, 3650
JOY_Y_RAW_MIN, JOY_Y_RAW_MAX = -250, 4195
JOY_DEADZONE_ENTER = 15
JOY_DEADZONE_EXIT = 8
JOY_SEND_MIN_DELTA = 3

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

    def __init__(self, mac_str: str,  channel: int = 6):
        self.wifi = network.WLAN(network.STA_IF)
        self.wifi.active(True)
        self.wifi.config(channel=channel) 

        self.esp = espnow.ESPNow()
        self.esp.active(True)

        self.peer = mac_str_to_bytes(mac_str)
        self.esp.add_peer(self.peer, channel=channel)
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
        # per-axis "are we currently centered" latch, for the hysteresis
        # deadzone below
        self._x_centered = True
        self._y_centered = True

    @staticmethod
    def _map(x, in_min, in_max, out_min, out_max):
        return int((x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)

    def _apply_hysteresis(self, value, was_centered):
        if was_centered:
            if abs(value) < JOY_DEADZONE_ENTER:
                return 0, True
            return value, False
        else:
            if abs(value) < JOY_DEADZONE_EXIT:
                return 0, True
            return value, False

    def read(self):
        x_raw = self.x_axis.read()
        y_raw = self.y_axis.read()

        jx = self._map(x_raw, JOY_X_RAW_MIN, JOY_X_RAW_MAX, -100, 100)
        jy = self._map(y_raw, JOY_Y_RAW_MIN, JOY_Y_RAW_MAX, 100, -100)

        jx, self._x_centered = self._apply_hysteresis(jx, self._x_centered)
        jy, self._y_centered = self._apply_hysteresis(jy, self._y_centered)
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
    channel = cfg.get("channel", DEFAULT_CONFIG["channel"])
    dance_count = cfg.get("dance_count", DEFAULT_CONFIG["dance_count"])
    height_presets = cfg.get("height_presets", DEFAULT_CONFIG["height_presets"])

    robot = RobotLink(robot_mac, channel)
    joystick = Joystick(pins["joystick_x"], pins["joystick_y"])

    btn_roll = DebouncedButton(pins["button1"])
    btn_height = DebouncedButton(pins["button2"])
    btn_wave = DebouncedButton(pins["button3"])
    btn_dance = DebouncedButton(pins["button4"])
    btn_ce = DebouncedButton(pins["button5"])
    btn_joy_sw = DebouncedButton(pins["joystick_sw"])

    height_cycler = Cycler(height_presets)
    wave_leg_cycler = Cycler(list(range(NUM_LEGS)))
    dance_cycler = Cycler(list(range(dance_count)))
    jmode_cycler = Cycler(J_MODES)
    ce_expanded = True

    last_joy_sent = (0, 0)   # last value actually transmitted over ESP-NOW
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
            dance = dance_cycler.next()
            robot.send("dance_id:{};".format(dance))
            time.sleep_ms(50)
            robot.send("gait:DANCE;")

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
            last_x, last_y = last_joy_sent
            became_centered = (jx, jy) == (0, 0) and (last_x, last_y) != (0, 0)
            moved_enough = (abs(jx - last_x) >= JOY_SEND_MIN_DELTA or
                             abs(jy - last_y) >= JOY_SEND_MIN_DELTA)

            if became_centered or moved_enough:
                robot.send("J_XY:{}|{}".format(jx, jy))
                last_joy_sent = (jx, jy)
            last_joy_send_ms = now

        time.sleep_ms(MAIN_LOOP_POLL_MS)


main()