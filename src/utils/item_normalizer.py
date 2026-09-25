"""
Item Normalizer and Extractor for Path of Exile 2 Character Data.

Normalizes raw poe.ninja and official GGG item models to expose full
affixes, mod IDs, roll magnitudes, properties, requirements, sockets,
and socketed runes/gems.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


# Standard mapping of slot numbers to inventory names if inventoryId is missing
SLOT_ID_TO_NAME: Dict[int, str] = {
    1: "Helm",
    2: "Gloves",
    3: "BodyArmour",
    4: "Amulet",
    5: "Boots",
    6: "Offhand",
    7: "Weapon",
    8: "Ring",
    9: "Ring2",
    11: "Belt",
    12: "Jewel",
    15: "Weapon2",
    16: "Offhand2",
}


def normalize_raw_item(item_obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize an item dictionary from poe.ninja charModel or PoB into a
    structured dictionary containing full affix breakdowns, mod IDs, and roll stats.
    """
    if not isinstance(item_obj, dict):
        return {}

    # charModel wraps item under itemData + itemSlot
    if "itemData" in item_obj:
        d = item_obj.get("itemData") or {}
        slot_num = item_obj.get("itemSlot")
    else:
        d = item_obj
        slot_num = item_obj.get("slot_id") or item_obj.get("itemSlot")

    inv_id = d.get("inventoryId") or (SLOT_ID_TO_NAME.get(slot_num) if slot_num else None) or d.get("slot") or "Unknown"

    name = d.get("name", "")
    type_line = d.get("typeLine") or d.get("type_line", "")
    base_type = d.get("baseType") or d.get("base_type") or type_line

    rarity = d.get("rarity") if d.get("rarity") is not None else (d.get("frameTypeId") if d.get("frameTypeId") is not None else d.get("frameType"))
    if isinstance(rarity, int):
        rarity_map = {0: "Normal", 1: "Magic", 2: "Rare", 3: "Unique", 4: "Gem", 5: "Currency"}
        rarity = rarity_map.get(rarity, "Unknown")
    elif not rarity:
        rarity = "Normal"

    # Properties
    properties = []
    raw_props = d.get("properties") or []
    if isinstance(raw_props, list):
        for p in raw_props:
            if not isinstance(p, dict):
                continue
            p_name = p.get("name", "")
            vals = [v[0] for v in p.get("values", []) if isinstance(v, (list, tuple)) and len(v) > 0]
            val_str = ", ".join(str(v) for v in vals) if vals else ""
            properties.append({"name": p_name, "value": val_str})

    # Requirements
    requirements: Dict[str, Any] = {}
    raw_reqs = d.get("requirements") or []
    if isinstance(raw_reqs, list):
        for r in raw_reqs:
            if not isinstance(r, dict):
                continue
            r_name = r.get("name", "")
            vals = [v[0] for v in r.get("values", []) if isinstance(v, (list, tuple)) and len(v) > 0]
            if vals:
                val = vals[0]
                if isinstance(val, str) and val.isdigit():
                    val = int(val)
                requirements[r_name.lower()] = val
                requirements[r_name] = val
    elif isinstance(raw_reqs, dict):
        requirements = raw_reqs

    # Mod breakdown
    raw_mods_dict = d.get("mods") or {}
    affixes: Dict[str, List[Dict[str, Any]]] = {
        "implicit": [],
        "explicit": [],
        "crafted": [],
        "enchant": [],
        "rune": [],
        "desecrated": [],
    }

    # Extract all mod categories
    for category in ["implicit", "explicit", "crafted", "enchant", "rune", "desecrated"]:
        text_mods = d.get(f"{category}Mods") or []
        cat_mods_list = raw_mods_dict.get(category) or [] if isinstance(raw_mods_dict, dict) else []

        # If both text and structured mods exist, pair them up where possible
        combined_category: List[Dict[str, Any]] = []
        for i, text in enumerate(text_mods):
            mod_meta = cat_mods_list[i] if i < len(cat_mods_list) and isinstance(cat_mods_list[i], dict) else {}
            combined_category.append({
                "text": text,
                "mod_id": mod_meta.get("id"),
                "stats": mod_meta.get("stats", {}),
            })

        # If there are more structured mods than text strings (or text was empty)
        if len(cat_mods_list) > len(combined_category):
            for mod_meta in cat_mods_list[len(combined_category):]:
                if isinstance(mod_meta, dict):
                    combined_category.append({
                        "text": None,
                        "mod_id": mod_meta.get("id"),
                        "stats": mod_meta.get("stats", {}),
                    })

        affixes[category] = combined_category

    # Sockets & socketed items
    sockets = d.get("sockets") or []
    socketed_items = []
    for s in d.get("socketedItems") or []:
        if isinstance(s, dict):
            s_name = s.get("name") or s.get("typeLine") or s.get("baseType")
            socketed_items.append({
                "name": s_name,
                "base_type": s.get("baseType"),
                "type_line": s.get("typeLine"),
                "frame_type": s.get("frameTypeId") or s.get("frameType"),
                "explicit_mods": s.get("explicitMods") or [],
                "bonded_mods": s.get("bondedMods") or [],
                "descr": s.get("descrText"),
            })

    # Quality
    quality = d.get("qualityProperty")
    if quality is None:
        for prop in properties:
            if "quality" in prop["name"].lower():
                try:
                    quality = int(prop["value"].replace("+", "").replace("%", ""))
                except Exception:
                    pass

    # Weapon set tagging
    weapon_set: Optional[int] = None
    if inv_id in ("Weapon2", "Offhand2") or slot_num in (15, 16):
        weapon_set = 2
    elif inv_id in ("Weapon", "Offhand") or slot_num in (6, 7):
        weapon_set = 1

    # Text mods representation for backwards compatibility with legacy formatters
    legacy_mods = {
        "implicit": [m["text"] for m in affixes["implicit"] if m.get("text")],
        "explicit": [
            m["text"] for m in (affixes["explicit"] + affixes["desecrated"] + affixes["crafted"]) if m.get("text")
        ],
    }

    return {
        "slot": inv_id,
        "slot_id": slot_num,
        "weapon_set": weapon_set,
        "name": name,
        "type_line": type_line,
        "base_type": base_type,
        "rarity": rarity,
        "item_level": d.get("ilvl"),
        "corrupted": d.get("corrupted", False),
        "desecrated": d.get("desecrated", False),
        "quality": quality,
        "properties": properties,
        "requirements": requirements,
        "mods": legacy_mods,
        "affixes": affixes,
        "sockets": sockets,
        "socketed_items": socketed_items,
        "raw_item_data": d,
    }


def extract_character_items(
    character_data: Dict[str, Any],
    slot_filter: Optional[str] = None,
    include_flasks: bool = True,
    include_jewels: bool = True,
) -> List[Dict[str, Any]]:
    """
    Extract and normalize all items from a character data dictionary.
    Supports filtering by slot and optional flask/jewel inclusion.
    """
    raw_data = character_data.get("raw_data") or {}
    char_model = raw_data.get("charModel") or raw_data if isinstance(raw_data, dict) else {}

    raw_items = (
        character_data.get("raw_items")
        or char_model.get("items")
        or character_data.get("items")
        or []
    )
    raw_flasks = (
        character_data.get("raw_flasks")
        or char_model.get("flasks")
        or character_data.get("flasks")
        or []
    )
    raw_jewels = (
        character_data.get("raw_jewels")
        or char_model.get("jewels")
        or character_data.get("jewels")
        or []
    )

    all_items: List[Dict[str, Any]] = []

    # Equipment items
    for item in raw_items:
        normalized = normalize_raw_item(item)
        if normalized:
            all_items.append(normalized)

    # Flasks
    if include_flasks:
        for flask in raw_flasks:
            norm_flask = normalize_raw_item(flask)
            if norm_flask:
                if not norm_flask.get("slot") or norm_flask["slot"] == "Unknown":
                    norm_flask["slot"] = "Flask"
                all_items.append(norm_flask)

    # Jewels
    if include_jewels:
        for jewel in raw_jewels:
            norm_jewel = normalize_raw_item(jewel)
            if norm_jewel:
                if not norm_jewel.get("slot") or norm_jewel["slot"] == "Unknown":
                    norm_jewel["slot"] = "Jewel"
                all_items.append(norm_jewel)

    # Apply slot filter if requested
    if slot_filter and slot_filter.lower() != "all":
        target = slot_filter.strip().lower()
        filtered = []
        for item in all_items:
            slot_name = str(item.get("slot", "")).lower()
            if target in slot_name or slot_name in target:
                filtered.append(item)
        return filtered

    return all_items


def extract_raw_character_payload(
    character_data: Dict[str, Any],
    section: str = "all",
    include_raw_model: bool = False,
) -> Dict[str, Any]:
    """
    Construct a complete, un-truncated raw character payload.
    """
    raw_data = character_data.get("raw_data") or {}
    char_model = raw_data.get("charModel") or raw_data if isinstance(raw_data, dict) else {}

    char_info = {
        "name": character_data.get("name") or char_model.get("name"),
        "account": character_data.get("account") or char_model.get("account"),
        "level": character_data.get("level") or char_model.get("level"),
        "class": character_data.get("class") or char_model.get("class"),
        "ascendancy": character_data.get("ascendancy") or char_model.get("ascendancy"),
        "league": character_data.get("league") or char_model.get("league"),
        "experience": character_data.get("experience") or char_model.get("experience"),
    }

    equipment = extract_character_items(
        character_data, include_flasks=False, include_jewels=False
    )
    flasks = extract_character_items(
        character_data, slot_filter="flask", include_flasks=True, include_jewels=False
    )
    jewels = extract_character_items(
        character_data, slot_filter="jewel", include_flasks=False, include_jewels=True
    )

    passive_tree_data = {
        "total_nodes": len(character_data.get("passive_tree") or char_model.get("passiveSelection") or []),
        "allocated_node_ids": character_data.get("passive_tree") or char_model.get("passiveSelection") or [],
        "weapon_set_1_node_ids": char_model.get("passiveSelectionSet1") or [],
        "weapon_set_2_node_ids": char_model.get("passiveSelectionSet2") or [],
        "keystones": character_data.get("keystones") or char_model.get("keystones") or [],
        "passive_counts": char_model.get("passiveCounts") or {},
    }

    skills_data = character_data.get("skills") or char_model.get("skills") or []
    stats_data = character_data.get("stats") or char_model.get("defensiveStats") or {}

    section_lower = section.lower().strip()
    if section_lower in ("items", "equipment", "gear"):
        return {
            "character": char_info,
            "equipment": equipment,
            "flasks": flasks,
            "jewels": jewels,
        }
    elif section_lower == "flasks":
        return {"character": char_info, "flasks": flasks}
    elif section_lower == "jewels":
        return {"character": char_info, "jewels": jewels}
    elif section_lower in ("passives", "passive_tree", "tree"):
        return {"character": char_info, "passive_tree": passive_tree_data}
    elif section_lower == "skills":
        return {"character": char_info, "skills": skills_data}
    elif section_lower in ("stats", "defenses"):
        return {"character": char_info, "defensive_stats": stats_data}

    # "all"
    payload: Dict[str, Any] = {
        "character": char_info,
        "equipment": equipment,
        "flasks": flasks,
        "jewels": jewels,
        "passive_tree": passive_tree_data,
        "skills": skills_data,
        "defensive_stats": stats_data,
    }
    if include_raw_model:
        payload["raw_model"] = char_model
    return payload


def format_items_markdown(items: List[Dict[str, Any]]) -> str:
    """
    Format a list of normalized items into detailed human-readable Markdown
    displaying all affixes, mod IDs, and roll magnitudes.
    """
    if not items:
        return "No items found."

    lines: List[str] = []
    for it in items:
        slot = it.get("slot") or "Unknown Slot"
        name = it.get("name")
        type_line = it.get("type_line") or it.get("base_type") or ""
        display_name = f"{name} ({type_line})" if name and name != type_line else (name or type_line or "Item")
        rarity = it.get("rarity", "Normal")
        ilvl = f"ilvl {it['item_level']}" if it.get("item_level") else ""
        corrupted = " [CORRUPTED]" if it.get("corrupted") else ""
        desecrated = " [DESECRATED]" if it.get("desecrated") else ""

        header = f"### {slot}: {display_name} [{rarity}{f', {ilvl}' if ilvl else ''}]{corrupted}{desecrated}"
        lines.append(header)

        # Properties
        if it.get("properties"):
            props_str = " | ".join(f"{p['name']}: {p['value']}" if p['value'] else p['name'] for p in it["properties"])
            lines.append(f"- **Properties:** {props_str}")

        # Requirements
        if it.get("requirements"):
            reqs_str = ", ".join(f"{k.capitalize()}: {v}" for k, v in it["requirements"].items())
            lines.append(f"- **Requirements:** {reqs_str}")

        # Sockets & socketed items
        if it.get("socketed_items"):
            sockets_str = "; ".join(f"{s['name']} ({s.get('base_type', '')})" for s in it["socketed_items"])
            lines.append(f"- **Socketed:** {sockets_str}")

        # Affixes
        affixes = it.get("affixes") or {}
        for category, cat_title in [
            ("implicit", "Implicit Mods"),
            ("explicit", "Explicit Mods"),
            ("crafted", "Crafted Mods"),
            ("enchant", "Enchantment Mods"),
            ("rune", "Rune Mods"),
            ("desecrated", "Desecrated Mods"),
        ]:
            mods_in_cat = affixes.get(category) or []
            if mods_in_cat:
                lines.append(f"- **{cat_title}:**")
                for mod in mods_in_cat:
                    mod_text = mod.get("text")
                    mod_id = mod.get("mod_id")
                    stats = mod.get("stats") or {}
                    stats_str = f" `{json.dumps(stats)}`" if stats else ""
                    id_str = f" *[{mod_id}]*" if mod_id else ""
                    if mod_text:
                        lines.append(f"  - {mod_text}{id_str}{stats_str}")
                    elif mod_id or stats:
                        lines.append(f"  - {id_str}{stats_str}")

        lines.append("")

    return "\n".join(lines)
