from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas import MT5Credentials
from auth import get_current_user
from mt5_manager import mt5_manager

router = APIRouter()


@router.post("/connect-mt5")
def connect_mt5(
    creds: MT5Credentials,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = mt5_manager.initialize(
        login=creds.mt5_login,
        password=creds.mt5_password,
        server=creds.mt5_server,
    )

    if not result:
        raise HTTPException(
            status_code=400,
            detail="MT5 connection failed",
        )

    info = mt5_manager.account_info()

    current_user.mt5_login = creds.mt5_login
    current_user.mt5_password = creds.mt5_password
    current_user.mt5_server = creds.mt5_server

    db.commit()

    return {
        "message": f"Connected: {info.name}",
        "balance": info.balance,
    }