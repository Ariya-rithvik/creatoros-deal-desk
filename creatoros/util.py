"""Small shared helpers: domains, homoglyphs, edit distance."""
import re
from typing import List, Optional
from urllib.parse import urlparse

_TWO_PART_TLDS = {"co.uk", "org.uk", "com.au", "co.in", "co.jp", "com.br", "co.za", "com.sg", "co.nz"}
_URL_RE = re.compile(r"https?://[^\s\"'<>)]+", re.I)
_EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")


def find_urls(text: str) -> List[str]:
    return [u.rstrip(".,;:") for u in _URL_RE.findall(text or "")]


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def registrable_domain(host: str) -> str:
    host = (host or "").lower().strip(".")
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    last_two = ".".join(parts[-2:])
    if last_two in _TWO_PART_TLDS and len(parts) >= 3:
        return ".".join(parts[-3:])
    return last_two


def email_domain(address: str) -> Optional[str]:
    """Domain of the first e-mail address in the string, original case preserved."""
    m = _EMAIL_RE.search(address or "")
    return m.group(1) if m else None


def deconfuse(domain: str) -> str:
    """Map visual look-alikes to their target letters: capital I -> l, 0 -> o, rn -> m, vv -> w.

    Capital I must be replaced BEFORE lowercasing, because I.lower() == 'i' would hide the trick.
    """
    d = domain.replace("I", "l")
    return d.lower().replace("0", "o").replace("rn", "m").replace("vv", "w")


_DIGIT_HOMOGLYPHS = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b"})


def homoglyph_key(label: str) -> str:
    """Normalise a domain label to the letters it visually READS as, for comparison only.

    Extends `deconfuse` with the digit-for-letter swaps typosquatters use, so 'elevenlab5'
    and 'elevenlabs' compare equal. Only digits with an unambiguous letter shape are mapped
    (2, 6 and 9 are left alone).
    """
    return deconfuse(label).translate(_DIGIT_HOMOGLYPHS)


def is_transposition(a: str, b: str) -> bool:
    """True if `a` is `b` with exactly one adjacent pair swapped ('sqaurespace' <- 'squarespace')."""
    if len(a) != len(b) or a == b:
        return False
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    return (len(diff) == 2 and diff[1] == diff[0] + 1
            and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])


def is_doubling(a: str, b: str) -> bool:
    """True if one string is the other with a single letter doubled ('nottion' <- 'notion')."""
    lo, hi = (a, b) if len(a) < len(b) else (b, a)
    if len(hi) != len(lo) + 1 or not lo:
        return False
    return any(hi[i] == hi[i - 1] and hi[:i] + hi[i + 1:] == lo for i in range(1, len(hi)))


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]
