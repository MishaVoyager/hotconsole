"""
Модуль с хелперами, которые могут пригодится при создании команд

Classes
--------
OSHelper
    Для взаимодействия с виндой (запуск служб, убийство процессов, переключение окон)
ServiceState(Enum)
    Состояние службы
DBHelper
    Для взаимодействия с БД SQLite
RequestsHelper
    Для создания запросов к внешнему API.
InnGenerator
    Для генерации ИНН
"""

import ctypes
import json
import keyboard
import os
import random
import re
import requests
import shutil
import sqlite3
import string
import subprocess
import sys
import time
import traceback
import win32api
import win32con
import win32gui
from PIL import Image
from enum import Enum


class DBHelper:
    """Класс для запросов в БД SQLite"""

    @classmethod
    def connect_and_execute_query(cls, db_path: str, query: str):
        """Открывает соединение, выполняет запрос и закрывает соединение"""
        con = cls.connect(db_path)
        return cls.execute_query(con, query, True)

    @classmethod
    def connect(cls, db_path: str):
        """Открывает соединение с БД. Выбрасывает ошибки при неправильном адресе.
        По умолчанию sqlite этого не делает, потому что метод connect используется в т.ч.
        для создания новой БД"""
        if not os.path.exists(db_path):
            raise AttributeError("Не найден файл базы данных")
        if db_path[-3:] != ".db":
            raise sqlite3.OperationalError("Файл не является базой данных sqlite")
        return sqlite3.connect(db_path)

    @classmethod
    def execute_query(cls, con: sqlite3.Connection, query: str, close_connection: bool = True):
        """Выполняет запрос к БД. Не используется with, т.к. он не закрывает соединение"""
        try:
            cur = con.cursor()
            cur.execute(query)
            statement = query.split()[0].lower()
            if statement == "select":
                return cur.fetchall()
            con.commit()
        except Exception as e:
            raise sqlite3.OperationalError("В ходе выполнения запроса возникла ошибка") from e
        finally:
            if close_connection:
                con.close()


class ServiceState(Enum):
    """Состояние службы"""

    STOPPED = 1
    RUNNING = 2


class OSHelper:
    """Класс OSHelper помогает взаимодействовать с ОС.
    Работает с методами winApi, запросами в командную строку и файловой системой
    """

    @staticmethod
    def set_english_layout():
        """Выбирает английскую раскладку, которая необходима для корректной установки горячих клавиш"""
        win32api.LoadKeyboardLayout("00000409", 1)

    @staticmethod
    def rerun_as_admin(even_if_admin: bool = False):
        """Перезпускает текущий скрипт из-под админа"""
        if not ctypes.windll.shell32.IsUserAnAdmin() or even_if_admin:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            os._exit(1)

    @staticmethod
    def close_window(title: str):
        """Закрывает окно, которое находит по заголовку"""
        hwnd = win32gui.FindWindow(None, title)
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

    @staticmethod
    def get_vbs_script_for_admin_rights() -> str:
        return """set "params=%*"
cd /d "%~dp0" && ( if exist "%temp%\getadmin.vbs" del "%temp%\getadmin.vbs" ) && fsutil dirty query %systemdrive% 1>nul 2>nul || (  echo Set UAC = CreateObject^("Shell.Application"^) : UAC.ShellExecute "cmd.exe", "/k cd ""%~sdp0"" && ""%~s0"" %params%", "", "runas", 1 >> "%temp%\getadmin.vbs" && "%temp%\getadmin.vbs" && exit /B )"""

    @staticmethod
    def write_install_libraries_bat(folder_path: str, bat_name: str):
        """Добавляет в папку батник для установки библиотек из requirements.txt.
        Он нужен для пользователей, которые не готовы руками вводить команды
        """
        bat = f"""@echo off
{OSHelper.get_vbs_script_for_admin_rights()}
python -m ensurepip
python -m pip install --upgrade hotconsole
python -m pip install -r "requirements.txt"
python -m pip show -v hotconsole
set /p userInput=Press Enter to continue...
exit
"""
        folder_path = os.path.join(folder_path, bat_name)
        if not os.path.exists(folder_path):
            OSHelper.write_file(folder_path, bat)

    @staticmethod
    def set_title(title: str):
        ctypes.windll.kernel32.SetConsoleTitleW(title)

    @staticmethod
    def kill_process_by_name(process_name: str) -> bool:
        output = subprocess.run(["tasklist"], capture_output=True, shell=True, check=True).stdout.decode("cp866")
        process_found = False
        for line in output.split("\r\n"):
            if line.startswith(process_name):
                process_found = True
                pid = line.removeprefix(process_name).replace(" ", "")[:5]
                if pid[4] not in string.digits:
                    pid = pid[:4]
                subprocess.call(["taskkill", "/f", "/t", "/PID", pid])
        return process_found

    @staticmethod
    def try_rerun_service(service: str, timeout: int = 10) -> bool:
        return OSHelper.change_service_state(ServiceState.STOPPED, service, timeout) and OSHelper.change_service_state(
            ServiceState.RUNNING, service, timeout
        )

    @staticmethod
    def try_stop_service(service: str, timeout: int = 10) -> bool:
        return OSHelper.change_service_state(ServiceState.STOPPED, service, timeout)

    @staticmethod
    def try_start_service(service: str, timeout: int = 10) -> bool:
        return OSHelper.change_service_state(ServiceState.RUNNING, service, timeout)

    @staticmethod
    def change_service_state(target_state: ServiceState, service: str, timeout: int = 10) -> bool:
        if OSHelper._service_has_target_state(target_state, service):
            return True
        match target_state:
            case ServiceState.STOPPED:
                subprocess.call(["sc", "stop", service])
            case ServiceState.RUNNING:
                subprocess.call(["sc", "start", service])
            case _:
                raise ValueError("Нет такого состояния службы!")
        for _ in range(timeout):
            time.sleep(1)
            if OSHelper._service_has_target_state(target_state, service):
                return True
        return False

    @staticmethod
    def _service_has_target_state(target_state: ServiceState, service: str) -> bool:
        output = subprocess.run(["sc", "query", service], capture_output=True, shell=True, check=True).stdout.decode(
            "cp866"
        )
        match target_state:
            case ServiceState.STOPPED:
                return "STOPPED" in output
            case ServiceState.RUNNING:
                return "RUNNING" in output
            case _:
                raise ValueError("Нет такого состояния службы!")

    @staticmethod
    def delete_folder(file_path: str, retries: int = 5):
        if not os.path.exists(file_path):
            print(f"\nНа ПК уже нет папки: {file_path}\n")
            return
        for _ in range(retries):
            try:
                shutil.rmtree(file_path)
            except Exception:
                pass
            time.sleep(1)
            if not os.path.exists(file_path):
                print(f"\nУдалили: {file_path}\n")
                return

    @staticmethod
    def update_json_file(key: str, value, path: str):
        with open(path, "r+", encoding="utf-8") as file:
            raw = file.read()
            data = json.loads(raw)
            data[key] = value
            new_json = json.dumps(data, indent=4)
            file.seek(0)
            file.write(new_json)
            file.truncate()

    @staticmethod
    def get_from_json_file(key: str, path: str):
        with open(path, "r", encoding="utf-8") as file:
            raw_json = file.read()
            data = json.loads(raw_json)
            if key not in data:
                raise KeyError(f"В файле {path} не найден ключ {key}")
            return data[key]

    @staticmethod
    def extract_whole_json(path: str) -> dict:
        with open(path, "r", encoding="utf-8") as file:
            return json.loads(file.read())

    @staticmethod
    def write_file(path: str, content: str):
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)

    @staticmethod
    def gen_random_string(length: int) -> str:
        letters = string.ascii_lowercase
        return "".join(random.choice(letters) for _ in range(length))

    @staticmethod
    def get_random_numbers(length: int) -> str:
        digits = string.digits
        return "".join(random.choice(digits) for _ in range(length))

    @staticmethod
    def flash_window(title: str):
        """Не используется, поскольку лучше переключаться на нужное окно, чем просто поджигать иконку"""
        hwnd = win32gui.FindWindow(None, title)
        win32gui.FlashWindow(hwnd, 1)

    @staticmethod
    def switch_to_window(title: str):
        try:
            hwnd = win32gui.FindWindow(None, title)
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            keyboard.press_and_release("alt + tab")
        finally:
            time.sleep(0.5)

    @staticmethod
    def get_current_console_title() -> str:
        GetConsoleTitle = ctypes.windll.kernel32.GetConsoleTitleW
        GetConsoleTitle.restype = ctypes.c_uint
        buffer_size = 100
        title_buffer = ctypes.create_unicode_buffer(buffer_size)
        GetConsoleTitle(title_buffer, buffer_size)
        return title_buffer.value

    @staticmethod
    def switch_to_script_window():
        """Переключения окна само на себя не работает, поэтому приходится запускать новый скрипт в отдельном окне"""
        console_title = OSHelper.get_current_console_title()
        script = str(
            f"""
import ctypes
import sys
if not ctypes.windll.shell32.IsUserAnAdmin():
    ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable, ' '.join(sys.argv), None, 1)
    exit()
import win32gui
import win32con
hwnd = win32gui.FindWindow(None, '{console_title}')
if win32gui.IsIconic(hwnd):
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(hwnd)"""
        )
        try:
            file_path = os.path.join(sys.path[0], "switcher.py")
            with open(file_path, "w+", encoding="utf-8") as file:
                file.writelines(script)
            script_window_is_background = win32gui.FindWindow(None, console_title) != win32gui.GetForegroundWindow()
            if script_window_is_background:
                subprocess.call(f"python {file_path}", creationflags=subprocess.CREATE_NEW_CONSOLE)
            os.remove(file_path)
            OSHelper.clean_console_input()
        except Exception:
            print(traceback.format_exc())
            keyboard.press_and_release("alt + tab")

    @staticmethod
    def clean_console_input():
        for _ in range(100):
            keyboard.press_and_release("backspace")

    @staticmethod
    def input_number(message: str = "") -> int:
        if message != "":
            message = f"\n{message}\n\n"
        number = input(message).strip()
        if not number.isdigit():
            raise TypeError("Вы ввели не число")
        return int(number)

    @staticmethod
    def input_number_array(message: str = "") -> list[int]:
        if message != "":
            message = f"\n{message}\n\n"
        numbers = input(message).strip().split()
        for number in numbers:
            if not number.isdigit():
                raise TypeError("Вы ввели не число")
        return list(map(int, numbers))


class RequestsHelper:
    @classmethod
    def check_request(cls, result):
        result.raise_for_status()
        print()
        print(result.request.method, result.url, sep=" ")
        print(result.status_code, result.reason, sep=" ")

    @classmethod
    def do_get_request(cls, session: requests.Session, url: str) -> dict:
        result = session.get(url)
        cls.check_request(result)
        return json.loads(result.content)

    @classmethod
    def do_post_request(cls, session: requests.Session, url: str, body: str) -> dict | None:
        session.headers["Content-Type"] = "application/json"
        result = session.post(url, data=body)
        cls.check_request(result)
        no_content = result.content is not None and result.content != ""
        return None if no_content else json.loads(result.content)


class InnGenerator:
    """Генерирует валидные ИНН для юрлиц и физлиц (ИП)"""

    _control_nums_ul = (2, 4, 10, 3, 5, 9, 4, 6, 8)
    _control_nums_fl = (
        (7, 2, 4, 10, 3, 5, 9, 4, 6, 8),
        (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8),
    )

    @classmethod
    def get_random_inn_ul(cls) -> str:
        """Получить случайный ИНН Юридического Лица"""
        inn = OSHelper.get_random_numbers(9)
        return inn + cls._get_controls_inn_ul(inn)

    @classmethod
    def get_random_inn_fl(cls) -> str:
        """Получить случайный ИНН Физического Лица"""
        inn = OSHelper.get_random_numbers(10)
        return inn + cls._get_controls_inn_fl(inn)

    @classmethod
    def _get_controls_inn_ul(cls, inn: str) -> str:
        """Получить контрольное число для ИНН Юридического лица"""
        inn = inn[:-1] if len(inn) == 10 else inn
        inn += cls._get_control_number(cls._control_nums_ul, inn)
        return inn[-1]

    @classmethod
    def _get_controls_inn_fl(cls, inn: str) -> str:
        """Получить контрольные числа для ИНН Физического лица"""
        inn = inn[:-2] if len(inn) == 12 else inn
        inn += cls._get_control_number(cls._control_nums_fl[0], inn)
        inn += cls._get_control_number(cls._control_nums_fl[1], inn)
        return inn[-2:]

    @classmethod
    def _get_control_number(cls, control_nums, inn: str) -> str:
        num = str(sum([x * int(y) for (x, y) in zip(control_nums, inn)]) % 11)
        return num if num != "10" else "0"
