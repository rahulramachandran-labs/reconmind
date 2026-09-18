from fastapi import Request

from app.config import Settings
from app.llm import LLMClient
from app.retrieval.service import RetrievalService


def get_retrieval(request: Request) -> RetrievalService:
    return request.app.state.retrieval


def get_llm(request: Request) -> LLMClient:
    return request.app.state.llm


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings
