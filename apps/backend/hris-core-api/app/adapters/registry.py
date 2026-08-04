from functools import lru_cache

from app.adapters.base import EappraisalAdapter, EleaveAdapter, SrmsAdapter
from app.adapters.eappraisal import HttpEappraisalAdapter
from app.adapters.eleave import HttpEleaveAdapter
from app.adapters.srms import HttpSrmsAdapter


@lru_cache(maxsize=1)
def get_srms_adapter() -> SrmsAdapter:
    return HttpSrmsAdapter()


@lru_cache(maxsize=1)
def get_eappraisal_adapter() -> EappraisalAdapter:
    return HttpEappraisalAdapter()


@lru_cache(maxsize=1)
def get_eleave_adapter() -> EleaveAdapter:
    return HttpEleaveAdapter()
