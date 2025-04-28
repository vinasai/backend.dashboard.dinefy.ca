# database.py
from pymongo import MongoClient
from app.config import MONGODB_URL

client = MongoClient(MONGODB_URL)

database = client.Call_Assistant_Dashboard

collection_user = database["users"]
collection_restaurant = database['restaurant_details']
collection_integrations = database["intergrations"]
collection_call_logs = database['call_logs']
Collection_billing = database['billing']
collection_email_verification = database["email_verification"]

# Add this new collection
collection_password_reset = database["password_reset"]

#admin collection
Collection_admin_billing = database['admin_billing']

# Create an index to automatically expire reset codes after 5 minutes
collection_password_reset.create_index("expires_at", expireAfterSeconds=0)