from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import shm_reader

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def infor():
    return shm_reader.information()

@app.get("/history")
def history(limit: int = Query(30, ge=1, le=1000)):
    return JSONResponse(shm_reader.get_latest_slot(limit))

app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
