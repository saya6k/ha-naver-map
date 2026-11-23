"""get_directions LLM tool."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from custom_components.naver_map.const import (
    DIRECTIONS_MODES,
    MODE_BICYCLE,
    MODE_CAR,
    MODE_TRANSIT,
    MODE_WALK,
)
from custom_components.naver_map.services import (
    ATTR_DESTINATION,
    ATTR_MODE,
    ATTR_ORIGIN,
    ATTR_WAYPOINTS,
    async_get_directions,
)

from .base_tool import BaseNaverTool
from .render import svg_card
from .schema import POINT_INPUT


class GetDirectionsTool(BaseNaverTool):
    """Build a Naver Map route between two points, with optional waypoints."""

    name = "naver_map__get_directions"
    title = "Get directions"
    description = (
        "Get a Naver Map route between an origin and destination (each an "
        "entity_id or a latitude/longitude), with optional ordered "
        "waypoints (max 5). Returns a route link and, when the best-effort "
        "lookup succeeds, duration/distance/arrival_time (plus transfers/"
        "fare for public transit)."
    )
    parameters = vol.Schema(
        {
            vol.Required("origin"): POINT_INPUT,
            vol.Required("destination"): POINT_INPUT,
            vol.Optional("waypoints"): [POINT_INPUT],
            vol.Optional("mode"): vol.In(DIRECTIONS_MODES),
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        args = tool_input.tool_args
        data = {
            ATTR_ORIGIN: args.get("origin"),
            ATTR_DESTINATION: args.get("destination"),
            ATTR_WAYPOINTS: args.get("waypoints") or [],
            ATTR_MODE: args.get("mode") or MODE_CAR,
        }
        response = await async_get_directions(hass, self.clients, data)
        return self.envelope(
            **response,
            featured_image=_route_card(response),
            instruction=(
                "A card with the route is already shown. Mention duration and "
                "distance if they aren't null; otherwise say only the route "
                "link is available (the best-effort ETA lookup failed)."
            ),
        )


_ROUTE_ACCENT = "#03c75a"
_MODE_LABELS = {
    MODE_CAR: "자동차",
    MODE_TRANSIT: "대중교통",
    MODE_WALK: "도보",
    MODE_BICYCLE: "자전거",
}


def _duration_text(seconds: int) -> str:
    minutes = max(round(seconds / 60), 1)
    hours, minutes = divmod(minutes, 60)
    if not hours:
        return f"{minutes}분"
    return f"{hours}시간 {minutes}분" if minutes else f"{hours}시간"


def _distance_text(meters: int) -> str:
    return f"{meters / 1000:.1f}km" if meters >= 1000 else f"{meters}m"


def _route_card(response: dict[str, Any]) -> str:
    """An SVG card: origin → destination, travel time, and the route's numbers."""
    legs = response["legs"]
    title = f"{legs[0]['from']} → {legs[-1]['to']}"
    subtitle = _MODE_LABELS.get(response["mode"], response["mode"])
    if len(legs) > 1:
        subtitle += f" · 경유 {len(legs) - 1}곳"
    if response["duration"] is None:
        return svg_card(
            title,
            [("소요 시간", "확인 불가"), ("경로", "네이버 지도 링크")],
            subtitle=subtitle,
            accent=_ROUTE_ACCENT,
        )
    arrival = datetime.fromisoformat(response["arrival_time"]).strftime("%H:%M")
    lines = [("거리", _distance_text(response["distance"]))]
    if "transfers" in response:
        lines.append(("환승", f"{response['transfers']}회"))
        lines.append(("요금", f"{response['fare']:,}원"))
    return svg_card(
        title,
        lines,
        subtitle=subtitle,
        accent=_ROUTE_ACCENT,
        big_value=_duration_text(response["duration"]),
        big_value_caption=f"{arrival} 도착 예정",
    )
