import tkinter as tk
from tkinter import scrolledtext
import subprocess
import sys
import os
import threading

# --- КОНФИГУРАЦИЯ ---
SCRIPT_TO_RUN = "repair.py"      # Имя файла с логикой бота
LOG_FILE = "bot_log.txt"         # Файл для хранения логов
STATUS_FILE = "bot_status.txt"   # Файл для хранения статуса 

# Цвета интерфейса
BG_COLOR = "#F3D3FF"
BUTTON_BG = "#CF92E4"
BUTTON_FG = "white"

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ЛОГОВ ---
def write_log_to_file(message):
    """Добавляет строку в файл лога"""
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(message)
    except Exception as e:
        print(f"Ошибка записи в лог: {e}")

def read_log_from_file():
    """Читает содержимое файла лога"""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        return ""
    except Exception as e:
        return f"Ошибка чтения лога: {e}"

def clear_log_file():
    """Очищает файл лога"""
    try:
        with open(LOG_FILE, 'w', encoding='utf-8'):
            pass 
    except Exception as e:
        print(f"Ошибка очистки лога: {e}")

# --- ОСНОВНОЙ КЛАСС ПРИЛОЖЕНИЯ ---
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Repair_UI")
        self.root.configure(bg=BG_COLOR)
        self.process = None

        self.is_running_in_this_window = False

        # --- СОЗДАНИЕ ВИДЖЕТОВ ---
        top_frame = tk.Frame(root, bg=BG_COLOR)
        top_frame.pack(pady=10, ipady=5)
        is_bot_already_running_elsewhere = self._is_bot_running_in_system()
        
        # Кнопка "Запустить"
        self.btn_start = tk.Button(
            top_frame, text="Запустить", command=self.start_bot,
            width=15, bg="#8ACF8C", fg="white", height=2, padx=15,
            state=tk.DISABLED if is_bot_already_running_elsewhere else tk.NORMAL
        )
        self.btn_start.pack(side=tk.LEFT, padx=5)

        # Кнопка "Стоп"
        self.btn_stop = tk.Button(
            top_frame, text="Стоп", command=self.stop_bot,
            width=15, bg="#bd234c", fg="white", height=2, padx=15,
            state=tk.NORMAL
        )
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        # Кнопка "Закрыть"
        self.btn_close = tk.Button(
            top_frame, text="Закрыть", command=self.close_app,
            width=15, bg="#9764b8", fg="white", height=2, padx=15
        )
        self.btn_close.pack(side=tk.RIGHT, padx=5)

        # Кнопка "Инструкция по работе"
        self.btn_instruction = tk.Button(
            top_frame, text="Инструкция по работе", 
            command=self.show_instruction_window,
            width=18, bg="#99D9CF", fg="white", height=2, padx=15
        )
        self.btn_instruction.pack(side=tk.LEFT, padx=5)

        # Кнопка "Очистить лог"
        self.btn_clear_log = tk.Button(
            top_frame, text="Очистить лог", command=self.clear_log,
            width=15, bg="#FF9FF7", fg="white", height=2, padx=15
        )
        self.btn_clear_log.pack(side=tk.RIGHT, padx=(0, 5))

        label_note = tk.Label(
            root, text="Перед запуском убедитесь, что база данных открыта и запущена",
            font=("Courier New", 10), bg=BG_COLOR
        )
        label_note.pack(pady=(0, 10))

        self.log_area = scrolledtext.ScrolledText(
            root, wrap=tk.WORD, width=80, height=25, font=("Courier New", 10), bg="white"
        )
        
        self.log_area.tag_configure('status', foreground='green')
        self.log_area.tag_configure('error', foreground='red')
        self.log_area.pack(padx=10, pady=5)
        
        old_logs = read_log_from_file()
        self.log_area.insert(tk.END, old_logs)
        
        self.log_area.configure(state='disabled')
        
        if is_bot_already_running_elsewhere:
            self.log("⚠️ Окно запущено. Бот работает в фоновом режиме.\n")

    # --- МЕТОДЫ ДЛЯ РАБОТЫ СО СТАТУСОМ БОТА ---
    def _write_status_to_file(self, status):
        try:
            with open(STATUS_FILE, 'w', encoding='utf-8') as f:
                f.write(status)
        except Exception as e:
            self.log(f"⚠️ Ошибка записи статуса: {e}\n")

    def _read_status_from_file(self):
        try:
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            return "STOPPED"
        except Exception as e:
            self.log(f"⚠️ Ошибка чтения статуса: {e}\n")
            return "STOPPED"

    def _is_bot_running_in_system(self):
        return self._read_status_from_file() == "RUNNING"
    
    # --- ОСНОВНАЯ ЛОГИКА УПРАВЛЕНИЯ ---
    def start_bot(self):
        """Запускает бота в отдельном потоке"""
        self.btn_start.config(state=tk.DISABLED) 
        thread = threading.Thread(target=self._run_bot_process)
        thread.daemon = True 
        thread.start()
    
    def _run_bot_process(self):
        """ЦЕЛЕВАЯ ФУНКЦИЯ ПОТОКА.Запускает repair.py"""
        try:
            self._write_status_to_file("RUNNING")
            self.is_running_in_this_window = True

            self.process = subprocess.Popen(
                [sys.executable, SCRIPT_TO_RUN],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, 
                text=True,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW 
            )
             
            self.log("✅ Статус: Бот запущен.\n")
             
            for line in iter(self.process.stdout.readline, ''):
                if line.strip():
                    self.log(line)
             
            if self.is_running_in_this_window:
                exit_code = self.process.returncode if self.process else "?"
                self.log(f"\n Бот завершил работу с кодом {exit_code} \n")
                self._finalize_stop()

        except Exception as e:
            error_msg = f"\n⚠️ Ошибка при запуске бота: {e}\n"
            print(error_msg)
            self.log(error_msg)
            self._finalize_stop()
    
    def stop_bot(self):
        was_running_before = False

        if self._is_bot_running_in_system() and not self.is_running_in_this_window:
            was_running_before = True

            try:
                subprocess.run(['taskkill', '/F', '/T', '/IM', 'python.exe'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._write_status_to_file("STOPPED")
            except Exception as e:
                self.log(f"\n⚠️ Не удалось убить зависший процесс: {e}\n")
         
        if not was_running_before and not self.is_running_in_this_window and not (self.process and self.process.poll() is None):
            self.log("На данный момент бот не был запущен!\n")
            return

        if self.process and self.is_running_in_this_window:
            self.log("\n Остановка бота... \n")
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                self.log("✅ Бот остановлен!\n")
            except Exception as e:
                self.log(f"\n⚠️ Ошибка при остановке процесса: {e}\n")
             
            if self.is_running_in_this_window:
                self._finalize_stop()
    
    def _finalize_stop(self):
        if self.process:
            self.process = None

        if self.is_running_in_this_window:
            self._write_status_to_file("STOPPED")

        self.is_running_in_this_window = False
        self.root.after(0, lambda: self.btn_start.config(state=tk.NORMAL))
    
    def close_app(self):
        self.root.destroy()
    
    def clear_log(self):
        
        clear_log_file()
        self.log_area.configure(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.configure(state='disabled')
    
    def log(self, message):
        write_log_to_file(message)
        final_message = message if message.endswith('\n') else message + '\n'
        self.root.after(0, lambda: self._update_log_area(final_message))
    
    def _update_log_area(self, message):
        self.log_area.configure(state='normal')
          
        tag = None
        low_msg = message.lower()
        if "ошибк" in low_msg or "⚠️" in message or "exception" in low_msg or "traceback" in low_msg:
            tag = 'error'
        elif "успешн" in low_msg or "запущен" in low_msg or "бот остановлен" in low_msg or "готов к работе" in low_msg:
            tag = 'status'
          
        if tag and tag in self.log_area.tag_names():
            self.log_area.insert(tk.END, message, tag)
        else:
            self.log_area.insert(tk.END, message)
              
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')

    def show_instruction_window(self):
        """Открывает новое окно с инструкцией по работе."""
        instruction_window = tk.Toplevel(self.root)
        instruction_window.title("Инструкция")
        
        # Цвет фона
        instruction_window.configure(bg=BG_COLOR)
        # Фиксация размера окна инструкции
        instruction_window.resizable(False, False)
        # Текст инструкции
        instruction_text = (
            "ИНСТРУКЦИЯ ПО РАБОТЕ С ИНТЕРФЕЙСОМ\n\n"
            "===================\n"
            "Кнопка 'Запустить'- запускает бота. Если кнопка 'заблокирована', значит - бот уже запущен и работает\n"
            "===================\n"
            "Кнопка 'Стоп'- останавливает бота. Завершает запущенный в этом же окне процесс\n"
            "===================\n"
            "Кнопка 'Очистить лог'- удаляет все записи из лога и файла\n"
            "===================\n"
            "Лог - выводит информацию о работе бота и нажатых кнопках\n"
            "===================\n\n"
            "ПРИНУДИТЕЛЬНАЯ ОСТАНОВКА БОТА ЧЕРЕЗ ДИСПЕТЧЕР ЗАДАЧ:\n"
            "Если после повторного открытия окна и нажатии на кнопку 'Стоп' бот продолжает работать, его можно остановить следующим образом:\n"
            "1. Открыть диспетчер задач (Ctrl+Shift+Esc)\n"
            "2. Перейти во вкладку 'Процессы' и найти файл python.exe (либо repair.py)\n"
            "3. Щёлкнуть по нему правой кнопкой мыши и выбрать 'Завершить задачу'"
        )
        # Виджет для текста с прокруткой
        instruction_area = scrolledtext.ScrolledText(
            instruction_window,
            wrap=tk.WORD,
            width=60,  # Ширина окна
            height=15, # Высота окна 
            font=("Courier New", 10),
            bg="white", # Цвет фона 
            state='disabled' 
        )
        # Текст
        instruction_area.configure(state='normal')
        instruction_area.insert(tk.END, instruction_text)
        instruction_area.configure(state='disabled')    
        instruction_area.pack(padx=10, pady=10)

if __name__ == "__main__":
     root = tk.Tk()
     app = App(root)
     root.mainloop()
