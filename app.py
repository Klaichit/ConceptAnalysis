import streamlit as st
import google.generativeai as genai
import json
import re
from datetime import datetime
from PIL import Image

st.set_page_config(
    page_title="Isometric Asset Breakdown",
    page_icon="🎮",
    layout="wide"
)

st.title("🎮 Isometric Asset Breakdown")
st.caption("Concept Art → Unity Isometric Asset List + Midjourney Prompts")

# ── Prompts ───────────────────────────────────────────────────────────────────

ANALYSIS_PROMPT = """You are a senior Game Art Director and Unity Technical Artist specializing in isometric mobile games.

Your job is to analyze concept art and produce a complete asset breakdown for a Unity isometric game with this grid system:
- Main Grid: isometric tile-based (e.g. 128x64px per tile)
- Sub-grid: each Main Grid tile is subdivided into 4 smaller slots for decoration placement (to avoid repetition)

Analyze the concept art and identify ALL visual zones/areas in the scene. For each zone, list every asset needed to recreate that scene as closely as possible in Unity isometric view.

Return ONLY valid JSON with this exact schema (no markdown, no code blocks):

{
  "scene_summary": "Overall description of the concept art scene",
  "art_style": "Visual style description (be specific: color mood, rendering style, lighting)",
  "global_palette": [
    { "name": "Color name", "hex": "#RRGGBB", "role": "dominant|supporting|accent" }
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
            "style_notes": "Texture hints, stylization notes, important visual details to preserve",
            "midjourney_subject": "Concise visual description for MJ prompt (object + key visual traits, no style words)",
            "animated": false,
            "animation_notes": "What animates and how, or null if static",
            "color_palette": [
              { "name": "Color name", "hex": "#RRGGBB", "role": "primary|secondary|accent|shadow|highlight" }
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
- base_tile: Ground/floor tile (terrain, water surface, sand) — Main Grid
- main_grid_object: Objects that occupy 1+ full grid tiles (large rocks, trees, buildings) — Main Grid
- sub_grid_decoration: Small details in the 4 sub-slots (pebbles, grass tufts, flowers) — Sub-grid
- character: Player, NPC, enemy, creature
- vfx: Particles, animated effects

Be exhaustive. The midjourney_subject field must describe only the visual subject itself."""


def build_mj_prompt(subject: str, art_style: str, category: str, sref_url: str, seed: str, ar: str) -> str:
    """Build a complete Midjourney prompt from parts."""

    iso_view = {
        "base_tile": "isometric tile, top-down 45 degree view, seamless tileable texture, flat ground surface",
        "main_grid_object": "isometric game asset, 45 degree isometric view, single object on transparent background",
        "sub_grid_decoration": "small isometric decoration asset, 45 degree view, tiny detail object, transparent background",
        "character": "isometric character sprite, 45 degree isometric view, full body, transparent background",
        "vfx": "isometric VFX sprite, 45 degree view, particle effect, transparent background",
    }.get(category, "isometric game asset, 45 degree view, transparent background")

    parts = [
        subject,
        iso_view,
        art_style,
        "game art, 2D illustration, clean edges",
        "--ar " + ar,
    ]
    if sref_url.strip():
        parts.append(f"--sref {sref_url.strip()}")
    if seed.strip():
        parts.append(f"--seed {seed.strip()}")

    return ", ".join(p for p in parts[:-2] if p) + " " + " ".join(parts[-2:]) if (sref_url.strip() or seed.strip()) else ", ".join(p for p in parts[:-1] if p) + " " + parts[-1]


def analyze_image(api_key: str, uploaded_file, extra_notes: str = "") -> dict:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    image = Image.open(uploaded_file)

    prompt = ANALYSIS_PROMPT
    if extra_notes:
        prompt += f"\n\nArt Director notes: {extra_notes}"
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
    "base_tile": "🟫", "main_grid_object": "🧱",
    "sub_grid_decoration": "🌿", "character": "🧑", "vfx": "✨",
}
CATEGORY_LABELS = {
    "base_tile": "Base Tile", "main_grid_object": "Main Grid Object",
    "sub_grid_decoration": "Sub-grid Decoration", "character": "Character", "vfx": "VFX",
}
PRIORITY_COLOR = {"high": "🔴", "medium": "🟡", "low": "🟢"}
COMPLEXITY_COLOR = {"simple": "🟢", "medium": "🟡", "complex": "🔴"}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Google Gemini API Key", type="password", help="Free at aistudio.google.com/apikey")
    st.caption("Free: 1,500 requests/day")

    st.divider()
    st.header("🎨 Midjourney Style")
    sref_url = st.text_input("Style Reference URL (--sref)", placeholder="https://cdn.midjourney.com/...")
    mj_seed  = st.text_input("Seed (--seed)", placeholder="e.g. 3849201")
    mj_ar    = st.selectbox("Aspect Ratio (--ar)", ["1:1", "4:3", "3:4", "16:9", "2:3"], index=0)
    st.caption("กรอก seed/sref แล้วกด Generate Prompts ได้เลย")

    st.divider()
    st.header("🔍 Filter")
    filter_categories = st.multiselect(
        "Show categories",
        list(CATEGORY_LABELS.keys()),
        default=list(CATEGORY_LABELS.keys()),
        format_func=lambda x: CATEGORY_ICONS[x] + " " + CATEGORY_LABELS[x],
    )

# ── Main ──────────────────────────────────────────────────────────────────────
tab_analyze, tab_prompts = st.tabs(["📦 Asset Breakdown", "🖼️ Midjourney Prompts"])

with tab_analyze:
    uploaded = st.file_uploader("Drop Concept Art here", type=["png", "jpg", "jpeg", "webp"], label_visibility="collapsed")
    extra_notes = st.text_input("Art Director notes (optional)", placeholder="e.g. Fantasy RPG, warm color tone, hero is a bear")

    if uploaded:
        col_img, col_meta = st.columns([1, 1])
        with col_img:
            st.image(uploaded, use_container_width=True)
        with col_meta:
            st.metric("File", uploaded.name)
            st.metric("Size", f"{uploaded.size / 1024:.1f} KB")

        if not api_key:
            st.warning("Enter Gemini API key in sidebar")

        if st.button("🔍 Analyze Assets", type="primary", disabled=not api_key):
            uploaded.seek(0)
            try:
                result = analyze_image(api_key, uploaded, extra_notes)
                st.session_state["result"] = result
                st.rerun()
            except json.JSONDecodeError as e:
                st.error(f"JSON parse error: {e}")
            except Exception as e:
                st.error(f"Error: {e}")

    if "result" in st.session_state:
        result = st.session_state["result"]
        zones = result.get("zones", [])
        all_assets = [a for z in zones for a in z.get("assets", []) if a.get("category") in filter_categories]

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Zones", len(zones))
        c2.metric("Total Assets", len(all_assets))
        c3.metric("Art Style", result.get("art_style", "—")[:18])
        c4.metric("Global Colors", len(result.get("global_palette", [])))

        st.subheader("Scene Summary")
        st.info(result.get("scene_summary", ""))

        gp = result.get("global_palette", [])
        if gp:
            st.subheader("🎨 Global Color Palette")
            cols = st.columns(min(len(gp), 8))
            for i, color in enumerate(gp):
                with cols[i % len(cols)]:
                    safe = color["hex"] if color["hex"].startswith("#") else f'#{color["hex"]}'
                    st.markdown(f'<div style="background:{safe};height:44px;border-radius:6px;border:1px solid #444;"></div>', unsafe_allow_html=True)
                    st.caption(f"**{color['name']}**\n`{color['hex']}`\n_{color.get('role','')}_")

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
                    st.markdown("---")
                    st.markdown(f"#### {icon} {asset['name']} &nbsp; {pri} &nbsp; `{label}`")
                    col_artist, col_dev = st.columns(2)
                    with col_artist:
                        st.markdown("**🎨 Artist Brief**")
                        ab = asset.get("artist_brief", {})
                        st.write(ab.get("description", ""))
                        if ab.get("style_notes"):
                            st.caption(f"Style: {ab['style_notes']}")
                        if ab.get("reference_notes"):
                            st.caption(f"📌 Ref: {ab['reference_notes']}")
                        st.write("✅ Animated" if ab.get("animated") else "⬜ Static")
                        if ab.get("animation_notes"):
                            st.caption(f"Anim: {ab['animation_notes']}")
                        for c in ab.get("color_palette", []):
                            safe = c["hex"] if c["hex"].startswith("#") else f'#{c["hex"]}'
                            st.markdown(hex_swatch(safe) + f"`{c['hex']}` {c['name']}", unsafe_allow_html=True)
                    with col_dev:
                        st.markdown("**⚙️ Dev Spec (Unity)**")
                        ds = asset.get("dev_spec", {})
                        for k, v in {
                            "Layer": ds.get("layer", "—"),
                            "Tile Size": ds.get("tile_size", "—"),
                            "Pivot": ds.get("pivot", "—"),
                            "Sorting Layer": ds.get("sorting_layer", "—"),
                            "Order in Layer": str(ds.get("order_in_layer", "—")),
                            "Collider": f"{ds.get('collider_type','none')} {'✅' if ds.get('has_collider') else '❌'}",
                            "Static": "✅" if ds.get("static") else "🔄 Dynamic",
                            "Complexity": f"{cmp} {asset.get('complexity','—').capitalize()}",
                        }.items():
                            st.write(f"**{k}:** {v}")
                        if ds.get("notes"):
                            st.caption(f"📝 {ds['notes']}")

        # Export JSON + MD
        st.divider()
        st.subheader("📤 Export")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        col_json, col_md = st.columns(2)
        with col_json:
            st.download_button("⬇️ JSON (Dev)", data=json.dumps(result, indent=2, ensure_ascii=False),
                               file_name=f"asset_breakdown_{ts}.json", mime="application/json")
        with col_md:
            lines = [f"# Isometric Asset Breakdown\n",
                     f"**Scene:** {result.get('scene_summary','')}\n",
                     f"**Art Style:** {result.get('art_style','')}\n", "---\n"]
            for zone in zones:
                lines.append(f"## 📍 {zone['zone_name']}\n{zone.get('description','')}\n")
                for a in zone.get("assets", []):
                    ab = a.get("artist_brief", {})
                    ds = a.get("dev_spec", {})
                    lines += [
                        f"### {CATEGORY_ICONS.get(a.get('category',''),'📦')} {a['name']}",
                        f"- **Category:** {CATEGORY_LABELS.get(a.get('category',''), '')}",
                        f"- **Priority:** {a.get('priority','')} | **Complexity:** {a.get('complexity','')}",
                        f"\n**Artist Brief**",
                        f"- {ab.get('description','')}",
                        f"- Style: {ab.get('style_notes','')}",
                        f"- Animated: {'Yes — ' + (ab.get('animation_notes') or '') if ab.get('animated') else 'No'}",
                        f"\n**Dev Spec**",
                        f"- Tile Size: {ds.get('tile_size','—')} | Pivot: {ds.get('pivot','—')}",
                        f"- Sorting Layer: {ds.get('sorting_layer','—')} / Order: {ds.get('order_in_layer','—')}",
                        f"- Collider: {ds.get('collider_type','none')} | Static: {'Yes' if ds.get('static') else 'No'}",
                        "",
                    ]
            st.download_button("⬇️ Markdown (Artist)", data="\n".join(lines),
                               file_name=f"asset_breakdown_{ts}.md", mime="text/markdown")

# ── Tab 2: Midjourney Prompts ─────────────────────────────────────────────────
with tab_prompts:
    if "result" not in st.session_state:
        st.info("Analyze a concept art first in the Asset Breakdown tab.")
    else:
        result = st.session_state["result"]
        art_style = result.get("art_style", "stylized 2D isometric game art")
        zones = result.get("zones", [])
        all_assets = [a for z in zones for a in z.get("assets", []) if a.get("category") in filter_categories]

        st.subheader("🖼️ Midjourney Prompts")

        # Style config recap
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.info(f"**sref:** {sref_url if sref_url.strip() else '_(not set)_'}")
        col_s2.info(f"**seed:** {mj_seed if mj_seed.strip() else '_(not set)_'}")
        col_s3.info(f"**ar:** {mj_ar}")

        if not sref_url.strip() and not mj_seed.strip():
            st.warning("Enter --sref URL and/or --seed in the sidebar to generate complete prompts.")

        st.caption(f"Art style detected: _{art_style}_")
        st.divider()

        # Build all prompts
        prompts_export = []
        for zone in zones:
            zone_assets = [a for a in zone.get("assets", []) if a.get("category") in filter_categories]
            if not zone_assets:
                continue

            st.markdown(f"### 📍 {zone['zone_name']}")
            for asset in zone_assets:
                cat = asset.get("category", "")
                icon = CATEGORY_ICONS.get(cat, "📦")
                label = CATEGORY_LABELS.get(cat, cat)
                ab = asset.get("artist_brief", {})
                subject = ab.get("midjourney_subject", ab.get("description", asset["name"]))

                prompt = build_mj_prompt(subject, art_style, cat, sref_url, mj_seed, mj_ar)
                prompts_export.append({"asset": asset["name"], "category": label, "zone": zone["zone_name"], "prompt": prompt})

                with st.container():
                    st.markdown(f"**{icon} {asset['name']}** `{label}`")
                    st.code(prompt, language=None)
                    st.caption(f"Subject: _{subject}_")
                    st.markdown("")

        # Export all prompts
        st.divider()
        st.subheader("📤 Export Prompts")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        col_pj, col_pm = st.columns(2)
        with col_pj:
            st.download_button(
                "⬇️ Download JSON",
                data=json.dumps(prompts_export, indent=2, ensure_ascii=False),
                file_name=f"mj_prompts_{ts}.json",
                mime="application/json",
            )
        with col_pm:
            md_lines = [f"# Midjourney Prompts\n",
                        f"sref: {sref_url} | seed: {mj_seed} | ar: {mj_ar}\n", "---\n"]
            for p in prompts_export:
                md_lines += [f"## {p['asset']} ({p['category']})", f"Zone: {p['zone']}", f"```", p["prompt"], f"```", ""]
            st.download_button(
                "⬇️ Download Markdown",
                data="\n".join(md_lines),
                file_name=f"mj_prompts_{ts}.md",
                mime="text/markdown",
            )
