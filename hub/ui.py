"""Shared presentation rules for browser-facing hub pages."""

BRUTALIST_STYLE = """
<style id="vannikawachh-brutalist-ui">
:root{--vk-black:#0a0a0a;--vk-paper:#f4f4f0;--vk-ink:#111;--vk-red:#b42318;--vk-green:#147a3d;--vk-blue:#145b9e}
html,body{font-family:Arial,Helvetica,sans-serif!important;background:var(--vk-black)!important;color:var(--vk-ink)!important}
button,.btn{border:2px solid var(--vk-ink)!important;border-radius:0!important;background:var(--vk-paper)!important;color:var(--vk-ink)!important;box-shadow:3px 3px 0 var(--vk-ink)!important;font-family:Arial,Helvetica,sans-serif!important;font-weight:900!important;letter-spacing:.04em!important;text-transform:uppercase!important}
button:hover,.btn:hover{filter:none!important;transform:translate(1px,1px);box-shadow:2px 2px 0 var(--vk-ink)!important}button:disabled,.btn:disabled{box-shadow:none!important}
.btn.primary,.btn.primary:hover,.mic.on{background:var(--vk-green)!important;border-color:var(--vk-green)!important;color:#fff!important}.btn.warn,.shout{background:var(--vk-red)!important;border-color:var(--vk-red)!important;color:#fff!important}
#panel,.side,#side{background:var(--vk-paper)!important;color:var(--vk-ink)!important;border-color:var(--vk-ink)!important;border-radius:0!important;box-shadow:none!important}
.card,.metric,.section,.glass,.wp,.pstep,.inc,#chip,.state,#status,#notice,.empty,.empty-box,.scene-chip,.map-title,.a-stat,.a-state{background:#fff!important;color:var(--vk-ink)!important;border:2px solid var(--vk-ink)!important;border-radius:0!important;box-shadow:4px 4px 0 var(--vk-ink)!important;backdrop-filter:none!important}
.card,.metric,.section,.wp,.pstep,.inc{box-shadow:none!important}.sub,.tag,.mut,.hint,.mini,.lbl,.label,.ptitle,.row span,.metric span,.wpMeta,.inc .m,.empty p,#notice{color:#555!important}
.brand,.title,.side h2,.empty h1{font-family:Arial,Helvetica,sans-serif!important;font-weight:900!important;letter-spacing:-.05em!important;text-transform:uppercase!important}.logo{border:2px solid var(--vk-ink)!important;border-radius:0!important;background:var(--vk-ink)!important}.logo svg{stroke:#fff!important}
.badge,.pill,.scene-chip,.map-title,.node{border:2px solid var(--vk-ink)!important;border-radius:0!important;background:#fff!important;color:var(--vk-ink)!important;box-shadow:2px 2px 0 var(--vk-ink)!important}.online,.green,.ok{color:var(--vk-green)!important}.amber{color:#8a5a00!important}.red,.no{color:var(--vk-red)!important}.blue{color:var(--vk-blue)!important}
input{border:2px solid var(--vk-ink)!important;border-radius:0!important;background:#fff!important;color:var(--vk-ink)!important;font-family:Arial,Helvetica,sans-serif!important}.meter,.a-bar{border-radius:0!important;border:1px solid var(--vk-paper)!important}.meter>div,.a-bar>div{background:var(--vk-paper)!important;border-radius:0!important}
.pstep.on,.wp.active{background:#e6eef7!important;border-color:var(--vk-blue)!important}.pstep.done,.wp.done{background:#dff1e4!important;border-color:var(--vk-green)!important}.pstep.fail,.state.red{background:#fbe3df!important;border-color:var(--vk-red)!important}.state.live i,.scene-chip.live i{box-shadow:none!important}.reticle{border-radius:0!important}.leaflet-control-attribution{border-radius:0!important}
@media(max-width:720px){#panel,.side,#side{border-left:0!important;border-top:3px solid var(--vk-ink)!important}}
</style>
"""


def brutalist_html(html: str) -> str:
    """Append the shared visual layer once without changing page behaviour."""
    if "vannikawachh-brutalist-ui" in html:
        return html
    return html.replace("</head>", BRUTALIST_STYLE + "</head>", 1)
