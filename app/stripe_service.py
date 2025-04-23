import stripe
from fastapi import HTTPException
from datetime import datetime
from typing import Dict, List, Optional
from app.models import PaymentMethod, AddPaymentMethod
from app.config import STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY

stripe.api_key = STRIPE_SECRET_KEY
stripe.publishable_key = STRIPE_PUBLISHABLE_KEY
stripe.api_version = "2022-11-15"  # Set the API version to the latest stable version

class StripeService:
    @staticmethod
    async def create_customer(email: str, name: str = None) -> str:
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={"signup_date": datetime.now().isoformat()}
            )
            return customer.id
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    @staticmethod
    async def create_payment_method(card_details: AddPaymentMethod) -> Dict:
        try:
            payment_method = stripe.PaymentMethod.create(
                type="card",
                card={
                    "number": card_details.card_number,
                    "exp_month": card_details.expiry_date.split('/')[0],
                    "exp_year": "20" + card_details.expiry_date.split('/')[1],
                    "cvc": card_details.cvc,
                },
                billing_details={
                    "name": card_details.cardholder_name,
                }
            )
            return payment_method
        except stripe.error.CardError as e:
            raise HTTPException(status_code=400, detail=f"Card error: {e.user_message}")
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    @staticmethod
    async def attach_payment_method_to_customer(payment_method_id: str, customer_id: str) -> bool:
        try:
            stripe.PaymentMethod.attach(
                payment_method_id,
                customer=customer_id,
            )
            return True
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    @staticmethod
    async def set_default_payment_method(customer_id: str, payment_method_id: str) -> bool:
        try:
            stripe.Customer.modify(
                customer_id,
                invoice_settings={
                    "default_payment_method": payment_method_id
                }
            )
            return True
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    @staticmethod
    async def create_subscription(
        customer_id: str,
        price_id: str,
        payment_method_id: Optional[str] = None,
        trial_days: int = 0,
        metadata: dict = None
    ) -> Dict:
        try:
            subscription_data = {
                "customer": customer_id,
                "items": [{"price": price_id}],
                "metadata": metadata or {},
                "expand": ["latest_invoice.payment_intent"]
            }
            
            if payment_method_id:
                subscription_data["default_payment_method"] = payment_method_id
            
            if trial_days > 0:
                subscription_data["trial_period_days"] = trial_days
            
            subscription = stripe.Subscription.create(**subscription_data)
            return subscription
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    @staticmethod
    async def cancel_subscription(subscription_id: str) -> Dict:
        try:
            return stripe.Subscription.delete(subscription_id)
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    @staticmethod
    async def get_subscription(subscription_id: str) -> Dict:
        try:
            return stripe.Subscription.retrieve(subscription_id)
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    @staticmethod
    async def create_payment_intent(
        amount: float,
        currency: str = "usd",
        customer_id: str = None,
        payment_method_id: str = None,
        save_payment_method: bool = False,
        metadata: dict = None
    ) -> Dict:
        try:
            # Convert dollars to cents
            amount_in_cents = int(amount * 100)
            
            intent_params = {
                "amount": amount_in_cents,
                "currency": currency,
                "confirm": False,
                "setup_future_usage": "off_session" if save_payment_method else None,
                "metadata": metadata or {}
            }
            
            if customer_id:
                intent_params["customer"] = customer_id
            if payment_method_id:
                intent_params["payment_method"] = payment_method_id
            
            intent = stripe.PaymentIntent.create(**intent_params)
            return intent
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    @staticmethod
    async def confirm_payment_intent(payment_intent_id: str) -> Dict:
        try:
            intent = stripe.PaymentIntent.confirm(payment_intent_id)
            return intent
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    @staticmethod
    async def get_customer_payment_methods(customer_id: str) -> list:
        try:
            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type="card"
            )
            return payment_methods.data
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    @staticmethod
    async def detach_payment_method(payment_method_id: str) -> bool:
        try:
            stripe.PaymentMethod.detach(payment_method_id)
            return True
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")