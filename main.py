from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import processes
import database

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
    return processes.information(["code"])

@app.get("/history")
def history(limit: int = Query(60, ge=1, le=1000)):
    return JSONResponse(database.get_latest(limit))

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
