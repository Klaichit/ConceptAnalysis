import streamlit as st
import google.generativeai as genai
import json
import re
from pathlib import Path
from datetime import datetime
from PIL import Image
import io

st.set_page_config(
    page_title="Concept Art Asset Analyzer",
    page_icon="🎨",
    layout="wide"
)

st.title("🎨 Concept Art Asset Analyzer")
st.caption("Upload concept art → Gemini Vision breaks down game assets, tags, and color palettes")

SYSTEM_PROMPT = """You are an expert Game Art Director and Technical Artist specializing in breaking down concept art into actionable game development assets.

When analyzing concept art, you MUST return a structured JSON response with this exact schema:

{
  "summary": "Brief overall description of the concept art",
  "assets": [
    {
      "id": "unique_id",
      "name": "Asset Name",
      "category": "character|prop|environment|ui_element|vfx",
      "description": "What this asset is",
      "tags": ["tag1", "tag2", "..."],
      "priority": "high|medium|low",
      "complexity": "simple|medium|complex",
      "color_palette": [
        {
          "name": "Color Name",
          "hex": "#RRGGBB",
          "role": "primary|secondary|accent|shadow|highlight",
          "usage": "Where/how this color is used on the asset"
        }
      ],
      "notes": "Technical notes for implementation"
    }
  ],
  "global_palette": [
    {
      "name": "Color Name",
      "hex": "#RRGGBB",
      "role": "dominant|supporting|accent",
      "usage": "Overall usage in the scene"
    }
  ],
  "art_style": "Description of art style (e.g., stylized, realistic, pixel art, etc.)",
  "recommended_pipeline": ["step1", "step2", "..."]
}

Category definitions:
- character: Player characters, NPCs, enemies, creatures
- prop: Interactive or decorative objects, weapons, items
- environment: Terrain, architecture, backgrounds, sky, ground
- ui_element: HUD components, icons, buttons, overlays
- vfx: Particles, magic effects, explosions, weather, lighting fx

Be thorough — identify every distinct asset visible. For colors, extract the actual colors visible in the art (not generic descriptions). Return ONLY valid JSON, no markdown code blocks."""

def analyze_image(api_key: str, uploaded_file, extra_notes: str = "") -> dict:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    image = Image.open(uploaded_file)

    prompt = SYSTEM_PROMPT
    if extra_notes:
        prompt += f"\n\nAdditional context: {extra_notes}"
    prompt += "\n\nAnalyze this concept art and return the full asset breakdown as JSON."

    with st.spinner("Gemini is analyzing the concept art..."):
        response = model.generate_content([prompt, image])

    full_text = response.text
    cleaned = re.sub(r"^```(?:json)?\s*", "", full_text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)

def hex_swatch(hex_color: str, size: int = 24) -> str:
    safe = hex_color if hex_color.startswith("#") else f"#{hex_color}"
    return f'<span style="display:inline-block;width:{size}px;height:{size}px;background:{safe};border:1px solid #555;border-radius:3px;vertical-align:middle;margin-right:6px;"></span>'

CATEGORY_ICONS = {
    "character": "🧑",
    "prop": "🗡️",
    "environment": "🌿",
    "ui_element": "🖼️",
    "vfx": "✨",
}

PRIORITY_COLORS = {"high": "🔴", "medium": "🟡", "low": "🟢"}

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        help="Get yours free at aistudio.google.com/apikey"
    )
    st.caption("Free tier: 15 requests/min, 1,500/day")
    st.divider()
    st.subheader("Filter Results")
    filter_categories = st.multiselect(
        "Show categories",
        ["character", "prop", "environment", "ui_element", "vfx"],
        default=["character", "prop", "environment", "ui_element", "vfx"],
    )
    st.divider()
    st.caption("Model: gemini-2.0-flash (free)")

# ── Main Area ─────────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Drop your concept art here",
    type=["png", "jpg", "jpeg", "webp"],
    label_visibility="collapsed",
)
extra_notes = st.text_input(
    "Optional context (game genre, art style direction, etc.)",
    placeholder="e.g. Fantasy RPG, stylized low-poly"
)

if uploaded:
    col_img, col_info = st.columns([1, 1])
    with col_img:
        st.image(uploaded, caption=uploaded.name, use_container_width=True)
    with col_info:
        st.metric("File", uploaded.name)
        st.metric("Size", f"{uploaded.size / 1024:.1f} KB")

    analyze_btn = st.button("🔍 Analyze Assets", type="primary", disabled=not api_key)

    if not api_key:
        st.warning("Enter your Gemini API key in the sidebar. Get it free at aistudio.google.com/apikey")

    if analyze_btn and api_key:
        uploaded.seek(0)
        try:
            result = analyze_image(api_key, uploaded, extra_notes)
            st.session_state["result"] = result
        except json.JSONDecodeError as e:
            st.error(f"Failed to parse Gemini's response as JSON: {e}")
        except Exception as e:
            st.error(f"Error: {e}")

# ── Results ───────────────────────────────────────────────────────────────────
if "result" in st.session_state:
    result: dict = st.session_state["result"]
    assets = [a for a in result.get("assets", []) if a.get("category") in filter_categories]

    st.divider()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Assets", len(result.get("assets", [])))
    col2.metric("Filtered", len(assets))
    col3.metric("Art Style", result.get("art_style", "—")[:20])
    col4.metric("Global Colors", len(result.get("global_palette", [])))

    st.subheader("Summary")
    st.info(result.get("summary", ""))

    if result.get("global_palette"):
        st.subheader("🎨 Global Color Palette")
        cols = st.columns(min(len(result["global_palette"]), 8))
        for i, color in enumerate(result["global_palette"]):
            with cols[i % len(cols)]:
                safe_hex = color["hex"] if color["hex"].startswith("#") else f'#{color["hex"]}'
                st.markdown(
                    f'<div style="background:{safe_hex};height:50px;border-radius:6px;border:1px solid #444;"></div>',
                    unsafe_allow_html=True,
                )
                st.caption(f"**{color['name']}**  \n`{color['hex']}`  \n_{color.get('role','')}_")

    st.subheader("📦 Asset Breakdown")

    tab_all, tab_char, tab_prop, tab_env, tab_ui, tab_vfx = st.tabs(
        ["All", "Characters", "Props", "Environment", "UI", "VFX"]
    )

    def render_asset_cards(asset_list):
        for asset in asset_list:
            icon = CATEGORY_ICONS.get(asset.get("category", ""), "📦")
            priority_dot = PRIORITY_COLORS.get(asset.get("priority", "medium"), "🟡")
            with st.expander(f"{icon} {asset['name']}  {priority_dot} `{asset.get('category','?')}`"):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.write(f"**Description:** {asset.get('description','')}")
                    tags = asset.get("tags", [])
                    if tags:
                        st.write("**Tags:** " + "  ".join(f"`{t}`" for t in tags))
                    if asset.get("notes"):
                        st.caption(f"📝 {asset['notes']}")
                with c2:
                    st.write(f"**Priority:** {asset.get('priority','—').capitalize()}")
                    st.write(f"**Complexity:** {asset.get('complexity','—').capitalize()}")
                    palette = asset.get("color_palette", [])
                    if palette:
                        st.write("**Colors:**")
                        for c in palette:
                            safe = c["hex"] if c["hex"].startswith("#") else f'#{c["hex"]}'
                            st.markdown(
                                hex_swatch(safe) + f"`{c['hex']}` {c['name']}",
                                unsafe_allow_html=True,
                            )

    cat_map = {
        tab_char: "character",
        tab_prop: "prop",
        tab_env: "environment",
        tab_ui: "ui_element",
        tab_vfx: "vfx",
    }
    with tab_all:
        render_asset_cards(assets)
    for tab, cat in cat_map.items():
        with tab:
            render_asset_cards([a for a in assets if a.get("category") == cat])

    pipeline = result.get("recommended_pipeline", [])
    if pipeline:
        st.subheader("🔧 Recommended Production Pipeline")
        for i, step in enumerate(pipeline, 1):
            st.write(f"{i}. {step}")

    st.divider()
    st.subheader("📤 Export")
    col_json, col_md = st.columns(2)

    with col_json:
        json_str = json.dumps(result, indent=2, ensure_ascii=False)
        st.download_button(
            "⬇️ Download JSON",
            data=json_str,
            file_name=f"asset_breakdown_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )

    with col_md:
        lines = [f"# Asset Breakdown\n", f"**Summary:** {result.get('summary','')}\n",
                 f"**Art Style:** {result.get('art_style','')}\n", "---\n"]
        for a in result.get("assets", []):
            lines.append(f"## {CATEGORY_ICONS.get(a.get('category',''),'📦')} {a['name']}")
            lines.append(f"- **Category:** {a.get('category','')}")
            lines.append(f"- **Priority:** {a.get('priority','')}")
            lines.append(f"- **Complexity:** {a.get('complexity','')}")
            lines.append(f"- **Description:** {a.get('description','')}")
            lines.append(f"- **Tags:** {', '.join(a.get('tags',[]))}")
            lines.append(f"- **Colors:** {', '.join(c['hex'] + ' ' + c['name'] for c in a.get('color_palette',[]))}")
            if a.get("notes"):
                lines.append(f"- **Notes:** {a['notes']}")
            lines.append("")
        md_str = "\n".join(lines)
        st.download_button(
            "⬇️ Download Markdown",
            data=md_str,
            file_name=f"asset_breakdown_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
        )
