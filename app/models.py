#moedels.py
from pydantic import BaseModel, EmailStr, HttpUrl
from typing import List, Optional
from datetime import datetime

class User_login(BaseModel):
    email: str
    password: str
    
class User(BaseModel):
    user_name:str
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

class IntegrationResponse(BaseModel):
    connected: bool
    message: str

# Clover Models
class CloverIntegrationBase(BaseModel):
    api_key: str
    merchant_id: str

class CloverIntegrationResponse(IntegrationResponse):
    api_key: Optional[str] = None
    merchant_id: Optional[str] = None

# Shopify Models
class ShopifyIntegrationBase(BaseModel):
    api_key: str
    api_secret: str
    shop_url: str

class ShopifyIntegrationResponse(IntegrationResponse):
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    shop_url: Optional[str] = None
    
class PaymentMethod(BaseModel):
    cardholder_name: str
    card_number: str
    expiry_date: str
    cvc: str

class PaymentHistory(BaseModel):
    date: str
    purchase_id: str
    amount: float
    minutes: int

class UserPayments(BaseModel):
    payment_methods: List[PaymentMethod]
    payment_history: List[PaymentHistory]