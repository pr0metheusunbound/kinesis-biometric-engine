import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- НАСТРОЙКА КРИПТОГРАФИИ ---
SECRET_KEY = b"kinesis_secure_fallback_salt_production_ready_9921"
SESSION_LIFETIME_SEC = 3600  # 1 час

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(
    filename="kinesis_telemetry.log", level=logging.INFO, format="%(message)s"
)
logger = logging.getLogger("kinesis_api")

app = FastAPI(title="Kinesis Enterprise Ingestion API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# --- PYDANTIC СХЕМЫ ---


class DeviceContext(BaseModel):
    """Контекст устройства, собираемый при рукопожатии"""

    screenWidth: int
    screenHeight: int
    viewportWidth: int
    viewportHeight: int
    devicePixelRatio: float


class MouseMovement(BaseModel):
    """Нормализованные координаты мыши"""

    x: float = Field(..., description="Нормализованная координата X [0.0, 1.0]")
    y: float = Field(..., description="Нормализованная координата Y [0.0, 1.0]")
    t: int = Field(..., description="Таймстамп события в мс")


class TelemetryBatch(BaseModel):
    movements: List[MouseMovement] = Field(default_factory=list)


# --- КРИПТОГРАФИЧЕСКИЕ ХЕЛПЕРЫ ---


def generate_secure_token(session_id: str) -> str:
    timestamp = str(int(time.time()))
    payload = f"{session_id}.{timestamp}".encode()
    signature = hmac.new(SECRET_KEY, payload, hashlib.sha256).hexdigest()
    return f"{session_id}.{timestamp}.{signature}"


def verify_session_token(token: Optional[str]) -> str:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing session token. Handshake required.",
        )
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError()

        session_id, timestamp_str, signature = parts

        if time.time() - int(timestamp_str) > SESSION_LIFETIME_SEC:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired. Please re-handshake.",
            )

        expected_payload = f"{session_id}.{timestamp_str}".encode()
        expected_signature = hmac.new(
            SECRET_KEY, expected_payload, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, signature):
            raise ValueError()

        return session_id

    except (ValueError, TypeError):
        logger.warning(f"Tampering attempt detected! Invalid token: {token}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session validation failed.",
        )


# --- ЭНДПОИНТЫ API ---


@app.post("/api/v1/handshake", status_code=status.HTTP_200_OK)
async def handshake(context: DeviceContext):
    """
    Единственная декларация Handshake.
    Принимает параметры экрана, генерирует токен и сохраняет контекст в лог.
    """
    server_side_session_id = str(uuid.uuid4())
    secure_token = generate_secure_token(server_side_session_id)

    session_metadata = {
        "type": "session_init",
        "sessionId": server_side_session_id,
        "context": context.model_dump(),
        "timestamp": time.time(),
    }

    # Неблокирующий сброс метаданных в лог
    await asyncio.to_thread(
        logging.info, json.dumps(session_metadata, ensure_ascii=False)
    )

    return {"status": "success", "token": secure_token}


@app.post("/api/v1/telemetry", status_code=status.HTTP_202_ACCEPTED)
async def receive_telemetry(
    data: TelemetryBatch,
    x_kinesis_session: Optional[str] = Header(None, alias="X-Kinesis-Session"),
):
    trusted_session_id = verify_session_token(x_kinesis_session)

    try:
        enriched_data = {
            "type": "telemetry_batch",
            "sessionId": trusted_session_id,
            "movements": [mv.model_dump() for mv in data.movements],
        }

        log_payload = json.dumps(enriched_data, ensure_ascii=False)
        await asyncio.to_thread(logging.info, log_payload)

        return {"status": "accepted"}

    except Exception as internal_error:
        logger.exception(
            f"Critical error during telemetry processing: {str(internal_error)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal telemetry processing error.",
        )
