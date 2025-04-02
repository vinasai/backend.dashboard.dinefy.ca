from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.models import User_login, User, RestaurantDetails ,CloverIntegrationBase, CloverIntegrationResponse, ShopifyIntegrationBase, ShopifyIntegrationResponse
from app.services import save_restaurant_details, get_restaurant_details , get_call_logs_service ,get_clover_integration, save_clover_integration, update_clover_integration, get_shopify_integration ,save_shopify_integration, update_shopify_integration
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
import app.services
from app.utils import get_current_user
from typing import List
from app.database import collection_restaurant
from fastapi import HTTPException

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    return await app.services.login_user(form_data, ACCESS_TOKEN_EXPIRE_MINUTES)

@router.post("/signup")
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
    try:
        return await save_restaurant_details(details, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/restaurant_details")
async def retrieve_restaurant_details(
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve restaurant details for the authenticated user
    """
    try:
        details = await get_restaurant_details(current_user)
        if not details:
            # Return default structure if no details exist
            return {
                "restaurant_name": "",
                "phone_number": "",
                "twilio_number": "",
                "address": "",
                "website": "",
                "email": current_user["user_email"],
                "openingHours": {
                    "monday": {"open": "9:00 AM", "close": "10:00 PM"},
                    "tuesday": {"open": "9:00 AM", "close": "10:00 PM"},
                    "wednesday": {"open": "9:00 AM", "close": "10:00 PM"},
                    "thursday": {"open": "9:00 AM", "close": "10:00 PM"},
                    "friday": {"open": "9:00 AM", "close": "11:00 PM"},
                    "saturday": {"open": "10:00 AM", "close": "11:00 PM"},
                    "sunday": {"open": "10:00 AM", "close": "9:00 PM"}
                },
                "features": {
                    "takeReservations": False,
                    "takeOrders": False,
                    "provideMenuInfo": False,
                    "handleComplaints": False
                },
                "greetingMessage": "Welcome to our restaurant! How can I assist you today?",
                "endingMessage": "Thank you for calling us! Have a great day!"
            }
        return details
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/Call_Logs")
async def retrieve_call_logs(
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve call logs for the authenticated user
    """
    return await get_call_logs_service(current_user)

@router.get("/integrations/clover", response_model=CloverIntegrationResponse)
async def get_clover(current_user: str = Depends(get_current_user)):
    """Get Clover integration status and details for current user"""
    integration = await get_clover_integration(current_user)
    
    if integration:
        return {
            "connected": integration.get("connected", False),
            "message": "Clover integration is connected",
            "api_key": integration.get("api_key"),
            "merchant_id": integration.get("merchant_id")
        }
    
    return {
        "connected": False,
        "message": "No Clover integration found"
    }

@router.post("/integrations/clover", response_model=CloverIntegrationResponse)
async def connect_clover(
    integration: CloverIntegrationBase,
    current_user: str = Depends(get_current_user)
):
    """Connect or update Clover integration for current user"""

    return await save_clover_integration(current_user, integration.dict())

@router.put("/integrations/clover", response_model=CloverIntegrationResponse)
async def disconnect_clover(current_user: str = Depends(get_current_user)):
    """Disconnect Clover integration for current user"""

    return await update_clover_integration(current_user)

@router.get("/integrations/shopify", response_model=ShopifyIntegrationResponse)
async def get_shopify(current_user: str = Depends(get_current_user)):
    """Get Shopify integration status and details for current user"""
    integration = await get_shopify_integration(current_user)
    
    if integration:
        return {
            "connected": integration.get("connected", False),
            "message": "Shopify integration is connected",
            "api_key": integration.get("api_key"),
            "api_secret": integration.get("api_secret"),
            "shop_url": integration.get("shop_url")
        }
    
    return {
        "connected": False,
        "message": "No Shopify integration found"
    }

@router.post("/integrations/shopify", response_model=ShopifyIntegrationResponse)
async def connect_shopify(
    integration: ShopifyIntegrationBase,
    current_user: str = Depends(get_current_user)
):
    """Connect or update Shopify integration for current user"""

    return await save_shopify_integration(current_user, integration.dict())

@router.put("/integrations/shopify", response_model=ShopifyIntegrationResponse)
async def disconnect_shopify(current_user: str = Depends(get_current_user)):
    """Disconnect Shopify integration for current user"""

    return await update_shopify_integration(current_user)

