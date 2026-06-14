/**
 * Kinesis.js v2.0.0 - Модуль сбора поведенческой телеметрии.
 * Защищен криптографическим Handshake-токеном бэкенда.
 */
class BehavioralCollector {
  constructor(config = {}) {
    // Базовый URL бэкенда (без эндпоинта)
    this.baseUrl = config.baseUrl || "http://localhost:8000";
    this.endpointTelemetry = `${this.baseUrl}/api/v1/telemetry`;
    this.endpointHandshake = `${this.baseUrl}/api/v1/handshake`;

    this.flushInterval = config.flushInterval || 5000;
    this.throttleMs = config.throttleMs || 50;

    this.buffer = [];
    this.sessionToken = null; // Сюда запишется подписанный сервером токен
    this.isHandshakeInProgress = false;
    this.lastRecordedTime = 0;
  }

  init() {
    // Step 1: Немедленно запрашиваем токен сессии у бэкенда
    this._performHandshake();

    // Step 2: Запускаем трекинг мыши (координаты будут копиться в буфер, пока ждем токен)
    window.addEventListener("mousemove", (e) => this._onMouseMove(e));

    // Step 3: Настраиваем периодический сброс данных на сервер
    this.intervalId = setInterval(() => this.flush(), this.flushInterval);

    // Step 4: Защита на случай ухода со страницы.
    // Используем visibilitychange вместо unload (современный стандарт)
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        this.flush(true); // true означает экстренный фоновый сброс
      }
    });
  }

  // 1. Изменяем метод рукопожатия, чтобы передать контекст устройства
  _performHandshake() {
    if (this.isHandshakeInProgress) return;
    this.isHandshakeInProgress = true;

    // Собираем характеристики экрана пользователя
    const screenContext = {
      screenWidth: window.screen.width,
      screenHeight: window.screen.height,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      devicePixelRatio: window.devicePixelRatio || 1,
    };

    fetch(this.endpointHandshake, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(screenContext), // Отправляем метаданные на сервер
    })
      .then((response) => {
        if (!response.ok) throw new Error("Handshake failed");
        return response.json();
      })
      .then((data) => {
        this.sessionToken = data.token;
        this.isHandshakeInProgress = false;
        console.log("[Kinesis] Handshake успешный. Контекст экрана передан.");
      })
      .catch((err) => {
        this.isHandshakeInProgress = false;
        console.error("[Kinesis] Ошибка Handshake:", err);
        setTimeout(() => this._performHandshake(), 5000);
      });
  }

  // 2. Модифицируем сбор координат (Переходим на нормализованные значения)
  _onMouseMove(event) {
    const now = performance.now();
    if (now - this.lastRecordedTime < this.throttleMs) return;
    this.lastRecordedTime = now;

    // Нормализация: переводим пиксели в диапазон от 0.0 до 1.0
    const normalizedX = event.clientX / window.innerWidth;
    const normalizedY = event.clientY / window.innerHeight;

    this.buffer.push({
      x: parseFloat(normalizedX.toFixed(5)), // Округляем до 5 знаков, чтобы не раздувать JSON
      y: parseFloat(normalizedY.toFixed(5)),
      t: Math.floor(performance.timeOrigin + now),
    });
  }

  flush(isEmergency = false) {
    // Если буфер пуст или сервер еще не выдал нам токен — отправлять нечего
    if (this.buffer.length === 0 || !this.sessionToken) return;

    const payload = JSON.stringify({ movements: this.buffer });
    this.buffer = []; // Очищаем буфер сразу, чтобы избежать дублирования при лагах сети

    const headers = {
      "Content-Type": "application/json",
      "X-Kinesis-Session": this.sessionToken, // Передаем подписанный сервером токен
    };

    if (isEmergency) {
      // ЭКСТРЕННЫЙ СБРОС (при закрытии вкладки)
      // Флаг keepalive: true приказывает браузеру завершить этот запрос в фоновом режиме,
      // даже если страница будет полностью уничтожена. При этом заголовки НЕ режутся.
      fetch(this.endpointTelemetry, {
        method: "POST",
        headers: headers,
        body: payload,
        keepalive: true,
      });
    } else {
      // ШТАТНЫЙ СБРОС (в фоне по таймеру)
      fetch(this.endpointTelemetry, {
        method: "POST",
        headers: headers,
        body: payload,
      }).catch((err) => {
        console.error("[Kinesis] Ошибка отправки пакета телеметрии:", err);
      });
    }
  }
}
