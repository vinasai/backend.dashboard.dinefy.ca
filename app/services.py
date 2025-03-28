# services.py
from app.database import collection_user
from app.models import User,RestaurantDetails
from app.utils import hash_password, verify_password, create_access_token,authenticate_user
from datetime import timedelta
from fastapi import HTTPException
from bson import ObjectId
from pymongo import DESCENDING
from typing import List
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.database import collection_restaurant

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

async def get_restaurant_details(current_user):
    """
    Retrieve restaurant details for a specific user
    """
    restaurant_settings = collection_restaurant.find_one(
        {"user_email": current_user["user_email"]}, 
        {"_id": 0}  # Exclude MongoDB's internal _id
    )
    
    if not restaurant_settings:
        raise HTTPException(status_code=404, detail="Restaurant details not found")
    
    return restaurant_settings

async def save_restaurant_details(details: RestaurantDetails, current_user):
    """
    Save restaurant details for a specific user
    """
    # Convert Pydantic model to dictionary and handle HttpUrl conversion
    details_dict = details.dict()
    
    # Convert HttpUrl to string
    if 'website' in details_dict:
        details_dict['website'] = str(details_dict['website'])
    
    # Add user email to the details
    details_dict['user_email'] = current_user["user_email"]
    
    # Check if details already exist for this user
    existing_settings = collection_restaurant.find_one({"email": current_user["user_email"]})
    
    if existing_settings:
        # Update existing details
        result = collection_restaurant.update_one(
            {"email": current_user["user_email"]},
            {"$set": details_dict}
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Failed to update restaurant details")
        return {"message": "Restaurant details updated successfully"}
    else:
        # Insert new details
        result = collection_restaurant.insert_one(details_dict)
        
        if not result.inserted_id:
            raise HTTPException(status_code=500, detail="Failed to save restaurant details")
        
        return {"message": "Restaurant details saved successfully"}
    
async def get_call_logs_service(current_user):
    """
    Retrieve call logs for the current user's Twilio number
    """
    # Fetch the user's Twilio number from the restaurant details
    restaurant_details = await get_restaurant_details(current_user)
    twilio_number = restaurant_details.get("twilio_number")
   
    if not twilio_number:
        raise HTTPException(status_code=404, detail="Twilio number not found for the user")
   
    # Query the call logs collection for the given Twilio number
    call_logs = collection_restaurant.find(
        {"twilio_number": twilio_number},
        {"_id": 0}  # Exclude MongoDB's internal _id
    ).sort("timestamp", DESCENDING)  # Sort by timestamp in descending order
   
    # Convert the cursor to a list
    call_logs_list = list(call_logs)
   
    if not call_logs_list:
        raise HTTPException(status_code=404, detail="No call logs found for the Twilio number")
   
    return call_logs_list
    