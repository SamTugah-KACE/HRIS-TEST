from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.models.tenant_mapping import TenantMapping


class SrmsAdapter(ABC):
    @abstractmethod
    def get_employee(self, mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_employees(
        self,
        mapping: TenantMapping,
        token: Optional[str],
        search: str = "",
        department: str = "",
        emp_status: str = "active",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_dashboard_summary(self, mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_organizations(self, token: Optional[str]) -> Dict[str, Any]:
        raise NotImplementedError

    def create_employee(self, mapping: TenantMapping, token: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": False, "status": "native_action_required", "module": "srms", "action_id": "create_employee"}

    def update_employee(self, mapping: TenantMapping, employee_id: str, token: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": False, "status": "native_action_required", "module": "srms", "action_id": "update_employee", "employee_id": employee_id}


class EappraisalAdapter(ABC):
    @abstractmethod
    def get_appraisal_summary(self, mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_employee_appraisals(self, mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_my_appraisals(self, mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
        raise NotImplementedError

    def execute_write_action(
        self,
        mapping: TenantMapping,
        token: Optional[str],
        action_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {"ok": False, "status": "native_action_required", "module": "eappraisal", "action_id": action_id}


class EleaveAdapter(ABC):
    @abstractmethod
    def get_leave_summary(self, mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_employee_leave_history(self, mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
        raise NotImplementedError

    def execute_write_action(
        self,
        mapping: TenantMapping,
        token: Optional[str],
        action_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {"ok": False, "status": "native_action_required", "module": "eleave", "action_id": action_id}
