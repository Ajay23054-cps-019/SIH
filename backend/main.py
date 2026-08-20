from fastapi import FastAPI, Query, HTTPException, Depends, Form, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import shm_reader
import auth

pwd = auth.create_default_admin()
if pwd:
    print("=" * 50, flush=True)
    print("DEFAULT ADMIN CREDENTIALS", flush=True)
    print("Username: admin", flush=True)
    print("Password: " + pwd, flush=True)
    print("=" * 50, flush=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_origins=["*", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = auth.validate_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


@app.post("/signup")
def signup(username: str = Form(...), password: str = Form(...)):
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    created = auth.create_user(username, password)
    if not created:
        raise HTTPException(status_code=400, detail="Username already exists")
    return {"message": "User created successfully"}


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    token = auth.validate_user(username, password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"message": "Login successful", "username": username, "access_token": token}


@app.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("access_token")
    if token:
        auth.revoke_token(token)
    response.delete_cookie("access_token")
    return {"message": "Logged out"}


@app.get("/api/live")
def infor(user=Depends(get_current_user)):
    return shm_reader.information()


@app.get("/api/history")
def history(limit: int = Query(30, ge=1, le=1000), user=Depends(get_current_user)):
    return JSONResponse(shm_reader.get_latest_slot(limit))
