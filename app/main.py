# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import router

from fastapi.security import OAuth2PasswordBearer

app = FastAPI(
    title="Your Restaurant Management API",
    description="API for Restaurant Management",
    version="0.1.0"
)

origins = [
   "https://dashboard.dinefy.ca",
   "https://dinefy.ca",
   "http://localhost:3000",
   "http://localhost:5005",
   "http://localhost:5173"   
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  
    allow_headers=["*"],  
)

app.include_router(router)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5005)
