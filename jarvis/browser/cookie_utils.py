"""Small, fail-closed helpers for HTTP cookie parsing and emission."""

from __future__ import annotations

import ipaddress
import math
import re
import time
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from http.cookies import CookieError, SimpleCookie
from typing import Any

import idna

try:
    from psl import domain_can_set_cookie as _psl_domain_can_set_cookie
    from psl import domain_suffixes as _psl_domain_suffixes
except ImportError:  # pragma: no cover - production dependency, fail closed below
    _psl_domain_can_set_cookie = None
    _psl_domain_suffixes = None

CookieIdentity = tuple[str, str, str, str | None]
COOKIE_MAX_AGE_SECONDS = 400 * 24 * 60 * 60


@dataclass(frozen=True)
class ResponseCookieAction:
    """One validated response-cookie mutation."""

    upsert: dict[str, Any] | None = None
    deletions: tuple[CookieIdentity, ...] = ()


_COOKIE_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_COOKIE_VALUE = re.compile(r"^[\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]*$")


def _split_cookie_parts(header: str) -> list[str]:
    """Split semicolon-delimited parts while preserving quoted cookie values."""

    parts: list[str] = []
    current: list[str] = []
    quoted = False
    escaped = False
    for character in header:
        if escaped:
            current.append(character)
            escaped = False
            continue
        if character == "\\" and quoted:
            current.append(character)
            escaped = True
            continue
        if character == '"':
            quoted = not quoted
            current.append(character)
            continue
        if character == ";" and not quoted:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(character)
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def parse_set_cookie_field(
    header: str,
) -> tuple[str, str, dict[str, str | None]] | None:
    """Parse the leading cookie pair and allow callers to interpret attributes.

    Only the first name/value pair can become a cookie. Unknown extension
    attributes are returned as metadata and can never be fabricated as cookies.
    """

    if not isinstance(header, str):
        return None
    parts = _split_cookie_parts(header)
    if not parts:
        return None
    leading = SimpleCookie()
    try:
        leading.load(parts[0])
    except CookieError:
        return None
    if len(leading) != 1:
        return None
    name, morsel = next(iter(leading.items()))
    if not name:
        return None

    attributes: dict[str, str | None] = {}
    for part in parts[1:]:
        attribute_name, separator, attribute_value = part.partition("=")
        normalized_name = attribute_name.strip().lower()
        if not normalized_name:
            continue
        attributes[normalized_name] = attribute_value.strip() if separator else None
    return name, morsel.value, attributes


def normalize_cookie_path(value: str | None, default_path: str) -> str:
    """Apply RFC6265's default-path rule to absent or invalid Path attributes."""

    candidate = str(value or "").strip('"')
    return candidate if candidate.startswith("/") else default_path


def cookie_prefix_is_valid(
    name: str,
    *,
    secure: bool,
    http_only: bool,
    host_only: bool,
    path: str,
    scheme: str,
) -> bool:
    """Validate security prefix invariants enforced by modern browsers."""

    if name.startswith("__Secure-") and (scheme != "https" or not secure):
        return False
    if name.startswith("__Host-") and (
        scheme != "https" or not secure or not host_only or path != "/"
    ):
        return False
    if name.startswith("__Http-") and (scheme != "https" or not secure or not http_only):
        return False
    if name.startswith("__Host-Http-") and not http_only:
        return False
    return True


def canonical_cookie_hostname(value: str) -> str:
    """Canonicalize a cookie hostname to the ASCII form used by browsers."""

    candidate = value.strip().lower()
    if candidate.endswith("."):
        raise ValueError("Cookie hostname is invalid.")
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    if not candidate or any(character in candidate for character in "/\\@"):
        raise ValueError("Cookie hostname is invalid.")
    try:
        return ipaddress.ip_address(candidate).compressed.lower()
    except ValueError:
        try:
            canonical = idna.encode(
                candidate,
                uts46=True,
                transitional=False,
                std3_rules=True,
            ).decode("ascii")
        except idna.IDNAError as exc:
            raise ValueError("Cookie hostname is invalid.") from exc
    labels = canonical.split(".")
    if (
        not canonical
        or len(canonical) > 253
        or any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or re.fullmatch(r"[a-z0-9-]+", label) is None
            for label in labels
        )
    ):
        raise ValueError("Cookie hostname is invalid.")
    if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", labels[-1], re.IGNORECASE):
        # WHATWG treats domains ending in a number as legacy IPv4 syntax
        # (for example 127.1 or 0x7f.1).  Reject those non-canonical spellings
        # so Chromium cannot mutate an identity different from our rollback key.
        raise ValueError("Cookie hostname uses non-canonical IPv4 syntax.")
    return canonical


def cookie_storage_domain(hostname: str) -> str:
    """Render a canonical host in the domain form Chromium exposes."""

    canonical = canonical_cookie_hostname(hostname)
    try:
        address = ipaddress.ip_address(canonical)
    except ValueError:
        return canonical
    return f"[{address.compressed.lower()}]" if address.version == 6 else canonical


def cookie_domain_attribute_is_allowed(request_host: str, cookie_domain: str) -> bool:
    """Validate Domain scope and reject public-suffix supercookies."""

    try:
        host = canonical_cookie_hostname(request_host)
        domain = canonical_cookie_hostname(cookie_domain.lstrip("."))
    except (AttributeError, ValueError):
        return False
    if host != domain and not host.endswith(f".{domain}"):
        return False
    try:
        ipaddress.ip_address(domain)
        return host == domain
    except ValueError:
        pass
    if "." not in domain:
        return host == domain == "localhost"
    return bool(_psl_domain_can_set_cookie is not None and _psl_domain_can_set_cookie(domain))


def url_cookie_scope(url: str) -> tuple[str, str, str]:
    """Return Playwright's scheme/domain/default-path canonicalization."""

    if (
        not isinstance(url, str)
        or "\\" in url
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in url)
    ):
        raise ValueError("Cookie URL is invalid.")
    try:
        parsed = urllib.parse.urlsplit(url)
        scheme = parsed.scheme.lower()
        hostname = canonical_cookie_hostname(parsed.hostname or "")
        _port = parsed.port
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Cookie URL is invalid.") from exc
    if scheme not in {"http", "https"} or not hostname or parsed.username is not None:
        raise ValueError("Cookie URL is invalid.")
    raw_path = parsed.path or "/"
    if re.search(r"%(?![0-9A-Fa-f]{2})", raw_path):
        raise ValueError("Cookie URL path is invalid.")
    path = urllib.parse.quote(
        _normalize_whatwg_path(raw_path),
        safe="/!$&'()*+,-.:;=@_[]%~",
    )
    default_path = path[: path.rfind("/") + 1] or "/"
    return scheme, hostname, default_path


def _normalize_whatwg_path(path: str) -> str:
    """Normalize URL dot segments before deriving Chromium's cookie path."""

    segments = path.split("/")
    normalized: list[str] = []
    last_index = len(segments) - 1
    for index, segment in enumerate(segments):
        dot_segment = re.sub(r"%2e", ".", segment, flags=re.IGNORECASE)
        if dot_segment == ".":
            if index == last_index:
                normalized.append("")
            continue
        if dot_segment == "..":
            if normalized and normalized[-1] != "":
                normalized.pop()
            if index == last_index:
                normalized.append("")
            continue
        normalized.append(segment)
    result = "/".join(normalized)
    return result if result.startswith("/") else f"/{result}"


def canonicalize_cookie(cookie: Mapping[str, Any]) -> dict[str, Any]:
    """Canonicalize one public cookie payload before any driver mutation."""

    if not isinstance(cookie, Mapping):
        raise ValueError("Cookie entry must be a mapping.")
    normalized = dict(cookie)
    has_url = isinstance(normalized.get("url"), str) and bool(normalized.get("url"))
    has_domain = normalized.get("domain") is not None
    has_path = normalized.get("path") is not None
    if has_url and (has_domain or has_path):
        raise ValueError("Cookie must use either URL or domain/path scope.")
    if has_url:
        scheme, domain, path = url_cookie_scope(str(normalized.pop("url")))
        normalized["domain"] = cookie_storage_domain(domain)
        normalized["path"] = path
        normalized["secure"] = scheme == "https"
    else:
        raw_domain = normalized.get("domain")
        raw_path = normalized.get("path")
        if not isinstance(raw_domain, str) or not raw_domain.strip():
            raise ValueError("Cookie domain is invalid.")
        if raw_domain.strip().endswith("."):
            raise ValueError("Cookie domain is invalid.")
        if not cookie_path_is_valid(raw_path):
            raise ValueError("Cookie path is invalid.")
        is_domain_cookie = raw_domain.strip().startswith(".")
        domain = canonical_cookie_hostname(raw_domain.strip().lstrip("."))
        if is_domain_cookie:
            if not cookie_domain_attribute_is_allowed(domain, domain):
                raise ValueError("Cookie domain is a public suffix.")
            # Chromium normalizes Domain=localhost and IP literals to host-only
            # cookies.  Canonicalize that shape before mutation so verification
            # and rollback address the same identity the browser will store.
            try:
                ipaddress.ip_address(domain)
                is_domain_cookie = False
            except ValueError:
                if "." not in domain:
                    is_domain_cookie = False
            if is_domain_cookie:
                domain = f".{domain}"
        if not is_domain_cookie:
            domain = cookie_storage_domain(domain)
        normalized["domain"] = domain
        normalized["path"] = raw_path
    if not cookie_path_is_valid(normalized.get("path")):
        raise ValueError("Cookie path is invalid.")
    if "expires" in normalized:
        normalized["expires"] = canonicalize_cookie_expiry(normalized["expires"])
    if "sameSite" in normalized:
        same_site = {
            "strict": "Strict",
            "lax": "Lax",
            "none": "None",
        }.get(str(normalized["sameSite"]).strip().lower())
        if same_site is None:
            raise ValueError("Cookie SameSite value is invalid.")
        normalized["sameSite"] = same_site

    partition_key = normalized.get("partitionKey")
    if partition_key is not None:
        if not isinstance(partition_key, str) or not partition_key:
            raise ValueError("Cookie partition key is invalid.")
        scheme, hostname, _path = url_cookie_scope(partition_key)
        try:
            ipaddress.ip_address(hostname)
            site = hostname
        except ValueError:
            if _psl_domain_suffixes is None:
                raise ValueError("Cookie partition key cannot be canonicalized.")
            suffixes = _psl_domain_suffixes(hostname)
            site = str(getattr(suffixes, "private", "") or hostname)
        authority = f"[{hostname}]" if ":" in hostname else hostname
        if site != hostname:
            authority = site
        normalized["partitionKey"] = f"{scheme}://{authority}"
        normalized.setdefault("_crHasCrossSiteAncestor", True)
    return normalized


def cookie_pair_is_safe(name: object, value: object) -> bool:
    """Reject malformed stored values instead of allowing header injection."""

    return (
        isinstance(name, str)
        and isinstance(value, str)
        and bool(_COOKIE_NAME.fullmatch(name))
        and bool(_COOKIE_VALUE.fullmatch(value))
    )


def cookie_expiry_is_valid(value: object) -> bool:
    """Accept Playwright's session sentinel, deletion zero, or future timestamps."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    numeric = float(value)
    return math.isfinite(numeric) and (numeric == -1 or numeric >= 0)


def canonicalize_cookie_expiry(value: object, *, now: float | None = None) -> int | float:
    """Apply Chromium's 400-day persistence cap without accepting bad sentinels."""

    if not cookie_expiry_is_valid(value):
        raise ValueError("Cookie expiry is invalid.")
    numeric = float(value)
    if numeric <= 0:
        return value  # preserve the public -1 session and 0 deletion sentinels
    maximum = (time.time() if now is None else now) + COOKIE_MAX_AGE_SECONDS
    return min(value, maximum)


def cookie_path_is_valid(value: object) -> bool:
    """Reject paths Chromium would rewrite or refuse at the mutation seam."""

    return (
        isinstance(value, str)
        and value.startswith("/")
        and all(0x21 <= ord(character) <= 0x7E for character in value)
        and ";" not in value
        and "\\" not in value
    )


def build_cookie_header(
    cookies: Iterable[Mapping[str, Any]],
    url: str,
    top_level_url: str | None = None,
) -> str:
    """Build an RFC-ordered Cookie header without collapsing duplicate names."""

    try:
        parsed = urllib.parse.urlsplit(url)
        scheme = parsed.scheme.lower()
        hostname = canonical_cookie_hostname(parsed.hostname or "")
    except (AttributeError, TypeError, ValueError):
        return ""
    if scheme not in {"http", "https"} or not hostname:
        return ""

    request_path = parsed.path or "/"
    try:
        top_level = urllib.parse.urlsplit(top_level_url or url)
        top_level_site = (
            top_level.scheme.lower(),
            canonical_cookie_hostname(top_level.hostname or ""),
        )
    except (AttributeError, TypeError, ValueError):
        top_level_site = ("", "")

    now = time.time()
    selected: list[tuple[int, int, str, str]] = []
    for index, cookie in enumerate(cookies):
        if cookie.get("partitionKey"):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        if not cookie_pair_is_safe(name, value):
            continue
        raw_domain = str(cookie.get("domain") or "").lower().strip()
        is_domain_cookie = raw_domain.startswith(".")
        try:
            domain = canonical_cookie_hostname(raw_domain.lstrip("."))
        except ValueError:
            continue
        cookie_path = str(cookie.get("path") or "/")
        if not domain or not cookie_path.startswith("/"):
            continue
        if hostname != domain and not (is_domain_cookie and hostname.endswith(f".{domain}")):
            continue
        if bool(cookie.get("secure")) and scheme != "https":
            continue
        if (
            str(cookie.get("sameSite") or "").lower() == "strict"
            and (scheme, hostname) != top_level_site
        ):
            continue
        if request_path != cookie_path and not request_path.startswith(
            cookie_path if cookie_path.endswith("/") else f"{cookie_path}/"
        ):
            continue
        if "expires" in cookie:
            try:
                expires = float(cookie["expires"])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(expires):
                continue
            if expires == 0 or (expires > 0 and expires <= now):
                continue
        selected.append((-len(cookie_path), index, name, value))

    selected.sort()
    return "; ".join(f"{name}={value}" for _, _, name, value in selected)


def response_action_overlays_secure_cookie(
    action: ResponseCookieAction,
    cookies: Iterable[Mapping[str, Any]],
    request_url: str,
) -> bool:
    """Return whether an insecure response mutation overlaps a Secure cookie."""

    try:
        if urllib.parse.urlsplit(request_url).scheme.lower() == "https":
            return False
    except (AttributeError, TypeError, ValueError):
        return True

    affected: list[tuple[str, str, str]] = [
        (name, domain, path) for name, domain, path, _partition_key in action.deletions
    ]
    if action.upsert is not None:
        affected.append(
            (
                str(action.upsert.get("name") or ""),
                str(action.upsert.get("domain") or ""),
                str(action.upsert.get("path") or "/"),
            )
        )

    def domains_overlap(left: str, right: str) -> bool:
        try:
            left = canonical_cookie_hostname(left.lower().lstrip("."))
            right = canonical_cookie_hostname(right.lower().lstrip("."))
        except ValueError:
            return False
        return bool(left and right) and (
            left == right or left.endswith(f".{right}") or right.endswith(f".{left}")
        )

    def paths_overlap(left: str, right: str) -> bool:
        def path_matches(request_path: str, cookie_path: str) -> bool:
            return request_path == cookie_path or request_path.startswith(
                cookie_path if cookie_path.endswith("/") else f"{cookie_path}/"
            )

        return path_matches(left, right) or path_matches(right, left)

    for cookie in cookies:
        if not bool(cookie.get("secure")) or cookie.get("partitionKey"):
            continue
        existing_name = str(cookie.get("name") or "")
        existing_domain = str(cookie.get("domain") or "")
        existing_path = str(cookie.get("path") or "/")
        for name, domain, path in affected:
            if (
                name == existing_name
                and domains_overlap(domain, existing_domain)
                and paths_overlap(path, existing_path)
            ):
                return True
    return False


def response_domain_storage_domain(
    request_host: str,
    domain_specified: bool,
    domain_attribute: str | None = None,
) -> str:
    """Mirror browser scope for an exact-host Domain attribute conservatively."""

    if not domain_specified:
        return cookie_storage_domain(request_host)
    cookie_domain = domain_attribute or request_host
    if cookie_domain != request_host:
        return f".{cookie_domain}"
    try:
        ipaddress.ip_address(request_host)
    except ValueError:
        # Chromium treats single-label Domain=localhost as host-only.
        if "." in request_host:
            return f".{request_host}"
    return cookie_storage_domain(request_host)


def parse_response_cookie_action(
    header: str,
    request_url: str,
    *,
    now: float | None = None,
) -> ResponseCookieAction | None:
    """Validate one ordered Set-Cookie field using a conservative scope policy.

    Without a public-suffix implementation, response ``Domain`` upserts are
    accepted only when they exactly equal the request host. Expiring cookies
    may target a matching parent domain so an existing domain cookie can still
    be removed.
    """

    parsed_field = parse_set_cookie_field(header)
    if parsed_field is None:
        return None
    name, value, attributes = parsed_field
    if "partitioned" in attributes:
        return None

    try:
        request = urllib.parse.urlsplit(request_url)
        scheme = request.scheme.lower()
        request_host = canonical_cookie_hostname(request.hostname or "")
        request_path = request.path or "/"
    except (AttributeError, TypeError, ValueError):
        return None
    if scheme not in {"http", "https"} or not request_host:
        return None

    default_path = (
        "/"
        if not request_path.startswith("/") or request_path.count("/") <= 1
        else request_path.rsplit("/", 1)[0] or "/"
    )
    path = normalize_cookie_path(attributes.get("path"), default_path)
    if not cookie_path_is_valid(path):
        return None
    secure = "secure" in attributes
    http_only = "httponly" in attributes
    if secure and scheme != "https":
        return None

    has_domain_attribute = "domain" in attributes
    domain_attribute = ""
    if has_domain_attribute:
        raw_domain = str(attributes.get("domain") or "").strip().strip('"').lower()
        if not raw_domain or raw_domain.endswith("."):
            return None
        try:
            domain_attribute = canonical_cookie_hostname(raw_domain.lstrip("."))
        except ValueError:
            return None
        if not cookie_domain_attribute_is_allowed(request_host, domain_attribute):
            return None

    same_site = {
        "strict": "Strict",
        "lax": "Lax",
        "none": "None",
    }.get(str(attributes.get("samesite") or "").strip().strip('"').lower())
    if same_site == "None" and not secure:
        return None
    if not cookie_prefix_is_valid(
        name,
        secure=secure,
        http_only=http_only,
        host_only=not has_domain_attribute,
        path=path,
        scheme=scheme,
    ):
        return None

    observed_at = time.time() if now is None else now
    delete = False
    expires_at: float | None = None
    max_age_valid = False
    max_age_value = str(attributes.get("max-age") or "").strip().strip('"')
    if max_age_value:
        try:
            max_age = int(max_age_value)
            max_age_valid = True
            if max_age <= 0:
                delete = True
            else:
                expires_at = observed_at + max_age
                if not math.isfinite(expires_at):
                    return None
        except (ValueError, OverflowError):
            pass
    expires_value = str(attributes.get("expires") or "").strip().strip('"')
    if not max_age_valid and expires_value:
        try:
            parsed_expiry = parsedate_to_datetime(expires_value)
            if parsed_expiry.tzinfo is None:
                parsed_expiry = parsed_expiry.replace(tzinfo=timezone.utc)
            expires_at = parsed_expiry.timestamp()
            delete = expires_at <= observed_at
        except (TypeError, ValueError, OverflowError):
            expires_at = None

    if delete:
        if has_domain_attribute:
            deletion_domain = (
                response_domain_storage_domain(request_host, True)
                if request_host == domain_attribute
                else f".{domain_attribute}"
            )
            return ResponseCookieAction(deletions=((name, deletion_domain, path, None),))
        return ResponseCookieAction(deletions=((name, request_host, path, None),))

    if not cookie_pair_is_safe(name, value):
        return None

    entry: dict[str, Any] = {
        "name": name,
        "value": value,
        "domain": response_domain_storage_domain(
            request_host,
            has_domain_attribute,
            domain_attribute or None,
        ),
        "path": path,
        "secure": secure,
    }
    if expires_at is not None:
        entry["expires"] = canonicalize_cookie_expiry(expires_at, now=observed_at)
    if http_only:
        entry["httpOnly"] = True
    if same_site is not None:
        entry["sameSite"] = same_site
    return ResponseCookieAction(upsert=entry)
