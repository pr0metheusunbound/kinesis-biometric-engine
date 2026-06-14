import asyncio
import random
import time

import requests
from playwright.async_api import async_playwright

TARGET_URL = "http://localhost:5500/index.html"  # Твой тестовый HTML-стенд
API_BASE_URL = "http://localhost:8000"

# Фиксируем размеры экрана для детерминированности тестов
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720


async def simulate_smart_robotic_mouse(page, from_pos, to_pos, steps=25):
    """
    Имитирует движение мыши с добавлением псевдо-случайного шума (из библиотеки random).
    Пытается обмануть проверку на идеальную линейность (Rigidity Check).
    """
    x1, y1 = from_pos
    x2, y2 = to_pos

    for i in range(steps + 1):
        t = i / steps
        # Базовая идеальная траектория
        current_x = x1 + (x2 - x1) * t
        current_y = y1 + (y2 - y1) * t

        # Внедряем микро-шум (не более 1.5 пикселей), имитируя искусственный тремор
        # Это должно размыть Rigidity_Ratio, чтобы координата не была идеально мертвой
        jitter_x = random.uniform(-1.5, 1.5)
        jitter_y = random.uniform(-1.5, 1.5)

        await page.mouse.move(current_x + jitter_x, current_y + jitter_y)

        # Рандомизируем задержку между шагами (от 30 до 60 мс) вместо жестких 40 мс
        # Это прямая попытка сломать стабильность скорости (раздуть IQR)
        step_delay = random.uniform(0.03, 0.06)
        await asyncio.sleep(step_delay)


async def run_ui_bot():
    """Эмуляция продвинутого UI-бота с использованием случайных величин."""
    print("\n[UI Bot] Запуск продвинутой эмуляции с генерацией шума...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}
        )
        page = await context.new_page()

        page.on("console", lambda msg: print(f"[Browser Console] {msg.text}"))

        await page.goto(TARGET_URL)
        await asyncio.sleep(1.0)

        # 1. Движение к инпуту логина
        print("[UI Bot] Движение к логину с подмешиванием шума...")
        await simulate_smart_robotic_mouse(page, (100, 100), (450, 240))
        await page.click("#username")

        # Рандомизируем задержку между нажатиями клавиш (человеческий фактор)
        for char in "smart_bot_evasion@matrix.io":
            await page.type("#username", char, delay=int(random.uniform(40, 120)))

        # Небольшая пауза "на размышление" перед следующим действием
        await asyncio.sleep(random.uniform(0.4, 0.8))

        # 2. Движение к инпуту пароля
        print("[UI Bot] Движение к паролю...")
        await simulate_smart_robotic_mouse(page, (450, 240), (450, 310))
        await page.click("#password")

        for char in "VolatilePass99!":
            await page.type("#password", char, delay=int(random.uniform(30, 100)))

        await asyncio.sleep(random.uniform(0.3, 0.6))

        # 3. Движение к кнопке отправки
        print("[UI Bot] Движение к кнопке Войти...")
        await simulate_smart_robotic_mouse(page, (450, 310), (520, 420))

        # Имитируем удержание клика на случайное время
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.up()

        print("[UI Bot] Закрытие сессии...")
        await context.close()
        await browser.close()
        print("[UI Bot] Сессия браузера завершена.")


def run_api_bypass_bot():
    """
    ВЕКТОР 2: Прямая атака на API (Эмуляция умного бота без UI).
    Пытается подделать сессию, проходя легитимный Handshake,
    но генерируя математически идеальный (роботизированный) трек.
    """
    print("\n[API Bot] Запуск прямой атаки на Ingestion API в обход браузера...")

    # Шаг 1: Бот ОДЯЗАН пройти рукопожатие, иначе бэкенд вернет 401.
    # Мы симулируем параметры экрана
    handshake_payload = {
        "screenWidth": 1920,
        "screenHeight": 1080,
        "viewportWidth": VIEWPORT_WIDTH,
        "viewportHeight": VIEWPORT_HEIGHT,
        "devicePixelRatio": 1.0,
    }

    print("[API Bot] Выполнение легитимного Handshake для получения токена...")
    hs_response = requests.post(
        f"{API_BASE_URL}/api/v1/handshake", json=handshake_payload
    )
    if hs_response.status_code != 200:
        print(f"[API Bot] Ошибка Handshake: {hs_response.text}")
        return

    token = hs_response.json().get("token")
    print(f"[API Bot] Токен успешно получен: {token[:20]}...[SIGNED]")

    # Шаг 2: Бот генерирует математически идеальную прямую линию в нормализованных координатах (0..1)
    print("[API Bot] Генерация поддельного пакета координат (идеальная прямая)...")
    movements = []
    start_time = int(time.time() * 1000)

    # Прямая линия от (x=0.1, y=0.1) до (x=0.5, y=0.5) за 20 шагов
    for i in range(21):
        t_factor = i / 20
        movements.append(
            {
                "x": round(0.1 + (0.5 - 0.1) * t_factor, 5),
                "y": round(0.1 + (0.5 - 0.1) * t_factor, 5),
                "t": start_time + (i * 50),  # Шаг ровно 50мс
            }
        )

    telemetry_payload = {"movements": movements}
    headers = {
        "Content-Type": "application/json",
        "X-Kinesis-Session": token,  # Передаем валидный подписанный токен
    }

    # Шаг 3: Отправка напрямую в API
    print("[API Bot] Отправка телеметрии напрямую в эндпоинт...")
    tel_response = requests.post(
        f"{API_BASE_URL}/api/v1/telemetry", json=telemetry_payload, headers=headers
    )
    print(f"[API Bot] Ответ сервера: {tel_response.status_code} {tel_response.json()}")


if __name__ == "__main__":
    import sys

    # Переключение режимов через аргументы командной строки
    if len(sys.argv) > 1 and sys.argv[1] == "--api":
        run_api_bypass_bot()
    else:
        asyncio.run(run_ui_bot())
