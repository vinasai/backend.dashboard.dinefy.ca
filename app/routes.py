from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import app.database
from app.models import User_login, User,UpdateEmail,ChangePassword, CloverIntegrationBase, CloverIntegrationResponse, ShopifyIntegrationBase, ShopifyIntegrationResponse,PasswordChangeResponse,DeleteAccountResponse,DeleteAccount,RestaurantDetails,PasswordResetRequest, VerifyResetCodeRequest
import app.models
from app.services import get_user_integrations, update_integration
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
import app.services
from app.utils import get_current_user
from fastapi import HTTPException
from fastapi import Query
from datetime import date, datetime, timedelta

from pydantic import EmailStr



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
async def update_user_email(email_data: dict, current_user: str = Depends(get_current_user)):
    """
    Update user email endpoint.
    Requires current password for verification.
    """
    return await app.services.updated_user_email(email_data, current_user)
       
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

@router.post("/restaurant_details")
async def create_or_update_restaurant_details(
    details: RestaurantDetails, 
    current_user: User = Depends(get_current_user)
):
    """
    Create or update restaurant details for the authenticated user
    """
    try:
        return await app.services.save_restaurant_details(details, current_user)
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
        details = await app.services.get_restaurant_details(current_user)
        if not details:
            # Return default structure if no details exist
            return {
                "restaurant_name": "",
                "phone_number": "",
                "address": "",
                "website": "",
                "email": "",
                "openingHours": {
                    "monday": {"open": "", "close": ""},
                    "tuesday": {"open": "", "close": ""},
                    "wednesday": {"open": "", "close": ""},
                    "thursday": {"open": "", "close": ""},
                    "friday": {"open": "", "close": ""},
                    "saturday": {"open":"", "close": ""},
                    "sunday": {"open": "", "close": ""}
                },
                "features": {
                    "takeReservations": False,
                    "takeOrders": False,
                    "provideMenuInfo": False,
                    "handleComplaints": False
                },
                "greetingMessage": "",
                "endingMessage": ""
            }
        return details
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/user/twilio_number")
async def get_twilio_number(current_user: User = Depends(get_current_user)):
    """
    Get the Twilio number for the current user
    """
    try:
        twilio_number = await app.services.get_user_twilio_number(current_user["user_email"])
        return {"twilio_number": twilio_number}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/forgot-password")
async def forgot_password(request: PasswordResetRequest):
    """
    Request a password reset code.
    """
    return await app.services.request_password_reset(request.email)

@router.post("/reset-password")
async def reset_password(request: VerifyResetCodeRequest):
    """
    Verify the reset code and reset the password.
    """
    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    
    return await app.services.verify_reset_code_and_reset_password(
        request.email,
        request.code,
        request.new_password
    )
    
@router.get("/billing", response_model=app.models.BillingResponse)
async def get_billing_info(current_user: dict = Depends(get_current_user)):
    """
    Get a user's billing information including payment methods, history, and usage
    """
    return await app.services.get_user_billing_info(current_user)

@router.post("/payment-methods")
async def add_new_payment_method(payment_method: app.models.AddPaymentMethodStripe, current_user: dict = Depends(get_current_user)):
    """
    Add a new payment method for the user with enhanced validation
    """
    return await app.services.add_payment_method(payment_method, current_user)

@router.delete("/payment-methods/{payment_method_index}")
async def remove_payment_method(payment_method_index: str, current_user: dict = Depends(get_current_user)):
    """
    Remove a payment method by its index
    """
    return await app.services.delete_payment_method(payment_method_index, current_user)

@router.post("/purchase", response_model=app.models.PurchaseResponse)
async def buy_minutes(purchase_data: app.models.PurchaseMinutes, current_user: dict = Depends(get_current_user)):
    """
    Purchase additional minutes using the specified payment method
    """
    return await app.services.purchase_minutes(purchase_data, current_user)

@router.get("/overview/call-data", response_model=app.models.CallDataResponse)
async def get_overview_call_data(
    start_date: date = Query(None), 
    end_date: date = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Get call data for the overview dashboard.
    If dates are not provided, defaults to last 7 days.
    """
    if not start_date:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=6)  # Last 7 days including today
    elif not end_date:
        end_date = start_date + timedelta(days=6)  # 7 days from start date
        
    return await app.services.get_call_data(start_date, end_date, current_user["user_email"])


@router.get("/user/minutes-remaining", response_model=app.models.MinutesRemainingResponse)
async def get_minutes_remaining(current_user: User = Depends(get_current_user)):
    """
    Get the minutes remaining and total minutes for the current user
    """
    try:
        minutes_info = await app.services.get_user_minutes_info(current_user["user_email"])
        return minutes_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/request-verification")
async def request_verification(request_data: app.models.EmailVerification):
    return await app.services.request_email_verification(request_data.email)

@router.post("/resend-verification")
async def resend_verification(request_data: app.models.EmailVerification):
    return await app.services.request_email_verification(request_data.email)

@router.post("/verify-email")
async def verify_email(verify_data: app.models.VerifyEmailRequest):
    result = await app.services.verify_email_code(verify_data.email, verify_data.code)
    
    # Mark email as verified in verification collection
    app.database.collection_email_verification.update_one(
        {"email": verify_data.email},
        {"$set": {"verified": True}}
    )
    
    return result

@router.post("/send-email")
async def send_email(request: app.models.DemoRequest):
    return await app.services.send_email(request)

@router.post("/contact-email")
async def contact_email(request: app.models.ContactRequest):
    return await app.services.contact_email(request)