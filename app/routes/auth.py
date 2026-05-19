"""
Phase 3 — Authentication routes.
Email/password signup/signin, Google auth, GitHub auth, repo selection.
"""
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import httpx

from app.core.auth import (
    create_token,
    create_or_get_social_user,
    create_user,
    get_user_by_email,
    get_current_user,
    verify_password,
    Role,
)
from app.core.multi_repo import get_repo_manager
from app.core.config import settings


auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignUpRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None


class SignInRequest(BaseModel):
    email: str
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: Optional[str] = None
    access_token: Optional[str] = None


class GitHubAuthRequest(BaseModel):
    github_token: str


class RepoSelectionRequest(BaseModel):
    repo_id: str
    branch: str = "main"


def _user_response(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "user_id": user.get("user_id"),
        "email": user.get("email"),
        "full_name": user.get("full_name"),
        "provider": user.get("provider"),
        "provider_id": user.get("provider_id"),
        "avatar_url": user.get("avatar_url"),
    }


def _github_api(client: httpx.Client, path: str, token: str) -> httpx.Response:
    return client.get(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        },
        timeout=15,
    )


def _exchange_github_code(code: str) -> str:
    client_id = settings.github_client_id
    client_secret = settings.github_client_secret
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="GitHub client ID/secret not configured on server")

    with httpx.Client(timeout=15) as client:
        resp = client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={"client_id": client_id, "client_secret": client_secret, "code": code},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange GitHub code for access token")
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise HTTPException(status_code=400, detail="No access_token returned from GitHub")
        return token


def _ensure_access_token(token_or_code: str) -> str:
    if not token_or_code:
        return token_or_code
    # Common GitHub access tokens start with 'gh' (gho_, ghu_, ghp_, etc.). If it doesn't, treat it as a code and exchange it.
    if token_or_code.startswith("gh"):
        return token_or_code
    return _exchange_github_code(token_or_code)


def _fetch_github_user(token: str) -> Dict[str, Any]:
    token = _ensure_access_token(token)
    with httpx.Client() as client:
        resp = _github_api(client, "/user", token)
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid GitHub token")
        return resp.json()


def _fetch_github_repos(token: str) -> List[Dict[str, Any]]:
    repos = []
    token = _ensure_access_token(token)
    with httpx.Client() as client:
        page = 1
        while True:
            resp = _github_api(
                client,
                f"/user/repos?visibility=all&per_page=100&page={page}",
                token,
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=401, detail="Failed to list GitHub repos")
            data = resp.json()
            if not isinstance(data, list) or len(data) == 0:
                break
            repos.extend([
                {
                    "full_name": repo.get("full_name"),
                    "name": repo.get("name"),
                    "html_url": repo.get("html_url"),
                    "private": repo.get("private"),
                    "default_branch": repo.get("default_branch") or "main",
                    "owner_login": repo.get("owner", {}).get("login"),
                }
                for repo in data
            ])
            if len(data) < 100:
                break
            page += 1
    return repos


def _fetch_github_branches(token: str, owner: str, repo: str) -> List[Dict[str, Any]]:
    token = _ensure_access_token(token)
    with httpx.Client() as client:
        resp = _github_api(client, f"/repos/{owner}/{repo}/branches?per_page=100", token)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Unable to list branches")
        return [
            {"name": branch.get("name"), "commit_sha": branch.get("commit", {}).get("sha")}
            for branch in resp.json()
        ]


def _verify_google_token(id_token: Optional[str], access_token: Optional[str]) -> Dict[str, Any]:
    if id_token:
        url = "https://oauth2.googleapis.com/tokeninfo"
        params = {"id_token": id_token}
    elif access_token:
        url = "https://www.googleapis.com/oauth2/v1/userinfo"
        params = {"alt": "json"}
    else:
        raise HTTPException(status_code=400, detail="Google id_token or access_token required")

    with httpx.Client(timeout=15) as client:
        if id_token:
            response = client.get(url, params=params)
        else:
            response = client.get(url, params=params, headers={"Authorization": f"Bearer {access_token}"})

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google token")
    return response.json()


@auth_router.post("/signup")
async def signup(req: SignUpRequest):
    existing = get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = create_user(
        email=req.email,
        password=req.password,
        full_name=req.full_name or req.email.split("@")[0],
    )
    token = create_token(user["user_id"], "*", Role.VIEWER)
    return {"status": "success", "data": {"token": token, "user": _user_response(user)}}


@auth_router.post("/signin")
async def signin(req: SignInRequest):
    user = get_user_by_email(req.email)
    if not user or not user.get("hashed_password"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(req.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(user["user_id"], "*", Role.VIEWER)
    return {"status": "success", "data": {"token": token, "user": _user_response(user)}}


@auth_router.post("/google")
async def google_auth(req: GoogleAuthRequest):
    payload = _verify_google_token(req.id_token, req.access_token)
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Google profile email not available")

    provider_id = payload.get("sub") or payload.get("id")
    user = create_or_get_social_user(
        provider="google",
        provider_id=str(provider_id),
        email=email,
        full_name=payload.get("name") or email.split("@")[0],
        avatar_url=payload.get("picture"),
        oauth_token=req.access_token or req.id_token,
    )
    token = create_token(user["user_id"], "*", Role.VIEWER)
    return {"status": "success", "data": {"token": token, "user": _user_response(user)}}


@auth_router.post("/github")
async def github_auth(req: GitHubAuthRequest):
    # Accept either a frontend-provided temporary code or a real GitHub access token.
    access_token = _ensure_access_token(req.github_token)
    profile = _fetch_github_user(access_token)
    email = profile.get("email")
    if not email:
        with httpx.Client(timeout=15) as client:
            resp = _github_api(client, "/user/emails", access_token)
            if resp.status_code == 200:
                primary = next((item for item in resp.json() if item.get("primary") and item.get("verified")), None)
                email = primary.get("email") if primary else None

    user = create_or_get_social_user(
        provider="github",
        provider_id=str(profile.get("id")),
        email=email,
        full_name=profile.get("name") or profile.get("login"),
        avatar_url=profile.get("avatar_url"),
        oauth_token=access_token,
    )
    repos = _fetch_github_repos(access_token)
    token = create_token(user["user_id"], "*", Role.VIEWER)
    return {"status": "success", "data": {"token": token, "user": _user_response(user), "repos": repos}}


@auth_router.get("/github/repos")
async def github_repos(github_token: str = Query(..., alias="token")):
    repos = _fetch_github_repos(github_token)
    return {"status": "success", "data": repos}


@auth_router.get("/github/repos/{owner}/{repo}/branches")
async def github_branches(owner: str, repo: str, github_token: str = Query(..., alias="token")):
    branches = _fetch_github_branches(github_token, owner, repo)
    return {"status": "success", "data": branches}


@auth_router.post("/select")
async def select_repo(req: RepoSelectionRequest, authorization: Optional[str] = Header(None)):
    user_token = await get_current_user(authorization)
    if user_token is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    role_text = get_repo_manager().get_user_role(req.repo_id, user_token.user_id) or "viewer"
    try:
        role = Role(role_text)
    except ValueError:
        role = Role.VIEWER

    token = create_token(user_token.user_id, req.repo_id, role)
    return {
        "status": "success",
        "data": {
            "token": token,
            "repo_id": req.repo_id,
            "branch": req.branch,
            "role": role.value,
        },
    }


@auth_router.get("/me")
async def me(authorization: Optional[str] = Header(None)):
    user_token = await get_current_user(authorization)
    if user_token is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"status": "success", "data": {"user_id": user_token.user_id, "repo_id": user_token.repo_id, "role": user_token.role.value}}
