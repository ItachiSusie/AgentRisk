"""Isolated synthetic FHIR resource ledger for the extension track.

This is deliberately separate from the upstream MedAgentBench simulated POST.
Only synthetic records belong here; callers supply a new ledger per episode.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from ..contracts import canonical, sha256


@dataclass
class FHIRState:
    snapshot: dict[str, list[dict]]
    patient_id: str
    authorized_patients: set[str] | None = None
    resources: dict[str, list[dict]] = field(init=False)
    changes: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.resources = copy.deepcopy(self.snapshot)
        for kind, rows in self.resources.items():
            for row in rows:
                if row.get("resourceType") != kind:
                    raise ValueError("resource type mismatch")

    def reset(self) -> None:
        self.resources = copy.deepcopy(self.snapshot)
        self.changes.clear()

    def search(self, kind: str, patient_id: str) -> list[dict]:
        self._authorize(patient_id)
        return copy.deepcopy([r for r in self.resources.get(kind, [])
                              if self._patient(r) == patient_id])

    def read(self, kind: str, resource_id: str, patient_id: str) -> dict:
        self._authorize(patient_id)
        for row in self.resources.get(kind, []):
            if row.get("id") == resource_id and self._patient(row) == patient_id:
                return copy.deepcopy(row)
        raise KeyError(resource_id)

    def create(self, resource: dict, patient_id: str, idempotency_key: str) -> dict:
        self._authorize(patient_id)
        self._validate(resource, patient_id)
        if not idempotency_key:
            raise ValueError("idempotency key required")
        for change in self.changes:
            if change["idempotency_key"] == idempotency_key:
                if change["body_sha256"] != sha256(canonical(resource)):
                    raise ValueError("idempotency key reused with different body")
                return self.read(resource["resourceType"], change["resource_id"], patient_id)
        kind = resource["resourceType"]
        row = copy.deepcopy(resource)
        row.setdefault("id", "synthetic-" + sha256(idempotency_key)[:16])
        if any(existing.get("id") == row["id"] for existing in self.resources.get(kind, [])):
            raise ValueError("duplicate resource id")
        self.resources.setdefault(kind, []).append(row)
        self.changes.append({"operation": "create", "resource_type": kind,
                             "resource_id": row["id"], "idempotency_key": idempotency_key,
                             "body_sha256": sha256(canonical(resource))})
        return copy.deepcopy(row)

    def update(self, kind: str, resource_id: str, patch: dict, patient_id: str) -> dict:
        self._authorize(patient_id)
        if any(k in patch for k in ("id", "resourceType", "subject", "patient")):
            raise ValueError("identity fields cannot be patched")
        for row in self.resources.get(kind, []):
            if row.get("id") == resource_id and self._patient(row) == patient_id:
                row.update(copy.deepcopy(patch))
                self._validate(row, patient_id)
                self.changes.append({"operation": "update", "resource_type": kind,
                                     "resource_id": resource_id,
                                     "body_sha256": sha256(canonical(row))})
                return copy.deepcopy(row)
        raise KeyError(resource_id)

    def fingerprint(self) -> str:
        return sha256(canonical(self.resources))

    def _authorize(self, patient_id: str) -> None:
        if patient_id not in (self.authorized_patients or {self.patient_id}):
            raise PermissionError("patient outside episode scope")

    @staticmethod
    def _patient(resource: dict) -> str | None:
        ref = resource.get("subject", resource.get("patient"))
        if isinstance(ref, dict):
            ref = ref.get("reference")
        if isinstance(ref, str):
            return ref.removeprefix("Patient/")
        return None

    def _validate(self, resource: dict, patient_id: str) -> None:
        if not isinstance(resource, dict) or not isinstance(resource.get("resourceType"), str):
            raise ValueError("FHIR resourceType required")
        if self._patient(resource) != patient_id:
            raise PermissionError("resource patient mismatch")
        json.dumps(resource)
