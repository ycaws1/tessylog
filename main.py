import os
import time
import secrets
import requests
import urllib.parse
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from dotenv import load_dotenv

load_dotenv()

# Configuration from environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
# Ensure REDIRECT_URI is stripped of whitespace
REDIRECT_URI = os.getenv("REDIRECT_URI", "").strip()
SCOPES = "openid offline_access vehicle_device_data vehicle_cmds vehicle_charging_cmds"
AUDIENCE = os.getenv("AUDIENCE", "https://fleet-api.prd.na.vn.cloud.tesla.com")

print(CLIENT_ID)
print(CLIENT_SECRET)
print(REDIRECT_URI)
print(SCOPES)
print(AUDIENCE)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic here if needed
    yield
    # Shutdown logic here if needed

app = FastAPI(lifespan=lifespan)

class TeslaAPI:
    def __init__(self, client_id, client_secret, redirect_uri, scopes):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.tokens = {}
        self.state = secrets.token_urlsafe(32)

    def valid(self):
        return self.tokens and (int(time.time()) - self.tokens.get("obtained_at", 0) < self.tokens.get("expires_in", 0) - 60)

    def refresh(self):
        r = requests.post("https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token", data={
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.tokens["refresh_token"]
        }).json()
        r["obtained_at"] = int(time.time())
        self.tokens.update(r)

    def api_get(self, path):
        if not self.valid():
            if "refresh_token" in self.tokens:
                self.refresh()
            else:
                return None
        return requests.get(
            f"{AUDIENCE}{path}",
            headers={"Authorization": f"Bearer {self.tokens['access_token']}"}
        )

    def api_post(self, path):
        if not self.valid():
            if "refresh_token" in self.tokens:
                self.refresh()
            else:
                return None
        return requests.post(
            f"{AUDIENCE}{path}",
            headers={"Authorization": f"Bearer {self.tokens['access_token']}"}
        )

    def get_vehicles(self):
        resp = self.api_get("/api/1/vehicles")
        if resp is None: return []
        try:
            return resp.json().get('response', [])
        except Exception:
            return []

    def get_vehicle_state(self, vid):
        vehicles = self.get_vehicles()
        vehicle = next((v for v in vehicles if str(v.get('id')) == str(vid)), None)
        return vehicle.get('state') if vehicle else None

    def wake_up_vehicle(self, vid):
        return self.api_post(f"/api/1/vehicles/{vid}/wake_up")

    def get_vehicle_data(self, vid):
        return self.api_get(f"/api/1/vehicles/{vid}/vehicle_data")

tesla_api = TeslaAPI(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, SCOPES)

@app.get("/", response_class=HTMLResponse)
async def index():
    if not tesla_api.tokens:
        url = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/authorize?" + urllib.parse.urlencode({
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPES,
            "state": tesla_api.state
        })
        return f"<h1>Tesla Fleet</h1><a href='{url}'>Login with Tesla</a>"
    
    cars = tesla_api.get_vehicles()
    return "<h1>Your Vehicles</h1>" + "".join(
        f"<p><a href='/vehicle/{c['id']}'>{c['display_name']} ({c['vin']})</a></p>"
        for c in cars
    )

@app.get("/auth/callback")
async def callback(request: Request):
    params = dict(request.query_params)
    
    if "error" in params:
        return HTMLResponse(content=f"<h1>Tesla OAuth Error</h1><pre>{params}</pre>", status_code=400)

    # Validate state parameter
    state = params.get("state")
    if state != tesla_api.state:
        return HTMLResponse(content="<h1>Invalid state parameter (possible CSRF)</h1>", status_code=400)

    code = params.get("code")
    if not code:
        return HTMLResponse(content=f"<pre>{params}</pre>", status_code=400)

    resp = requests.post("https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token", data={
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI
    })
    
    if resp.status_code != 200:
        return HTMLResponse(content=f"<h1>Token Exchange Failed</h1><pre>{resp.text}</pre>", status_code=400)
    
    token = resp.json()
    token["obtained_at"] = int(time.time())
    tesla_api.tokens.update(token)
    return RedirectResponse(url="/")

@app.get("/vehicle/{vid}", response_class=HTMLResponse)
async def vehicle(vid: str):
    # 1. Get vehicle state (without waking up)
    state = tesla_api.get_vehicle_state(vid)
    if state is None:
        raise HTTPException(status_code=404, detail="Vehicle not found in account.")
    
    # 2. If not online, try to wake up
    if state != 'online':
        wake_resp = tesla_api.wake_up_vehicle(vid)
        try:
            wake_data = wake_resp.json()
        except Exception:
            return HTMLResponse(content=f"<h2>Wake up command failed (non-JSON response):</h2><pre>{wake_resp.text}</pre>", status_code=500)
        
        # 3. Poll for 'online' state, up to 5 times
        for attempt in range(5):
            time.sleep(2)
            poll_state = tesla_api.get_vehicle_state(vid)
            if poll_state == 'online':
                break
        else:
            return HTMLResponse(content=f"<h2>Vehicle did not wake up after several attempts.</h2><pre>{wake_data}</pre>", status_code=500)
    
    # 4. Fetch vehicle data
    data_resp = tesla_api.get_vehicle_data(vid)
    try:
        data = data_resp.json()
    except Exception:
        return HTMLResponse(content=f"<h2>Error parsing vehicle data response:</h2><pre>{data_resp.text}</pre>", status_code=500)

    # Pretty-print: flatten top-level keys and show as HTML table
    def render_dict(d, parent_key=""):
        rows = []
        for k, v in d.items():
            key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                rows.extend(render_dict(v, key))
            else:
                rows.append(f"<tr><td>{key}</td><td>{v}</td></tr>")
        return rows

    vehicle_info = data.get('response', {})
    table_rows = render_dict(vehicle_info)
    html = f'''
    <html>
    <head>
    <style>
        body {{ font-family: Arial, sans-serif; background: #f8f8f8; }}
        table {{ border-collapse: collapse; width: 80%; margin: 2em auto; background: #fff; }}
        th, td {{ border: 1px solid #ccc; padding: 8px 12px; }}
        th {{ background: #eee; }}
        tr:nth-child(even) {{ background: #f2f2f2; }}
        h2 {{ text-align: center; }}
    </style>
    </head>
    <body>
    <h2>Vehicle Data</h2>
    <table>
        <tr><th>Field</th><th>Value</th></tr>
        {''.join(table_rows)}
    </table>
    </body>
    </html>
    '''
    return html

@app.get("/.well-known/appspecific/com.tesla.3p.public-key.pem")
def get_tesla_public_key():
    public_key_path = os.path.join(os.getcwd(), "certs", "public-key.pem")
    if os.path.exists(public_key_path):
        return FileResponse(public_key_path)
    return JSONResponse(content={"error": "Public key file not found"}, status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)