import tkinter as tk
from tkinter import scrolledtext
import subprocess
import sys
import os
import threading

# --- 1. НАСТРОЙКИ И КОНСТАНТЫ ---
SCRIPT_TO_RUN = "repair.py"  # Имя основного скрипта бота
LOG_FILE = "bot_log.txt"     # Файл для сохранения логов

# --- 2. ФУНКЦИИ ДЛЯ РАБОТЫ С ЛОГАМИ (ФАйЛОМ) ---

def write_log_to_file(message):
    """Записывает сообщение в файл логов."""
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(message)
    except Exception:
        pass # Игнорируем ошибки записи в файл

def read_log_from_file():
    """Читает содержимое файла логов при запуске окна."""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        return ""
    except Exception:
        return ""

# --- 3. ОСНОВНОЙ КЛАСС ПРИЛОЖЕНИЯ ---

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Панель управления ботом")
        self.process = None  # Процесс бота
        self.is_running = False

        # --- СОЗДАНИЕ ВИДЖЕТОВ ---
        top_frame = tk.Frame(root)
        top_frame.pack(pady=10)

        self.btn_start = tk.Button(top_frame, text="Запустить", command=self.start_bot, width=15, bg="#4CAF50", fg="white")
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_stop = tk.Button(top_frame, text="Стоп", command=self.stop_bot, width=15, bg="#f44336", fg="white", state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.btn_close = tk.Button(top_frame, text="Закрыть", command=self.close_app, width=15, bg="#9e9e9e", fg="white")
        self.btn_close.pack(side=tk.RIGHT, padx=5)

        # Загрузка старых логов из файла
        old_logs = read_log_from_file()

        label_note = tk.Label(root, text="Перед запуском убедитесь, что база данных открыта и запущена.", font=("Arial", 10))
        label_note.pack(pady=(0, 10))

        self.log_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=80, height=25, font=("Courier New", 10))
        self.log_area.pack(padx=10, pady=5)
        
        # Вставляем старые логи в окно
        self.log_area.insert(tk.END, old_logs)
        self.log_area.configure(state='disabled')

    # --- ЛОГИКА УПРАВЛЕНИЯ ---

    def start_bot(self):
        """Запускает бота в отдельном потоке."""
        if self.is_running:
            return

        self.is_running = True
        self.update_buttons()
        
        thread = threading.Thread(target=self.run_subprocess)
        thread.daemon = True
        thread.start()

    def run_subprocess(self):
        """Запускает процесс бота и перенаправляет вывод в интерфейс."""
        try:
            self.process = subprocess.Popen(
                [sys.executable, SCRIPT_TO_RUN],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding='utf-8' # Явно указываем кодировку для subprocess
            )
            for line in self.process.stdout:
                self.log(line)
            
            if self.process.returncode is not None and self.is_running:
                self.log(f"\n--- Бот завершил работу с кодом {self.process.returncode} ---\n")
                self.is_running = False
                self.update_buttons()

        except Exception as e:
            self.log(f"\n⚠️ Ошибка при запуске: {e}\n")
            self.is_running = False
            self.update_buttons()

    def stop_bot(self):
        """Останавливает процесс бота."""
        if self.process and self.is_running:
            self.log("\n--- Остановка бота... ---\n")
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            
            self.process = None
            self.is_running = False
            self.update_buttons()

    def close_app(self):
        """Закрывает только окно приложения."""
        self.root.destroy()

    def update_buttons(self):
        """Обновляет состояние кнопок."""
        if self.is_running:
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
            self.log("🟢 Статус: Бот запущен.\n")
        else:
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self.log("🔴 Статус: Бот остановлен.\n")

    def log(self, message):
        """Выводит сообщение на экран и сохраняет его в файл."""
        write_log_to_file(message) # Сохраняем в файл

        # Выводим на экран (в "экранчик")
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, message)
        self.log_area.see(tk.END) # Прокрутка вниз
        self.log_area.configure(state='disabled')


# --- 4. ТОЧКА ВХОДА В ПРИЛОЖЕНИЕ ---
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()