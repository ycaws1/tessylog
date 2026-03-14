from typing import Union
from fastapi import FastAPI
from fastapi.responses import FileResponse
import os

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}

@app.get("/.well-known/appspecific/com.tesla.3p.public-key.pem")
def get_tesla_public_key():
    public_key_path = os.path.join(os.getcwd(), "keys", "public-key.pem")
    if os.path.exists(public_key_path):
        return FileResponse(public_key_path)
    return {"error": "Public key file not found"}, 404
