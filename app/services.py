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
from app.database import collection_restaurant, collection_call_logs ,collection_integrations, collection_user
from jwt.exceptions import PyJWTError

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

async def update_user_email( new_email , current_user: dict):
    existing_user = collection_user.find_one(
        {"user_email": new_email.email}, 
        {"_id": 0, "user_email": 1, "user_pw": 1}
    )
    