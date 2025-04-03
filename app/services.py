# services.py
from app.database import collection_user
from app.models import User
from app.utils import hash_password, verify_password, create_access_token,authenticate_user
from datetime import timedelta
from fastapi import HTTPException
from bson import ObjectId
from pymongo import DESCENDING
from typing import List
from fastapi.security import OAuth2PasswordBearer
from app.database import collection_restaurant, collection_call_logs ,collection_integrations, collection_user,collection_password_reset,Collection_billing
from jwt.exceptions import PyJWTError
from fastapi import HTTPException
from datetime import datetime, timedelta
from pydantic import EmailStr
import secrets
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.config import MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM, MAIL_PORT, MAIL_SERVER, MAIL_FROM_NAME
import uuid
import re

# Configure email
# conf = ConnectionConfig(
#     MAIL_USERNAME=MAIL_USERNAME,
#     MAIL_PASSWORD=MAIL_PASSWORD,
#     MAIL_FROM=MAIL_FROM,
#     MAIL_PORT=MAIL_PORT,
#     MAIL_SERVER=MAIL_SERVER,
#     MAIL_FROM_NAME=MAIL_FROM_NAME,
#     MAIL_TLS=True,
#     MAIL_SSL=False,
#     USE_CREDENTIALS=True
# )

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def login_user(form_data, access_token_expire_minutes):
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token_expires = timedelta(minutes=access_token_expire_minutes)
    access_token = create_access_token(data={"email": user['user_email']}, expires_delta=access_token_expires)
    print(access_token)
    return {"access_token": access_token,"token_type": "bearer"}

def create_new_user(user:User):
    existing_user = collection_user.find_one({"user_email": user.user_email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash the password before storing in the database
    hashed_password = hash_password(user.user_pw)
    
    # Modify user data to include hashed password
    user_data = user.dict()
    user_data["user_pw"] = hashed_password

    # Insert user data into MongoDB
    inserted_user = collection_user.insert_one(user_data)

    return {"message": "User created successfully"}

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

async def updated_user_email(new_email, current_user):
    """
    Update user email endpoint.
    Requires current password for verification.
    """
    try:
        # Validate request data
        if not new_email.new_email or not new_email.confirm_password:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        # Find user in database
        user = collection_user.find_one({"user_email": current_user["user_email"]})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify current password
        if not verify_password(new_email.confirm_password, user["user_pw"]):
            raise HTTPException(status_code=401, detail="Invalid current password")
        
        # Update email in all collections
        collections_to_update = [collection_user, collection_call_logs, collection_integrations, collection_restaurant]  # Add other collections here if needed
        for collection in collections_to_update:
            try:
                result = collection.update_many(
                    {"user_email": current_user["user_email"]},
                    {"$set": {"user_email": new_email.new_email}}
            )
                # Log a warning if no documents were updated in the collection
                if result.modified_count == 0:
                    print(f"Warning: No documents updated in {collection.name}")
            except Exception as e:
                # Log the exception and continue with the next collection
                print(f"Error updating email in {collection.name}: {e}")
        
        return {"new_email": new_email.new_email}
    
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
        
        # Delete user from the user collection only
        result = collection_user.delete_one({"user_email": current_user["user_email"]})
        if result.deleted_count == 0:
            raise HTTPException(status_code=500, detail="Failed to delete account from the user collection")
        
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
    # message = MessageSchema(
    #     subject="Password Reset Verification Code",
    #     recipients=[email],
    #     body=f"""
    #     <html>
    #     <body>
    #         <h1>Password Reset Request</h1>
    #         <p>You have requested to reset your password. Use the verification code below:</p>
    #         <h2>{verification_code}</h2>
    #         <p>This code will expire in 5 minutes.</p>
    #         <p>If you did not request a password reset, please ignore this email.</p>
    #     </body>
    #     </html>
    #     """,
    #     subtype="html"
    # )
    
    # fm = FastMail(conf)
    # try:
    #     await fm.send_message(message)
    #     print(f"Password reset code sent to {email}")
    # except Exception as e:
    #     print(f"Failed to send email: {e}")
    #     # You may want to handle this error more gracefully
    
    return {"message": "If your email is registered, a reset code has been sent"}

# async def verify_reset_code_and_reset_password(email: EmailStr, code: str, new_password: str):
#     """
#     Verify the reset code and update the user's password if valid.
    
#     Args:
#         email: The user's email address
#         code: The verification code
#         new_password: The new password
        
#     Returns:
#         Dict containing success message
#     """
#     # Find the reset request
#     reset_request = collection_password_reset.find_one({
#         "email": email,
#         "code": code
#     })
    
#     if not reset_request:
#         raise HTTPException(status_code=400, detail="Invalid verification code")
    
#     # Check if the code has expired
#     if reset_request["expires_at"] < datetime.utcnow():
#         # Remove expired reset request
#         collection_password_reset.delete_one({"_id": reset_request["_id"]})
#         raise HTTPException(status_code=400, detail="Verification code has expired")
    
#     # Find the user
#     user = collection_user.find_one({"user_email": email})
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
    
#     # Hash the new password
#     hashed_password = hash_password(new_password)
    
#     # Update the user's password
#     result = collection_user.update_one(
#         {"user_email": email},
#         {"$set": {"user_pw": hashed_password}}
#     )
#     if result.modified_count == 0:
#         raise HTTPException(status_code=500, detail="Failed to update password")
    
#     # Remove the reset request
#     collection_password_reset.delete_one({"_id": reset_request["_id"]})
    
#     return {"message": "Password has been reset successfully"}


# Rate: $0.05 per minute (20 minutes per dollar)
RATE_PER_MINUTE = 0.05

async def get_user_billing_info(current_user):
    """
    Get billing information for a user including payment methods, payment history, and usage
    """
    user_email = current_user["user_email"]
    
    # Get user from database
    user = Collection_billing.find_one({"user_email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Extract billing information
    payment_methods = user.get("payment_methods", [])
    payment_history = user.get("payment_history", [])
    
    # For now, we'll generate mock usage data until actual usage tracking is implemented
    usage_data = [
        {"date": "2025-01", "minutes": 120},
        {"date": "2025-02", "minutes": 145},
        {"date": "2025-03", "minutes": 180}
    ]
    
    # Calculate remaining minutes
    total_minutes_purchased = sum(payment.get("minutes", 0) for payment in payment_history)
    total_minutes_used = sum(usage.get("minutes", 0) for usage in usage_data)
    remaining_minutes = total_minutes_purchased - total_minutes_used
    
    return {
        "remaining_minutes": remaining_minutes,
        "total_minutes": total_minutes_purchased,
        "payment_methods": payment_methods,
        "payment_history": payment_history,
        "usage_data": usage_data
    }

async def add_payment_method(payment_method_data, current_user):
    """
    Add a payment method for a user with enhanced validation
    """
    user_email = current_user["user_email"]
    
    # Enhanced card number validation
    card_number = payment_method_data.card_number.replace(" ", "")  # Remove spaces
    if not card_number.isdigit() or len(card_number) < 13 or len(card_number) > 19:
        raise HTTPException(status_code=400, detail="Invalid card number. Card number must be between 13 and 19 digits")
    
    # Validate expiry date format (MM/YY)
    expiry_date = payment_method_data.expiry_date
    if not re.match(r'^\d{2}/\d{2}$', expiry_date):
        raise HTTPException(status_code=400, detail="Invalid expiry date format. Please use MM/YY format")
    
    # Validate month and year
    try:
        month, year = expiry_date.split('/')
        month_int = int(month)
        year_int = int("20" + year)
        
        if month_int < 1 or month_int > 12:
            raise HTTPException(status_code=400, detail="Invalid month. Month must be between 01 and 12")
        
        # Check if card is expired
        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.month
        
        if year_int < current_year or (year_int == current_year and month_int < current_month):
            raise HTTPException(status_code=400, detail="Card has expired")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")
    
    # Validate CVV
    cvc = payment_method_data.cvc
    if not cvc.isdigit() or len(cvc) < 3 or len(cvc) > 4:
        raise HTTPException(status_code=400, detail="Invalid CVC. CVV must be 3 or 4 digits")
    
    # Check if cardholder name is provided
    if not payment_method_data.cardholder_name.strip():
        raise HTTPException(status_code=400, detail="Cardholder name is required")
    
    # Mask the card number for storage (keep only last 4 digits)
    masked_card_number = "*" * (len(card_number) - 4) + card_number[-4:]
    
    # Create a payment method record
    payment_method = {
        "cardholder_name": payment_method_data.cardholder_name,
        "card_number": masked_card_number,  # Store masked version
        "expiry_date": payment_method_data.expiry_date,
        "cvc": "***"  # Don't store actual CVC
    }
    
    # Check if user already exists in billing collection
    user = Collection_billing.find_one({"user_email": user_email})
    
    if user:
        # Add payment method to existing user's account
        result = Collection_billing.update_one(
            {"user_email": user_email},
            {"$push": {"payment_methods": payment_method}}
        )
    else:
        # Create new user record with payment method
        result = Collection_billing.insert_one({
            "user_email": user_email,
            "payment_methods": [payment_method],
            "payment_history": []
        })
        
    if (user and result.modified_count == 0) or (not user and not result.inserted_id):
        raise HTTPException(status_code=500, detail="Failed to add payment method")
    
    return {"message": "Payment method added successfully"}

async def purchase_minutes(purchase_data, current_user):
    """
    Purchase minutes using the specified payment method
    """
    user_email = current_user["user_email"]
    
    # Get user from database
    user = Collection_billing.find_one({"user_email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user has payment methods
    payment_methods = user.get("payment_methods", [])
    if not payment_methods:
        raise HTTPException(status_code=400, detail="No payment method available")
    
    # Validate payment method selection
    try:
        payment_method_index = int(purchase_data.payment_method_id)
        if payment_method_index < 0 or payment_method_index >= len(payment_methods):
            raise HTTPException(status_code=400, detail="Invalid payment method selected")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid payment method ID")
    
    # Get the selected payment method
    selected_payment_method = payment_methods[payment_method_index]
    
    # Calculate minutes based on amount
    amount = purchase_data.amount
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
        
    minutes = int(amount / RATE_PER_MINUTE)
    
    # Generate a purchase ID
    purchase_id = f"PUR-{uuid.uuid4().hex[:8].upper()}"
    
    # Record the transaction
    payment_record = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "purchase_id": purchase_id,
        "amount": amount,
        "minutes": minutes
    }
    
    # Add to payment history
    result = Collection_billing.update_one(
        {"user_email": user_email},
        {"$push": {"payment_history": payment_record}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to record purchase")
    
    return {
        "success": True,
        "message": f"Successfully purchased {minutes} minutes",
        "purchase_id": purchase_id,
        "amount": amount,
        "minutes": minutes,
        "date": payment_record["date"]
    }

async def delete_payment_method(payment_method_index, current_user):
    """
    Delete a payment method by its index in the array
    """
    user_email = current_user["user_email"]
    
    # Convert index to integer
    try:
        index = int(payment_method_index)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment method index")
    
    # Get user from database
    user = Collection_billing.find_one({"user_email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if payment method exists at the specified index
    payment_methods = user.get("payment_methods", [])
    if index < 0 or index >= len(payment_methods):
        raise HTTPException(status_code=404, detail="Payment method not found")
    
    # Use MongoDB's array update operators to remove the element at the specified index
    result = Collection_billing.update_one(
        {"user_email": user_email},
        {"$unset": {f"payment_methods.{index}": 1}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to remove payment method")
    
    # Now pull any null elements to clean up the array
    Collection_billing.update_one(
        {"user_email": user_email},
        {"$pull": {"payment_methods": None}}
    )
    
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