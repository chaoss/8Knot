/*
 * Pass-through filter for the repo/org search MultiSelect (search_utils.py).
 *
 * The server already filters and ranks the options (full-text + trigram search
 * in postgres-cache). Mantine's default filter would re-filter them by label
 * substring and hide valid matches such as typos ("kubrnetes") or spaced
 * queries ("chaoss / collectoss"), so show the options as the server returned them.
 */
window.dashMantineFunctions = window.dashMantineFunctions || {};

window.dashMantineFunctions.passThroughFilter = function ({ options }) {
    return options;
};
