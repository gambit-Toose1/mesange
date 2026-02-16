import webview
import sys
import os
import urllib.request

SERVER_URL = "http://127.0.0.1:8000"

if __name__ == "__main__":
    print("🚀 Запуск десктоп приложения...")
    print(f"📡 Подключение к серверу: {SERVER_URL}")

    try:
        urllib.request.urlopen(SERVER_URL, timeout=5)
        print("✅ Сервер доступен")
    except Exception as e:
        print(f"❌ Сервер недоступен! Запустите server.py сначала.")
        print(f"Ошибка: {e}")
        input("Нажмите Enter для выхода...")
        sys.exit(1)

    window = webview.create_window(
        'Python Messenger Pro',
        SERVER_URL,
        width=1200,
        height=800,
        resizable=True,
        min_size=(800, 600)
    )

    print("✅ Приложение запущено!")
    print("💡 Нажмите Ctrl+Q для выхода")
    webview.start()