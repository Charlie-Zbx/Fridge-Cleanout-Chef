import os
import uvicorn
from . import settings

if __name__ == "__main__":
    uvicorn.run("kitchen.api:app",host=os.environ.get("KITCHEN_HOST","127.0.0.1"),port=int(os.environ.get("PORT",os.environ.get("KITCHEN_PORT","8000"))),workers=1)
