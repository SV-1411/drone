"""Regression checks for the browser drone views."""

from hub import webapp


def _route(path):
    matches = [route for route in webapp.app.routes if getattr(route, "path", None) == path]
    assert len(matches) == 1
    return matches[0]


def test_travel_view_is_separate_from_gazebo_view():
    travel = _route("/drone-travel-3d")
    gazebo = _route("/drone-flight")

    assert travel.endpoint.__module__ == "hub.drone_travel_3d"
    assert gazebo.endpoint.__module__ == "hub.gazebo_flight_view"


def test_travel_view_supports_standalone_and_embedded_modes():
    endpoint = _route("/drone-travel-3d").endpoint
    standalone = endpoint(embedded=False)
    embedded = endpoint(embedded=True)

    assert '<body class="standalone">' in standalone
    assert '<body class="embedded">' in embedded
    assert "fetch('/drone_state'" in standalone
    assert "UrlTemplateImageryProvider" in standalone
    assert "World_Imagery/MapServer/tile/{z}/{y}/{x}" in standalone
    assert "World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}" in standalone
    assert "baseLayer:false" in standalone
    assert "tile.openstreetmap.org" not in standalone
    assert "__CESIUM_ION_TOKEN__" not in standalone
    assert 'id="zoomIn"' in standalone
    assert 'id="zoomOut"' in standalone
    assert 'id="scaleBar"' in standalone
    assert "viewer.trackedEntity=drone" in standalone
    assert "controller.minimumZoomDistance=4" in standalone
    assert "viewer.flyTo(drone" not in standalone
    assert "viewer.zoomTo(drone" not in standalone
    assert "targetEntity.show=missionVisible" in standalone
    assert "routeEntity.show=missionVisible" in standalone


def test_hardware_page_embeds_the_travel_view_as_a_lazy_tab():
    html = _route("/drone-hardware").endpoint()

    assert "HARDWARE &amp; SYSTEMS" in html
    assert "LIVE 3D TRAVEL" in html
    assert "frame.src='/drone-travel-3d?embedded=1'" in html
    assert "fetch('/drone_state?ts='" in html
