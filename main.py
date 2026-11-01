from datetime import datetime
from enum import Enum
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict




class Settings(BaseSettings):
    app_name: str = "Учёт заказов кофейни"
    default_page_size: int = 10
    max_page_size: int = 50

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]




class DrinkSize(str, Enum):
    small = "small"
    medium = "medium"
    large = "large"


class OrderStatus(str, Enum):
    pending = "pending"
    ready = "ready"
    completed = "completed"
    cancelled = "cancelled"


# ---------- Модели ----------

class OrderCreate(BaseModel):
    drink: str = Field(
        min_length=1,
        max_length=100,
        description="Название напитка из меню",
        examples=["Латте"],
    )
    size: DrinkSize = Field(description="Размер напитка", examples=["medium"])
    quantity: int = Field(
        gt=0,
        description="Количество порций",
        examples=[2],
    )
    customer_name: Optional[str] = Field(
        default=None,
        description="Имя клиента (необязательно)",
        examples=["Ирина"],
    )


class OrderUpdate(BaseModel):
    drink: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Название напитка из меню",
        examples=["Капучино"],
    )
    size: Optional[DrinkSize] = Field(
        default=None, description="Размер напитка", examples=["large"]
    )
    quantity: Optional[int] = Field(
        default=None, gt=0, description="Количество порций", examples=[1]
    )
    customer_name: Optional[str] = Field(
        default=None, description="Имя клиента", examples=["Олег"]
    )
    status: Optional[OrderStatus] = Field(
        default=None, description="Новый статус заказа", examples=["ready"]
    )


class Order(BaseModel):
    id: int = Field(description="Идентификатор заказа", examples=[1])
    drink: str = Field(
        description="Название напитка из меню", examples=["Латте"]
    )
    size: DrinkSize = Field(description="Размер напитка", examples=["medium"])
    quantity: int = Field(description="Количество порций", examples=[2])
    customer_name: Optional[str] = Field(
        default=None, description="Имя клиента", examples=["Ирина"]
    )
    status: OrderStatus = Field(
        description="Статус заказа", examples=["pending"]
    )
    created_at: datetime = Field(
        description="Момент создания заказа", examples=["2026-07-10T09:15:00"]
    )


# ---------- Хранилище и счётчик ----------

orders: dict = {}
next_order_id: int = 1


def get_next_id() -> int:
    """Отдельный счётчик: id не повторяются даже после удаления заказов."""
    global next_order_id
    current = next_order_id
    next_order_id += 1
    return current


# ---------- Приложение ----------

app = FastAPI(
    title="Учёт заказов кофейни",
    description="Мини-сервис для баристы: создание, просмотр, обновление и отмена заказов.",
    version="1.0.0",
)


# ---------- Сервисные эндпоинты ----------

@app.get("/", tags=["Сервис"], summary="Приветствие сервиса")
def root():
    return {"message": "Сервис учёта заказов кофейни на связи"}


@app.get("/info", tags=["Сервис"], summary="Информация о сервисе")
def info(settings: SettingsDep):
    return {
        "app_name": settings.app_name,
        "orders_count": len(orders),
    }


# ---------- Заказы ----------

@app.post(
    "/orders",
    response_model=Order,
    status_code=status.HTTP_201_CREATED,
    tags=["Заказы"],
    summary="Создать новый заказ",
)
def create_order(payload: OrderCreate):
    new_order = Order(
        id=get_next_id(),
        drink=payload.drink,
        size=payload.size,
        quantity=payload.quantity,
        customer_name=payload.customer_name,
        status=OrderStatus.pending,
        created_at=datetime.now(),
    )
    orders[new_order.id] = new_order
    return new_order


@app.get(
    "/orders",
    response_model=list,
    tags=["Заказы"],
    summary="Список заказов с фильтром и постраничной выдачей",
)
def list_orders(
    settings: SettingsDep,
    status_filter: Optional[OrderStatus] = Query(
        default=None, alias="status", description="Фильтр по статусу заказа"
    ),
    limit: Optional[int] = Query(
        default=None, ge=1, description="Сколько заказов вернуть"
    ),
    offset: int = Query(default=0, ge=0, description="Сколько пропустить"),
):
    if limit is None:
        limit = settings.default_page_size
    limit = min(limit, settings.max_page_size)

    result = list(orders.values())
    if status_filter is not None:
        result = [o for o in result if o.status == status_filter]
    return result[offset : offset + limit]


@app.get(
    "/orders/{order_id}",
    response_model=Order,
    tags=["Заказы"],
    summary="Получить заказ по идентификатору",
)
def get_order(order_id: int):
    order = orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order


@app.patch(
    "/orders/{order_id}",
    response_model=Order,
    tags=["Заказы"],
    summary="Частично обновить заказ",
)
def update_order(order_id: int, payload: OrderUpdate):
    order = orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    changes = payload.model_dump(exclude_unset=True)
    updated = order.model_copy(update=changes)
    orders[order_id] = updated
    return updated


@app.delete(
    "/orders/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Заказы"],
    summary="Отменить (удалить) заказ",
)
def delete_order(order_id: int):
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    del orders[order_id]
    return Response(status_code=status.HTTP_204_NO_CONTENT)