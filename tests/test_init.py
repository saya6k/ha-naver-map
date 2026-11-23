"""Smoke tests proving the naver_map integration loads under HA."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from homeassistant.components.frontend import DATA_PANELS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from homeassistant.loader import async_get_integration

from custom_components.naver_map.const import DOMAIN
from tests.const import ENTRY_DATA
from tests.vendor.ha_common import MockConfigEntry

FRONTEND_DIR = Path(__file__).parent.parent / "custom_components" / DOMAIN / "frontend"


async def test_integration_manifest_loads(hass: HomeAssistant) -> None:
    """HA discovers the custom integration and parses a valid manifest."""
    integration = await async_get_integration(hass, DOMAIN)

    assert integration.domain == DOMAIN
    assert integration.config_flow is True


async def test_setup_entry_stores_domain_data(hass: HomeAssistant) -> None:
    """Setting up a config entry initializes hass.data[DOMAIN]."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert DOMAIN in hass.data


async def test_unload_entry_clears_domain_data(hass: HomeAssistant) -> None:
    """Unloading a config entry removes its data from hass.data[DOMAIN]."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.entry_id not in hass.data[DOMAIN]


async def test_setup_entry_registers_sidebar_panel(hass: HomeAssistant) -> None:
    """The entry adds the Naver Map sidebar panel backed by the bundled JS module."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    panel = hass.data[DATA_PANELS]["naver-map"]
    assert panel.sidebar_title == "Naver Map"
    assert panel.sidebar_icon == "mdi:map-marker"
    assert panel.require_admin is False
    custom = panel.config["_panel_custom"]
    assert custom["name"] == "naver-map-panel"
    assert custom["embed_iframe"] is False
    # The panel pads itself for notches/home indicators instead of HA padding it.
    assert custom["handle_safe_area"] is True
    assert custom["module_url"].startswith("/naver_map_static/naver-map-panel.js?v=")


def test_panel_module_ships_with_integration() -> None:
    """The panel JS module exists in the integration's frontend directory."""
    assert (FRONTEND_DIR / "naver-map-panel.js").is_file()


async def test_panel_frontend_directory_is_served(hass: HomeAssistant) -> None:
    """The static URL the panel module lives under serves the frontend directory."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    resource = next(
        r for r in hass.http.app.router.resources() if r.canonical == "/naver_map_static"
    )
    assert resource.get_info()["directory"] == FRONTEND_DIR


async def test_reload_entry_keeps_single_panel(hass: HomeAssistant) -> None:
    """Unloading removes the panel; reloading registers it again without errors."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert "naver-map" not in hass.data[DATA_PANELS]

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert "naver-map" in hass.data[DATA_PANELS]


async def test_setup_retry_after_panel_failure(hass: HomeAssistant) -> None:
    """A setup that fails on the panel leaves nothing registered, so a retry succeeds."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.naver_map.async_register_panel",
        side_effect=HomeAssistantError("panel failed"),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR

    assert await hass.config_entries.async_reload(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED
    assert [api.id for api in llm.async_get_apis(hass)].count(DOMAIN) == 1
