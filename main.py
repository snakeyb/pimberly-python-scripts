import os
from typing import Any, Callable, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request

load_dotenv()

app = FastAPI(title="Pimberly Python Scripts")


WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PIMBERLY_API_KEY = os.getenv("PIMBERLY_API_KEY")
PIMBERLY_API_BASE_URL = os.getenv("PIMBERLY_API_BASE_URL")


def trim(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def uppercase(value: Any) -> Any:
    if isinstance(value, str):
        return value.upper()
    return value


def lowercase(value: Any) -> Any:
    if isinstance(value, str):
        return value.lower()
    return value


def remove_double_spaces(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    return value


SCRIPT_REGISTRY: dict[str, Callable[[Any], Any]] = {
    "trim": trim,
    "uppercase": uppercase,
    "lowercase": lowercase,
    "remove_double_spaces": remove_double_spaces,
}


@app.get("/")
def health_check():
    return {"status": "ok", "service": "pimberly-python-scripts"}


@app.post("/debug/pimberly-webhook")
async def debug_pimberly_webhook(request: Request):
    headers = dict(request.headers)
    body = await request.body()

    print("---- INCOMING WEBHOOK DEBUG ----")
    print("Headers:")
    print(headers)
    print("Raw body:")
    print(body.decode("utf-8"))
    print("--------------------------------")

    return {
        "status": "received",
        "headers": headers,
        "rawBody": body.decode("utf-8"),
    }


@app.post("/pimberly/run-script")
async def run_script(
    request: Request,
    x_pimberly_secret: Optional[str] = Header(default=None),
):
    if not WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="WEBHOOK_SECRET is not configured")

    if x_pimberly_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorised")

    payload = await request.json()

    product_id = payload.get("productId")
    field_name = payload.get("field")
    script_name = payload.get("script")
    current_value = payload.get("value")

    if not product_id:
        raise HTTPException(status_code=400, detail="Missing productId")

    if not field_name:
        raise HTTPException(status_code=400, detail="Missing field")

    if not script_name:
        raise HTTPException(status_code=400, detail="Missing script")

    if script_name not in SCRIPT_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown script: {script_name}")

    new_value = SCRIPT_REGISTRY[script_name](current_value)

    # For early testing, you may want to return the result before writing back.
    # Once happy, set dryRun to false in the incoming payload.
    dry_run = payload.get("dryRun", True)

    pimberly_writeback_result = None

    if not dry_run:
        pimberly_writeback_result = writeback_to_pimberly(
            product_id=product_id,
            field_name=field_name,
            new_value=new_value,
    )

    return {
        "status": "success",
        "dryRun": dry_run,
        "productId": product_id,
        "field": field_name,
        "script": script_name,
        "oldValue": current_value,
        "newValue": new_value,
        "pimberlyWriteback": pimberly_writeback_result,
    }


def writeback_to_pimberly(product_id: str, field_name: str, new_value: Any):
    if not PIMBERLY_API_KEY:
        raise HTTPException(status_code=500, detail="PIMBERLY_API_KEY is not configured")

    if not PIMBERLY_API_BASE_URL:
        raise HTTPException(status_code=500, detail="PIMBERLY_API_BASE_URL is not configured")

    url = f"{PIMBERLY_API_BASE_URL}/core/products/{product_id}"

    payload = {
        field_name: new_value,
        "whTriggerScript":""
    }

    print("---- PIMBERLY WRITEBACK DEBUG ----")
    print(f"URL: {url}")
    print(f"Field: {field_name}")
    print(f"New value: {new_value}")
    print(f"Payload: {payload}")
    print("----------------------------------")

    response = requests.put(
        url,
        headers={
            "Authorization": f"{PIMBERLY_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )

    print("---- PIMBERLY RESPONSE DEBUG ----")
    print(f"Status code: {response.status_code}")
    print(f"Response text: {response.text}")
    print("---------------------------------")

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Failed to write back to Pimberly",
                "statusCode": response.status_code,
                "response": response.text,
            },
        )

    return {
        "statusCode": response.status_code,
        "response": response.text,
    }