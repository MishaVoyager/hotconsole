"""
Основной модуль библиотеки hotconsole - для инициализации, запуска скриптов и обработки команд.

Classes
-------

Command
    Датакласс, на основе которого создаются команды
CommandHelpers
    Полезные методы для команд, например, для запроса номера опции
Config
    Конфиг пользователя, который создается в файле data.json
Runner
    Запускает приложение - для этого надо создать объект и вызывать метод run()
Init
    Инициализирует, например, создает или обновляет конфиг (не надо вызывать напрямую)
Executor
    Выполняет команды, обрабатывает ошибки
Hotkey
    Именованный кортеж: горячая клавиша, команда и номер опции
Hotstring
    Именнованный кортеж: короткая строка, описание, полная строка

Constants
---------
SCRIPTS_PATH
    Адрес папки со скриптами пользователя
CONFIG_PATH
    Адрес пользовательского конфига data.json
MAIN_NAME
    Название файла, из которого пользователь запускает скрипты
DEFAULT_TITLE
    Заголовок в консоли по умолчанию
"""

import collections
import getpass
import json
import os
import sqlite3
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable

import keyboard
import requests
from pydantic import BaseModel, ConfigDict, ValidationError, PositiveInt

from hotconsole.helpers import OSHelper

SCRIPTS_PATH = sys.path[0]
CONFIG_PATH = os.path.join(SCRIPTS_PATH, "data.json")
MAIN_NAME = os.path.abspath(str(sys.modules['__main__'].__file__)).split("\\")[-1]
DEFAULT_TITLE = "Hotconsole Scripts"
Hotkey = collections.namedtuple("Hotkey", ["keyboard_key", "command", "option_number"])
Hotstring = collections.namedtuple("Hotstring", ["abbreviation", "description", "string"])


class Config(BaseModel):
    """Пользовательский конфиг - хранит информацию и позволяет кастомизировать приложение

    Parameters
    ----------
    version: PositiveInt
        Версия конфига
    consoleMode: bool
        Если true - скрипты запускаются в консольном режиме без горячих клавиш
    refuseStartup: bool
        Если true - приложение не предлагает добавить запуск в автозагрузку
    """
    model_config = ConfigDict(extra="allow")

    version: PositiveInt
    consoleMode: bool
    refuseStartup: bool

    def dump(self):
        """Перезаписывает фактический конфиг"""
        OSHelper.write_file(CONFIG_PATH, self.model_dump_json(indent=4))

    @staticmethod
    def load_config():
        """Получает фактический конфиг в виде конфига"""
        return Config(**OSHelper.extract_whole_json(CONFIG_PATH))

    @staticmethod
    def load_dict() -> dict:
        """Получает фактический конфиг в виде словаря"""
        return Config(**OSHelper.extract_whole_json(CONFIG_PATH)).load_config().model_dump()

    @staticmethod
    def load_string() -> str:
        """Получает фактический конфиг в текстовом виде"""
        return Config(**OSHelper.extract_whole_json(CONFIG_PATH)).load_config().model_dump_json(indent=4)

    @staticmethod
    def is_corrupted() -> bool:
        """Соответствует ли фактический конфиг модели"""
        try:
            Config.load_config()
            return False
        except ValidationError:
            return True

    @staticmethod
    def actualize():
        """Актуализирует конфиг при каждом запуске команды"""
        pass


@dataclass()
class Command:
    """На основе объектов этого класса создаются горячие клавиши и команды в консоли

    Parameters
    ------------
    name: str
        Короткое название команды используется в консольном режиме
    description: str
        Объяснение, что можно сделать при помощи команды - отображается при ошибках
    execute: Callable
        Собственно команда
    options: list[str]
        Номер опции запрашиваем у пользователя перед выполнением команды
    options_message: str
        Фраза, с которой запрашиваем номер опции
    """

    name: str
    description: str
    execute: Callable[[int | None], str]
    options: list[str] = field(default_factory=list)
    options_message: str = "Введите номер варианта"

    def __post_init__(self):
        if self.options_message == "":
            self.options_message = "Введите номер варианта"

    def __str__(self):
        return f"Название команды: {self.name}, описание: {self.description}"


class CommandHelpers:
    """Класс со вспомогательными методами, которыми пользуются команды"""

    @classmethod
    def ask_option_number_from_one(cls, options: list, message: str = "Введите номер варианта"):
        """Запросить у пользователя номер нужной опции"""
        OSHelper.switch_to_script_window()
        print(f"\n{message}\n")
        if isinstance(options[0], tuple):
            cls.print_options_tuple(options)
        elif isinstance(options[0], str):
            cls.print_options(options)
        else:
            raise TypeError("У команды некорректные опции. Должен быть массив строк или кортежей строк")
        option_number = OSHelper.input_number()
        if option_number > len(options) or option_number < 1:
            raise ValueError("Выбран некорректный вариант")
        return option_number

    @classmethod
    def ask_option_numbers_from_one(cls, options: list, message: str = "Введите номер варианта"):
        """Запросить у пользователя номера нужных опций"""
        OSHelper.switch_to_script_window()
        print(message + "\n")
        cls.print_options(options)
        option_numbers = OSHelper.input_number_array()
        for number in option_numbers:
            if number > len(options) or number < 1:
                raise ValueError("Выбран некорректный вариант")
        return option_numbers

    @classmethod
    def print_options(cls, options: list):
        """Пронумеровать и вывести в консоль список опций"""
        for index, name in enumerate(options):
            print(f"{str(index + 1)}. {name}")

    @classmethod
    def print_options_tuple(cls, options: list):
        """Пронумеровать и вывести в консоль список опций - вторых элементов кортежа"""
        for index, (_, name) in enumerate(options):
            print(f"{str(index + 1)}. {name}")

    @classmethod
    def ask_value_for_config(cls, key: str, message: str = "Вы еще не прописали этот параметр в конфиге") -> str:
        """
        Запросить у пользователя значение параметра для конфига.
        При отказе возвращает пустую строку
        """
        print(f"\n{message}")
        value = input("Введите значение - или пустую строку, чтобы выйти из команды\n\n").strip()
        if value == "":
            print("Ок, можете добавить в следующий раз или вручную в data.json")
        else:
            OSHelper.update_json_file(key, value, CONFIG_PATH)
        return value

    @classmethod
    def get_from_config_or_ask_user(cls, key: str, message: str = "Вы еще не прописали этот параметр в конфиге") -> str:
        """
        Берет значение из конфига - а если оно пустое, спрашивает у пользователя.
        При отказе возвращает пустую строку
        """
        value = OSHelper.get_from_json_file(key, CONFIG_PATH)
        if value == "":
            value = CommandHelpers.ask_value_for_config(key, message)
        return value

    @classmethod
    def print_error(cls, message: str = "При выполнении скрипта возникла ошибка, попробуйте снова"):
        """Печатает текст ошибки на красном фоне"""
        print(f'\n\033[0;30;41m {message} \033[0;0;0m\n\n')

    @classmethod
    def print_success(cls, message: str = "Скрипт завершился успешно"):
        """Печатает текст успеха на зеленом фоне"""
        print(f'\n\033[0;30;42m {message} \033[0;0;0m\n\n')


class Executor:
    """Класс готовит данные для команд, выполняет команды и обрабатывает их ошибки"""

    @classmethod
    def try_execute(cls, command: Command, option_number: int | None = None):
        keyboard.stash_state()
        try:
            config = Config(**OSHelper.extract_whole_json(CONFIG_PATH))
            config.actualize()
            if command.options != [] and option_number is None:
                option_number = CommandHelpers.ask_option_number_from_one(command.options, command.options_message)
            error_message = command.execute(option_number)
            if error_message is None:
                CommandHelpers.print_success()
            else:
                print(f"\n{error_message}")
                CommandHelpers.print_error()
        except requests.ConnectionError:
            cls.print_exception(command, "Нет связи с сервером")
        except requests.HTTPError:
            cls.print_exception(command, "Что-то не так с запросом")
        except AttributeError:
            cls.print_exception(command, "На ПК не найдена база данных кассы")
        except sqlite3.OperationalError:
            cls.print_exception(command, "\nНе удалось подключиться к базе данных db.db\n")
        except Exception:
            cls.print_exception(command)
        finally:
            keyboard.stash_state()

    @classmethod
    def print_exception(cls, command: Command, message: str = ""):
        print(traceback.format_exc())
        print("Не удалось " + command.description.lower())
        if message != "":
            CommandHelpers.print_error(message)
        else:
            CommandHelpers.print_error()


class Init:
    """Класс инициализации, который используется раннером"""

    @classmethod
    def init_or_update_config(cls, init_config: Config, migrations: list[Callable] = []):
        """
        Если файла конфига нет, он создается из INIT_CONFIG.
        Если есть - в него автоматически добавляются новые поля.
        Для изменения старых полей - по порядку применяются migrations
        """
        OSHelper.write_install_libraries_bat(SCRIPTS_PATH, "install-libs.bat")
        if cls._should_init():
            cls._update(True, init_config)
            return
        cls.migrate_if_needed(init_config, migrations)
        if Config.is_corrupted():
            cls._update(True, init_config)
            return
        if cls._should_update(init_config):
            cls._update(False, init_config)

    @classmethod
    def _update(cls, init: bool, init_config: Config):
        """Создает файл конфига data.json или добавляет в него новые поля"""
        new_config = init_config if init else cls.add_new_fields(init_config)
        new_config.dump()
        CommandHelpers.print_success("Файл data.json успешно обновлен")
        input("Для продолжения нажмите Enter...\n")
        OSHelper.rerun_as_admin()

    @classmethod
    def _should_init(cls):
        """Проверяет, нужно ли инициализировать конфиг"""
        return not os.path.exists(CONFIG_PATH)

    @classmethod
    def _should_update(cls, init_config: Config) -> bool:
        return Config.load_config().version != init_config.version

    @classmethod
    def add_new_fields(cls, init_config: Config):
        """Добавляет новые поля в конфиг пользователя"""
        config: dict = Config.load_dict()
        for key, value in init_config.model_dump().items():
            if key not in config.keys() or key == "version":
                config[key] = value
        return Config(**config)

    @classmethod
    def clean_excess_fields(cls, init_config: Config):
        config = OSHelper.extract_whole_json(CONFIG_PATH)
        excess_fields = list()
        for key in config.keys():
            if key not in init_config.model_dump().keys():
                excess_fields.append(key)
        for excess_field in excess_fields:
            config.pop(excess_field)
        OSHelper.write_file(CONFIG_PATH, json.dumps(config, indent=4))

    @classmethod
    def migrate_if_needed(cls, init_config: Config, migrations: list[Callable]):
        """Если в Runner переданы миграции, запускает их, затем удаляет лишние поля"""
        if len(migrations) == 0:
            return
        if Config.is_corrupted() or cls._should_update(init_config):
            for migration in migrations:
                migration()
            cls.clean_excess_fields(init_config)

    @classmethod
    def add_to_startup(cls, title: str):
        """Предлагает автоматически добавить скрипты в папку с автозагрузкой"""
        config = Config.load_config()
        if config.refuseStartup:
            return
        try:
            startup_path = r"C:\Users\%s\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup" % getpass.getuser()
            name = "run_hotconsole_"
            name += MAIN_NAME.split(".")[0] + ".bat" if title == DEFAULT_TITLE else f"{title.lower()}.bat"
            bat_path = os.path.join(startup_path, name)
            if os.path.exists(bat_path):
                config.refuseStartup = True
                config.dump()
                return
            message = "Добавить приложение в автозагрузку, чтобы не включать их вручную?"
            option_number = CommandHelpers.ask_option_number_from_one(["Да", "Нет"], message)
            if option_number == 1:
                with open(bat_path, "w+", encoding="utf-8") as file:
                    file.write(f"@python \"{os.path.join(SCRIPTS_PATH, MAIN_NAME)}\"")
                print("\nСкрипты успешно добавлены в автозагрузку")
        except Exception:
            print("\n\nНе удалось добавить батник для автозапуска скриптов в папку Автозагрузка\n\n")
        finally:
            config.refuseStartup = True
            config.dump()

    @classmethod
    def _install_libs(cls):
        """Правильнее - вызывать команду pip вручную или пользоваться батником"""
        try:
            print("\nУстанавливаются необходимые библиотеки...\n")
            requirements = os.path.join(SCRIPTS_PATH, "requirements.txt")
            subprocess.check_call([sys.executable, "-m", "ensurepip"])
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", f"{requirements}"])
        except Exception:
            input("\n\nНе удалось установить библиотеки.\n\nВозможно, неправильно установлен питон")


class Runner:
    """Инициализирует, запускает и выполняет приложение со скриптами

    Parameters
    ------------
    init_config: Config
        Пользовательский конфиг, по умолчанию с полями version, consoleMode, refuseStartup
    config_actualizer: Callable | None
        Актуализатор конфига срабатывает при выполнении каждой команды, по умолчанию pass
    title: str
        Название окошка консоли со скриптами, по умолчанию Hotconsole Scripts
    migrations: list[Callable]
        Миграции для безболезненного обновления конфига ваших пользователей, по умолчанию пустой список

    Methods
    ------------
    run(hotkeys: list[Hotkey], hotstrings: list[Hotstring] | None = None)
        Единственная функция, которую надо использовать напрямую, запускает приложение
    console_mode(hotkeys: list[Hotkey])
        Запускает приложение в консольном режиме, без горячих клавиш
    def add_hotkey(key: str, command: Command, option_number: int)
        Привязывает горячую клавишу к выполнению команды через Executor
    add_hotstring(short_string: str, string: str)
        Добавляет горячую строку
    print_hotkeys(hotkeys: list[Hotkey])
        Выводит список горячих клавиш    
    print_commands(commands: list[Command])
        Выводит список команд в консольном режиме
    is_screen_locked()
        Проверяет, заблокирован ли экран
    restart_after_lock
        Перезапускает приложение после блокировки экрана (иначе горячие клавиши перестанут работать)
    """

    def __init__(
            self,
            init_config: Config = Config(version=1, consoleMode=False, refuseStartup=False),
            config_actualizer: Callable | None = None,
            title: str = DEFAULT_TITLE,
            migrations: list[Callable] = [],
    ):
        self.init_config = init_config
        self.config_actualizer = config_actualizer
        self.title = title
        self.migrations = migrations
        if config_actualizer is not None:
            Config.actualize = config_actualizer
        if title is not None:
            OSHelper.set_title(title)
        Init.init_or_update_config(init_config, migrations)
        Init.add_to_startup(title)

    def run(self, hotkeys: list[Hotkey], hotstrings: list[Hotstring] | None = None):
        """Приложение запускается в режиме горячих клавиш по умолчанию,
        а если в конфиге consoleMode = false, то в режиме консольных команд

        Parameters
        ------------
            hotkeys: list[Hotkey]
                Список горячих клавиш для запуска команд
            hotstrings: list[Hotstring] | None
                Список горячих строк для автозамены строк
        """
        CommandHelpers.print_success("Горячие клавиши готовы!")
        for hotkey in hotkeys:
            self.add_hotkey(hotkey.keyboard_key, hotkey.command, hotkey.option_number)
        if hotstrings is not None:
            for hotstring in hotstrings:
                self.add_hotstring(hotstring.abbreviation, hotstring.string)
        keyboard.add_hotkey("alt+h", lambda: self.print_hotkeys(hotkeys))
        keyboard.add_hotkey("alt+q", lambda: self.console_mode(hotkeys))
        self.print_hotkeys(hotkeys)
        if Config.load_config().consoleMode:
            CommandHelpers.print_success("Включен режим только консольных команд")
            print("Чтобы выключить, выставьте в data.json consoleMode = false\n")
            self.console_mode(hotkeys)
        self.restart_after_lock()

    def console_mode(self, hotkeys: list[Hotkey]):
        """Запускаем скрипты в консольном режиме, без горячих клавиш"""
        OSHelper.clean_console_input()
        CommandHelpers.print_success("Консольные команды ждут вас!")
        commands: list[Command] = [hotkey.command for hotkey in hotkeys]
        commands_names = {command.name: command for command in commands}
        while True:
            self.print_commands(commands)
            args = input().strip().split()
            if len(args) == 0:
                continue
            try:
                if args[0] == 'exit':
                    OSHelper.rerun_as_admin(True)
                if len(args) == 1:
                    Executor.try_execute(commands_names[args[0]])
                elif len(args) == 2:
                    Executor.try_execute(commands_names[args[0]], int(args[1]))
                else:
                    CommandHelpers.print_error("У команды есть лишние аргументы")
            except KeyError:
                CommandHelpers.print_error("Команда не найдена")
            except ValueError:
                CommandHelpers.print_error("Номер опции должен быть числом")

    def add_hotkey(self, key: str, command: Command, option_number: int):
        """Добавляем горячую клавишу на команду с определенными параметрами"""
        keyboard.add_hotkey(key, lambda: Executor.try_execute(command, option_number))

    def add_hotstring(self, short_string: str, string: str):
        """Добавляем горячую строку: если напечатать ее и нажать на пробел, подставится полная строка"""
        keyboard.add_abbreviation(short_string, string)

    def print_hotkeys(self, hotkeys: list[Hotkey]):
        """Выводим список горячих клавиш в режиме горячих клавиш"""
        table_style = "{0:<8} \t{1:<40} \t{2:20}"
        print(table_style.format("Комбо", "Описание команды", "Номер опции"))
        print()
        for hotkey in hotkeys:
            print(table_style.format(hotkey.keyboard_key, hotkey.command.description, hotkey.option_number or ""))
        print(table_style.format("alt+h", "Вывести список горячих клавиш в консоль", ""))
        print()
        print(table_style.format("alt+q", "Переключиться на консольный режим", ""))
        print()

    def print_commands(self, commands: list[Command]):
        """Выводим список команд в консольном режиме"""
        table_style = "{0:<8} \t{1:<40}"
        print(table_style.format("Команда", "Описание"))
        for command in commands:
            print(table_style.format(f"{command.name}", f"{command.description}"))
        print(table_style.format("exit", "Вернуться в режим горячих клавиш"))
        print("\n ")

    def is_screen_locked(self) -> bool:
        """Определяем, что экран заблокирован по названию соответсвующего процесса"""
        process_name = "LogonUI.exe"
        outputall = subprocess.check_output("TASKLIST")
        return process_name in str(outputall)

    def restart_after_lock(self):
        """При блокировке экрана скрипты перестают работать, но они автоматически перезапускаются"""
        while not self.is_screen_locked():
            time.sleep(15)
        while True:
            time.sleep(2)
            if not self.is_screen_locked():
                print("Перезапуск после блокировки...\n")
                OSHelper.rerun_as_admin(True)
