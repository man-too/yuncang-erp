"""认证路由"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.utils.auth import hash_password, verify_password, create_access_token, decode_access_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/api/auth", tags=["认证"])
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """依赖注入：获取当前登录用户"""
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的令牌")
    user = db.query(User).filter(User.id == int(payload.get("sub", 0))).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")
    return user


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    return TokenResponse(access_token=token)


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱已被注册")

    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
        display_name=req.display_name or req.username,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role.value not in ("admin", "manager"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return db.query(User).all()
