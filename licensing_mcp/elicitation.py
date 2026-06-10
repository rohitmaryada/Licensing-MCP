"""
Shared elicitation utilities.

The MCP spec restricts elicitation schemas to a flat object of primitives:
StringSchema | NumberSchema | BooleanSchema | EnumSchema. Two Pydantic
idioms violate that and are rejected by strict clients (Inspector, Claude
Desktop):

  1. Optional[X] → "anyOf": [X, null] — a union. Use plain annotations with
     default=None; optionality is conveyed by omission from "required".
  2. Field(default=None) → "default": null — spec requires defaults to match
     the field type. ElicitationBase strips null defaults from the schema.

Every elicitation model in this codebase must inherit from ElicitationBase.
See memory/elicitation-sdk-gotchas.md for the full debugging history.
"""

from pydantic import BaseModel


class ElicitationBase(BaseModel):
    """Base model whose JSON schema is sanitised for MCP elicitation clients."""

    @classmethod
    def model_json_schema(cls, *args, **kwargs):  # type: ignore[override]
        schema = super().model_json_schema(*args, **kwargs)
        for prop in schema.get("properties", {}).values():
            if prop.get("default", "missing") is None:
                prop.pop("default", None)
        return schema
