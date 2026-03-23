from typing import Optional
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
import httpx
import os
import secrets
from dotenv import load_dotenv
load_dotenv()  # must be before os.getenv() calls

# from database import init_db, save_tokens, get_tokens, save_state, verify_and_delete_state

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # runs on startup
    yield
    # anything after yield runs on shutdown

app = FastAPI(lifespan=lifespan)

client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")
audience = os.getenv("AUDIENCE")
redirect_uri = os.getenv("REDIRECT_URI")

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/.well-known/appspecific/com.tesla.3p.public-key.pem")
def get_tesla_public_key():
    public_key_path = os.path.join(os.getcwd(), "certs", "public-key.pem")
    if os.path.exists(public_key_path):
        return FileResponse(public_key_path)
    return {"error": "Public key file not found"}, 404


# # ─── Step 1: Kick off OAuth ───────────────────────────────────────────────────
# from urllib.parse import urlencode

# @app.get("/auth/login")
# def login():
#     state = secrets.token_urlsafe(32)
#     save_state(state)

#     params = {
#         "response_type": "code",
#         "client_id": client_id,
#         "redirect_uri": redirect_uri,
#         "scope": "openid offline_access user_data vehicle_device_data vehicle_cmds vehicle_charging_cmds",
#         "state": state,
#     }

#     tesla_auth_url = f"https://auth.tesla.com/oauth2/v3/authorize?{urlencode(params)}"
#     print({"url": tesla_auth_url})
#     return RedirectResponse(tesla_auth_url)

# # ─── Step 2: Callback ─────────────────────────────────────────────────────────

# @app.get("/callback")
# async def callback(request: Request):
#     print(f"DEBUG: Full URL received: {str(request.url)}")
#     print(f"DEBUG: All params: {dict(request.query_params)}")
#     code = request.query_params.get("code")
#     state = request.query_params.get("state")
#     error = request.query_params.get("error")

#     print(f"DEBUG: Callback received with state: {state}, code: {'present' if code else 'missing'}, error: {error}")

#     if error:
#         return JSONResponse({"error": error}, status_code=400)

#     if not code or not state:
#         return JSONResponse({
#             "error": "Missing params",
#             "received_url": str(request.url),
#             "received_params": dict(request.query_params)
#         }, status_code=400)

#     if not verify_and_delete_state(state):
#         print(f"DEBUG: State verification failed for state: {state}")
#         return JSONResponse({"error": "Invalid state — may have expired or server reloaded", "state": state}, status_code=400)

#     async with httpx.AsyncClient() as client:
#         response = await client.post(
#             "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token",
#             data={
#                 "grant_type": "authorization_code",
#                 "client_id": client_id,
#                 "client_secret": client_secret,
#                 "code": code,
#                 "redirect_uri": redirect_uri,
#                 "audience": audience,
#             },
#             headers={"Content-Type": "application/x-www-form-urlencoded"},
#         )

#     print(f"DEBUG: Tesla token response status: {response.status_code}")
#     if response.status_code != 200:
#         print(f"DEBUG: Tesla token response body: {response.text}")
#         return JSONResponse(
#             {"error": "Token exchange failed", "detail": response.text},
#             status_code=response.status_code,
#         )

#     tokens = response.json()
#     save_tokens(tokens["access_token"], tokens.get("refresh_token"))
#     return {"message": "Auth successful — tokens saved to DB"}


# # ─── Step 3: Refresh ──────────────────────────────────────────────────────────

# @app.post("/auth/refresh")
# async def refresh_token_endpoint():
#     stored = get_tokens()
#     if not stored or not stored.get("refresh_token"):
#         return JSONResponse({"error": "No refresh token in DB"}, status_code=400)

#     async with httpx.AsyncClient() as client:
#         response = await client.post(
#             "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token",
#             data={
#                 "grant_type": "refresh_token",
#                 "client_id": client_id,
#                 "refresh_token": stored["refresh_token"],
#             },
#             headers={"Content-Type": "application/x-www-form-urlencoded"},
#         )

#     if response.status_code != 200:
#         return JSONResponse(
#             {"error": "Refresh failed", "detail": response.text},
#             status_code=response.status_code,
#         )

#     tokens = response.json()
#     save_tokens(tokens["access_token"], tokens.get("refresh_token"))

#     return {"message": "Tokens refreshed and saved"}

# # ─── Utility: inspect stored tokens ──────────────────────────────────────────

# @app.get("/auth/tokens")
# def inspect_tokens():
#     stored = get_tokens()
#     if not stored:
#         return JSONResponse({"error": "No tokens stored"}, status_code=404)
#     # Mask tokens for safety
#     return {
#         "access_token": stored["access_token"][:20] + "...",
#         "refresh_token": stored["refresh_token"][:20] + "..." if stored.get("refresh_token") else None,
#         "updated_at": stored["updated_at"],
#     }


# async def tesla_get(path: str):
#     """Helper to make authenticated Tesla API calls"""
#     stored = get_tokens()
#     if not stored:
#         return JSONResponse({"error": "No tokens found, please login"}, status_code=401)
    
#     async with httpx.AsyncClient() as client:
#         response = await client.get(
#             f"{audience}{path}",
#             headers={"Authorization": f"Bearer {stored['access_token']}"}
#         )
    
#     if response.status_code == 401:
#         return JSONResponse({"error": "Token expired, call /auth/refresh"}, status_code=401)
    
#     return response.json()

# @app.get("/vehicles")
# async def get_vehicles():
#     return await tesla_get("/api/1/vehicles")

# @app.get("/vehicles/{vehicle_id}")
# async def get_vehicle(vehicle_id: str):
#     return await tesla_get(f"/api/1/vehicles/{vehicle_id}")

# @app.get("/vehicles/{vehicle_id}/state")
# async def get_vehicle_state(vehicle_id: str):
#     return await tesla_get(f"/api/1/vehicles/{vehicle_id}/vehicle_data")

# # @app.get("/vehicles/{vehicle_id}/wake")
# # async def wake_vehicle(vehicle_id: str):
#     # stored = get_tokens()
#     # async with httpx.AsyncClient() as client:
#     #     # Note: audience is already prefixed with https
#     #     response = await client.post(
#     #         f"{audience}/api/1/vehicles/{vehicle_id}/wake_up",
#     #         headers={"Authorization": f"Bearer {stored['access_token']}"}
#     #     )
#     # return response.json()
#     # wait tesla_get(f"/api/1/vehicles/{vehicle_id}/vehicle_data")

# # @app.get("/vehicles/{vehicle_id}/wake")
# # async def wake_vehicle(vehicle_id: str):
# #     stored = get_tokens()
# #     async with httpx.AsyncClient() as client:
# #         response = await client.post(
# #             f"{audience}/api/1/vehicles/{vehicle_id}/wake_up",
# #             headers={"Authorization": f"Bearer {stored['access_token']}"}
# #         )
# #     return response.json()