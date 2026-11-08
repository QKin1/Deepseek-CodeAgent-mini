ARCHITECTURE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schema_version", "source_documents", "requirements", "components", "diagrams", "traceability", "artifact_candidates", "open_questions", "conflicts", "warnings", "source_text"],
    "properties": {
        "schema_version": {"type": "string"},
        "source_documents": {"type": "array", "items": {"type": "object", "required": ["name", "sha256", "line_count"]}},
        "requirements": {"type": "array", "items": {"type": "object", "required": ["id", "mentions", "in_traceability_matrix"]}},
        "components": {"type": "array", "items": {"type": "object", "required": ["name"]}},
        "diagrams": {"type": "array", "items": {"type": "object", "required": ["name", "source_file", "line_start", "line_end", "source", "is_balanced"]}},
        "traceability": {"type": "array", "items": {"type": "object", "required": ["requirement_id", "included"]}},
        "artifact_candidates": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "object", "required": ["source_file", "line", "text"]}},
        "conflicts": {"type": "array", "items": {"type": "object", "required": ["type", "message"]}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "source_text": {"type": "object", "additionalProperties": {"type": "string"}},
    },
    "additionalProperties": True,
}
