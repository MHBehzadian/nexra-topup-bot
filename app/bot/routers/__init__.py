from .start import router as start_router
from .topup import router as topup_router
from .change_password import router as change_password_router
from .approval import router as approval_router

all_routers = [start_router, topup_router, change_password_router, approval_router]
