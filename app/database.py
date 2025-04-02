# database.py
from pymongo import MongoClient
from app.config import MONGODB_URL

client = MongoClient(MONGODB_URL)

database = client.Call_Assistant_Dashboard

collection_user = database["users"]
collection_restaurant = database['restaurant_details']
collection_clover = database["clover_integrations"]
collection_shopify = database["shopify_integrations"]
collection_call_logs = database['call_logs']