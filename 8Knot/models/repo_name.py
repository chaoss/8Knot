import re

# scheme and "www." are optional so pasted URLs match the stored owner/repo in any of those forms
_REPO_URL_PREFIX = re.compile(r"(?:https?://)?(?:www\.)?(github|gitlab)\.com/", re.IGNORECASE)


def clean_repo_name(repo_name: str) -> tuple[str, str]:
    """
    Strip a GitHub or GitLab URL prefix from a repository name.

    Returns:
        Tuple of (cleaned_name, platform) where platform is 'github', 'gitlab', or 'unknown'
    """
    match = _REPO_URL_PREFIX.match(repo_name or "")
    if not match:
        return repo_name, "unknown"
    return repo_name[match.end() :], match.group(1).lower()
