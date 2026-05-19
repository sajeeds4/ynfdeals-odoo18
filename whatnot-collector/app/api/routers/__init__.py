from fastapi import APIRouter

from . import auctions, auth, collector, customer_service, diagnostics, employees, health, integrations, inventory, medusa, purchases, sessions, store_sync

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(collector.router, prefix="/collector", tags=["collector"])
api_router.include_router(customer_service.router, prefix="/customer-service", tags=["customer-service"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(auctions.router, prefix="/auctions", tags=["auctions"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(purchases.router, prefix="/purchases", tags=["purchases"])
api_router.include_router(employees.router, prefix="/employees", tags=["employees"])
api_router.include_router(diagnostics.router, prefix="/diagnostics", tags=["diagnostics"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
api_router.include_router(store_sync.router, prefix="/store-sync", tags=["store-sync"])
api_router.include_router(medusa.router, prefix="/medusa", tags=["medusa"])
