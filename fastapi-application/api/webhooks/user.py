from core.schemas.user import UserRegisteredNotification
from fastapi import APIRouter

router = APIRouter()


@router.post("user-created")
def notify_user_created(info: UserRegisteredNotification):
    """
    This webhook will be triggered when a user is created.
    """
