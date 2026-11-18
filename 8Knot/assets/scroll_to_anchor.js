/*
 * Scroll the URL's #fragment target into view. Registered as a Dash clientside
 * callback on url.hash — see index_callbacks.py.
 *
 * The target ids already exist: each graph card carries a nav id (the
 * VisualizationAIO `id=` set in the viz files), and the codebase heatmaps use
 * the ids on their layout rows. This adds NO ids — it only fixes WHEN the
 * scroll happens:
 *   - Dash renders the page client-side AFTER the browser's one native hash
 *     scroll, so at that moment the target element does not exist yet.
 *   - Graphs above the target then load asynchronously and reflow the page,
 *     moving the target. That settle time is variable and unbounded (cached
 *     vs live data, count/kind of graphs above, network), so no single delay
 *     is correct — too short misses the slow tail, too long stalls every page.
 *
 * So we keep the target pinned at center on a short interval until the layout
 * settles: each tick is a no-op before the element exists and a no-op once it
 * is centered, and it self-corrects instantly as the page reflows. It stops at
 * the first user scroll (armed only after our first scroll, so leftover scroll
 * momentum can't cancel it early) or after a 6s cap.
 */
window.dash_clientside = Object.assign({}, window.dash_clientside, {
    eightknot: {
        scroll_to_anchor: function (hash_) {
            if (!hash_) { return window.dash_clientside.no_update; }
            var id = hash_.replace(/^#/, "");
            var stopAt = Date.now() + 6000;
            var armed = false;
            var timer = setInterval(function () {
                var el = document.getElementById(id);
                if (el) {
                    el.scrollIntoView({ block: "center", behavior: "instant" });
                    if (!armed) {
                        armed = true;
                        var cancel = function () { clearInterval(timer); };
                        window.addEventListener("wheel", cancel, { passive: true, once: true });
                        window.addEventListener("touchmove", cancel, { passive: true, once: true });
                    }
                }
                if (Date.now() > stopAt) { clearInterval(timer); }
            }, 200);
            return window.dash_clientside.no_update;
        },
    },
});
