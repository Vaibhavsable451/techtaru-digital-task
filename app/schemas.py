"""Pydantic models = the contract the LLM output must satisfy."""
from enum import Enum
from pydantic import BaseModel, Field


class DocType(str, Enum):
    resume = "resume"
    invoice = "invoice"


# ---------- Resume ----------
class Experience(BaseModel):
    company: str | None = None
    title: str | None = None
    start_date: str | None = Field(None, description="As written, e.g. 'Jan 2022'")
    end_date: str | None = Field(None, description="'Present' if current")
    description: str | None = None


class Education(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    graduation_year: str | None = None


class Resume(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


# ---------- Invoice ----------
class LineItem(BaseModel):
    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    total: float | None = None


class Invoice(BaseModel):
    invoice_number: str | None = None
    vendor_name: str | None = None
    customer_name: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str | None = Field(None, description="ISO code or symbol, e.g. INR, USD")
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None


SCHEMAS: dict[DocType, type[BaseModel]] = {
    DocType.resume: Resume,
    DocType.invoice: Invoice,
}


# ---------- API ----------
class ExtractRequest(BaseModel):
    text: str = Field(..., description="Unstructured resume or invoice text")
    doc_type: DocType = DocType.resume


class ExtractResponse(BaseModel):
    doc_type: DocType
    model: str
    data: dict
    warnings: list[str] = Field(default_factory=list)
