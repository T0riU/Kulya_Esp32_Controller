# Kulya ESP32 Controller
**Language / Мова:** [English](#english) | [Українська](#українська)

---

# English

## About the Project

Firmware for an ESP32-based physical controller designed specifically for the updated Kulya Firmware.

## About Ukrainian Robotics – Kulya 4.0

Ukrainian Robotics – Kulya 4.0 is an open-source hexapod robot platform designed for education, robotics research, and DIY enthusiasts.

This repository is not an official Ukrainian Robotics project. It is an independent software project that extends and improves the original platform by providing alternative firmware, controllers, and software tools.

**Official project:** [Ukrainian Robotics – Kulya 4.0](https://www.ukrainerobotics.com/en/diy)

## Related Projects
| Project                      | Description                        |
| ---------------------------- | ---------------------------------- |
| [**Kulya Firmware**](https://github.com/T0riU/Kulya_Firmware)           | Robot firmware and configuration   |
| [**Kulya ESP32 Controller**](https://github.com/T0riU/Kulya_Esp32_Controller)   | ESP32 physical controller firmware |
| [**Kulya Python Controller**](https://github.com/T0riU/Kulya_Py_ControllerAndCalibration) | PC controller and calibration      |
| [**Kulya Android Controller**](https://github.com/T0riU/Kulya_Controller) | Android mobile controller          |

## Installation

Flashing and file-upload steps are the same as for the robot's own board — see the **Installation** section of the [Kulya Firmware README](https://github.com/T0riU/Kulya_Firmware) for the full Thonny / MicroPython setup process.

Before uploading, open `config.json` and set it to match your hardware:
- `robot_mac` — the MAC address of the robot's ESP32 (the ESP-NOW peer this remote talks to)
- `pins` — the GPIO pins your 5 buttons and joystick (X, Y, and press-switch) are actually wired to

## How It Works

### Startup

**`boot.py`** — the first script executed when the remote's board powers on. It prints a startup banner, waits 3 seconds (to allow interrupting the boot via REPL if needed), then imports `sender.py`, which runs the remote's main loop.

### Configuration

**`config.json`** — holds the two things that vary per physical build:
- `robot_mac` — the target robot's MAC address for ESP-NOW
- `pins` — GPIO numbers for `button1`-`button5`, `joystick_x`, `joystick_y`, and `joystick_sw`

**`load_config()`** (in `sender.py`) reads this file at startup. If it's missing or can't be parsed, the remote falls back to a built-in `DEFAULT_CONFIG` and prints a warning in the REPL, so it can still boot and be reconfigured afterward.

### Robot Link (ESP-NOW)

**`RobotLink`** wraps the ESP-NOW radio: it brings up Wi-Fi in station mode, registers the robot's MAC as an ESP-NOW peer, and exposes a single `send(text)` method. Every command sent is a plain string in the same `gait:NAME;param:value;` protocol used by the BLE desktop controller — the robot's firmware doesn't need to know or care whether a command came from BLE or ESP-NOW.

### Button Input

**`DebouncedButton`** — an active-low button on an internal pull-up. `poll()` returns `True` exactly once per physical press (on the falling edge), only after the signal has held stable for `debounce_ms` (200 ms by default). Holding the button down does not repeat-fire — it only fires again after a release followed by a new press.

### Joystick Input

**`Joystick`** reads two ADC channels (X and Y). Each axis has its own calibrated raw min/max (the raw ADC ranges are not perfectly symmetric around center), which get mapped to a clean **-100..100** range. A small deadzone (±4) suppresses noise near the resting center so the robot doesn't drift when the stick is released.

### Cycler

**`Cycler`** is a small generic helper: given a list of values, each call to `.next()` returns the current value and advances (wrapping back to the start after the last one). It's reused for three unrelated things in `main()`: stepping through height presets, stepping through leg indices, and stepping through `J_mode` values — each button/cycler pair keeps its own independent position in its list.

### Main Loop

On boot, `main()`:
1. Loads the config and pin map
2. Creates the `RobotLink`, the `Joystick`, and 6 `DebouncedButton` instances (roll, height, wave, dance, CE, joystick-press)
3. Sends the robot an initial state: `gait:WALK;` followed by `J_mode:steer;`

Then it loops continuously (polling every 10 ms):

| Input | Action |
|---|---|
| **Button 1** | Sends `gait:ROLL;` |
| **Button 2** | Cycles through 3 height presets (`low` → `standard` → `high`) and sends `height:`, `raise:`, and `spread:` for the selected preset |
| **Button 3** | Cycles through leg indices 0-5 and sends `gait:WAVE;leg_num:N;` |
| **Button 4** | Cycles through leg indices 0-5 and sends `gait:DANCE;leg_num:N;` |
| **Button 5** | Toggles between "expanded" and "folded": sends `gait:CE;` + `ce_value:5;`, or `ce_value:100;` + `gait:WALK;`, flipping state each press |
| **Joystick press** | Cycles `J_mode` through `tilt` → `shift` → `steer` → `sides` and sends `J_mode:` |
| **Joystick movement** | Polled at 20 Hz (every 50 ms); sends `J_XY:x|y` only when the reading has changed since the last send, to avoid flooding identical packets |

## Usage

1. Set `robot_mac` and `pins` in `config.json` to match your wiring, then upload the files to the board.
2. Power on the remote — after the 3-second boot delay, it connects to the robot over ESP-NOW and immediately puts it into `WALK` mode with `steer` joystick behavior.
3. Move the joystick to steer the robot; press it to cycle through joystick modes (`tilt` / `shift` / `steer` / `sides`) if you want the stick to control something other than steering.
4. Use the 5 buttons for: rolling gait, cycling height presets, waving a leg (cycles which leg each press), triggering a dance (cycles which leg each press), and toggling fold/unfold.

## Notes

This code works, but it hasn't been tested for bugs, so some may exist. If anything is unclear, you find a bug, or you have questions about how or why something works a certain way, feel free to write and ask.

The remote and the robot firmware speak the same text protocol used by the BLE desktop controller — any command this remote can send could equally be sent from the PC controller, and vice versa.

---

# Українська

## Про проєкт

Прошивка для фізичного пульта на базі ESP32, розроблена спеціально під оновлену Kulya Firmware.

## Про Ukrainian Robotics – Kulya 4.0

Ukrainian Robotics – Kulya 4.0 — це платформа гексапода з відкритим кодом, створена для освіти, робототехнічних досліджень та DIY-ентузіастів.

Цей репозиторій не є офіційним проєктом Ukrainian Robotics. Це незалежний софтверний проєкт, що розширює та покращує оригінальну платформу, надаючи альтернативну прошивку, контролери та програмні інструменти.

**Офіційний проєкт:** [Ukrainian Robotics – Kulya 4.0](https://www.ukrainerobotics.com/diy)

## Пов'язані проєкти
| Проєкт                      | Опис                        |
| ---------------------------- | ---------------------------------- |
| [**Kulya Firmware**](https://github.com/T0riU/Kulya_Firmware)           | Прошивка та конфігурація робота   |
| [**Kulya ESP32 Controller**](https://github.com/T0riU/Kulya_Esp32_Controller)   | Прошивка фізичного пульта на ESP32 |
| [**Kulya Python Controller**](https://github.com/T0riU/Kulya_Py_ControllerAndCalibration) | ПК-контролер і калібрування      |
| [**Kulya Android Controller**](https://github.com/T0riU/Kulya_Controller) | Android-контролер          |

## Встановлення

Процес прошивки й завантаження файлів такий самий, як для плати самого робота — див. розділ **Встановлення** в [README Kulya Firmware](https://github.com/T0riU/Kulya_Firmware) для повного опису налаштування через Thonny / MicroPython.

Перед завантаженням відкрий `config.json` і виправ його під своє залізо:
- `robot_mac` — MAC-адреса ESP32 самого робота (ESP-NOW peer, з яким спілкується цей пульт)
- `pins` — GPIO-піни, до яких фактично підключені 5 кнопок і джойстик (X, Y та кнопка-клац)

## Як це працює

### Запуск

**`boot.py`** — перше, що виконується при старті плати пульта. Виводить банер запуску, чекає 3 секунди (щоб можна було перервати завантаження через REPL, якщо треба), потім імпортує `sender.py`, який запускає головний цикл пульта.

### Конфігурація

**`config.json`** — містить дві речі, що змінюються від збірки до збірки:
- `robot_mac` — MAC-адреса робота для ESP-NOW
- `pins` — номери GPIO для `button1`-`button5`, `joystick_x`, `joystick_y` і `joystick_sw`

**`load_config()`** (у `sender.py`) читає цей файл при старті. Якщо файл відсутній або не парситься, пульт відкочується на вбудований `DEFAULT_CONFIG` і виводить попередження в REPL, щоб він все одно завантажився і його можна було перенастроїти пізніше.

### Зв'язок з роботом (ESP-NOW)

**`RobotLink`** обгортає радіо ESP-NOW: піднімає Wi-Fi в режимі станції, реєструє MAC робота як ESP-NOW peer і надає єдиний метод `send(text)`. Кожна надіслана команда — звичайний рядок у тому самому протоколі `gait:ИМЯ;параметр:значення;`, що й у BLE-пульта на ПК — прошивці робота не важливо, звідки прийшла команда: з BLE чи з ESP-NOW.

### Кнопки

**`DebouncedButton`** — активна на LOW кнопка на внутрішньому pull-up. `poll()` повертає `True` рівно один раз на фізичне натискання (по спадаючому фронту), тільки після того, як сигнал протримався стабільним `debounce_ms` (200 мс за замовчуванням). Утримання кнопки не викликає повторного спрацювання — воно відбудеться знову лише після відпускання і нового натискання.

### Джойстик

**`Joystick`** читає два ADC-канали (X і Y). Кожна вісь має власний відкалібрований діапазон сирих значень (сирі діапазони ADC не ідеально симетричні відносно центру), який мапиться в чистий діапазон **-100..100**. Невелика мертва зона (±4) прибирає шум біля центру спокою, щоб робот не "плив" при відпущеному стіку.

### Cycler

**`Cycler`** — невеликий загальний хелпер: маючи список значень, кожен виклик `.next()` повертає поточне значення і рухається далі (по колу, повертаючись на початок після останнього). Використовується для трьох різних речей у `main()`: перебору пресетів висоти, перебору індексів ніг і перебору значень `J_mode` — кожна пара кнопка/циклер тримає свою окрему позицію у своєму списку.

### Головний цикл

При старті `main()`:
1. Завантажує конфіг і мапу пінів
2. Створює `RobotLink`, `Joystick` і 6 екземплярів `DebouncedButton` (roll, height, wave, dance, CE, натискання джойстика)
3. Шле роботу початковий стан: `gait:WALK;`, потім `J_mode:steer;`

Далі йде безперервний цикл (опитування кожні 10 мс):

| Вхід | Дія |
|---|---|
| **Кнопка 1** | Шле `gait:ROLL;` |
| **Кнопка 2** | Перебирає 3 пресети висоти (`low` → `standard` → `high`) і шле `height:`, `raise:` та `spread:` для обраного пресету |
| **Кнопка 3** | Перебирає індекси ніг 0-5 і шле `gait:WAVE;leg_num:N;` |
| **Кнопка 4** | Перебирає індекси ніг 0-5 і шле `gait:DANCE;leg_num:N;` |
| **Кнопка 5** | Перемикає між "розкладено" і "складено": шле `gait:CE;` + `ce_value:5;`, або `ce_value:100;` + `gait:WALK;`, перевертаючи стан кожним натисканням |
| **Натискання джойстика** | Перебирає `J_mode` через `tilt` → `shift` → `steer` → `sides` і шле `J_mode:` |
| **Рух джойстика** | Опитується на 20 Гц (кожні 50 мс); шле `J_XY:x|y` лише коли значення змінилось з останнього надсилання, щоб не заспамити однаковими пакетами |

## Використання

1. Виставити `robot_mac` і `pins` у `config.json` під своє підключення, потім завантажити файли на плату.
2. Увімкнути пульт — після 3-секундної затримки старту він з'єднується з роботом по ESP-NOW і одразу переводить його в режим `WALK` з поведінкою джойстика `steer`.
3. Рухати джойстик, щоб керувати напрямком; натиснути на нього, щоб перемкнути режим джойстика (`tilt` / `shift` / `steer` / `sides`), якщо потрібно, щоб стік керував чимось іншим, ніж напрямком.
4. Використовувати 5 кнопок для: ходи ROLL, перебору пресетів висоти, махання ногою (кожне натискання — інша нога), запуску танцю (кожне натискання — інша нога) та перемикання складено/розкладено.

## Примітки

Цей код працює, але не тестувався на наявність багів, тож вони можуть траплятися. Якщо щось незрозуміло, знайшли баг, або є питання по тому, як і чому щось працює саме так — пишіть і запитуйте.

Пульт і прошивка робота говорять тим самим текстовим протоколом, що й BLE-пульт на ПК — будь-яку команду, яку може надіслати цей пульт, так само можна надіслати і з ПК-контролера, і навпаки.