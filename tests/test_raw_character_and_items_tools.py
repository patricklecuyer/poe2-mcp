import json
import pytest
from unittest.mock import AsyncMock

from src.mcp_server import PoE2BuildOptimizerMCP
from src.utils.item_normalizer import (
    normalize_raw_item,
    extract_character_items,
    extract_raw_character_payload,
    format_items_markdown,
)


SAMPLE_RAW_ITEM = {
    "itemData": {
        "name": "Doom Loom",
        "typeLine": "Expert Heavy Crown",
        "baseType": "Heavy Crown",
        "inventoryId": "Helm",
        "ilvl": 82,
        "frameType": 2,
        "corrupted": False,
        "properties": [
            {"name": "Armour", "values": [["150", 1]]},
            {"name": "Energy Shield", "values": [["45", 0]]},
        ],
        "requirements": [
            {"name": "Level", "values": [["65", 0]]},
            {"name": "Str", "values": [["112", 0]]},
        ],
        "implicitMods": ["+25 to maximum Life"],
        "explicitMods": [
            "+85 to maximum Life",
            "+35% to Fire Resistance",
            "+30% to Cold Resistance",
        ],
        "mods": {
            "implicit": [{"id": "ItemImplicitLife1", "stats": {"maximum_life": 25}}],
            "explicit": [
                {"id": "ItemLocalLife8", "stats": {"maximum_life": 85}},
                {"id": "FireResist5", "stats": {"fire_damage_resistance_%": 35}},
                {"id": "ColdResist4", "stats": {"cold_damage_resistance_%": 30}},
            ],
        },
        "sockets": [{"group": 0, "type": "rune"}],
        "socketedItems": [
            {
                "name": "Greater Iron Rune",
                "typeLine": "Greater Iron Rune",
                "explicitMods": ["+50 to Armour"],
                "mods": {"explicit": [{"id": "RuneArmour2", "stats": {"armour": 50}}]},
            }
        ],
    },
    "itemSlot": 0,
}


def test_normalize_raw_item():
    norm = normalize_raw_item(SAMPLE_RAW_ITEM)
    assert norm["name"] == "Doom Loom"
    assert norm["base_type"] == "Heavy Crown"
    assert norm["slot"] == "Helm"
    assert norm["item_level"] == 82
    assert norm["rarity"] == "Rare"

    # Properties & Requirements
    props_dict = {p["name"]: p["value"] for p in norm["properties"]}
    assert props_dict["Armour"] == "150"
    assert props_dict["Energy Shield"] == "45"
    assert norm["requirements"]["Level"] == 65
    assert norm["requirements"]["Str"] == 112

    # Affixes
    assert len(norm["affixes"]["implicit"]) == 1
    assert norm["affixes"]["implicit"][0]["mod_id"] == "ItemImplicitLife1"
    assert norm["affixes"]["implicit"][0]["stats"] == {"maximum_life": 25}

    assert len(norm["affixes"]["explicit"]) == 3
    assert norm["affixes"]["explicit"][0]["mod_id"] == "ItemLocalLife8"
    assert norm["affixes"]["explicit"][0]["stats"] == {"maximum_life": 85}

    # Sockets & Socketed items
    assert len(norm["sockets"]) == 1
    assert len(norm["socketed_items"]) == 1
    assert norm["socketed_items"][0]["name"] == "Greater Iron Rune"
    assert norm["socketed_items"][0]["explicit_mods"] == ["+50 to Armour"]


def test_extract_character_items():
    char_data = {
        "raw_items": [SAMPLE_RAW_ITEM],
        "raw_flasks": [
            {
                "itemData": {
                    "name": "Quick Flask",
                    "typeLine": "Ultimate Life Flask",
                    "baseType": "Ultimate Life Flask",
                    "inventoryId": "Flask",
                    "explicitMods": ["40% increased recovery rate"],
                    "mods": {"explicit": [{"id": "FlaskRate1", "stats": {"rate": 40}}]},
                }
            }
        ],
        "raw_jewels": [],
    }

    # All items including flasks
    items = extract_character_items(char_data, include_flasks=True, include_jewels=True)
    assert len(items) == 2
    assert items[0]["slot"] == "Helm"
    assert items[1]["slot"] == "Flask"

    # Slot filtering
    helm_items = extract_character_items(char_data, slot_filter="Helm")
    assert len(helm_items) == 1
    assert helm_items[0]["slot"] == "Helm"

    flask_items = extract_character_items(char_data, slot_filter="Flask")
    assert len(flask_items) == 1
    assert flask_items[0]["name"] == "Quick Flask"


def test_extract_raw_character_payload():
    char_data = {
        "name": "Hero",
        "account": "Player#123",
        "class": "Monk",
        "ascendancy": "Invoker",
        "level": 90,
        "league": "runesofaldur",
        "raw_items": [SAMPLE_RAW_ITEM],
        "raw_flasks": [],
        "raw_jewels": [],
        "passive_tree": [101, 102, 103],
        "keystones": ["Chaos Inoculation"],
        "skills": [{"name": "Falling Thunder", "level": 20}],
        "stats": {"life": 3500, "energyShield": 1200},
    }

    payload = extract_raw_character_payload(char_data, section="all")
    assert payload["character"]["name"] == "Hero"
    assert payload["character"]["level"] == 90
    assert len(payload["equipment"]) == 1
    assert payload["passive_tree"]["total_nodes"] == 3
    assert payload["passive_tree"]["keystones"] == ["Chaos Inoculation"]
    assert payload["defensive_stats"]["life"] == 3500

    # Section filtering
    equip_only = extract_raw_character_payload(char_data, section="equipment")
    assert "equipment" in equip_only
    assert "passive_tree" not in equip_only


def test_format_items_markdown():
    norm = normalize_raw_item(SAMPLE_RAW_ITEM)
    md = format_items_markdown([norm])
    assert "Doom Loom (Expert Heavy Crown)" in md
    assert "### Helm: Doom Loom" in md
    assert "Armour: 150" in md
    assert "+85 to maximum Life" in md
    assert "[ItemLocalLife8]" in md
    assert "Greater Iron Rune" in md


@pytest.mark.asyncio
async def test_mcp_server_raw_data_and_items_tools():
    server = PoE2BuildOptimizerMCP()
    server.char_fetcher = AsyncMock()

    mock_char_data = {
        "name": "Hero",
        "account": "Player-123",
        "class": "Monk",
        "ascendancy": "Invoker",
        "level": 90,
        "league": "runesofaldur",
        "raw_items": [SAMPLE_RAW_ITEM],
        "raw_flasks": [],
        "raw_jewels": [],
        "passive_tree": [101, 102],
        "keystones": [],
        "skills": [],
        "stats": {"life": 3000},
    }
    server.char_fetcher.get_character.return_value = mock_char_data

    # Test get_character_raw_data (json)
    raw_res = await server.handle_call_tool("get_character_raw_data", {"account": "Player-123", "character": "Hero"})
    assert len(raw_res) == 1
    parsed = json.loads(raw_res[0].text)
    assert parsed["character"]["name"] == "Hero"
    assert len(payload_eq := parsed["equipment"]) == 1
    assert payload_eq[0]["affixes"]["explicit"][0]["mod_id"] == "ItemLocalLife8"

    # Test get_character_raw_data (markdown)
    raw_md_res = await server.handle_call_tool("get_character_raw_data", {"account": "Player-123", "character": "Hero", "format": "markdown"})
    assert len(raw_md_res) == 1
    assert "# Raw Character Data: Hero" in raw_md_res[0].text
    assert "Doom Loom" in raw_md_res[0].text

    # Test get_character_items (json)
    items_res = await server.handle_call_tool("get_character_items", {"account": "Player-123", "character": "Hero"})
    assert len(items_res) == 1
    items_parsed = json.loads(items_res[0].text)
    assert items_parsed["total_items"] == 1
    assert items_parsed["items"][0]["name"] == "Doom Loom"

    # Test get_character_items (markdown)
    items_md_res = await server.handle_call_tool("get_character_items", {"account": "Player-123", "character": "Hero", "format": "markdown"})
    assert len(items_md_res) == 1
    assert "# Items for Hero" in items_md_res[0].text
    assert "Doom Loom" in items_md_res[0].text
