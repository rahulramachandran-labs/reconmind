from fastapi import Request

from app.config import Settings
from app.llm import LLMChain
from app.retrieval.service import RetrievalService
from app.sessions import SessionStore


def get_retrieval(request: Request) -> RetrievalService:
    return request.app.state.retrieval


def get_llm(request: Request) -> LLMChain:
    return request.app.state.llm


def get_sessions(request: Request) -> SessionStore:
    return request.app.state.sessions


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings
