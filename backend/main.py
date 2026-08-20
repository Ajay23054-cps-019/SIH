from fastapi import FastAPI, Query, HTTPException, Depends, Form, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_user(request: Request):
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
def login(response: Response, username: str = Form(...), password: str = Form(...)):
    token = auth.validate_user(username, password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=24 * 60 * 60,
    )
    return {"message": "Login successful", "username": username}


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


app.mount("/", StaticFiles(directory="/home/ajay/Desktop/SIH/frontend", html=True), name="frontend")
