from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

from app.schemas import Project


class ProjectStore:
    def __init__(self) -> None:
        self.root = Path(os.getenv("APP_DATA_DIR", "data"))
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def save(self, project: Project) -> None:
        with self._lock:
            (self.root / f"{project.id}.json").write_text(
                project.model_dump_json(indent=2), encoding="utf-8"
            )

    def get(self, project_id: str) -> Project:
        path = self.root / f"{project_id}.json"
        if not path.exists():
            raise KeyError(project_id)
        return Project.model_validate_json(path.read_text(encoding="utf-8"))

    def export(self, project: Project) -> dict:
        return json.loads(project.model_dump_json())
