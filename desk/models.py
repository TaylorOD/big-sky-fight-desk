from datetime import date
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


class Source(BaseModel):
    title: str
    url: str

    @field_validator("url")
    @classmethod
    def public_url(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Sources must use public HTTPS URLs.")
        return value


class Fact(BaseModel):
    text: str
    source_urls: list[str]


class Evidence(BaseModel):
    summary: str
    facts: list[Fact]
    uncertainties: list[str]


class Segment(BaseModel):
    heading: str
    text: str
    fact_ids: list[int]


class Script(BaseModel):
    title: str
    description: str
    segments: list[Segment]
    cover_brief: str

    def spoken(self):
        return "\n\n".join(s.text for s in self.segments)


class Review(BaseModel):
    passed: bool
    issues: list[str]
    notes: str


class ListeningReview(Review):
    naturalness: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)


class Brief(BaseModel):
    topic: str = Field(min_length=10, max_length=1200)
    as_of: date
    minutes: int = Field(default=4, ge=2, le=5)


class Edit(BaseModel):
    script: Script
