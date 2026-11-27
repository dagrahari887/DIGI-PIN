"""
api/v1/digipin.py
------------------
GET  /api/v1/digipin/{code}   -- reverse lookup: DIGIPIN -> bounding box + center
POST /api/v1/digipin/decode   -- same, via request body (useful when the code
                                  contains characters awkward in a URL path)
"""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import TenantContext, get_tenant
from core.digipin_engine import decode, DigipinError
from schemas.digipin import DecodeRequest, DigipinDecodeResponse

router = APIRouter(prefix="/api/v1/digipin", tags=["digipin"])


def _decode_or_422(digipin: str) -> DigipinDecodeResponse:
    try:
        box = decode(digipin)
    except DigipinError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    center_lat, center_lon = box.center
    return DigipinDecodeResponse(
        digipin=digipin.upper(),
        bounding_box=box.as_dict(),
        center={"latitude": round(center_lat, 7), "longitude": round(center_lon, 7)},
    )


@router.get("/{code}", response_model=DigipinDecodeResponse)
async def get_digipin(code: str, tenant: TenantContext = Depends(get_tenant)):
    return _decode_or_422(code)


@router.post("/decode", response_model=DigipinDecodeResponse)
async def decode_digipin(payload: DecodeRequest, tenant: TenantContext = Depends(get_tenant)):
    return _decode_or_422(payload.digipin)
