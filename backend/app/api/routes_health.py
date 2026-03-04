from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..database import get_db
from ..schemas import HealthResponse
from ..config import get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"
    return HealthResponse(
        status="ok",
        db_ok=(db_status == "ok"),
    )


@router.get("/debug/archer-raw")
def debug_archer_raw():
    """Use ArcherClient auto-discovery to fetch yesterday's data and return raw response info."""
    from ..services.archer_client import ArcherClient, _ENDPOINT_CANDIDATES, _DATE_PARAM_CANDIDATES
    import httpx as _httpx

    settings = get_settings()
    yesterday = date.today() - timedelta(days=1)
    base_url = settings.archer_base_url.rstrip("/")

    auth_headers: dict = {}
    auth_params: dict = {}
    if settings.archer_api_key:
        auth_headers = {"Authorization": f"Bearer {settings.archer_api_key}"}
    elif settings.archer_username:
        auth_params = {"username": settings.archer_username, "password": settings.archer_password}

    results = []
    with _httpx.Client() as client:
        for path in _ENDPOINT_CANDIDATES:
            for param_from, param_to in _DATE_PARAM_CANDIDATES:
                params = {param_from: str(yesterday), param_to: str(yesterday), **auth_params}
                try:
                    resp = client.get(
                        f"{base_url}{path}", params=params,
                        headers=auth_headers, timeout=15,
                    )
                    if resp.status_code == 200:
                        raw = resp.json()
                        row_list = raw if isinstance(raw, list) else next(
                            (raw[k] for k in ("data","results","rows","earnings","reports","items","records")
                             if k in raw and isinstance(raw[k], list)), []
                        )
                        results.append({
                            "path": path,
                            "date_params": [param_from, param_to],
                            "status": resp.status_code,
                            "row_count": len(row_list),
                            "envelope_keys": list(raw.keys()) if isinstance(raw, dict) else "list",
                            "first_row_keys": list(row_list[0].keys()) if row_list else [],
                            "first_row_sample": row_list[0] if row_list else None,
                        })
                except Exception as e:
                    results.append({"path": path, "date_params": [param_from, param_to], "error": str(e)})

    return {"yesterday": str(yesterday), "working_endpoints": [r for r in results if "row_count" in r]}
