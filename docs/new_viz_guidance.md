# Steps to create a new visualization

## Motivation

Adding figures to this application is an excellent way to contribute.
We've worked hard to make sure that the contribution of a figure
or of some analysis based on our data doesn't require knowledge of our app's
technical architecture or of its deployment design.

This document will highlight the few boilerplate steps that one needs to follow
to get up-and-running quickly.

## Guidance

### Read the code

Please try to understand the architecture by reading the code before you begin
any of your own development work. There are few "gotchas" but some are unavoidable.
A recommended way of doing this is to start by looking at `8Knot/pages/repo_overview/repo_overview.py`.
This file sketches the markup of the Overview page. You'll see that we import
the files that have the appropriate callback functions for the pages' figures from
`8Knot/pages/repo_overview/visualizations`. In this respect, we aim to isolate larger logical
"chunks" of our application - the page's structure is higher in the hierarchy, and
individual visualizations are imported and further organized below.

### Visualization Template

The [Visualization Template](https://github.com/chaoss/8Knot/blob/dev/8Knot/pages/visualization_template/viz_template.py) takes you step-by-step through the process of creating a new visualization.

### Data and Queries

Assuming that you already have the appropriate credentials to access our Augur
database instance (or have your own), you'll find that the queries to our
Database are in the folder `8Knot/queries`. These queries may be reused across multiple
visualizations. When considering creating your own visualization, please
see whether the available queries to our database instance are sufficient.

If the existing queries do not suffice:
1. Exhaust the possibility of making minor changes, such adding
new columns or aggregations, to existing queries.
2. If a completely new query is necessary, use the [Query Template](https://github.com/chaoss/8Knot/blob/dev/8Knot/queries/query_template.py)
to build a new query.

Note: make sure to do a `docker compose down` before rebuilding to be able to access any new or edited queries.

### Importing your queries

If you look at the import list at the top of a visualization file such as
`8Knot/pages/contributions/visualizations/commits_over_time.py`, you'll find that we
import the query function `8Knot/queries/commits_query.py`.

In the new visualization you're creating, please make sure to import the relevant
query in this way, and please also make sure to name this import by a sensible
short-hand if it's a query you've written, or use the short-hand that we've chosen
for queries used elsewhere:

e.g. `from queries.commits_query import commits_query as cmq`

### Using your queries

We've written a utility (`8Knot/pages/utils/job_utils.py`) and a cache manager
(`8Knot/cache_manager/cache_manager.py`) to make your life as easy as possible. Please
read through those files to understand what they're doing generally, but
feel no responsibility to dive very deep if that isn't your area of interest.
Instead, follow the format of other queries that are already available.

Use our Cache Manager interface as shown in other visualization files and the visualization template. A common error
is to copy the use of the manager from any other visualization callback and to not
replace the query function short-hand reference. For instance, if another visualization used
`commits_query`, named `cmq` as we described earlier, but you were intending to use
another query, you would need to replace `cmq` with your specific query short-hand in the following:

```python
ready, results, graph_update, interval_update = handle_job_state(jm, cmq, repolist)
if not ready:
    # set n_intervals to 0 so it'll fire again.
    return graph_update, interval_update
```

This code-block is our solution to the challenge of abstracting-away all of the
background-worker and caching logic necessary to make this app run.

## Conclusion

We hope this guide helps you along the way to implementing your own visualizations. We would love
any feedback or PR's updating this document as that becomes necessary.
