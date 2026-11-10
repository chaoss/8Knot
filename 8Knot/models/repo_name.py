def clean_repo_name(repo_name: str) -> tuple[str, str]:
    """
    Clean repository names by removing GitHub and GitLab URL prefixes.

    Supports both GitHub and GitLab repositories for future compatibility.

    Args:
        repo_name: The original repository name/URL

    Returns:
        Tuple of (cleaned_name, platform) where platform is 'github', 'gitlab', or 'unknown'
    """
    if not repo_name:
        return repo_name, "unknown"

    # Define prefixes with their corresponding platforms
    github_prefixes = ["https://github.com/"]

    gitlab_prefixes = ["https://gitlab.com/"]

    cleaned_name = repo_name
    repo_name_lower = repo_name.lower()

    # Check GitHub prefixes
    for prefix in github_prefixes:
        if repo_name_lower.startswith(prefix):
            cleaned_name = cleaned_name[len(prefix) :]
            return cleaned_name, "github"

    # Check GitLab prefixes
    for prefix in gitlab_prefixes:
        if repo_name_lower.startswith(prefix):
            cleaned_name = cleaned_name[len(prefix) :]
            return cleaned_name, "gitlab"

    # No known prefix found
    return cleaned_name, "unknown"
