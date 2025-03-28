#moedels.py
from pydantic import BaseModel, EmailStr, HttpUrl
from typing import Optional
from datetime import datetime

class User_login(BaseModel):
    email: str
    password: str
    
class User(BaseModel):
    name:str
    user_email:str
    user_pw:str
    twilio_number:str

class TimeRange(BaseModel):
    open: str
    close: str

class OpeningHours(BaseModel):
    monday: TimeRange
    tuesday: TimeRange
    wednesday: TimeRange
    thursday: TimeRange
    friday: TimeRange
    saturday: TimeRange
    sunday: TimeRange

class Features(BaseModel):
    takeReservations: bool
    takeOrders: bool
    provideMenuInfo: bool
    handleComplaints: bool

class RestaurantDetails(BaseModel):
    restaurant_name: str
    phone_number: str
    twilio_number: str
    address: str
    website: HttpUrl
    email: EmailStr
    openingHours: OpeningHours
    features: Features
    greetingMessage: str
    endingMessage: str
    
class CallLogs(BaseModel):
    status: str
    date_time: str
    phone_number: str
    duration: str
    satisfaction: int
    
    class CallDetails(BaseModel):
        transcript: Optional[str]
        recording_url: Optional[HttpUrl]

    call_details: CallDetails
