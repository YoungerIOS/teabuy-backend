from fastapi import FastAPI

from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.middleware import request_context_middleware
from app.core.response import ok
from app.modules.address.router import router as address_router
from app.modules.auth.router import router as auth_router
from app.modules.cart.router import router as cart_router
from app.modules.checkin.router import router as checkin_router
from app.modules.catalog.router import router as catalog_router
from app.modules.health.router import router as health_router
from app.modules.home.router import router as home_router
from app.modules.internal.router import router as internal_router
from app.modules.internal_catalog.router import router as internal_catalog_router
from app.modules.navigation.router import router as navigation_router
from app.modules.notification.router import router as notification_router
from app.modules.order.router import router as order_router
from app.modules.payment.router import router as payment_router
from app.modules.profile.router import router as profile_router
from app.modules.refund.router import router as refund_router
from app.modules.review.router import router as review_router

app = FastAPI(title=settings.app_name)
register_exception_handlers(app)
app.middleware("http")(request_context_middleware)


@app.get("/")
def root():
    return ok({"service": settings.app_name, "env": settings.app_env})


api_prefix = settings.api_prefix
app.include_router(health_router, prefix=api_prefix)
app.include_router(auth_router, prefix=api_prefix)
app.include_router(home_router, prefix=api_prefix)
app.include_router(catalog_router, prefix=api_prefix)
app.include_router(cart_router, prefix=api_prefix)
app.include_router(checkin_router, prefix=api_prefix)
app.include_router(address_router, prefix=api_prefix)
app.include_router(order_router, prefix=api_prefix)
app.include_router(payment_router, prefix=api_prefix)
app.include_router(refund_router, prefix=api_prefix)
app.include_router(review_router, prefix=api_prefix)
app.include_router(profile_router, prefix=api_prefix)
app.include_router(notification_router, prefix=api_prefix)
app.include_router(navigation_router, prefix=api_prefix)
app.include_router(internal_router, prefix=api_prefix)
app.include_router(internal_catalog_router, prefix=api_prefix)
