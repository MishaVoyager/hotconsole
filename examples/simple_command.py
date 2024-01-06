from hotconsole.helpers import OSHelper
from hotconsole.commands import Command, Runner, Hotkey


def turn_service(option_number):
    match option_number:
        case 1:
            OSHelper.try_stop_service("SERVICE")
        case 2:
            OSHelper.try_start_service("SERVICE")
        case 3:
            OSHelper.try_rerun_service("SERVICE")


TurnService = Command(
    "turn",
    "Отключить или включить службу",
    turn_service,
    [
        "Включить SERVICE",
        "Выключить SERVICE",
        "Перезапустить SERVICE",
    ],
)

HOTKEYS = [
    Hotkey("alt+t", TurnService, None),
    Hotkey("alt+1", TurnService, 1)
]


def main():
    Runner().run(HOTKEYS)


if __name__ == "__main__":
    OSHelper.rerun_app_as_admin()
    OSHelper.set_english_layout()
    main()
