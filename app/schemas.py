from pydantic import BaseModel
from typing import Optional

class ItemBase(BaseModel):
    name: str
    description: str

class ItemCreate(ItemBase):
    pass

class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class Item(ItemBase):
    id: int

    class Config:
        orm_mode = True