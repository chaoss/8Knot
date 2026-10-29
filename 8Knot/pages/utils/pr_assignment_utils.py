def pr_assignment(df, start_date, end_date):
    """
    This function takes a start and a end date and determines how many
    prs in that time interval are assigned and unassigned.

    Args:
    -----
        df : Pandas Dataframe
            Dataframe with pr assignment actions of the assignees

        start_date : Datetime Timestamp
            Timestamp of the start time of the time interval

        end_date : Datetime Timestamp
            Timestamp of the end time of the time interval

    Returns:
    --------
        int, int: Number of assigned and unassigned prs in the time window
    """

    # drop rows that are more recent than the end date
    df_created = df[df["created_at"] <= end_date]

    # Keep prs that were either still open after the 'start_date' or that have not been closed.
    df_in_range = df_created[(df_created["closed_at"] > start_date) | (df_created["closed_at"].isnull())]

    # number of prs open in time interval
    num_prs_open = df_in_range["pull_request_id"].nunique()

    events = df_in_range[df_in_range["assign_date"] <= end_date]
    assignments = events[events["assignment_action"] == "assigned"].groupby("pull_request_id").size()
    unassignments = events[events["assignment_action"] == "unassigned"].groupby("pull_request_id").size()

    # A PR is assigned while any of its reviewer assignments remain active.
    active_assignments = assignments.subtract(unassignments, fill_value=0)
    num_prs_assigned = int((active_assignments > 0).sum())

    # number of unassigned prs during the time interval
    num_prs_unassigned = num_prs_open - num_prs_assigned

    # return the number of assigned and unassigned prs
    return num_prs_assigned, num_prs_unassigned
