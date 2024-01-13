from hotconsole.hotconsole import Command, Runner, Hotkey
from hotconsole.helpers import OSHelper

# Допустим, мы хотим включать, выключать и перезапускать службу
# Причем делать это одной командой, а не создавать 3 разных
# Иначе у нас будут однотипные команды и слишком много горячих клавиш

SERVICE = "some_service_name"

# Давайте подготовим для команды список вариантов
turn_service_options = ["Включить", "Выключить", "Перезапустить"]


# При запуске команды у пользователя автоматически запросится номер варианта
# Если он введет неправильный номер - появится сообщение об ошибке
# Если правильный - номер передастся в нашу функцию, где мы его и обработаем
def turn_service(option_number):
    match option_number:
        case 1:
            OSHelper.try_stop_service(SERVICE)
        case 2:
            OSHelper.try_start_service(SERVICE)
        case 3:
            OSHelper.try_rerun_service(SERVICE)


TurnService = Command(
    "turn",
    "Отключить или включить службу",
    turn_service,
    turn_service_options
)

HOTKEYS = [
    # Если нажать alt+t - произойдет переключение на окно консоли, где будет вопрос о номере варианта
    Hotkey("alt+t", TurnService, None),
    # Но при желании мы можем назначить горячую клавишу сразу же с опцией!
    # В этом случае сервис включится без лишних вопросов
    Hotkey("alt+1", TurnService, 1)
]


Runner().run(HOTKEYS)
