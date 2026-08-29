"""
VayuSutra APIx - AI Policy Analyst Router (grounded)
"""
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/ai", tags=["AI Policy Analyst"])


class Question(BaseModel):
    question: str = Field(..., min_length=3, description="Policy/analyst question")


@router.post("/ask", summary="Ask the AI Policy Analyst a data-grounded question")
def ask(question: Question):
    from ...services.ai_analyst import answer_policy_question
    try:
        return answer_policy_question(question.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyst error: {e}")


@router.get("/capabilities", summary="What the analyst can answer")
def capabilities():
    return {"intents": [
        "Why did airfare inflation increase today?",
        "Which routes contributed most to CPI pressure?",
        "What is the 7-day airfare forecast?",
        "What caused the current pressure score?",
        "Compare DEL-BOM and DEL-BLR.",
        "What happens if airfare increases by 10%?",
        "Are there any market anomalies?",
        "How reliable is the current data?",
        "What are the top rising/falling routes?",
    ], "note": "Answers are grounded in verified platform data and never hallucinated."}
