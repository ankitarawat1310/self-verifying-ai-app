from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ActorSpec(BaseModel):
    id: str
    name: str
    permissions: list[str] = Field(default_factory=list)


class EntityFieldSpec(BaseModel):
    name: str
    type: str = "string"


class EntitySpec(BaseModel):
    name: str
    fields: list[EntityFieldSpec] = Field(default_factory=list)


class BusinessRuleSpec(BaseModel):
    id: str
    description: str
    actors: list[str] = Field(default_factory=list)


class EndpointSpec(BaseModel):
    method: str
    path: str
    business_action: str
    allowed_roles: list[str] = Field(default_factory=list)


class WorkflowSpecDocument(BaseModel):
    workflow_id: str
    application_name: str
    description: str = ""
    actors: list[ActorSpec] = Field(min_length=1)
    entities: list[EntitySpec] = Field(default_factory=list)
    business_rules: list[BusinessRuleSpec] = Field(default_factory=list)
    endpoints: list[EndpointSpec] = Field(min_length=1)
    invariants: list[str] = Field(default_factory=list)

    @field_validator("endpoints")
    @classmethod
    def methods_upper(cls, endpoints: list[EndpointSpec]) -> list[EndpointSpec]:
        for ep in endpoints:
            ep.method = ep.method.upper()
        return endpoints

    def endpoint_paths(self) -> list[str]:
        return [e.path for e in self.endpoints]

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
