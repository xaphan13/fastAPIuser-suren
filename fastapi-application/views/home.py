from typing import Annotated

from core.authentication.fastapi_users import current_active_user
from core.models import User
from fastapi import APIRouter, Depends, Request
from jinja_templates import templates

router = APIRouter(
    prefix="/home",
)


@router.get(
    "/",
    include_in_schema=False,
    name="home",
)
def home(
    request: Request,
    user: Annotated[
        User,
        Depends(current_active_user),
    ],
):
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "user": user,
        },
    )
