from hotconsole.hotconsole import Command, Hotkey, Runner

command = Command("greet", "Приветствовать мир", lambda _: print("Hello, World!"))
hotkey = Hotkey("alt+shift+9", command, None)
Runner().run([hotkey])

# Для краткости мы здесь использовали лямбду
# Многострочных лямбд в питоне нет, поэтому, как правило, понадобится отдельная функция
# Например:
# def greet(option_number=None):
#     print("Hello, World!")
# Тогда команда будет выглядеть так:
# command = Command("greet", "Приветствовать мир", greet)
