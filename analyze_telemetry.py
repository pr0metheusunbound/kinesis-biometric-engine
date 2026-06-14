import collections
import json
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Константы для стандартизации признаков
VIRTUAL_CANVAS_WIDTH: float = 1920.0
VIRTUAL_CANVAS_HEIGHT: float = 1080.0


def calculate_entropy(angles: np.ndarray, bins: int = 16) -> float:
    """Вычисляет информационную энтропию Шеннона (NumPy векторизация)."""
    if len(angles) == 0:
        return 0.0

    counts, _ = np.histogram(angles, bins=bins, range=(-np.pi, np.pi))
    probs = counts / len(angles)

    nonzero_probs = probs[probs > 0]
    if len(nonzero_probs) == 0:
        return 0.0

    entropy_scalar = -np.sum(nonzero_probs * np.log2(nonzero_probs))
    return float(entropy_scalar)


def analyze_session(
    session_id: str,
    movements: List[Dict[str, Any]],
    device_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Продвинутый биомеханический анализ.
    Детектирует искусственный белый шум (генераторы random) через автокорреляцию дельт.
    """
    resolution: str = "Unknown"
    if device_context is not None:
        v_width = device_context.get("viewportWidth", 0)
        v_height = device_context.get("viewportHeight", 0)
        resolution = f"{v_width}x{v_height}"

    default_result: Dict[str, Any] = {
        "Session": session_id[:8],
        "Points": len(movements),
        "Entropy": 0.0,
        "Vel_IQR": 0.0,
        "Dx_Autocorr": 0.0,
        "Resolution": resolution,
        "Verdict": "Insufficient Data",
    }

    if len(movements) < 8:  # Для корреляции нужно чуть больше точек
        return default_result

    df = pd.DataFrame(movements)

    # Масштабирование на Виртуальный эталонный холст
    df["x_scaled"] = df["x"] * VIRTUAL_CANVAS_WIDTH
    df["y_scaled"] = df["y"] * VIRTUAL_CANVAS_HEIGHT

    # Расчет физических дельт
    df["dx"] = df["x_scaled"].diff()
    df["dy"] = df["y_scaled"].diff()
    df["dt"] = df["t"].diff() / 1000.0

    df = df.dropna().copy()
    df["dt"] = df["dt"].replace(0, 0.001)

    df["raw_velocity"] = np.sqrt(df["dx"] ** 2 + df["dy"] ** 2) / df["dt"]
    df["angle"] = np.arctan2(df["dy"], df["dx"])

    # Защита от телепортаций
    HUMAN_MAX_VELOCITY = 8000.0
    clean_df = df[df["raw_velocity"] < HUMAN_MAX_VELOCITY].copy()

    if len(clean_df) < 5:
        default_result["Verdict"] = "🤖 BOT (Teleportation Spam)"
        return default_result

    # Извлечение базовых фичей
    angles_array = clean_df["angle"].to_numpy()
    velocity_array = clean_df["raw_velocity"].to_numpy()

    entropy = calculate_entropy(angles_array)
    q75, q25 = np.percentile(velocity_array, [75, 25])
    velocity_iqr = float(q75 - q25)

    # --- КРИТИЧЕСКИЙ ПРИЗНАК: АВТОКОРРЕЛЯЦИЯ (Борьба с random.uniform) ---
    # Считаем корреляцию между текущим dx и предыдущим dx (lag=1)
    # Если значение близко к 0 или отрицательное — это хаотичный синтетический шум
    dx_autocorr = clean_df["dx"].autocorr(lag=1)

    # Заменяем NaN (если дельты были совсем мертвыми) на 0.0
    if pd.isna(dx_autocorr):
        dx_autocorr = 0.0

    # --- СУПЕР-МАТРИЦА ДЕТЕКЦИИ ---
    # 1. Классический тупой бот (низкая энтропия + стабильная скорость)
    is_classic_bot = entropy < 2.3 and velocity_iqr < 1500.0

    # 2. Продвинутый бот с random.uniform (высокая энтропия, но отсутствует человеческая инерция)
    # У человека при активном движении автокорреляция дельт обычно > 0.25
    is_noise_bot = dx_autocorr < 0.15 and velocity_iqr < 2500.0

    if is_classic_bot or is_noise_bot:
        verdict = f"🤖 BOT (AutoCorr: {round(dx_autocorr, 2)})"
    else:
        verdict = "👤 HUMAN"

    return {
        "Session": session_id[:8],
        "Points": len(movements),
        "Entropy": round(entropy, 3),
        "Vel_IQR": round(velocity_iqr, 2),
        "Dx_Autocorr": round(dx_autocorr, 3),
        "Resolution": resolution,
        "Verdict": verdict,
    }

    if len(movements) < 5:
        return default_result

    df = pd.DataFrame(movements)

    # Масштабирование на Виртуальный эталонный холст
    df["x_scaled"] = df["x"] * VIRTUAL_CANVAS_WIDTH
    df["y_scaled"] = df["y"] * VIRTUAL_CANVAS_HEIGHT

    # Расчет дельт
    df["dx"] = df["x_scaled"].diff()
    df["dy"] = df["y_scaled"].diff()
    df["dt"] = df["t"].diff() / 1000.0

    df = df.dropna().copy()
    df["dt"] = df["dt"].replace(0, 0.001)

    df["velocity"] = np.sqrt(df["dx"] ** 2 + df["dy"] ** 2) / df["dt"]
    df["angle"] = np.arctan2(df["dy"], df["dx"])

    angles_array = df["angle"].to_numpy()
    velocity_array = df["velocity"].to_numpy()

    entropy = calculate_entropy(angles_array)
    velocity_variance = (
        float(np.var(velocity_array)) if len(velocity_array) > 0 else 0.0
    )

    if entropy < 2.2 and velocity_variance < 500000:
        verdict = "🤖 BOT"
    else:
        verdict = "👤 HUMAN"

    return {
        "Session": session_id[:8],
        "Points": len(movements),
        "Entropy": round(entropy, 3),
        "Vel_Variance": round(velocity_variance, 2),
        "Resolution": resolution,
        "Verdict": verdict,
    }


def main() -> None:
    log_file_path: str = "kinesis_telemetry.log"

    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Явно объявляем типы словарей, убирая Unknown
    session_contexts: Dict[str, Dict[str, Any]] = {}
    session_movements: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)

    try:
        with open(log_file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    event: Dict[str, Any] = json.loads(line)
                    session_id = event.get("sessionId")
                    event_type = event.get("type")

                    if not session_id or not isinstance(session_id, str):
                        continue

                    if event_type == "session_init":
                        session_contexts[session_id] = event.get("context", {})
                    elif event_type == "telemetry_batch":
                        movements_data = event.get("movements", [])
                        if isinstance(movements_data, list):
                            session_movements[session_id].extend(movements_data)

                except json.JSONDecodeError:
                    print(f"[Warning] Сломанный JSON в строке {line_num}, пропускаем.")
    except FileNotFoundError:
        print(f"[Error] Файл логов {log_file_path} не найден.")
        return

    results: List[Dict[str, Any]] = []
    for session_id, movements in session_movements.items():
        # Теперь .get() возвращает строго Optional[Dict[str, Any]], что совпадает с сигнатурой функции
        context: Optional[Dict[str, Any]] = session_contexts.get(session_id, None)
        analysis = analyze_session(session_id, movements, context)
        results.append(analysis)

    report_df = pd.DataFrame(results)

    print("\n" + "=" * 75)
    print("               KINESIS BIOMETRIC ANTI-FRAUD REPORT")
    print("=" * 75)
    if not report_df.empty:
        print(report_df.to_string(index=False))
    else:
        print("Нет данных для анализа.")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
