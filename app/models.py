#moedels.py
from pydantic import BaseModel, EmailStr, HttpUrl, Field, validator
from typing import List, Optional
from datetime import datetime, date
import re
import uuid

class User_login(BaseModel):
    email: str
    password: str
    
class User(BaseModel):
    user_name:str
    user_email:str
    user_pw:str
    twilio_number:str

class UpdateEmail(BaseModel):
    new_email: str
    confirm_password: str
    
class ChangePassword(BaseModel):
    currentPassword: str
    newPassword: str
    confirmPassword: str

class PasswordChangeResponse(BaseModel):
    message: str
    
class DeleteAccount(BaseModel):
    CurrentEmail: str

class DeleteAccountResponse(BaseModel):
    message: str

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
    address: str
    website: HttpUrl
    email: EmailStr
    openingHours: OpeningHours
    features: Features
    greetingMessage: str
    endingMessage: str
    
class TranscriptEntry(BaseModel):
    role: str
    text: str

class CallDetails(BaseModel):
    transcript: Optional[List[TranscriptEntry]]

class CallLogs(BaseModel):
    status: str
    date_time: str
    phone_number: str
    duration: float
    satisfaction: int
    call_details: CallDetails
    order: bool
    user_email: str

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

class PasswordResetRequest(BaseModel):
    email: EmailStr

class VerifyResetCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)   
    
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
           
class PaymentMethod(BaseModel):
    cardholder_name: str
    card_number: str
    expiry_date: str
    cvc: str = "***"  # We don't return actual CVC


class AddPaymentMethodStripe(BaseModel):
    payment_method_id: str
    cardholder_name: Optional[str] = None  # Added field for cardholder name
    setup_for_future_use: bool = False

  
class AddPaymentMethod(BaseModel):
    cardholder_name: str
    card_number: str
    expiry_date: str
    cvc: str
    setup_for_future_use: bool = False
    
    @validator('cardholder_name')
    def validate_cardholder_name(cls, v):
        if not v.strip():
            raise ValueError('Cardholder name is required')
        return v
        
    @validator('card_number')
    def validate_card_number(cls, v):
        # Remove spaces for validation
        card_number = v.replace(" ", "")
        if not card_number.isdigit() or len(card_number) < 13 or len(card_number) > 19:
            raise ValueError('Card number must be between 13 and 19 digits')
        return v
        
    @validator('expiry_date')
    def validate_expiry_date(cls, v):
        if not re.match(r'^\d{2}/\d{2}$', v):
            raise ValueError('Expiry date must be in MM/YY format')
            
        month, year = v.split('/')
        month_int = int(month)
        year_int = int("20" + year)
        
        if month_int < 1 or month_int > 12:
            raise ValueError('Month must be between 01 and 12')
            
        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.month
        
        if year_int < current_year or (year_int == current_year and month_int < current_month):
            raise ValueError('Card has expired')
            
        return v
        
    @validator('cvc')
    def validate_cvc(cls, v):
        if not v.isdigit() or len(v) < 3 or len(v) > 4:
            raise ValueError('CVV must be 3 or 4 digits')
        return v

class PaymentHistoryItem(BaseModel):
    date: str
    purchase_id: str
    amount: float
    minutes: int

class PurchaseMinutes(BaseModel):
    amount: float
    payment_method_id: str
    save_payment_method: bool = False
    
    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be greater than zero')
        return v

class UsageData(BaseModel):
    date: str
    minutes: int

class BillingResponse(BaseModel):
    remaining_minutes: int
    total_minutes: int
    payment_methods: List[PaymentMethod]
    payment_history: List[PaymentHistoryItem]

class StripePaymentIntent(BaseModel):
    client_secret: Optional[str] = None
    payment_intent_id: Optional[str] = None
    amount: Optional[int] = None
    currency: Optional[str] = None
    status: Optional[str] = None

class PurchaseResponse(BaseModel):
    success: bool
    message: str
    purchase_id: Optional[str] = None
    amount: Optional[float] = None
    minutes: Optional[int] = None
    date: Optional[str] = None
    payment_intent: Optional[StripePaymentIntent] = None  # For client-side confirmation
    
# Subscription specific models
class SubscriptionRequest(BaseModel):
    payment_method_id: str
    cardholder_name: str
    billing_address: str

class SubscriptionResponse(BaseModel):
    success: bool
    message: str
    subscription_id: Optional[str] = None
    start_date: Optional[str] = None
    current_period_end: Optional[str] = None
    status: Optional[str] = None

class SubscriptionInfo(BaseModel):
    subscription_id: str
    status: str
    start_date: str
    current_period_end: str
    price: float
    auto_renew: bool
    
class CallDataEntry(BaseModel):
    date: str
    calls: int
    minutes: float
    orders: int
    satisfaction: float

class CallDataResponse(BaseModel):
    data: List[CallDataEntry]
    stats: dict

class DateRangeRequest(BaseModel):
    start_date: date
    end_date: date
    
class MinutesRemainingResponse(BaseModel):
    remaining_minutes: float
    total_minutes: int 
    
class EmailVerification(BaseModel):
    email: EmailStr

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str

class DemoRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str
    restaurant: str
    address: str = ""
    date: str
    time: str
    message: str = ""
    consent: bool

class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str

class UserDetailsResponse(BaseModel):
    _id: str
    email: EmailStr
    twilio_number: str
    restaurant_name: str
    phone_number: str
    address: str
    website: HttpUrl
    features: Features
    greetingMessage: str
    endingMessage: str

class CreditPurchaseRequest(BaseModel):
    service: str
    amount: float
    date: str
    description: str
    invoiceNumber: str