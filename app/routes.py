from fastapi import APIRouter, Depends, Request
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
from typing import List
from pydantic import EmailStr
from app.stripe_service import StripeService
from app.models import PaymentMethod, AddPaymentMethod, PurchaseResponse
from app.database import Collection_billing
from fastapi import BackgroundTasks
import uuid
import stripe
from app.config import STRIPE_WEBHOOK_SECRET, MONTHLY_SUBSCRIPTION_PRICE_ID


router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

STRIPE_WEBHOOK_SECRET = STRIPE_WEBHOOK_SECRET

# Price ID for your $149/month subscription plan
MONTHLY_SUBSCRIPTION_PRICE_ID = MONTHLY_SUBSCRIPTION_PRICE_ID

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
   
# Modified subscribe route with email notification
@router.post("/subscribe", response_model=app.models.SubscriptionResponse)
async def create_subscription(
    subscription_data: app.models.SubscriptionRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new monthly subscription ($149/month)
    """
    user_email = current_user["user_email"]
    user = Collection_billing.find_one({"user_email": user_email})
    
    if not user:
        # Add user to the Collection_billing if not found
        user = {
            "user_email": user_email,
            "stripe_customer_id": None,
            "subscription": None,
            "payment_methods": []
        }
        Collection_billing.insert_one(user)
    
    # Check if user already has an active subscription
    if user.get("subscription") and user["subscription"].get("status") == "active":
        raise HTTPException(status_code=400, detail="User already has an active subscription")
    
    stripe_customer_id = user.get("stripe_customer_id")
    if not stripe_customer_id:
        # Create a new customer if one doesn't exist
        stripe_customer_id = await StripeService.create_customer(email=user_email)
        Collection_billing.update_one(
            {"user_email": user_email},
            {"$set": {"stripe_customer_id": stripe_customer_id}}
        )
    
    try:
        # If using client-side payment method ID (from Stripe Elements)
        payment_method = stripe.PaymentMethod.retrieve(subscription_data.payment_method_id)
        
        # Attach payment method to customer if not already attached
        if payment_method.customer != stripe_customer_id:
            await StripeService.attach_payment_method_to_customer(
                payment_method_id=subscription_data.payment_method_id,
                customer_id=stripe_customer_id
            )
        
        # Set as default payment method
        await StripeService.set_default_payment_method(
            customer_id=stripe_customer_id,
            payment_method_id=subscription_data.payment_method_id
        )
        
        # Store payment method info in our database (masked card)
        card_info = payment_method.card
        last4 = card_info.last4
        exp_month = card_info.exp_month
        exp_year = card_info.exp_year
        card_brand = card_info.brand
        
        payment_method_record = {
            "stripe_payment_method_id": subscription_data.payment_method_id,
            "cardholder_name": subscription_data.cardholder_name,
            "card_last4": last4,
            "card_expiry": f"{exp_month:02d}/{str(exp_year)[-2:]}",
            "card_brand": card_brand,
            "billing_address": subscription_data.billing_address,
            "is_default": True
        }
        
        # Create subscription in Stripe
        subscription = await StripeService.create_subscription(
            customer_id=stripe_customer_id,
            price_id=MONTHLY_SUBSCRIPTION_PRICE_ID,
            payment_method_id=subscription_data.payment_method_id,
            metadata={
                "user_email": user_email
            }
        )
        
        # Format dates
        start_date = datetime.fromtimestamp(subscription.start_date).strftime("%Y-%m-%d")
        current_period_end = datetime.fromtimestamp(subscription.current_period_end).strftime("%Y-%m-%d")
        
        # Store subscription info in our database
        subscription_record = {
            "subscription_id": subscription.id,
            "status": subscription.status,
            "start_date": start_date,
            "current_period_end": current_period_end,
            "price": 149.00,
            "auto_renew": True,
            "plan": "monthly",
            "payment_methods": [payment_method_record],
            "payment_history": [
                {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "purchase_id": f"SUB-{uuid.uuid4().hex[:8].upper()}",
                    "amount": 149.00,
                    "type": "subscription",
                    "description": "Monthly Subscription - Initial Payment",
                    "status": "completed"
                }
            ]
        }
        
        # Update database
        Collection_billing.update_one(
            {"user_email": user_email},
            {"$set": {"subscription": subscription_record}}
        )
        
        # Send subscription confirmation email in the background
        background_tasks.add_task(
            app.services.send_subscription_confirmation_email,
            user_email,
            "monthly"
        )
        
        # Record successful payment
        payment_record = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "purchase_id": "PUR-Free",
            "amount": "Free",
            "minutes": 1000,
            "status": "completed"
        }
        
        Collection_billing.update_one(
            {"user_email": user_email},
            {"$push": {"payment_history": payment_record}}
        )
        
        return app.models.SubscriptionResponse(
            success=True,
            message="Subscription activated successfully",
            subscription_id=subscription.id,
            start_date=start_date,
            current_period_end=current_period_end,
            status=subscription.status
        )
        
    except stripe.error.CardError as e:
        raise HTTPException(status_code=400, detail=f"Card error: {e.user_message}")
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process subscription: {str(e)}")

# Modified cancel subscription route with email notification
@router.post("/cancel-subscription", response_model=app.models.SubscriptionResponse)
async def cancel_subscription(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Cancel an active subscription
    """
    user_email = current_user["user_email"]
    user = Collection_billing.find_one({"user_email": user_email})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    subscription = user.get("subscription")
    if not subscription or subscription.get("status") != "active":
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    try:
        # Cancel the subscription in Stripe
        cancelled = await StripeService.cancel_subscription(subscription["subscription_id"])
        
        # Update our database
        Collection_billing.update_one(
            {"user_email": user_email},
            {
                "$set": {
                    "subscription.status": "canceled",
                    "subscription.auto_renew": False
                }
            }
        )
        
        # Send cancellation email in the background
        end_date = subscription.get("current_period_end", datetime.now().strftime("%Y-%m-%d"))
        formatted_end_date = datetime.strptime(end_date, "%Y-%m-%d").strftime("%B %d, %Y")
        background_tasks.add_task(
            app.services.send_subscription_cancellation_email,
            user_email,
            formatted_end_date
        )
        
        return app.models.SubscriptionResponse(
            success=True,
            message="Subscription cancelled successfully. You'll have access until the end of your billing period.",
            subscription_id=subscription["subscription_id"],
            status="canceled"
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel subscription: {str(e)}")

@router.get("/subscription", response_model=app.models.SubscriptionInfo)
async def get_subscription(current_user: dict = Depends(get_current_user)):
    """
    Get current subscription status
    """
    user_email = current_user["user_email"]
    user = Collection_billing.find_one({"user_email": user_email})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    subscription = user.get("subscription")
    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    # If it's been a while since we updated subscription status, fetch latest from Stripe
    try:
        stripe_subscription = await StripeService.get_subscription(subscription["subscription_id"])
        
        # Update local record with latest status
        subscription["status"] = stripe_subscription.status
        subscription["current_period_end"] = datetime.fromtimestamp(
            stripe_subscription.current_period_end
        ).strftime("%Y-%m-%d")
        
        Collection_billing.update_one(
            {"user_email": user_email},
            {"$set": {"subscription": subscription}}
        )
    except:
        # If we can't reach Stripe, just return what we have
        pass
    
    return app.models.SubscriptionInfo(**subscription)

@router.put("/update-payment-method", response_model=app.models.SubscriptionResponse)
async def update_subscription_payment_method(
    payment_data: app.models.SubscriptionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update the payment method used for subscription
    """
    user_email = current_user["user_email"]
    user = Collection_billing.find_one({"user_email": user_email})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    subscription = user.get("subscription")
    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription found")
    
    stripe_customer_id = user.get("stripe_customer_id")
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="No customer record found")
    
    try:
        # Attach payment method to customer
        await StripeService.attach_payment_method_to_customer(
            payment_method_id=payment_data.payment_method_id,
            customer_id=stripe_customer_id
        )
        
        # Set as default payment method
        await StripeService.set_default_payment_method(
            customer_id=stripe_customer_id,
            payment_method_id=payment_data.payment_method_id
        )
        
        # Store payment method info in our database
        payment_method = stripe.PaymentMethod.retrieve(payment_data.payment_method_id)
        card_info = payment_method.card
        
        payment_method_record = {
            "stripe_payment_method_id": payment_data.payment_method_id,
            "cardholder_name": payment_data.cardholder_name,
            "card_last4": card_info.last4,
            "card_expiry": f"{card_info.exp_month:02d}/{str(card_info.exp_year)[-2:]}",
            "card_brand": card_info.brand,
            "billing_address": payment_data.billing_address,
            "is_default": True
        }
        
        # Set existing payment methods to non-default
        Collection_billing.update_many(
            {"user_email": user_email, "payment_methods.is_default": True},
            {"$set": {"payment_methods.$.is_default": False}}
        )
        
        # Add new payment method
        Collection_billing.update_one(
            {"user_email": user_email},
            {"$push": {"payment_methods": payment_method_record}}
        )
        
        return app.models.SubscriptionResponse(
            success=True,
            message="Payment method updated successfully",
            subscription_id=subscription["subscription_id"],
            status=subscription["status"]
        )
    except stripe.error.CardError as e:
        raise HTTPException(status_code=400, detail=f"Card error: {e.user_message}")
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update payment method: {str(e)}")

@router.get("/billingstatus", response_model=dict)
async def get_billing_status(current_user: dict = Depends(get_current_user)):
    """
    Check if the user has an active subscription.
    """
    user_email = current_user["user_email"]
    
    # Get user from database
    user = Collection_billing.find_one({"user_email": user_email})
    if not user:
        return {"has_subscription": False}
    
    # Check subscription status
    subscription = user.get("subscription", {})
    if subscription:
        current_period_end = datetime.strptime(subscription.get("current_period_end", ""), "%Y-%m-%d").date()
        today = datetime.now().date()
        has_active_subscription = subscription.get("status") == "active" or (subscription.get("status") == "canceled" and today <= current_period_end)
    else:
        has_active_subscription = False
    
    return {"has_subscription": has_active_subscription}

# Enhanced webhook handler with email notifications
@router.post("/webhook", status_code=200)
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle Stripe webhook events for subscription lifecycle
    """
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        # Verify webhook signature using your webhook secret
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    if event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        subscription_id = invoice.get('subscription')
        print(f"Subscription ID: {subscription_id}")
        
        if subscription_id:
            # Find user with this subscription
            user = Collection_billing.find_one({"subscription.subscription_id": subscription_id})
            
            if user:
                user_email = user.get("user_email")
                
                # Check the invoice's billing_reason
                billing_reason = invoice.get('billing_reason')
                print(f"Billing reason: {invoice.get('billing_reason')}")
                
                # Only process as renewal if billing_reason is 'subscription_cycle'
                if billing_reason == 'subscription_cycle':
                    # Get the current date
                    today = datetime.now().strftime("%Y-%m-%d")
                    
                    # Check if this is truly a renewal or just a duplicate event
                    # by checking if there's already a payment for today
                    subscription = user.get("subscription", {})
                    payment_history = subscription.get("payment_history", [])
                    
                    # Check if there's already a payment for today
                    payment_for_today = False
                    for payment in payment_history:
                        if payment.get("date") == today:
                            payment_for_today = True
                            break
                    
                    # Check if the subscription was created today
                    subscription_created_today = subscription.get("start_date") == today
                    
                    # Only add payment if it's not a duplicate and not the initial payment
                    if not payment_for_today or not subscription_created_today:
                        Collection_billing.update_one(
                            {"_id": user["_id"]},
                            {"$push": {
                                "subscription.payment_history": {
                                    "date": today,
                                    "purchase_id": f"SUB-{uuid.uuid4().hex[:8].upper()}",
                                    "amount": invoice.amount_paid / 100.0,
                                    "type": "subscription",
                                    "description": "Monthly Subscription Renewal",
                                    "status": "completed"
                                }
                            }}
                        )
                        
                        
                        # Remove any previous free minutes record with the same purchase ID
                        Collection_billing.update_one(
                            {"user_email": user_email},
                            {"$pull": {"payment_history": {"purchase_id": "PUR-Free"}}}
                        )
                        
                        # Add the new free minutes record
                        payment_record = {
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "purchase_id": "PUR-Free",
                            "amount": "Free",
                            "minutes": 1000,
                            "status": "completed"
                        }
                        
                        Collection_billing.update_one(
                            {"user_email": user_email},
                            {"$push": {"payment_history": payment_record}}
                        )
                        
                        # Send payment success email for renewals
                        if user_email:
                            background_tasks.add_task(
                                app.services.send_subscription_renewal_email,
                                user_email,
                                invoice.amount_paid / 100.0
                            )
    
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        subscription_id = invoice.get('subscription')
        
        if subscription_id:
            # Update subscription status
            user = Collection_billing.find_one({"subscription.subscription_id": subscription_id})
            
            if user:
                user_email = user.get("user_email")
                # Mark payment as failed for the subscription
                Collection_billing.update_one(
                    {"_id": user["_id"]},
                    {"$push": {
                        "subscription.payment_history": {
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "purchase_id": f"SUB-{uuid.uuid4().hex[:8].upper()}",
                            "amount": invoice.amount_due / 100.0,
                            "type": "subscription",
                            "description": "Monthly Subscription Renewal - Failed",
                            "status": "failed"
                        }
                    }}
                )
                
                # Send payment failed email
                if user_email:
                    background_tasks.add_task(
                        app.services.send_payment_failed_email,
                        user_email,
                        invoice.amount_due / 100.0
                    )
    
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        
        # Find user with this subscription
        user = Collection_billing.find_one({"subscription.subscription_id": subscription.id})
        
        # Update user's subscription status when cancelled
        if user:
            user_email = user.get("user_email")
            Collection_billing.update_one(
                {"subscription.subscription_id": subscription.id},
                {"$set": {
                    "subscription.status": "canceled",
                    "subscription.auto_renew": False
                }}
            )
            
            # Send subscription ended email if it was auto-cancelled by Stripe
            if user_email:
                background_tasks.add_task(
                    app.services.send_subscription_ended_email,
                    user_email
                )
    
    return {"status": "success"}

@router.post("/contact-email")
async def contact_email(request: app.models.ContactRequest):
    return await app.services.contact_email(request)


#admin routes
@router.get("/admin/allrestaurentdetails")
async def get_all_restaurents_details(current_user: User = Depends(get_current_user)):
    """
    Retrieve all users with their details.
    """
    try:
        users = await app.services.get_all_restaurents_details_service(current_user)
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))