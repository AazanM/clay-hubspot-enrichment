"""Basic email quality checks."""
import re

from .models import Lead

EMAIL_RE = re.compile(r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$", re.I)
FREE_MAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "proton.me", "protonmail.com"}
ROLE_PREFIXES = {"info", "sales", "hello", "contact", "admin", "support", "team", "office"}
DISPOSABLE = {"mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com", "yopmail.com"}


def validate_lead(lead: Lead) -> Lead:
    for flag in ("role_address", "free_mail", "invalid_email", "disposable"):
        while flag in lead.flags:
            lead.flags.remove(flag)
    email = lead.email.strip().lower()
    lead.email = email
    if not EMAIL_RE.fullmatch(email):
        lead.flags.append("invalid_email")
        return lead
    local, domain = email.rsplit("@", 1)
    if local.split("+", 1)[0] in ROLE_PREFIXES:
        lead.flags.append("role_address")
    if domain in FREE_MAIL:
        lead.flags.append("free_mail")
    if domain in DISPOSABLE:
        lead.flags.append("disposable")
    return lead
