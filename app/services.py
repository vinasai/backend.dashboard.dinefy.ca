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
from app.database import collection_restaurant, collection_call_logs ,collection_integrations, collection_user,collection_password_reset,Collection_billing,collection_email_verification 
from jwt.exceptions import PyJWTError
from fastapi import HTTPException
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

    return {"access_token": access_token}

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
        # We don't want to reveal if an email exists in the system
        # So we return success regardless, but only generate a code if the user exists
        return {"message": "If your email is registered, a reset code has been sent"}
    
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
            "stripe_payment_intent_id": confirmed_intent.id,
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

async def get_call_data(start_date, end_date, user_email):
    """
    Retrieve call data for a specific date range and user.
    Returns formatted data for the Overview dashboard.
    """
    try:
        # Convert string dates to datetime objects for MongoDB query
        start = datetime.combine(start_date, datetime.min.time())
        end = datetime.combine(end_date, datetime.max.time())
        
        # Query call logs within the date range
        pipeline = [
            {
                "$match": {
                    "user_email": user_email,
                    "call_date": {"$gte": start, "$lte": end}
                }
            },
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$call_date"}},
                    "calls": {"$sum": 1},
                    "minutes": {"$sum": "$duration_minutes"},
                    "orders": {"$sum": {"$cond": [{"$eq": ["$order_placed", True]}, 1, 0]}},
                    "satisfaction_sum": {"$sum": "$satisfaction_rating"},
                    "satisfaction_count": {"$sum": {"$cond": [{"$gt": ["$satisfaction_rating", 0]}, 1, 0]}}
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
            {
                "$sort": {"date": 1}
            }
        ]
        
        call_data = list(collection_call_logs.aggregate(pipeline))
        
        # If no data is found for some dates in the range, fill with zeros
        date_range = []
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            existing_data = next((item for item in call_data if item["date"] == date_str), None)
            
            if existing_data:
                date_range.append(existing_data)
            else:
                date_range.append({
                    "date": date_str,
                    "calls": 0,
                    "minutes": 0,
                    "orders": 0,
                    "satisfaction": 0
                })
            
            current_date += timedelta(days=1)

        # Calculate overall statistics
        total_calls = sum(item["calls"] for item in call_data)
        total_minutes = sum(item["minutes"] for item in call_data)
        total_orders = sum(item["orders"] for item in call_data)
        
        # Calculate average satisfaction
        satisfaction_values = [item["satisfaction"] for item in call_data if item["satisfaction"] > 0]
        avg_satisfaction = sum(satisfaction_values) / len(satisfaction_values) if satisfaction_values else 0
        
        # Get previous period data for comparison
        days_diff = (end_date - start_date).days + 1
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days_diff - 1)
        
        # Query previous period
        prev_pipeline = [
            {
                "$match": {
                    "user_email": user_email,
                    "call_date": {"$gte": datetime.combine(prev_start, datetime.min.time()), 
                                 "$lte": datetime.combine(prev_end, datetime.max.time())}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "prev_calls": {"$sum": 1},
                    "prev_minutes": {"$sum": "$duration_minutes"},
                    "prev_orders": {"$sum": {"$cond": [{"$eq": ["$order_placed", True]}, 1, 0]}},
                    "prev_satisfaction_sum": {"$sum": "$satisfaction_rating"},
                    "prev_satisfaction_count": {"$sum": {"$cond": [{"$gt": ["$satisfaction_rating", 0]}, 1, 0]}}
                }
            }
        ]
        
        prev_data = list(collection_call_logs.aggregate(prev_pipeline))
        prev_period = prev_data[0] if prev_data else {
            "prev_calls": 0, 
            "prev_minutes": 0, 
            "prev_orders": 0,
            "prev_satisfaction_sum": 0,
            "prev_satisfaction_count": 0
        }
        
        # Calculate percentage changes
        calls_change = calculate_percent_change(total_calls, prev_period.get("prev_calls", 0))
        minutes_change = calculate_percent_change(total_minutes, prev_period.get("prev_minutes", 0))
        orders_change = calculate_percent_change(total_orders, prev_period.get("prev_orders", 0))
        
        prev_avg_satisfaction = 0
        if prev_period.get("prev_satisfaction_count", 0) > 0:
            prev_avg_satisfaction = prev_period.get("prev_satisfaction_sum", 0) / prev_period.get("prev_satisfaction_count", 0)
        
        satisfaction_change = calculate_percent_change(avg_satisfaction, prev_avg_satisfaction)
        
        stats = {
            "total_calls": total_calls,
            "total_minutes": total_minutes,
            "total_orders": total_orders,
            "avg_satisfaction": round(avg_satisfaction, 1),
            "calls_change": calls_change,
            "minutes_change": minutes_change,
            "orders_change": orders_change,
            "satisfaction_change": satisfaction_change
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

# Modified create_new_user function to check email verification
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
    
    # Hash the password before storing in the database
    hashed_password = hash_password(user.user_pw)
    
    # Modify user data to include hashed password
    user_data = user.dict()
    user_data["user_pw"] = hashed_password
    user_data["verified"] = True
    user_data["created_at"] = datetime.utcnow()
    
    # Insert user data into MongoDB
    inserted_user = collection_user.insert_one(user_data)
    
    # Remove the verification document
    collection_email_verification.delete_one({"email": user.user_email})
    
    return {"message": "User created successfully"}