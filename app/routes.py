from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.models import User_login, User, RestaurantDetails
from app.services import save_restaurant_details, get_restaurant_details , get_call_logs_service
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
import app.services
from app.utils import get_current_user
from typing import List

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    return await app.services.login_user(form_data, ACCESS_TOKEN_EXPIRE_MINUTES)

@router.post("/users")
async def create_user(user: User):
    return app.services.create_new_user(user)

@router.post("/login")
async def login(user_login: User_login ):
    return app.services.login_user_manual(user_login, ACCESS_TOKEN_EXPIRE_MINUTES)

@router.post("/restaurant_details")
async def create_or_update_restaurant_details(
    details: RestaurantDetails, 
    current_user: User = Depends(get_current_user)
):
    """
    Create or update restaurant details for the authenticated user
    """
    return await save_restaurant_details(details, current_user)

@router.get("/restaurant_details")
async def retrieve_restaurant_details(
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve restaurant details for the authenticated user
    """
    return await get_restaurant_details(current_user)

@router.get("/Call_Logs")
async def retrieve_call_logs(
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve call logs for the authenticated user
    """
    return await get_call_logs_service(current_user)