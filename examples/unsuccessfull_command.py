from hotconsole.hotconsole import Command, Hotkey, Runner

# В этом примере при вызове команды возникает ошибка
# В результате выводится traceback и сообщение об ошибке
command = Command("greet", "Приветствовать мир", lambda: print("Hello, World!"))
hotkey = Hotkey("alt+shift+5", command, None)
Runner().run([hotkey])

# Ошибка возникает, потому что в функции команды обязательно должен быть параметр с номером опции
# В случае лямбды можно сделать так: lambda _: print("Hello, World!")
# В случае функции так: def greet(option_number=None)
