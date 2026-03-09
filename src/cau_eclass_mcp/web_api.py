"""
REST API for credential management and server status
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .utils.credentials import CredentialManager
import time

router = APIRouter()
cred_manager = CredentialManager()

# Track server start time for uptime calculation
_server_start_time = time.time()


class CredentialsInput(BaseModel):
    """Input model for saving credentials"""
    username: str = Field(..., min_length=1, description="CAU student ID")
    password: str = Field(..., min_length=1, description="CAU portal password")


class CredentialsStatusResponse(BaseModel):
    """Response model for credential status"""
    configured: bool


class MessageResponse(BaseModel):
    """Generic message response"""
    status: str
    message: str


class ServerStatusResponse(BaseModel):
    """Server status information"""
    running: bool
    authenticated: bool
    uptime_seconds: int


@router.post("/credentials", response_model=MessageResponse)
async def save_credentials(creds: CredentialsInput):
    """Save credentials to OS keyring"""
    try:
        success = cred_manager.save_credentials(creds.username, creds.password)
        if success:
            return MessageResponse(
                status="success",
                message=f"Credentials saved for user: {creds.username}"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to save credentials to keyring. Check server logs for details."
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/credentials/status", response_model=CredentialsStatusResponse)
async def get_credentials_status():
    """Check if credentials are configured"""
    exists = cred_manager.check_credentials_exist()
    return CredentialsStatusResponse(configured=exists)


@router.delete("/credentials", response_model=MessageResponse)
async def delete_credentials():
    """Delete stored credentials from keyring"""
    try:
        success = cred_manager.delete_credentials()
        if success:
            return MessageResponse(
                status="success",
                message="Credentials deleted successfully"
            )
        else:
            return MessageResponse(
                status="warning",
                message="No credentials found to delete"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=ServerStatusResponse)
async def get_server_status():
    """Get server status information"""
    uptime = int(time.time() - _server_start_time)
    return ServerStatusResponse(
        running=True,
        authenticated=cred_manager.check_credentials_exist(),
        uptime_seconds=uptime
    )
