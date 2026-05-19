from server.company_db import (
    in_house_orders_summary,
    in_house_sales_summary,
    list_employee_accounts,
    list_in_house_orders,
    list_in_house_sales,
)


def list_employees():
    return list_employee_accounts()


def employee_overview():
    return {"ok": True, **in_house_sales_summary()}


def list_employee_sales(limit: int = 200):
    return {"ok": True, "rows": list_in_house_sales(limit=limit)}


def list_employee_orders(limit: int = 200):
    return {"ok": True, "rows": list_in_house_orders(limit=limit)}


def employee_orders_overview():
    return {"ok": True, **in_house_orders_summary()}

