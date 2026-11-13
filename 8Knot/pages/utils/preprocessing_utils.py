ACTION_NAMES = {
    "pull_request_open": "PR Opened",
    "pull_request_comment": "PR Comment",
    "pull_request_closed": "PR Closed",
    "pull_request_merged": "PR Merged",
    "pull_request_review_COMMENTED": "PR Review",
    "pull_request_review_APPROVED": "PR Review",
    "pull_request_review_CHANGES_REQUESTED": "PR Review",
    "pull_request_review_DISMISSED": "PR Review",
    "issue_opened": "Issue Opened",
    "issue_closed": "Issue Closed",
    "issue_comment": "Issue Comment",
    "commit": "Commit",
}


def contributors_df_action_naming(df):
    """Renames verbs in 'Action' column

    Args:
        df (pd.DataFrame): contributors code table

    Returns:
        pd.DataFrame: processed dataframe
    """
    df = df.copy()
    # rename known actions in one pass; unknown actions keep their value
    renamed = df["action"].map(ACTION_NAMES)
    df["action"] = renamed.where(renamed.notna(), df["action"])
    df["cntrb_id"] = df["cntrb_id"].astype(str)  # contributor ids to strings
    df.rename(columns={"action": "Action"}, inplace=True)
    return df


def cntrb_per_file(df):
    # pandas column and format updates
    df["cntrb_ids"] = df["cntrb_ids"].str.split(",")
    df["reviewer_ids"] = df["reviewer_ids"].str.split(",")
    df = df.reset_index()
    df.drop("index", axis=1, inplace=True)
    return df
