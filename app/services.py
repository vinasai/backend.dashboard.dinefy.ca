# services.py
from app.database import collection_user
from app.models import User,PurchaseResponse, StripePaymentIntent
from app.utils import hash_password, verify_password, create_access_token,authenticate_user
from datetime import timedelta
from fastapi import HTTPException
from bson import ObjectId
from pymongo import DESCENDING
from typing import List
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import JSONResponse
from app.database import collection_restaurant, collection_call_logs ,collection_integrations, collection_user,collection_password_reset,Collection_billing,collection_email_verification,Collection_admin_billing
from jwt.exceptions import PyJWTError
from fastapi import HTTPException, status
from datetime import datetime, timedelta
from pydantic import EmailStr
import secrets
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
import uuid
import re
from app.stripe_service import StripeService
import stripe
import random
import string
from app.config import (
    MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM, 
    MAIL_PORT, MAIL_SERVER, MAIL_FROM_NAME,
    MAIL_STARTTLS, MAIL_SSL_TLS
)
from typing import Optional
from datetime import datetime, date

# Configure FastMail
conf = ConnectionConfig(
    MAIL_USERNAME=MAIL_USERNAME,
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_FROM=MAIL_FROM,
    MAIL_PORT=MAIL_PORT,
    MAIL_SERVER=MAIL_SERVER,
    MAIL_FROM_NAME=MAIL_FROM_NAME,
    MAIL_STARTTLS=MAIL_STARTTLS,
    MAIL_SSL_TLS=MAIL_SSL_TLS,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

# Rate: $0.15 per minute (20 minutes per dollar)
RATE_PER_MINUTE = 0.15

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def login_user(form_data, access_token_expire_minutes):
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token_expires = timedelta(minutes=access_token_expire_minutes)
    access_token = create_access_token(data={"email": user['user_email']}, expires_delta=access_token_expires)
    print(access_token)
    return {"access_token": access_token,"token_type": "bearer"}

def login_user_manual(user_login, ACCESS_TOKEN_EXPIRE_MINUTES):
    existing_user = collection_user.find_one(
        {"user_email": user_login.email}, 
        {"_id": 0, "user_email": 1, "user_pw": 1}
    )
    if not existing_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_pw = existing_user["user_pw"]  

    if not verify_password(user_login.password, user_pw):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"email": user_login.email}, expires_delta=access_token_expires
    )
    # Find user role
    user = collection_user.find_one({"user_email": user_login.email})
    if user:
        role = user.get("role", "user")  # Default to 'user' if role is not found
    else:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if user exists in the billing collection
    user_in_billing = Collection_billing.find_one({"user_email": user_login.email})
    is_in_billing = bool(user_in_billing)

    return {"access_token": access_token, "role": role, "is_in_billing": is_in_billing}

async def updated_user_email(email_data, current_user):
    """
    Update user email endpoint.
    Requires current password for verification.
    """
    try:
        # Validate request data
        if "new_email" not in email_data or "confirm_password" not in email_data:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        # Find user in database
        user = collection_user.find_one({"user_email": current_user["user_email"]})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check verification status
        verification_complete = email_data.get("verification_complete", False)
        if not verification_complete:
            raise HTTPException(status_code=400, detail="Email verification required")
        
        # Find verification record to ensure it's verified
        verification = collection_email_verification.find_one({
            "email": email_data["new_email"],
            "verified": True
        })
        
        if not verification:
            raise HTTPException(status_code=400, detail="Email not verified")
        
        # Update email in all collections
        collections_to_update = [collection_user, collection_call_logs, collection_integrations, collection_restaurant,Collection_billing]  # Add other collections here if needed
        for collection in collections_to_update:
            try:
                result = collection.update_many(
                    {"user_email": current_user["user_email"]},
                    {"$set": {"user_email": email_data["new_email"]}}
            )
                # Log a warning if no documents were updated in the collection
                if result.modified_count == 0:
                    print(f"Warning: No documents updated in {collection.name}")
            except Exception as e:
                # Log the exception and continue with the next collection
                print(f"Error updating email in {collection.name}: {e}")
        
        return {"new_email": email_data["new_email"]}
    
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

async def changed_user_password(new_password, current_user):
    """
    Change user password endpoint.
    Requires current password for verification.
    """
    try:
        # Validate request data
        if not new_password.newPassword or not new_password.confirmPassword:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        # Find user in database
        user = collection_user.find_one({"user_email": current_user["user_email"]})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify current password
        if not verify_password(new_password.currentPassword, user["user_pw"]):
            raise HTTPException(status_code=401, detail="Invalid current password")
        
        # Hash the new password
        hashed_new_password = hash_password(new_password.newPassword)
        
        # Update password in the user collection only
        result = collection_user.update_one(
            {"user_email": current_user["user_email"]},
            {"$set": {"user_pw": hashed_new_password}}
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Failed to update password")
        
        return {"message": "Password changed successfully"}
    
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    
async def deleted_user_account(delete_account, current_user):
    """
    Delete user account endpoint.
    Requires current password for verification.
    """
    try:
        # Validate request data
        if not delete_account.CurrentEmail:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        # Find user in database
        user = collection_user.find_one({"user_email": current_user["user_email"]})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify current email matches the user's email
        if delete_account.CurrentEmail != current_user["user_email"]:
            raise HTTPException(status_code=401, detail="Invalid current email")
        
        # Collections to delete user data from
        collections_to_delete = [collection_user, collection_call_logs, collection_integrations, collection_restaurant,Collection_billing]
        
        # Iterate through each collection and delete user data
        for collection in collections_to_delete:
            try:
                result = collection.delete_many({"user_email": current_user["user_email"]})
                # Log a warning if no documents were deleted in the collection
                if result.deleted_count == 0:
                    print(f"Warning: No documents deleted in {collection.name}")
            except Exception as e:
                # Log the exception and continue with the next collection
                print(f"Error deleting data from {collection.name}: {e}")
        
        return {"message": "Account deleted successfully"}
    
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

async def get_restaurant_details(current_user):
    """
    Retrieve restaurant details for a specific user
    """
    restaurant_details = collection_restaurant.find_one(
        {"user_email": current_user["user_email"]},
        {"_id": 0}  # Exclude MongoDB's internal _id
    )
    return restaurant_details

async def save_restaurant_details(RestaurantDetails, current_user):
    """
    Save restaurant details for a specific user
    """
    # Convert Pydantic model to dictionary and handle HttpUrl conversion
    details_dict = RestaurantDetails.dict()
    
    # Convert HttpUrl to string if it exists
    if 'website' in details_dict and details_dict['website']:
        details_dict['website'] = str(details_dict['website'])
    
    # Add user email to the details
    details_dict['user_email'] = current_user["user_email"]
    
    # Check if details already exist for this user
    existing_details = collection_restaurant.find_one({"user_email": current_user["user_email"]})
    
    if existing_details:
        # Update existing details
        result = collection_restaurant.update_one(
            {"user_email": current_user["user_email"]},
            {"$set": details_dict}
        )
        if result.modified_count == 0:
            return {"message": "No changes detected", "status": "unchanged"}
        return {"message": "Restaurant details updated successfully", "status": "updated"}
    else:
        # Insert new details
        result = collection_restaurant.insert_one(details_dict)
        if not result.inserted_id:
            raise HTTPException(status_code=500, detail="Failed to save restaurant details")
        return {"message": "Restaurant details saved successfully", "status": "created"}
  
async def get_call_logs_service(current_user):
    """
    Retrieve call logs for the current user's user email.
    """

    # Query the call logs collection for the given user email
    call_logs = collection_call_logs.find(
        {"user_email": current_user["user_email"]},
        {"_id": 0}  # Exclude MongoDB's internal _id
    ).sort("timestamp", DESCENDING)  # Sort by timestamp in descending order

    # Convert the cursor to a list
    call_logs_list = list(call_logs)

    # Return the call logs list or an empty array if no logs are found
    return call_logs_list if call_logs_list else []
  
async def get_user_integrations(current_user: dict):
    """Get all integrations for a user"""
    integrations = collection_integrations.find_one({"user_email": current_user["user_email"]})
    if integrations:
        integrations.pop("_id", None)
        return integrations
    return None

async def update_integration(current_user: dict, integration_name: str, integration_data: dict):
    """Update a specific integration for a user"""
    user_email = current_user["user_email"]
    
    # Check if the user already has integrations
    existing_integrations = await get_user_integrations(current_user)
    
    if existing_integrations:
        # Update the specific integration
        collection_integrations.update_one(
            {"user_email": user_email},
            {"$set": {f"integrations.{integration_name}": integration_data}}
        )
    else:
        # Create a new integrations document
        new_integration = {
            "user_email": user_email,
            "integrations": {
                integration_name: integration_data
            }
        }
        collection_integrations.insert_one(new_integration)


async def request_password_reset(email: EmailStr):
    """
    Generate a password reset code and store it in the database.
    
    Args:
        email: The user's email address
        
    Returns:
        Dict containing success message
    """
    # Check if user exists
    user = collection_user.find_one({"user_email": email})
    if not user:
        raise HTTPException(status_code=404, detail="Email is not registered")
    
    # Generate a 6-digit verification code
    verification_code = ''.join(secrets.choice('0123456789') for _ in range(6))
    
    # Store the code in the database with expiration time (5 minutes from now)
    expiration_time = datetime.utcnow() + timedelta(minutes=5)
    
    # Remove any existing reset requests for this email
    collection_password_reset.delete_many({"email": email})
    
    # Insert the new reset request
    collection_password_reset.insert_one({
        "email": email,
        "code": verification_code,
        "expires_at": expiration_time,
        "created_at": datetime.utcnow()
    })
    
    # For development, we'll just print it
    print(f"Password reset code for {email}: {verification_code}")
    
    # Send the verification code to the user's email
    message = MessageSchema(
        subject="Password Reset Verification Code - Dinefy",
        recipients=[email],
        body=f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h2 style="color: #2c3e50;">Password Reset Request</h2>
                    <p style="font-size: 16px; color: #34495e;">
                        We received a request to reset the password associated with your Dinefy account.
                    </p>
                    <p style="font-size: 16px; color: #34495e;">
                        Please use the verification code below to proceed:
                    </p>
                    <p style="font-size: 26px; font-weight: bold; color: #e74c3c; text-align: center;">
                        {verification_code}
                    </p>
                    <p style="font-size: 16px; color: #34495e;">
                        This code will expire in <strong>5 minutes</strong> for your security.
                    </p>
                    <p style="font-size: 14px; color: #7f8c8d;">
                        If you did not initiate this password reset request, no further action is required. Your account remains secure.
                    </p>
                    <br>
                    <p style="font-size: 16px; color: #34495e;">
                        Best regards,<br>
                        The Dinefy Team
                    </p>
                </div>
            </body>
        </html>
        """,
        subtype="html"
    )

    
    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        print(f"Password reset code sent to {email}")
    except Exception as e:
        print(f"Failed to send email: {e}")
        # You may want to handle this error more gracefully
    
    return {"message": "If your email is registered, a reset code has been sent"}

async def send_email(request):
    message = MessageSchema(
        subject="New Demo Request from Dinefy",
        recipients=[MAIL_USERNAME],  # Add your target email(s)
        body=f"""
        You have received a new demo request:

        Name: {request.name}
        Email: {request.email}
        Phone: {request.phone}
        Restaurant: {request.restaurant}
        Address: {request.address}
        Preferred Date: {request.date}
        Preferred Time: {request.time}
        Message: {request.message}
        Consent Given: {request.consent}
        """,
        subtype="plain"
    )

    fm = FastMail(conf)
    await fm.send_message(message)

    return JSONResponse(status_code=status.HTTP_200_OK, content={"message": "Email sent successfully"})

async def contact_email(request):
    message = MessageSchema(
        subject="Contact with Dinefy",
        recipients=[MAIL_USERNAME], 
        body=f"""
        You have received a new contact request:

        Name: {request.name}
        Email: {request.email}
        Message: {request.subject}
        Message: {request.message}
        """,
        subtype="plain"
    )

    fm = FastMail(conf)
    await fm.send_message(message)

    return JSONResponse(status_code=status.HTTP_200_OK, content={"message": "Email sent successfully"})

async def verify_reset_code_and_reset_password(email: EmailStr, code: str, new_password: str):
    """
    Verify the reset code and update the user's password if valid.
    
    Args:
        email: The user's email address
        code: The verification code
        new_password: The new password
        
    Returns:
        Dict containing success message
    """
    # Find the reset request
    reset_request = collection_password_reset.find_one({
        "email": email,
        "code": code
    })
    
    if not reset_request:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    
    # Check if the code has expired
    if reset_request["expires_at"] < datetime.utcnow():
        # Remove expired reset request
        collection_password_reset.delete_one({"_id": reset_request["_id"]})
        raise HTTPException(status_code=400, detail="Verification code has expired")
    
    # Find the user
    user = collection_user.find_one({"user_email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Hash the new password
    hashed_password = hash_password(new_password)
    
    # Update the user's password
    result = collection_user.update_one(
        {"user_email": email},
        {"$set": {"user_pw": hashed_password}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update password")
    
    # Remove the reset request
    collection_password_reset.delete_one({"_id": reset_request["_id"]})
    
    return {"message": "Password has been reset successfully"}


async def get_user_billing_info(current_user):
    """
    Get billing information for a user including payment methods, payment history, and usage
    """
    user_email = current_user["user_email"]
    
    # Get user from database
    user = Collection_billing.find_one({"user_email": user_email})
    if not user:
        # Return empty data if no user is found
        return {
            "remaining_minutes": 0,
            "total_minutes": 0,
            "payment_methods": [],
            "payment_history": []
        }
    
    # Extract billing information
    payment_methods = user.get("payment_methods", [])
    payment_history = user.get("payment_history", [])
    
    # Retrieve call durations for the specific user
    call_logs = collection_call_logs.find(
        {"user_email": current_user["user_email"]},
        {"duration": 1, "_id": 0}
    )

    # Convert durations to total minutes
    total_minutes_used = 0
    for log in call_logs:
        duration = log.get("duration", "0:00")
        try:
            minutes, seconds = map(int, duration.split(":"))
            total_minutes_used += minutes + (seconds / 60)
        except ValueError:
            print(f"Invalid duration format: {duration}")

    # Calculate remaining minutes
    total_minutes_purchased = sum(payment.get("minutes", 0) for payment in payment_history)
    remaining_minutes = int(max(0, total_minutes_purchased - total_minutes_used))

    return {
        "remaining_minutes": remaining_minutes,
        "total_minutes": total_minutes_purchased,
        "payment_methods": payment_methods,
        "payment_history": payment_history
    }

async def add_payment_method(payment_method_data, current_user):
    """
    Add a payment method using Stripe payment method ID
    """
    user_email = current_user["user_email"]
    
    # Check if user has a Stripe customer ID, create if not
    user = Collection_billing.find_one({"user_email": user_email})
    stripe_customer_id = user.get("stripe_customer_id") if user else None
    
    if not stripe_customer_id:
        stripe_customer_id = await StripeService.create_customer(
            email=user_email,
            name=current_user.get("name", "")
        )
        
        if not user:
            # Create new user record
            Collection_billing.insert_one({
                "user_email": user_email,
                "stripe_customer_id": stripe_customer_id,
                "payment_methods": [],
                "payment_history": []
            })
        else:
            # Update existing user with Stripe customer ID
            Collection_billing.update_one(
                {"user_email": user_email},
                {"$set": {"stripe_customer_id": stripe_customer_id}}
            )
    
    # Attach payment method to customer
    await StripeService.attach_payment_method_to_customer(
        payment_method_data.payment_method_id,
        stripe_customer_id
    )
    
    # Retrieve payment method details from Stripe
    payment_method = stripe.PaymentMethod.retrieve(payment_method_data.payment_method_id)
    
    # Use the user-provided cardholder name if available, otherwise fallback
    cardholder_name = payment_method_data.cardholder_name or payment_method.billing_details.name or "Cardholder"
    
    # Create our local masked version for display
    payment_method_record = {
        "cardholder_name": cardholder_name,
        "card_number": f"**** **** **** {payment_method.card.last4}",
        "expiry_date": f"{payment_method.card.exp_month:02d}/{payment_method.card.exp_year % 100:02d}",
        "cvc": "***",
        "stripe_payment_method_id": payment_method.id,
        "fingerprint": payment_method.card.fingerprint,
        "brand": payment_method.card.brand,
        "last4": payment_method.card.last4
    }
    
    # Update database
    result = Collection_billing.update_one(
        {"user_email": user_email},
        {"$push": {"payment_methods": payment_method_record}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to add payment method")
    
    return {"message": "Payment method added successfully", "stripe_payment_method_id": payment_method.id}

async def purchase_minutes(purchase_data, current_user):
    """
    Purchase minutes using Stripe payment processing
    """
    user_email = current_user["user_email"]
    user = Collection_billing.find_one({"user_email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    stripe_customer_id = user.get("stripe_customer_id")
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="No payment methods available")
    
    # Check if payment_method_id is a Stripe ID or our index
    if purchase_data.payment_method_id.startswith("pm_"):
        # It's a Stripe PaymentMethod ID
        stripe_payment_method_id = purchase_data.payment_method_id
    else:
        # It's our index-based ID
        try:
            payment_method_index = int(purchase_data.payment_method_id)
            payment_methods = user.get("payment_methods", [])
            if payment_method_index < 0 or payment_method_index >= len(payment_methods):
                raise HTTPException(status_code=400, detail="Invalid payment method selected")
            
            stripe_payment_method_id = payment_methods[payment_method_index].get("stripe_payment_method_id")
            if not stripe_payment_method_id:
                raise HTTPException(status_code=400, detail="Payment method not properly initialized")
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid payment method ID")
    
    # Calculate minutes
    amount = purchase_data.amount
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
    
    minutes = int(amount / RATE_PER_MINUTE)
    purchase_id = f"PUR-{uuid.uuid4().hex[:8].upper()}"
    
    # Create Stripe payment intent
    payment_intent = await StripeService.create_payment_intent(
        amount=amount,
        customer_id=stripe_customer_id,
        payment_method_id=stripe_payment_method_id,
        save_payment_method=purchase_data.save_payment_method,
        metadata={
            "purchase_id": purchase_id,
            "user_email": user_email,
            "minutes": str(minutes)
        }
    )
    
    # For immediate confirmation (you might want client-side confirmation instead)
    try:
        confirmed_intent = await StripeService.confirm_payment_intent(payment_intent.id)
        
        if confirmed_intent.status != "succeeded":
            raise HTTPException(
                status_code=400,
                detail=f"Payment failed: {confirmed_intent.last_payment_error.message if confirmed_intent.last_payment_error else 'Unknown error'}"
            )
        
        # Record successful payment
        payment_record = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "purchase_id": purchase_id,
            "amount": amount,
            "minutes": minutes,
            "status": "completed"
        }
        
        Collection_billing.update_one(
            {"user_email": user_email},
            {"$push": {"payment_history": payment_record}}
        )
        
        return PurchaseResponse(
            success=True,
            message=f"Successfully purchased {minutes} minutes",
            purchase_id=purchase_id,
            amount=amount,
            minutes=minutes,
            date=payment_record["date"]
        )
    except Exception as e:
        # In production, you might want to handle this differently
        return PurchaseResponse(
            success=False,
            message=str(e),
            payment_intent=StripePaymentIntent(
                client_secret=payment_intent.client_secret,
                payment_intent_id=payment_intent.id,
                amount=amount,
                currency=payment_intent.currency,
                status=payment_intent.status
            )
        )

async def delete_payment_method(payment_method_index, current_user):
    """
    Delete a payment method both locally and in Stripe
    """
    user_email = current_user["user_email"]
    
    try:
        index = int(payment_method_index)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment method index")
    
    user = Collection_billing.find_one({"user_email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    payment_methods = user.get("payment_methods", [])
    if index < 0 or index >= len(payment_methods):
        raise HTTPException(status_code=404, detail="Payment method not found")
    
    # Get Stripe payment method ID before deleting
    stripe_payment_method_id = payment_methods[index].get("stripe_payment_method_id")
    
    # Remove from our database first
    result = Collection_billing.update_one(
        {"user_email": user_email},
        {"$unset": {f"payment_methods.{index}": 1}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to remove payment method")
    
    # Clean up null elements
    Collection_billing.update_one(
        {"user_email": user_email},
        {"$pull": {"payment_methods": None}}
    )
    
    # If we have a Stripe ID, detach from customer
    if stripe_payment_method_id:
        try:
            await StripeService.detach_payment_method(stripe_payment_method_id)
        except Exception as e:
            # Log this error but don't fail the request
            print(f"Failed to detach Stripe payment method: {str(e)}")
    
    return {"message": "Payment method removed successfully"}

async def get_user_twilio_number(user_email: str) -> str:
    """Get the Twilio number associated with a user's email"""
    try:
        user = collection_user.find_one({"user_email": user_email})
        if user:
            return user["twilio_number"]
        return ""
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_call_data(start_date: datetime.date, end_date: datetime.date, user_email: str):
    try:
        start = datetime.combine(start_date, datetime.min.time())
        end = datetime.combine(end_date, datetime.max.time())

        print(f"Searching for data:\nUser email: {user_email}\nDate range: {start} to {end}")

        sample_data = list(collection_call_logs.find({"user_email": user_email}).limit(1))
        print(f"Sample data available: {len(sample_data) > 0}")
        # if sample_data:
        #     print(f"Sample document: {sample_data[0]}")

        pipeline = [
            {
                "$match": {
                    "user_email": user_email,
                    "$expr": {
                        "$and": [
                            {
                                "$let": {
                                    "vars": {
                                        "date_obj": {
                                            "$dateFromString": {
                                                "dateString": "$date_time",
                                                "format": "%Y-%m-%d %H:%M"
                                            }
                                        }
                                    },
                                    "in": {
                                        "$and": [
                                            {"$gte": ["$$date_obj", start]},
                                            {"$lte": ["$$date_obj", end]}
                                        ]
                                    }
                                }
                            }
                        ]
                    }
                }
            },
            {
                "$group": {
                    "_id": {
                        "$substr": ["$date_time", 0, 10]
                    },
                    "calls": {"$sum": 1},
                    "minutes": {
                        "$sum": {
                            "$let": {
                                "vars": {
                                    "time_parts": {"$split": ["$duration", ":"]}
                                },
                                "in": {
                                    "$divide": [
                                        {
                                            "$add": [
                                                {
                                                    "$multiply": [
                                                        {"$toInt": {"$arrayElemAt": ["$$time_parts", 0]}},
                                                        60
                                                    ]
                                                },
                                                {"$toInt": {"$arrayElemAt": ["$$time_parts", 1]}}
                                            ]
                                        },
                                        60
                                    ]
                                }
                            }
                        }
                    },
                    "orders": {"$sum": {"$cond": [{"$eq": ["$order", True]}, 1, 0]}},
                    "satisfaction_sum": {"$sum": "$satisfaction"},
                    "satisfaction_count": {"$sum": 1}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "date": "$_id",
                    "calls": 1,
                    "minutes": 1,
                    "orders": 1,
                    "satisfaction": {
                        "$cond": [
                            {"$gt": ["$satisfaction_count", 0]},
                            {"$divide": ["$satisfaction_sum", "$satisfaction_count"]},
                            0
                        ]
                    }
                }
            },
            {"$sort": {"date": 1}}
        ]

        # print("Executing pipeline:", pipeline)
        call_data = list(collection_call_logs.aggregate(pipeline))
        print(f"Found {len(call_data)} results")
        if call_data:
            print(f"Sample result: {call_data[0]}")

        date_range = []
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            existing_data = next((item for item in call_data if item["date"] == date_str), None)
            date_range.append(existing_data or {
                "date": date_str,
                "calls": 0,
                "minutes": 0,
                "orders": 0,
                "satisfaction": 0
            })
            current_date += timedelta(days=1)

        total_calls = sum(item["calls"] for item in call_data)
        total_minutes = sum(item["minutes"] for item in call_data)
        total_orders = sum(item["orders"] for item in call_data)
        satisfaction_values = [item["satisfaction"] for item in call_data if item["satisfaction"] > 0]
        avg_satisfaction = sum(satisfaction_values) / len(satisfaction_values) if satisfaction_values else 0

        # Previous period data
        days_diff = (end_date - start_date).days + 1
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days_diff - 1)
        prev_start_dt = datetime.combine(prev_start, datetime.min.time())
        prev_end_dt = datetime.combine(prev_end, datetime.max.time())

        prev_pipeline = [
            {
                "$match": {
                    "user_email": user_email,
                    "$expr": {
                        "$and": [
                            {
                                "$let": {
                                    "vars": {
                                        "date_obj": {
                                            "$dateFromString": {
                                                "dateString": "$date_time",
                                                "format": "%Y-%m-%d %H:%M"
                                            }
                                        }
                                    },
                                    "in": {
                                        "$and": [
                                            {"$gte": ["$$date_obj", prev_start_dt]},
                                            {"$lte": ["$$date_obj", prev_end_dt]}
                                        ]
                                    }
                                }
                            }
                        ]
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "prev_calls": {"$sum": 1},
                    "prev_minutes": {
                        "$sum": {
                            "$let": {
                                "vars": {
                                    "time_parts": {"$split": ["$duration", ":"]}
                                },
                                "in": {
                                    "$divide": [
                                        {
                                            "$add": [
                                                {
                                                    "$multiply": [
                                                        {"$toInt": {"$arrayElemAt": ["$$time_parts", 0]}},
                                                        60
                                                    ]
                                                },
                                                {"$toInt": {"$arrayElemAt": ["$$time_parts", 1]}}
                                            ]
                                        },
                                        60
                                    ]
                                }
                            }
                        }
                    },
                    "prev_orders": {"$sum": {"$cond": [{"$eq": ["$order", True]}, 1, 0]}},
                    "prev_satisfaction_sum": {"$sum": "$satisfaction"},
                    "prev_satisfaction_count": {"$sum": 1}
                }
            }
        ]

        prev_data = list(collection_call_logs.aggregate(prev_pipeline))
        prev = prev_data[0] if prev_data else {
            "prev_calls": 0,
            "prev_minutes": 0,
            "prev_orders": 0,
            "prev_satisfaction_sum": 0,
            "prev_satisfaction_count": 0
        }

        prev_avg_satisfaction = (
            prev["prev_satisfaction_sum"] / prev["prev_satisfaction_count"]
            if prev["prev_satisfaction_count"] > 0 else 0
        )

        stats = {
            "total_calls": total_calls,
            "total_minutes": total_minutes,
            "total_orders": total_orders,
            "avg_satisfaction": round(avg_satisfaction, 1),
            "calls_change": calculate_percent_change(total_calls, prev["prev_calls"]),
            "minutes_change": round(calculate_percent_change(total_minutes, prev["prev_minutes"]), 2),
            "orders_change": calculate_percent_change(total_orders, prev["prev_orders"]),
            "satisfaction_change": calculate_percent_change(avg_satisfaction, prev_avg_satisfaction)
        }

        return {"data": date_range, "stats": stats}

    except Exception as e:
        print(f"Error getting call data: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving call data: {str(e)}")


def calculate_percent_change(current, previous):
    """Calculate percentage change between two values"""
    if previous == 0:
        return 100 if current > 0 else 0
    return round(((current - previous) / previous) * 100, 1)

def calculate_percent_change(current, previous):
    """Calculate percentage change between two values"""
    if previous == 0:
        return 100 if current > 0 else 0
    return round(((current - previous) / previous) * 100, 1)

async def get_user_minutes_info(user_email: str):
    """
    Get minutes information for a user including remaining minutes and total purchased minutes
    """
    # Get user from database
    user = Collection_billing.find_one({"user_email": user_email})
    if not user:
        return {"remaining_minutes": 0, "total_minutes": 0}
    
    # Retrieve call durations for the specific user
    call_logs = collection_call_logs.find(
        {"user_email": user_email},
        {"duration": 1, "_id": 0}
    )

    # Convert durations to total minutes
    total_minutes_used = 0
    for log in call_logs:
        duration = log.get("duration", "0:00")
        try:
            minutes, seconds = map(int, duration.split(":"))
            total_minutes_used += minutes + (seconds / 60)
        except ValueError:
            print(f"Invalid duration format: {duration}")

    # Get payment history to calculate total purchased minutes
    payment_history = user.get("payment_history", [])
    total_minutes_purchased = sum(payment.get("minutes", 0) for payment in payment_history)
    
    # Calculate remaining minutes
    remaining_minutes = max(0, total_minutes_purchased - total_minutes_used)
    
    return {
        "remaining_minutes": round(remaining_minutes, 1),
        "total_minutes": total_minutes_purchased
    }


def generate_verification_code(length=6):
    """Generate a random verification code of specified length."""
    return ''.join(random.choices(string.digits, k=length))


async def send_verification_email(email: EmailStr, verification_code: str):
    """Send verification email to user."""
    message = MessageSchema(
        subject="Email Verification - Dinefy",
        recipients=[email],
        body=f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1);">
                    <h2 style="color: #2c3e50;">Welcome to Dinefy!</h2>
                    <p style="font-size: 16px; color: #34495e;">
                        Thank you for registering with <strong>Dinefy</strong>.
                    </p>
                    <p style="font-size: 16px; color: #34495e;">
                        To complete your registration, please verify your email address using the verification code below:
                    </p>
                    <p style="font-size: 24px; font-weight: bold; color: #2980b9; text-align: center;">
                        {verification_code}
                    </p>
                    <p style="font-size: 16px; color: #34495e;">
                        Enter this code on the verification page. For your security, this code will expire in <strong>10 minutes</strong>.
                    </p>
                    <p style="font-size: 14px; color: #7f8c8d;">
                        After email verification use YOUR OWN TWILIO NUMBER or use this,
                    </p>
                    <p style="font-size: 24px; font-weight: bold; color: #2980b9; text-align: center;">
                        Temporary Dinefy number +1 978 631 1190 to sign up,
                    </p>
                    <p style="font-size: 14px; color: #7f8c8d;">
                        while we assign you one.
                    </p>
                    <p style="font-size: 14px; color: #7f8c8d;">
                        If you did not create an account with Dinefy, please disregard this message.
                    </p>
                    <br>
                    <p style="font-size: 16px; color: #34495e;">
                        Best regards,<br>
                        The Dinefy Team
                    </p>
                </div>
            </body>
        </html>
        """,
        subtype="html"
    )

    fm = FastMail(conf)
    await fm.send_message(message)
    return {"message": "Verification email sent"}

async def request_email_verification(email: EmailStr):
    """Generate and store verification code, then send email."""
    # Check if email already exists in users collection
    existing_user = collection_user.find_one({"user_email": email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Generate verification code
    verification_code = generate_verification_code()
    
    # Store verification code with expiry (10 minutes)
    expiry = datetime.utcnow() + timedelta(minutes=10)
    
    # Update or insert verification document
    collection_email_verification.update_one(
        {"email": email},
        {"$set": {
            "email": email,
            "verification_code": verification_code,
            "expiry": expiry
        }},
        upsert=True
    )
    
    # Send verification email
    await send_verification_email(email, verification_code)
    return {"message": "Verification email sent"}

async def verify_email_code(email: EmailStr, code: str):
    """Verify the email verification code."""
    # Find verification document
    verification = collection_email_verification.find_one({"email": email})
    
    if not verification:
        raise HTTPException(status_code=404, detail="Verification request not found")
    
    # Check if code has expired
    if datetime.utcnow() > verification.get("expiry", datetime.min):
        raise HTTPException(status_code=400, detail="Verification code has expired")
    
    # Check if code matches
    if verification["verification_code"] != code:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    
    # Mark email as verified after successful verification
    collection_email_verification.update_one(
        {"email": email},
        {"$set": {"verified": True}}
    )
    
    return {"message": "Email verified successfully"}

# Modified create_new_user function to check email verification and Twilio number uniqueness
def create_new_user(user: User):
    existing_user = collection_user.find_one({"user_email": user.user_email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check if email has been verified
    verification = collection_email_verification.find_one({
        "email": user.user_email,
        "verified": True
    })
    
    if not verification:
        raise HTTPException(status_code=400, detail="Email not verified")
    
    # Check if Twilio number is already in use
    existing_twilio_number = collection_user.find_one({"twilio_number": user.twilio_number})
    if existing_twilio_number:
        raise HTTPException(status_code=400, detail="Twilio number already in use")
    
    # Hash the password before storing in the database
    hashed_password = hash_password(user.user_pw)
    
    # Modify user data to include hashed password
    user_data = user.dict()
    user_data["user_pw"] = hashed_password
    user_data["verified"] = True
    user_data["created_at"] = datetime.utcnow()
    user_data["role"] = "user"
    
    # Insert user data into MongoDB
    inserted_user = collection_user.insert_one(user_data)
    
    # Remove the verification document
    collection_email_verification.delete_one({"email": user.user_email})
    
    return {"message": "User created successfully"}

async def send_subscription_confirmation_email(email: str, plan_type: str = "monthly"):
    """
    Send email confirmation when a user subscribes to a plan
    
    Args:
        email: The user's email address
        plan_type: The type of subscription plan (default: monthly)
    """
    current_date = datetime.now().strftime("%B %d, %Y")
    message = MessageSchema(
        subject="Your Dinefy Subscription is Confirmed",
        recipients=[email],
        body=f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h2 style="color: #2c3e50;">Subscription Confirmation</h2>
                    <p style="font-size: 16px; color: #34495e;">
                        Thank you for subscribing to Dinefy! Your {plan_type} subscription is now active.
                    </p>
                    <div style="background-color: #f8f9fa; border-radius: 5px; padding: 15px; margin: 20px 0;">
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            <strong>Subscription Details:</strong>
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            Plan: {plan_type.capitalize()} Plan ($149/month)
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            Start Date: {current_date}
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            Status: Active
                        </p>
                    </div>
                    <p style="font-size: 16px; color: #34495e;">
                        You can manage your subscription at any time from your account dashboard.
                    </p>
                    <p style="font-size: 16px; color: #34495e;">
                        If you have any questions or need assistance, please don't hesitate to contact our support team.
                    </p>
                    <br>
                    <p style="font-size: 16px; color: #34495e;">
                        Best regards,<br>
                        The Dinefy Team
                    </p>
                </div>
            </body>
        </html>
        """,
        subtype="html"
    )
    
    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        print(f"Subscription confirmation email sent to {email}")
        return True
    except Exception as e:
        print(f"Failed to send subscription confirmation email: {e}")
        return False

async def send_subscription_cancellation_email(email: str, end_date: str):
    """
    Send email confirmation when a user cancels their subscription
    
    Args:
        email: The user's email address
        end_date: The date when the subscription will end
    """
    current_date = datetime.now().strftime("%B %d, %Y")
    message = MessageSchema(
        subject="Your Dinefy Subscription Has Been Canceled",
        recipients=[email],
        body=f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h2 style="color: #2c3e50;">Subscription Cancellation Confirmation</h2>
                    <p style="font-size: 16px; color: #34495e;">
                        We're sorry to see you go. Your Dinefy subscription has been canceled as requested.
                    </p>
                    <div style="background-color: #f8f9fa; border-radius: 5px; padding: 15px; margin: 20px 0;">
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            <strong>Cancellation Details:</strong>
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            Cancellation Date: {current_date}
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            Service End Date: {end_date}
                        </p>
                    </div>
                    <p style="font-size: 16px; color: #34495e;">
                        You will continue to have access to all Dinefy features until the end of your current billing period.
                    </p>
                    <p style="font-size: 16px; color: #34495e;">
                        If you've changed your mind or canceled by mistake, you can reactivate your subscription anytime from your account dashboard before your service ends.
                    </p>
                    <p style="font-size: 16px; color: #34495e;">
                        We'd love to hear your feedback on why you decided to cancel. Your insights help us improve our service.
                    </p>
                    <br>
                    <p style="font-size: 16px; color: #34495e;">
                        Best regards,<br>
                        The Dinefy Team
                    </p>
                </div>
            </body>
        </html>
        """,
        subtype="html"
    )
    
    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        print(f"Subscription cancellation email sent to {email}")
        return True
    except Exception as e:
        print(f"Failed to send subscription cancellation email: {e}")
        return False
    

async def send_subscription_renewal_email(email: str, amount: float):
    """
    Send email notification for subscription renewal
    
    Args:
        email: The user's email address
        amount: The renewal amount charged
    """
    current_date = datetime.now().strftime("%B %d, %Y")
    message = MessageSchema(
        subject="Your Dinefy Subscription Has Been Renewed",
        recipients=[email],
        body=f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h2 style="color: #2c3e50;">Subscription Renewal Confirmation</h2>
                    <p style="font-size: 16px; color: #34495e;">
                        Your Dinefy subscription has been successfully renewed.
                    </p>
                    <div style="background-color: #f8f9fa; border-radius: 5px; padding: 15px; margin: 20px 0;">
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            <strong>Payment Details:</strong>
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            Amount: ${amount:.2f}
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            Date: {current_date}
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            Plan: Monthly Subscription
                        </p>
                    </div>
                    <p style="font-size: 16px; color: #34495e;">
                        Thank you for your continued support. You can view your billing details anytime in your account dashboard.
                    </p>
                    <br>
                    <p style="font-size: 16px; color: #34495e;">
                        Best regards,<br>
                        The Dinefy Team
                    </p>
                </div>
            </body>
        </html>
        """,
        subtype="html"
    )
    
    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        print(f"Subscription renewal email sent to {email}")
        return True
    except Exception as e:
        print(f"Failed to send subscription renewal email: {e}")
        return False

async def send_payment_failed_email(email: str, amount: float):
    """
    Send email notification for failed payment
    
    Args:
        email: The user's email address
        amount: The payment amount that failed
    """
    current_date = datetime.now().strftime("%B %d, %Y")
    message = MessageSchema(
        subject="Action Required: Your Dinefy Payment Failed",
        recipients=[email],
        body=f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h2 style="color: #2c3e50;">Payment Failed</h2>
                    <p style="font-size: 16px; color: #34495e;">
                        We were unable to process your subscription payment.
                    </p>
                    <div style="background-color: #f8f9fa; border-radius: 5px; padding: 15px; margin: 20px 0;">
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            <strong>Payment Details:</strong>
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            Amount: ${amount:.2f}
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            Date: {current_date}
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            Plan: Monthly Subscription
                        </p>
                    </div>
                    <p style="font-size: 16px; color: #34495e;">
                        <strong>What you need to do:</strong>
                    </p>
                    <ol style="font-size: 16px; color: #34495e;">
                        <li>Log in to your Dinefy account</li>
                        <li>Go to the Billing section</li>
                        <li>Update your payment method or add a new one</li>
                    </ol>
                    <p style="font-size: 16px; color: #34495e;">
                        We'll try charging your payment method again in the next few days. If we're still unable to process the payment, your subscription may be canceled.
                    </p>
                    <br>
                    <p style="font-size: 16px; color: #34495e;">
                        Best regards,<br>
                        The Dinefy Team
                    </p>
                </div>
            </body>
        </html>
        """,
        subtype="html"
    )
    
    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        print(f"Payment failed email sent to {email}")
        return True
    except Exception as e:
        print(f"Failed to send payment failed email: {e}")
        return False

async def send_subscription_ended_email(email: str):
    """
    Send email notification when a subscription ends (auto-cancellation)
    
    Args:
        email: The user's email address
    """
    current_date = datetime.now().strftime("%B %d, %Y")
    message = MessageSchema(
        subject="Your Dinefy Subscription Has Ended",
        recipients=[email],
        body=f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h2 style="color: #2c3e50;">Subscription Ended</h2>
                    <p style="font-size: 16px; color: #34495e;">
                        Your Dinefy subscription has ended, and your access to premium features has been discontinued.
                    </p>
                    <p style="font-size: 16px; color: #34495e;">
                        We value your business and hope you've enjoyed using our service. You can reactivate your subscription at any time from your account dashboard to regain access to all premium features.
                    </p>
                    <div style="background-color: #f8f9fa; border-radius: 5px; padding: 15px; margin: 20px 0;">
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            <strong>Subscription Details:</strong>
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            End Date: {current_date}
                        </p>
                        <p style="font-size: 16px; color: #34495e; margin: 5px 0;">
                            Status: Ended
                        </p>
                    </div>
                    <p style="font-size: 16px; color: #34495e;">
                        We'd love to hear your feedback on your experience with Dinefy. Your insights help us improve our service.
                    </p>
                    <p style="font-size: 16px; color: #34495e;">
                        If you have any questions or need assistance, please don't hesitate to contact our support team.
                    </p>
                    <br>
                    <p style="font-size: 16px; color: #34495e;">
                        Best regards,<br>
                        The Dinefy Team
                    </p>
                </div>
            </body>
        </html>
        """,
        subtype="html"
    )
    
    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        print(f"Subscription ended email sent to {email}")
        return True
    except Exception as e:
        print(f"Failed to send subscription ended email: {e}")
        return False
 
async def get_restaurant_name(current_user):
    try:
        user_email = current_user["user_email"]
        # Retrieve restaurant details for the user
        restaurant = collection_restaurant.find_one({"user_email": user_email}, {"restaurant_name": 1})
        if restaurant and restaurant.get("restaurant_name"):
            return restaurant.get("restaurant_name")
        else:
            return None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving restaurant name: {str(e)}")
        
          
#admin services  
async def get_all_restaurents_details_service(current_user):
    """
    Retrieve all restaurant details from the restaurant details collection.
    """
    try:
        # Query the restaurant collection to retrieve all documents
        restaurants = collection_restaurant.find({}, {"_id": 1, "restaurant_name": 1, "address": 1, "user_email": 1, "phone_number": 1, "website": 1, "features": 1, "greetingMessage": 1, "endingMessage": 1})
        
        # Convert the cursor to a list and include the ObjectId as a string
        restaurant_list = []
        for restaurant in restaurants:
            # Retrieve integrations for the user
            integrations = collection_integrations.find_one({"user_email": restaurant.get("user_email", "")})
            integration_status = {
            "shopify": integrations.get("integrations", {}).get("shopify", {}).get("connected", False) if integrations else False,
            "clover": integrations.get("integrations", {}).get("clover", {}).get("connected", False) if integrations else False,
            }
            
            twilionumber = collection_user.find_one({"user_email": restaurant.get("user_email", "")})
            if twilionumber:
                restaurant["twilio_number"] = twilionumber.get("twilio_number", "")
            
            restaurant_list.append({
            "id": str(restaurant["_id"]),
            "email": restaurant.get("user_email", ""),
            "restaurantName": restaurant.get("restaurant_name", ""),
            "phoneNumber": restaurant.get("phone_number", ""),
            "address": restaurant.get("address", ""),
            "website": restaurant.get("website", ""),
            "twilioNumber": restaurant.get("twilio_number", ""),
            "integrations": integration_status,
            "features": restaurant.get("features", {}),
            "messages": {
                "greeting": restaurant.get("greetingMessage", ""),
                "ending": restaurant.get("endingMessage", "")
            }
            })
        
        return restaurant_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving restaurant details: {str(e)}")

async def get_payments_service(current_user: dict, user_email: Optional[str] = None, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, search_email: Optional[str] = None):
    """
    Retrieve payment history for the authenticated user or a specific user (admin only)
    """
    try:
        # Check if the current user is admin
        user_data = collection_user.find_one({"user_email": current_user["user_email"]})
        is_admin = user_data and user_data.get("role") == "admin"
        
        # If not admin and trying to access other user's data
        if not is_admin and user_email and user_email != current_user["user_email"]:
            raise HTTPException(status_code=403, detail="Permission denied")
        
        # For admin users, fetch all payments if no specific user is requested
        if is_admin and not user_email and not search_email:
            # Get all users with billing data
            all_payments = []
            billing_cursor = Collection_billing.find({})
            
            for billing_data in billing_cursor:
                user_email = billing_data.get("user_email")
                if not user_email:
                    continue
                
                # Get payments for this user
                user_payments = billing_data.get("payment_history", [])
                
                # Get restaurant info for this user
                restaurant = collection_restaurant.find_one({"user_email": user_email}, {"restaurant_name": 1})
                restaurant_name = restaurant.get("restaurant_name") if restaurant else None
                
                # Add user email and restaurant name to each payment
                for payment in user_payments:
                    payment["user_email"] = user_email
                    payment["restaurant_name"] = restaurant_name
                
                # Add subscription payments if they exist
                if "subscription" in billing_data and "payment_history" in billing_data["subscription"]:
                    subscription_payments = billing_data["subscription"]["payment_history"]
                    
                    # Add subscription tag, user email and restaurant name to subscription payments
                    for payment in subscription_payments:
                        if "type" not in payment:
                            payment["type"] = "subscription"
                        payment["user_email"] = user_email
                        payment["restaurant_name"] = restaurant_name
                    
                    user_payments.extend(subscription_payments)
                
                all_payments.extend(user_payments)
            
            # Apply date filtering if needed
            if start_date or end_date:
                filtered_payments = []
                for payment in all_payments:
                    payment_date = datetime.strptime(payment["date"], "%Y-%m-%d").date()
                    
                    if start_date and payment_date < start_date:
                        continue
                        
                    if end_date and payment_date > end_date:
                        continue
                        
                    filtered_payments.append(payment)
                
                all_payments = filtered_payments
            
            # Sort payments by date (most recent first)
            all_payments.sort(key=lambda x: datetime.strptime(x["date"], "%Y-%m-%d"), reverse=True)
            
            return {"payments": all_payments}
        
        # Handle search by email (admin only)
        elif is_admin and search_email:
            all_payments = []
            # Find all users that match the search pattern
            email_pattern = {"$regex": search_email, "$options": "i"}  # Case-insensitive search
            billing_cursor = Collection_billing.find({"user_email": email_pattern})
            
            for billing_data in billing_cursor:
                user_email = billing_data.get("user_email")
                if not user_email:
                    continue
                
                # Get payments for this user
                user_payments = billing_data.get("payment_history", [])
                
                # Get restaurant info for this user
                restaurant = collection_restaurant.find_one({"user_email": user_email}, {"restaurant_name": 1})
                restaurant_name = restaurant.get("restaurant_name") if restaurant else None
                
                # Add user email and restaurant name to each payment
                for payment in user_payments:
                    payment["user_email"] = user_email
                    payment["restaurant_name"] = restaurant_name
                
                # Add subscription payments if they exist
                if "subscription" in billing_data and "payment_history" in billing_data["subscription"]:
                    subscription_payments = billing_data["subscription"]["payment_history"]
                    
                    # Add subscription tag, user email and restaurant name to subscription payments
                    for payment in subscription_payments:
                        if "type" not in payment:
                            payment["type"] = "subscription"
                        payment["user_email"] = user_email
                        payment["restaurant_name"] = restaurant_name
                    
                    user_payments.extend(subscription_payments)
                
                all_payments.extend(user_payments)
            
            # Apply date filtering if needed
            if start_date or end_date:
                filtered_payments = []
                for payment in all_payments:
                    payment_date = datetime.strptime(payment["date"], "%Y-%m-%d").date()
                    
                    if start_date and payment_date < start_date:
                        continue
                        
                    if end_date and payment_date > end_date:
                        continue
                        
                    filtered_payments.append(payment)
                
                all_payments = filtered_payments
            
            # Sort payments by date (most recent first)
            all_payments.sort(key=lambda x: datetime.strptime(x["date"], "%Y-%m-%d"), reverse=True)
            
            return {"payments": all_payments}
        
        else:
            # Original logic for specific user
            # Determine which user's data to retrieve
            target_email = user_email if user_email else current_user["user_email"]
            
            # Retrieve user's billing data
            billing_data = Collection_billing.find_one({"user_email": target_email})
            
            if not billing_data:
                return {"payments": []}
            
            # Retrieve restaurant name for the user
            restaurant = collection_restaurant.find_one({"user_email": target_email}, {"restaurant_name": 1})
            restaurant_name = restaurant.get("restaurant_name") if restaurant else None
            
            # Extract payment history
            payments = billing_data.get("payment_history", [])
            
            # Add user email and restaurant name to each payment
            for payment in payments:
                payment["user_email"] = target_email
                payment["restaurant_name"] = restaurant_name
            
            # Filter by date if provided
            if start_date or end_date:
                filtered_payments = []
                for payment in payments:
                    payment_date = datetime.strptime(payment["date"], "%Y-%m-%d").date()
                    
                    if start_date and payment_date < start_date:
                        continue
                        
                    if end_date and payment_date > end_date:
                        continue
                        
                    filtered_payments.append(payment)
                
                payments = filtered_payments
                
            # Add subscription payments if they exist
            if "subscription" in billing_data and "payment_history" in billing_data["subscription"]:
                subscription_payments = billing_data["subscription"]["payment_history"]
                
                # Filter subscription payments by date if provided
                if start_date or end_date:
                    filtered_sub_payments = []
                    for payment in subscription_payments:
                        payment_date = datetime.strptime(payment["date"], "%Y-%m-%d").date()
                        
                        if start_date and payment_date < start_date:
                            continue
                            
                        if end_date and payment_date > end_date:
                            continue
                            
                        filtered_sub_payments.append(payment)
                    
                    subscription_payments = filtered_sub_payments
                
                # Add subscription tag, user email and restaurant name to subscription payments
                for payment in subscription_payments:
                    if "type" not in payment:
                        payment["type"] = "subscription"
                    payment["user_email"] = target_email
                    payment["restaurant_name"] = restaurant_name
                
                payments.extend(subscription_payments)
            
            # Sort payments by date (most recent first)
            payments.sort(key=lambda x: datetime.strptime(x["date"], "%Y-%m-%d"), reverse=True)
            
            return {"payments": payments, "restaurant_name": restaurant_name}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving payment history: {str(e)}")


async def get_billing_users_service(current_user: dict):
    """
    Retrieve all users with billing information (admin only)
    """
    try:
        # Check if current user is admin
        user_data = collection_user.find_one({"user_email": current_user["user_email"]})
        if not user_data or user_data.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Permission denied")
        
        # Get all users with billing information
        billing_cursor = Collection_billing.find({}, {"user_email": 1, "_id": 0})
        users = []
        
        for billing_doc in billing_cursor:
            user_email = billing_doc.get("user_email")
            if user_email:
                # Get additional user info from users collection
                user_doc = collection_user.find_one({"user_email": user_email}, 
                                                  {"_id": 0, "user_email": 1, "role": 1, "twilio_number": 1})
                                
                if user_doc:
                    user_info = {
                        "email": user_email,
                        "role": user_doc.get("role", "user"),
                        "twilio_number": user_doc.get("twilio_number", "")
                    }
                                        
                    users.append(user_info)
        
        return {"users": users}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving users: {str(e)}")
    

async def get_credit_purchases_service(current_user: dict, service: Optional[str] = None, 
                                      start_date: Optional[str] = None, 
                                      end_date: Optional[str] = None):
    """
    Retrieve credit purchases for admin
    Default is to show all purchases when no filters are applied
    """
    try:
        # Check if current user is admin
        user_data = collection_user.find_one({"user_email": current_user["user_email"]})
        if not user_data or user_data.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Permission denied")
        
        # Build query for credit purchases
        query = {}
        
        # Filter by service if provided
        if service and service != "all":
            query["service"] = service
            
        # Apply date filters only if explicitly provided
        if start_date or end_date:
            date_query = {}
            if start_date:
                date_query["$gte"] = start_date
            if end_date:
                date_query["$lte"] = end_date
            
            if date_query:
                query["date"] = date_query
        
        # Debug: Print the query to check its structure
        print(f"MongoDB Query: {query}")
        
        # Execute query for admin billing data
        # Sort by date descending to show newest purchases first
        purchases = list(Collection_admin_billing.find(query, {"_id": 0}).sort("date", -1))
        
        # Debug: Print the number of purchases found
        print(f"Found {len(purchases)} purchases")
        
        # Calculate total amount from admin purchases
        total_amount = sum(purchase.get("amount", 0) for purchase in purchases)
        
        # Calculate net earnings based on user purchased minutes
        net_earnings = 0
        
        # Date filters for user payment history - only apply if explicitly provided
        user_date_filter = {}
        if start_date:
            user_date_filter["$gte"] = start_date
        if end_date:
            user_date_filter["$lte"] = end_date
        
        # Get all users' billing data
        user_billing_cursor = Collection_billing.find({})
        
        # Calculate net earnings from all users' purchased minutes
        for billing_data in user_billing_cursor:
            payment_history = billing_data.get("payment_history", [])
                        
            for payment in payment_history:
                # Check if payment contains minutes
                if "minutes" in payment:
                    # Apply date filter only if specified
                    if user_date_filter and "date" in payment:
                        payment_date = payment["date"]
                        if user_date_filter.get("$gte") and payment_date < user_date_filter["$gte"]:
                            continue
                        if user_date_filter.get("$lte") and payment_date > user_date_filter["$lte"]:
                            continue
                    
                    # Calculate earnings per minute (0.15 - 0.0485)
                    net_earnings += payment["minutes"] * (0.15 - 0.0485)
        
        return {
            "purchases": purchases,
            "total_amount": total_amount,
            "net_earnings": net_earnings
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving credit purchases: {str(e)}")

async def add_credit_purchase_service(current_user: dict, purchase_data: dict):
    """
    Add a new credit purchase
    """
    try:
        # Check if current user is admin
        user_data = collection_user.find_one({"user_email": current_user["user_email"]})
        if not user_data or user_data.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Permission denied")
        
        # Validate required fields
        required_fields = ["service", "amount", "date", "description", "invoiceNumber"]
        for field in required_fields:
            if field not in purchase_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Format date if it's a datetime object
        if isinstance(purchase_data["date"], datetime):
            purchase_data["date"] = purchase_data["date"].strftime("%Y-%m-%d")
            
        # Ensure amount is a number
        try:
            purchase_data["amount"] = float(purchase_data["amount"])
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Amount must be a valid number")
        
        # Add purchase ID and timestamp
        purchase_data["purchase_id"] = str(ObjectId())
        purchase_data["created_at"] = datetime.now().isoformat()
        purchase_data["created_by"] = current_user["user_email"]
        
        # Insert into database
        result = Collection_admin_billing.insert_one(purchase_data)
        
        if not result.inserted_id:
            raise HTTPException(status_code=500, detail="Failed to save purchase")
            
        return {"message": "Credit purchase added successfully", "purchase_id": str(result.inserted_id)}
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding credit purchase: {str(e)}")
    
def convert_duration_to_minutes(duration_str: str) -> float:
    """
    Convert duration string in format "minutes:seconds" to decimal minutes
    Example: "1:21" -> 1.35 (1 minute 21 seconds = 1.35 minutes)
    """
    try:
        if not duration_str:
            return 0.0
        
        parts = duration_str.split(":")
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes + (seconds / 60)
        else:
            # If format is unexpected, try to convert directly to float
            return float(duration_str)
    except (ValueError, TypeError):
        return 0.0

def admin_overview_data(start_date: datetime, end_date: datetime, user_email: Optional[str] = None): 
    # Filter users
    if user_email and user_email != "all":
        users_filter = {"user_email": user_email}
    else:
        users_filter = {}
    users = list(collection_user.find(users_filter))
    total_users = len(users)
    
    # Filter call logs
    call_logs_filter = {
        "date_time": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
    }
    if user_email and user_email != "all":
        call_logs_filter["user_email"] = user_email
    call_logs = list(collection_call_logs.find(call_logs_filter))
    
    # Convert string duration to minutes before summing
    total_used_minutes = sum(convert_duration_to_minutes(log.get("duration", "0:00")) for log in call_logs)

    # Prepare date strings for comparison
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    
    # Filter billing records
    billing_filter = {}
    if user_email and user_email != "all":
        billing_filter["user_email"] = user_email
    
    billing_records = list(Collection_billing.find(billing_filter))
    # Extract and filter payment history from billing records
    payments = []
    
    for billing in billing_records:
        # Extract payment history
        payment_history = billing.get("payment_history", [])
        
        # Filter by date
        filtered_payments = [
            payment for payment in payment_history
            if start_date_str <= payment.get("date", "") <= end_date_str
        ]
        
        # Add user email to each payment
        for payment in filtered_payments:
            payment["user_email"] = billing.get("user_email")
        
        payments.extend(filtered_payments)
    
    # Calculate total purchased minutes
    total_purchased_minutes = sum(payment.get("minutes", 0) for payment in payments)
    
    # Prepare usage and purchased minutes over time
    usage_over_time = {}
    purchased_over_time = {}
    
    for log in call_logs:
        date = log["date_time"][:10]  # only date part (YYYY-MM-DD)
        # Convert duration string to minutes for this date
        minutes = convert_duration_to_minutes(log.get("duration", "0:00"))
        usage_over_time[date] = usage_over_time.get(date, 0) + minutes
    
    for payment in payments:
        date = payment["date"]
        purchased_over_time[date] = purchased_over_time.get(date, 0) + payment.get("minutes", 0)
    
    # Prepare the graph data
    all_dates = sorted(set(list(usage_over_time.keys()) + list(purchased_over_time.keys())))
    graph_data = []
    for date in all_dates:
        graph_data.append({
            "date": date,
            "usage": round(usage_over_time.get(date, 0), 2),  # Round to 2 decimal places for readability
            "purchased": purchased_over_time.get(date, 0)
        })
    # Filter twilio minutes
    twilio_filter = {
        "service":"twilio",
    }
    
    # Filter openai minutes
    openai_filter = {
        "service":"openai",
    }

    twilio_records = list(Collection_admin_billing.find(twilio_filter))
    openai_records = list(Collection_admin_billing.find(openai_filter))
    
    call_logs = list(collection_call_logs.find())
    # Convert string duration to minutes before summing
    total_used = sum(convert_duration_to_minutes(log.get("duration", "0:00")) for log in call_logs)

    # Convert amount to minutes
    total_twilio_minutes = sum(log.get("amount")/0.0085 for log in twilio_records) - total_used
    total_openai_minutes = sum(log.get("amount")/0.04 for log in openai_records) - total_used

    return {
        "total_users": total_users,
        "total_used_minutes": round(total_used_minutes, 2),  # Round the total for consistency
        "total_purchased_minutes": total_purchased_minutes,
        "graph_data": graph_data,
        "total_twilio_minutes":total_twilio_minutes,
        "total_openai_minutes":total_openai_minutes
    }
    
async def update_user_twilio_number_service(user_id: str, twilio_number: str, current_user):
    """
    Update a user's Twilio number in the user collection.
    """
    try:
        # First, get the restaurant to find the user email
        restaurant = collection_restaurant.find_one({"_id": ObjectId(user_id)})
        if not restaurant:
            raise HTTPException(status_code=404, detail="Restaurant not found")
        
        user_email = restaurant.get("user_email")
        if not user_email:
            raise HTTPException(status_code=404, detail="User email not found in restaurant data")
        
        # Update the twilio_number field in the user collection
        result = collection_user.update_one(
            {"user_email": user_email},
            {"$set": {"twilio_number": twilio_number}}
        )
        
        if result.modified_count == 0:
            # If no document was modified, check if the user exists
            user = collection_user.find_one({"user_email": user_email})
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            # If user exists but no modification was made, it might be that the same number was provided
        
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating Twilio number: {str(e)}")