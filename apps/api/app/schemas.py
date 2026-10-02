from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Needs(StrictModel):
    catalog_mode: Literal['demo', 'real'] = 'demo'
    target: Literal['keyboard', 'mouse', 'keyboard_mouse_bundle']
    budget_minor: int = Field(gt=0, le=100000000, strict=True)
    currency: Literal['CNY'] = 'CNY'
    primary_use: Literal['coding', 'office', 'gaming', 'portable']
    connection: Literal['any', 'wireless', 'bluetooth', 'wired'] = 'any'
    quiet: Literal['any', 'prefer', 'required'] = 'any'
    numpad: Literal['any', 'required', 'excluded'] = 'any'
    text: str = Field(default='', max_length=2000)


class AnalyzeRequest(StrictModel):
    structured_input: Needs
    text: str = Field(default='', max_length=2000)
    base_requirement_revision_id: str | None = None


class ConfirmRequest(StrictModel):
    needs: Needs
    base_requirement_revision_id: str | None = None


class RecommendRequest(StrictModel):
    requirement_revision_id: str


class Reason(StrictModel):
    text: str = Field(max_length=300)
    evidence_ids: list[str] = Field(min_length=1, max_length=5)


class ModelExplanation(StrictModel):
    scheme_id: str
    reasons: list[Reason] = Field(max_length=3)
    tradeoffs: list[str] = Field(max_length=3)


class Explanations(StrictModel):
    schemes: list[ModelExplanation] = Field(max_length=3)
