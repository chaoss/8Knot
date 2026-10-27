---
name: New Visualization Request
about: Outline the generation of a new visualization
title: 'New Visualization: name_here '
labels: Visualizations
assignees: ''

---

**Please describe the background and context for this new visualization**
A clear and concise description of what the proposed visualization is and its connection to dash app design. E.g. This visualization is for the community page of the dashboard to give the perspective of [...]

**Describe the perspective you'd like the final visual to give**
A clear and concise description of the type of graph or metric thats to be created. Include specifics on what data from augur should be used and link to plotly graph

**Acceptance criteria for the issue and visualization to be complete**
- [ ] Take the concept -> high level overview of what the visualization will be and detail it in the issue
- [ ] Review current set of queries to see if one already gathers the information needed or a small edit could get it there
- [ ] Create visualization notebook in the [CHAOSS DS WG](https://github.com/chaoss/wg-data-science) [ISSUE](url)
- [ ] Visualization notebook -> 8Knot PR for visualization following the visualization template
- [ ] Create 8Knot visualization PR from the notebook using the [visualization template](https://github.com/chaoss/8Knot/blob/dev/8Knot/pages/visualization_template/viz_template.py)
- [ ] Optional - add new query using the [query template](https://github.com/chaoss/8Knot/blob/dev/8Knot/queries/query_template.py)


**Additional context**
Add any other context or screenshots about the feature request here.
