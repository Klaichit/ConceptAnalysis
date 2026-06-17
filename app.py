import streamlit as st
import google.generativeai as genai
import json
import re
from pathlib import Path
from datetime import datetime
from PIL import Image

st.set_page_config(
    page_title="Isometric Asset Breakdown",
    page_icon="🎮",
    layout="wide"
)

st.title("🎮 Isometric Asset Breakdown")
st.caption("Concept Art → Unity Isometric Asset List (Artist Brief + Dev Spec)")

SYSTEM_PROMPT = """You are a senior Game Art Director and Unity Technical Artist specializing in isometric mobile games.

Your job is to analyze concept art and produce a complete asset breakdown for a Unity isometric game with this grid system:
- Main Grid: isometric tile-based (e.g. 128x64px per tile)
- Sub-grid: each Main Grid tile is subdivided into 4 smaller slots for decoration placement (to avoid repetition)

Analyze the concept art and identify ALL visual zones/areas in the scene. For each zone, list every asset needed to recreate that scene as closely as possible in Unity isometric view.

Return ONLY valid JSON with this exact schema (no markdown, no code blocks):

{
  "scene_summary": "Overall description of the concept art scene",
  "art_style": "Visual style description",
  "global_palette": [
    {
      "name": "Color name",
      "hex": "#RRGGBB",
      "role": "dominant|supporting|accent"
    }
  ],
  "zones": [
    {
      "zone_id": "zone_01",
      "zone_name": "Zone name (e.g. River Zone, Dry Land Zone)",
      "description": "What this zone looks like",
      "assets": [
        {
          "id": "asset_01",
          "name": "Asset name",
          "category": "base_tile|main_grid_object|sub_grid_decoration|character|vfx",
          "artist_brief": {
            "description": "What this asset looks like, visual details",
            "style_notes": "Texture hints, stylization notes, important visual details",
            "animated": true,
            "animation_notes": "What animates and how, or null if static",
            "color_palette": [
              {
                "name": "Color name",
                "hex": "#RRGGBB",
                "role": "primary|secondary|accent|shadow|highlight"
              }
            ],
            "reference_notes": "Which part of the concept art to reference"
          },
          "dev_spec": {
            "layer": "base_tile|main_grid_object|sub_grid_decoration|character|vfx",
            "tile_size": "1x1|2x1|1x2|2x2|etc",
            "pivot": "bottom-center|center|bottom-left",
            "sorting_layer": "Ground|Decoration|Object|Character|VFX",
            "order_in_layer": 0,
            "has_collider": true,
            "collider_type": "box|polygon|none",
            "static": true,
            "notes": "Unity implementation notes"
          },
          "priority": "high|medium|low",
          "complexity": "simple|medium|complex"
        }
      ]
    }
  ]
}

Category rules:
- base_tile: The ground/floor tile itself (terrain, water surface, sand) — goes on Main Grid
- main_grid_object: Objects that occupy 1+ full grid tiles (large rocks, trees, buildings) — placed on Main Grid
- sub_grid_decoration: Small details placed in the 4 sub-slots of a tile (pebbles, grass tufts, small flowers) — placed on Sub-grid
- character: Player, NPC, enemy, creature
- vfx: Particles, animated effects (water ripple, wind, sparkle)

Be exhaustive — list every distinct visual element needed to recreate the scene."""

def analyze_image(api_key: str, uploaded_file, extra_notes: str = "") -> dict:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    image = Image.open(uploaded_file)

    prompt = SYSTEM_PROMPT
    if extra_notes:
        prompt += f"\n\nAdditional context from art director: {extra_notes}"
    prompt += "\n\nAnalyze this concept art and return the full isometric asset breakdown as JSON."

    with st.spinner("Analyzing concept art..."):
        response = model.generate_content([prompt, image])

    cleaned = re.sub(r"^```(?:json)?\s*", "", response.text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)

def hex_swatch(hex_color: str, size: int = 20) -> str:
    safe = hex_color if hex_color.startswith("#") else f"#{hex_color}"
    return f'<span style="display:inline-block;width:{size}px;height:{size}px;background:{safe};border:1px solid #555;border-radius:3px;vertical-align:middle;margin-right:5px;"></span>'

CATEGORY_ICONS = {
    "base_tile": "🟫",
    "main_grid_object": "🧱",
    "sub_grid_decoration": "🌿",
    "character": "🧑",
    "vfx": "✨",
}

CATEGORY_LABELS = {
    "base_tile": "Base Tile",
    "main_grid_object": "Main Grid Object",
    "sub_grid_decoration": "Sub-grid Decoration",
    "character": "Character",
    "vfx": "VFX",
}

PRIORITY_COLOR = {"high": "🔴", "medium": "🟡", "low": "🟢"}
COMPLEXITY_COLOR = {"simple": "🟢", "medium": "🟡", "complex": "🔴"}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        help="Free at aistudio.google.com/apikey"
    )
    st.caption("Free: 1,500 requests/day")
    st.divider()
    st.subheader("Filter")
    filter_categories = st.multiselect(
        "Show categories",
        list(CATEGORY_LABELS.keys()),
        default=list(CATEGORY_LABELS.keys()),
        format_func=lambda x: CATEGORY_ICONS[x] + " " + CATEGORY_LABELS[x],
    )
    st.divider()
    st.caption("Model: gemini-2.0-flash")

# ── Main ──────────────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Drop Concept Art here",
    type=["png", "jpg", "jpeg", "webp"],
    label_visibility="collapsed",
)
extra_notes = st.text_input(
    "Art Director notes (optional)",
    placeholder="e.g. Fantasy RPG, warm color tone, hero is a bear"
)

if uploaded:
    col_img, col_meta = st.columns([1, 1])
    with col_img:
        st.image(uploaded, use_container_width=True)
    with col_meta:
        st.metric("File", uploaded.name)
        st.metric("Size", f"{uploaded.size / 1024:.1f} KB")

    if not api_key:
        st.warning("Enter Gemini API key in sidebar — free at aistudio.google.com/apikey")

    if st.button("🔍 Analyze Assets", type="primary", disabled=not api_key):
        uploaded.seek(0)
        try:
            result = analyze_image(api_key, uploaded, extra_notes)
            st.session_state["result"] = result
        except json.JSONDecodeError as e:
            st.error(f"JSON parse error: {e}")
        except Exception as e:
            st.error(f"Error: {e}")

# ── Results ───────────────────────────────────────────────────────────────────
if "result" in st.session_state:
    result: dict = st.session_state["result"]
    zones = result.get("zones", [])

    all_assets = [a for z in zones for a in z.get("assets", []) if a.get("category") in filter_categories]

    st.divider()

    # Stats
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Zones", len(zones))
    c2.metric("Total Assets", len(all_assets))
    c3.metric("Art Style", result.get("art_style", "—")[:18])
    c4.metric("Global Colors", len(result.get("global_palette", [])))

    st.subheader("Scene Summary")
    st.info(result.get("scene_summary", ""))

    # Global Palette
    gp = result.get("global_palette", [])
    if gp:
        st.subheader("🎨 Global Color Palette")
        cols = st.columns(min(len(gp), 8))
        for i, color in enumerate(gp):
            with cols[i % len(cols)]:
                safe = color["hex"] if color["hex"].startswith("#") else f'#{color["hex"]}'
                st.markdown(f'<div style="background:{safe};height:44px;border-radius:6px;border:1px solid #444;"></div>', unsafe_allow_html=True)
                st.caption(f"**{color['name']}**\n`{color['hex']}`\n_{color.get('role','')}_")

    # Zone breakdown
    st.subheader("📦 Asset Breakdown by Zone")

    for zone in zones:
        zone_assets = [a for a in zone.get("assets", []) if a.get("category") in filter_categories]
        if not zone_assets:
            continue

        with st.expander(f"📍 **{zone['zone_name']}** — {len(zone_assets)} assets", expanded=True):
            st.caption(zone.get("description", ""))

            for asset in zone_assets:
                cat = asset.get("category", "")
                icon = CATEGORY_ICONS.get(cat, "📦")
                label = CATEGORY_LABELS.get(cat, cat)
                pri = PRIORITY_COLOR.get(asset.get("priority", "medium"), "🟡")
                cmp = COMPLEXITY_COLOR.get(asset.get("complexity", "medium"), "🟡")

                st.markdown(f"---")
                st.markdown(f"#### {icon} {asset['name']} &nbsp; {pri} &nbsp; `{label}`")

                col_artist, col_dev = st.columns(2)

                # Artist Brief
                with col_artist:
                    st.markdown("**🎨 Artist Brief**")
                    ab = asset.get("artist_brief", {})
                    st.write(ab.get("description", ""))
                    if ab.get("style_notes"):
                        st.caption(f"Style: {ab['style_notes']}")
                    if ab.get("reference_notes"):
                        st.caption(f"📌 Ref: {ab['reference_notes']}")

                    anim = "✅ Animated" if ab.get("animated") else "⬜ Static"
                    st.write(anim)
                    if ab.get("animation_notes"):
                        st.caption(f"Anim: {ab['animation_notes']}")

                    palette = ab.get("color_palette", [])
                    if palette:
                        st.write("Colors:")
                        for c in palette:
                            safe = c["hex"] if c["hex"].startswith("#") else f'#{c["hex"]}'
                            st.markdown(hex_swatch(safe) + f"`{c['hex']}` {c['name']} _{c.get('role','')}_", unsafe_allow_html=True)

                # Dev Spec
                with col_dev:
                    st.markdown("**⚙️ Dev Spec (Unity)**")
                    ds = asset.get("dev_spec", {})

                    rows = {
                        "Layer": ds.get("layer", "—"),
                        "Tile Size": ds.get("tile_size", "—"),
                        "Pivot": ds.get("pivot", "—"),
                        "Sorting Layer": ds.get("sorting_layer", "—"),
                        "Order in Layer": str(ds.get("order_in_layer", "—")),
                        "Collider": f"{ds.get('collider_type','none')} {'✅' if ds.get('has_collider') else '❌'}",
                        "Static": "✅" if ds.get("static") else "🔄 Dynamic",
                        "Complexity": f"{cmp} {asset.get('complexity','—').capitalize()}",
                        "Priority": f"{pri} {asset.get('priority','—').capitalize()}",
                    }
                    for k, v in rows.items():
                        st.write(f"**{k}:** {v}")

                    if ds.get("notes"):
                        st.caption(f"📝 {ds['notes']}")

    # Export
    st.divider()
    st.subheader("📤 Export")

    col_json, col_md = st.columns(2)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    with col_json:
        st.download_button(
            "⬇️ Download JSON (Dev)",
            data=json.dumps(result, indent=2, ensure_ascii=False),
            file_name=f"asset_breakdown_{ts}.json",
            mime="application/json",
        )

    with col_md:
        lines = [
            f"# Isometric Asset Breakdown\n",
            f"**Scene:** {result.get('scene_summary','')}\n",
            f"**Art Style:** {result.get('art_style','')}\n",
            "---\n",
        ]
        for zone in zones:
            lines.append(f"## 📍 {zone['zone_name']}")
            lines.append(f"{zone.get('description','')}\n")
            for a in zone.get("assets", []):
                ab = a.get("artist_brief", {})
                ds = a.get("dev_spec", {})
                lines.append(f"### {CATEGORY_ICONS.get(a.get('category',''),'📦')} {a['name']}")
                lines.append(f"- **Category:** {CATEGORY_LABELS.get(a.get('category',''), a.get('category',''))}")
                lines.append(f"- **Priority:** {a.get('priority','')} | **Complexity:** {a.get('complexity','')}")
                lines.append(f"\n**Artist Brief**")
                lines.append(f"- {ab.get('description','')}")
                lines.append(f"- Style: {ab.get('style_notes','')}")
                lines.append(f"- Animated: {'Yes — ' + ab.get('animation_notes','') if ab.get('animated') else 'No'}")
                colors = ", ".join(f"{c['hex']} {c['name']}" for c in ab.get("color_palette", []))
                if colors:
                    lines.append(f"- Colors: {colors}")
                lines.append(f"\n**Dev Spec**")
                lines.append(f"- Tile Size: {ds.get('tile_size','—')} | Pivot: {ds.get('pivot','—')}")
                lines.append(f"- Sorting Layer: {ds.get('sorting_layer','—')} / Order: {ds.get('order_in_layer','—')}")
                lines.append(f"- Collider: {ds.get('collider_type','none')} | Static: {'Yes' if ds.get('static') else 'No'}")
                if ds.get("notes"):
                    lines.append(f"- Notes: {ds['notes']}")
                lines.append("")

        st.download_button(
            "⬇️ Download Markdown (Artist)",
            data="\n".join(lines),
            file_name=f"asset_breakdown_{ts}.md",
            mime="text/markdown",
        )
