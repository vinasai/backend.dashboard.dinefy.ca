from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.models import User_login, User,UpdateEmail,ChangePassword, CloverIntegrationBase, CloverIntegrationResponse, ShopifyIntegrationBase, ShopifyIntegrationResponse,PasswordChangeResponse,DeleteAccountResponse,DeleteAccount
from app.services import get_user_integrations, update_integration
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
import app.services
from app.utils import get_current_user

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

@router.put("/update-email")
async def update_user_email(new_email: UpdateEmail, current_user: str = Depends(get_current_user)):
    """
    Update user email endpoint.
    Requires current password for verification.
    """
    return await app.services.updated_user_email(new_email, current_user)
       
@router.put("/change-password" ,response_model=PasswordChangeResponse)
async def change_user_password(ChangePassword: ChangePassword, current_user: str = Depends(get_current_user)):
    """
    Change user password endpoint.
    Requires current password for verification.
    """
    return await app.services.changed_user_password(ChangePassword, current_user)
    

@router.delete("/delete-account" , response_model=DeleteAccountResponse)
async def delete_user_account(delete_account: DeleteAccount, current_user: str = Depends(get_current_user)):
    """
    Delete user account endpoint.
    Requires current password for verification.
    """
    return await app.services.deleted_user_account(delete_account, current_user)


@router.get("/Call_Logs")
async def retrieve_call_logs(
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve call logs for the authenticated user
    """
    return await app.services.get_call_logs_service(current_user)

# Clover Routes
@router.get("/integrations/clover", response_model=CloverIntegrationResponse)
async def get_clover(current_user: str = Depends(get_current_user)):
    """Get Clover integration status and details"""
    integrations = await get_user_integrations(current_user)
    
    if integrations and integrations.get("integrations", {}).get("clover"):
        clover = integrations["integrations"]["clover"]
        return {
            "connected": clover.get("connected", False),
            "message": "Clover integration is connected",
            "api_key": clover.get("api_key"),
            "merchant_id": clover.get("merchant_id")
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
    """Connect or update Clover integration"""
    clover_data = {
        "connected": True,
        "api_key": integration.api_key,
        "merchant_id": integration.merchant_id
    }
    
    await update_integration(current_user, "clover", clover_data)
    
    return {
        "connected": True,
        "message": "Clover integration connected successfully",
        "api_key": integration.api_key,
        "merchant_id": integration.merchant_id
    }

@router.put("/integrations/clover", response_model=CloverIntegrationResponse)
async def disconnect_clover(current_user: str = Depends(get_current_user)):
    """Disconnect Clover integration"""
    clover_data = {"connected": False}
    await update_integration(current_user, "clover", clover_data)
    
    return {
        "connected": False,
        "message": "Clover integration disconnected successfully"
    }

# Shopify Routes
@router.get("/integrations/shopify", response_model=ShopifyIntegrationResponse)
async def get_shopify(current_user: str = Depends(get_current_user)):
    """Get Shopify integration status and details"""
    integrations = await get_user_integrations(current_user)
    
    if integrations and integrations.get("integrations", {}).get("shopify"):
        shopify = integrations["integrations"]["shopify"]
        return {
            "connected": shopify.get("connected", False),
            "message": "Shopify integration is connected",
            "api_key": shopify.get("api_key"),
            "api_secret": shopify.get("api_secret"),
            "shop_url": shopify.get("shop_url")
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
    """Connect or update Shopify integration"""
    shopify_data = {
        "connected": True,
        "api_key": integration.api_key,
        "api_secret": integration.api_secret,
        "shop_url": integration.shop_url
    }
    
    await update_integration(current_user, "shopify", shopify_data)
    
    return {
        "connected": True,
        "message": "Shopify integration connected successfully",
        "api_key": integration.api_key,
        "api_secret": integration.api_secret,
        "shop_url": integration.shop_url
    }

@router.put("/integrations/shopify", response_model=ShopifyIntegrationResponse)
async def disconnect_shopify(current_user: str = Depends(get_current_user)):
    """Disconnect Shopify integration"""
    shopify_data = {"connected": False}
    await update_integration(current_user, "shopify", shopify_data)
    
    return {
        "connected": False,
        "message": "Shopify integration disconnected successfully"
    }

