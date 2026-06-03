import re
from dataclasses import dataclass, field

# ─── PII / sensitive data patterns ───────────────────────────────────────────
_PATTERNS: dict[str, str] = {
    "email":          r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b',
    "ssn":            r'\b\d{3}-\d{2}-\d{4}\b',
    "credit_card":    r'\b(?:\d{4}[- ]?){3}\d{4}\b',
    "phone":          r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
    "openai_key":     r'\bsk-[a-zA-Z0-9]{20,}\b',
    "anthropic_key":  r'\bsk-ant-[a-zA-Z0-9\-]{20,}\b',
    "google_key":     r'\bAIza[0-9A-Za-z\-_]{35}\b',
    "aws_key":        r'\bAKIA[0-9A-Z]{16}\b',
    "ip_address":     r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b',
    "passport":       r'\b[A-Z]{1,2}[0-9]{6,9}\b',
    "iban":           r'\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b',
}

# Severity per finding type
_SEVERITY: dict[str, str] = {
    "openai_key":    "critical",
    "anthropic_key": "critical",
    "google_key":    "critical",
    "aws_key":       "critical",
    "ssn":           "critical",
    "credit_card":   "high",
    "iban":          "high",
    "passport":      "high",
    "email":         "medium",
    "phone":         "medium",
    "ip_address":    "low",
}

_COMPILED = {k: re.compile(v) for k, v in _PATTERNS.items()}


@dataclass
class Finding:
    type: str
    severity: str
    sample: str        # first 40 chars of match, redacted in middle


@dataclass
class ScanResult:
    is_sensitive: bool
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> list[dict]:
        return [{"type": f.type, "severity": f.severity, "sample": f.sample}
                for f in self.findings]


def _redact(text: str) -> str:
    if len(text) <= 6:
        return "***"
    return text[:3] + "*" * (len(text) - 6) + text[-3:]


def scan(text: str) -> ScanResult:
    """Scan text for PII and sensitive data patterns."""
    findings: list[Finding] = []
    seen_types: set[str] = set()

    for ptype, pattern in _COMPILED.items():
        matches = pattern.findall(text)
        if matches and ptype not in seen_types:
            seen_types.add(ptype)
            severity = _SEVERITY.get(ptype, "medium")
            # Critical secrets (API keys, SSNs): never echo any characters —
            # even a 3-char prefix/suffix can help an attacker identify the value.
            sample = "[redacted]" if severity == "critical" else _redact(str(matches[0])[:40])
            findings.append(Finding(
                type=ptype,
                severity=severity,
                sample=sample,
            ))

    # De-duplicate and sort by severity
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: order.get(f.severity, 9))

    return ScanResult(is_sensitive=len(findings) > 0, findings=findings)
