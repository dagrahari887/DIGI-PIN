from pydantic import BaseModel, Field


class DecodeRequest(BaseModel):
    digipin: str = Field(..., min_length=10, max_length=12, description="A 10-character DIGIPIN, dashed or not.")


class BoundingBoxSchema(BaseModel):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class CenterSchema(BaseModel):
    latitude: float
    longitude: float


class DigipinDecodeResponse(BaseModel):
    digipin: str
    bounding_box: BoundingBoxSchema
    center: CenterSchema
