from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# from models import *
# from database import *
# from aqi_routes import *
# from user_routes import *
# from node_routes import *

from api.models import *
from api.database import *
from api.aqi_routes import *
from api.user_routes import *
from api.node_routes import *
from api.notification_routes import *

load_dotenv()

app = FastAPI(
    title="Air Quality API",
    description="",
    root_path="/eng.rmuti"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

app.include_router(aqi_router)
app.include_router(user_router, prefix="/auth")
app.include_router(node_router)
app.include_router(notification_router)

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)