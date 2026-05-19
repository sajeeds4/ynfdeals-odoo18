from fastapi import APIRouter

from app.services.employee_service import (
    employee_orders_overview,
    employee_overview,
    list_employee_orders,
    list_employee_sales,
    list_employees,
)

router = APIRouter()


@router.get("")
def employees():
    return {"ok": True, "rows": list_employees()}


@router.get("/summary")
def employees_summary():
    return employee_overview()


@router.get("/sales")
def employee_sales(limit: int = 200):
    return list_employee_sales(limit=limit)


@router.get("/orders")
def employee_orders(limit: int = 200):
    return list_employee_orders(limit=limit)


@router.get("/orders/summary")
def employee_orders_summary():
    return employee_orders_overview()
