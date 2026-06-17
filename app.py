import streamlit as st
import openai
import base64
import json
import re
import csv
import io
import requests
from datetime import datetime
from PIL import Image

st.set_page_config(
    page_title="Isometric Asset Breakdown",
    page_icon="🎮",
    layout="wide"
)

st.title("🎮 Isometric Asset Breakdown")
st.caption("Concept Art → Unity Isometric Asset List + Midjourney Prompts")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODELS = {
    "Gemini 2.0 Flash (free)":        "google/gemini-2.0-flash-001",
    "Gemini 2.5 Flash Preview (free)": "google/gemini-2.5-flash-preview-05-20:free",
    "Llama 4 Maverick (free)":         "meta-llama/llama-4-maverick:free",
    "Gemini 2.5 Pro (paid)":           "google/gemini-2.5-pro-preview",
    "Claude Sonnet 4.6 (paid)":        "anthropic/claude-sonnet-4-6",
}

ANALYSIS_PROMPT = """You are a senior Game Art Director and Unity Technical Artist specializing in isometric mobile games.

Your job is to analyze concept art and produce a complete asset breakdown for a Unity isometric game with this grid system:
- Main Grid: isometric tile-based (e.g. 128x64px per tile)
- Sub-grid: each Main Grid tile is subdivided into 4 smaller slots for decoration placement (to avoid repetition)

Analyze the concept art and identify ALL visual zones/areas in the scene. For each zone, list every asset needed to recreate that scene as closely as possible in Unity isometric view.

Return ONLY valid JSON with this exact schema (no markdown, no code blocks):

{
  "scene_summary": "Overall description of the concept art scene",
  "art_style": "Visual style description (color mood, rendering style, lighting)",
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
            "style_notes": "Texture hints, stylization notes, important visual details",
            "midjourney_subject": "Concise visual description for MJ prompt (object + key visual traits only)",
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
- main_grid_object: Objects that occupy 1+ full grid tiles (trees, large rocks, buildings) — Main Grid
- sub_grid_decoration: Small details in the 4 sub-slots (pebbles, grass tufts, flowers) — Sub-grid
- character: Player, NPC, enemy, creature
- vfx: Particles, animated effects

Be exhaustive. midjourney_subject must describe only the visual subject itself, no style words."""


def encode_image(uploaded_file) -> str:
    data = uploaded_file.read()
    return base64.b64encode(data).decode("utf-8")


def get_mime_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")


def analyze_image(api_key: str, model: str, uploaded_file, extra_notes: str = "") -> dict:
    client = openai.OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)

    uploaded_file.seek(0)
    image_b64 = encode_image(uploaded_file)
    mime = get_mime_type(uploaded_file.name)

    user_text = "Analyze this concept art and return the full isometric asset breakdown as JSON."
    if extra_notes:
        user_text += f"\n\nArt Director notes: {extra_notes}"

    with st.spinner(f"Analyzing with {model}..."):
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": ANALYSIS_PROMPT},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                    {"type": "text", "text": user_text},
                ]},
            ],
            max_tokens=8000,
        )

    raw = response.choices[0].message.content
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def notion_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}


def notion_get_pages(token: str) -> list:
    """Return list of pages the integration can access."""
    r = requests.post("https://api.notion.com/v1/search",
                      headers=notion_headers(token),
                      json={"filter": {"value": "page", "property": "object"}, "page_size": 20})
    if r.ok:
        return [{"id": p["id"], "title": p.get("properties", {}).get("title", {}).get("title", [{}])[0].get("plain_text", "Untitled")}
                for p in r.json().get("results", []) if p.get("object") == "page"]
    return []


def notion_create_asset_db(token: str, parent_page_id: str, scene_summary: str) -> str:
    """Create Asset Breakdown database, return database_id."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": f"🎮 Asset Breakdown — {scene_summary[:40]}"}}],
        "properties": {
            "Asset Name":    {"title": {}},
            "Zone":          {"rich_text": {}},
            "Category":      {"select": {"options": [
                {"name": "Base Tile", "color": "brown"},
                {"name": "Main Grid Object", "color": "orange"},
                {"name": "Sub-grid Decoration", "color": "green"},
                {"name": "Character", "color": "blue"},
                {"name": "VFX", "color": "purple"},
            ]}},
            "Priority":      {"select": {"options": [
                {"name": "high", "color": "red"}, {"name": "medium", "color": "yellow"}, {"name": "low", "color": "green"}
            ]}},
            "Complexity":    {"select": {"options": [
                {"name": "simple", "color": "green"}, {"name": "medium", "color": "yellow"}, {"name": "complex", "color": "red"}
            ]}},
            "Tile Size":     {"rich_text": {}},
            "Sorting Layer": {"rich_text": {}},
            "Collider":      {"rich_text": {}},
            "Static":        {"checkbox": {}},
            "Animated":      {"checkbox": {}},
            "Description":   {"rich_text": {}},
            "Style Notes":   {"rich_text": {}},
            "Dev Notes":     {"rich_text": {}},
        }
    }
    r = requests.post("https://api.notion.com/v1/databases", headers=notion_headers(token), json=payload)
    r.raise_for_status()
    return r.json()["id"]


def notion_create_prompt_db(token: str, parent_page_id: str, scene_summary: str) -> str:
    """Create MJ Prompts database, return database_id."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": f"🖼️ MJ Prompts — {scene_summary[:40]}"}}],
        "properties": {
            "Asset Name": {"title": {}},
            "Zone":       {"rich_text": {}},
            "Category":   {"select": {"options": [
                {"name": "Base Tile", "color": "brown"},
                {"name": "Main Grid Object", "color": "orange"},
                {"name": "Sub-grid Decoration", "color": "green"},
                {"name": "Character", "color": "blue"},
                {"name": "VFX", "color": "purple"},
            ]}},
            "Prompt":     {"rich_text": {}},
            "Status":     {"select": {"options": [
                {"name": "To Do", "color": "gray"},
                {"name": "In Progress", "color": "yellow"},
                {"name": "Done", "color": "green"},
            ]}},
        }
    }
    r = requests.post("https://api.notion.com/v1/databases", headers=notion_headers(token), json=payload)
    r.raise_for_status()
    return r.json()["id"]


def notion_add_row(token: str, db_id: str, props: dict):
    payload = {"parent": {"database_id": db_id}, "properties": props}
    r = requests.post("https://api.notion.com/v1/pages", headers=notion_headers(token), json=payload)
    r.raise_for_status()


def rt(text: str) -> dict:
    """Shorthand: rich_text property value."""
    return {"rich_text": [{"text": {"content": str(text)[:2000]}}]}


def push_to_notion(token: str, parent_page_id: str, result: dict, prompts_export: list):
    """Create both databases and fill rows."""
    scene = result.get("scene_summary", "Scene")[:40]
    zones = result.get("zones", [])

    # Create databases
    asset_db_id  = notion_create_asset_db(token, parent_page_id, scene)
    prompt_db_id = notion_create_prompt_db(token, parent_page_id, scene)

    # Fill Asset Breakdown
    for zone in zones:
        for a in zone.get("assets", []):
            ab = a.get("artist_brief", {})
            ds = a.get("dev_spec", {})
            notion_add_row(token, asset_db_id, {
                "Asset Name":    {"title": [{"text": {"content": a["name"]}}]},
                "Zone":          rt(zone["zone_name"]),
                "Category":      {"select": {"name": CATEGORY_LABELS.get(a.get("category",""), a.get("category",""))}},
                "Priority":      {"select": {"name": a.get("priority", "medium")}},
                "Complexity":    {"select": {"name": a.get("complexity", "medium")}},
                "Tile Size":     rt(ds.get("tile_size", "")),
                "Sorting Layer": rt(ds.get("sorting_layer", "")),
                "Collider":      rt(ds.get("collider_type", "none")),
                "Static":        {"checkbox": bool(ds.get("static", True))},
                "Animated":      {"checkbox": bool(ab.get("animated", False))},
                "Description":   rt(ab.get("description", "")),
                "Style Notes":   rt(ab.get("style_notes", "")),
                "Dev Notes":     rt(ds.get("notes", "")),
            })

    # Fill MJ Prompts
    for p in prompts_export:
        notion_add_row(token, prompt_db_id, {
            "Asset Name": {"title": [{"text": {"content": p["asset"]}}]},
            "Zone":       rt(p["zone"]),
            "Category":   {"select": {"name": p["category"]}},
            "Prompt":     rt(p["prompt"]),
            "Status":     {"select": {"name": "To Do"}},
        })

    return asset_db_id, prompt_db_id


def build_mj_prompt(subject: str, art_style: str, category: str, sref_url: str, seed: str, ar: str) -> str:
    iso_view = {
        "base_tile":            "isometric tile, top-down 45 degree view, seamless tileable texture, flat ground surface",
        "main_grid_object":     "isometric game asset, 45 degree isometric view, single object, transparent background",
        "sub_grid_decoration":  "small isometric decoration asset, 45 degree view, tiny detail object, transparent background",
        "character":            "isometric character sprite, 45 degree isometric view, full body, transparent background",
        "vfx":                  "isometric VFX sprite, 45 degree view, particle effect, transparent background",
    }.get(category, "isometric game asset, 45 degree view, transparent background")

    core = f"{subject}, {iso_view}, {art_style}, game art, 2D illustration, clean edges"
    params = f"--ar {ar}"
    if sref_url.strip():
        params += f" --sref {sref_url.strip()}"
    if seed.strip():
        params += f" --seed {seed.strip()}"
    return f"{core} {params}"


def hex_swatch(hex_color: str, size: int = 20) -> str:
    safe = hex_color if hex_color.startswith("#") else f"#{hex_color}"
    return f'<span style="display:inline-block;width:{size}px;height:{size}px;background:{safe};border:1px solid #555;border-radius:3px;vertical-align:middle;margin-right:5px;"></span>'


CATEGORY_ICONS  = {"base_tile": "🟫", "main_grid_object": "🧱", "sub_grid_decoration": "🌿", "character": "🧑", "vfx": "✨"}
CATEGORY_LABELS = {"base_tile": "Base Tile", "main_grid_object": "Main Grid Object", "sub_grid_decoration": "Sub-grid Decoration", "character": "Character", "vfx": "VFX"}
PRIORITY_COLOR  = {"high": "🔴", "medium": "🟡", "low": "🟢"}
COMPLEXITY_COLOR = {"simple": "🟢", "medium": "🟡", "complex": "🔴"}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("OpenRouter API Key", type="password", help="Get yours at openrouter.ai/keys")
    model_label = st.selectbox("Model", list(MODELS.keys()), index=0)
    model = MODELS[model_label]
    st.caption(f"`{model}`")

    st.divider()
    st.header("🎨 Midjourney Style")
    sref_url = st.text_input("Style Reference URL (--sref)", placeholder="https://cdn.midjourney.com/...")
    mj_seed  = st.text_input("Seed (--seed)", placeholder="e.g. 3849201")
    mj_ar    = st.selectbox("Aspect Ratio (--ar)", ["1:1", "4:3", "3:4", "16:9", "2:3"], index=0)

    st.divider()
    st.header("📓 Notion")
    notion_token = st.text_input("Notion Integration Token", type="password",
                                  help="notion.so/my-integrations → New integration → Copy token")
    notion_page_id = st.text_input("Parent Page ID", placeholder="32-char page ID",
                                    help="เปิด Notion page → Share → Copy link → เอา ID หลัง notion.so/")
    st.caption("Share page นั้นกับ integration ก่อนนะครับ")

    st.divider()
    st.header("🔍 Filter")
    filter_categories = st.multiselect(
        "Show categories",
        list(CATEGORY_LABELS.keys()),
        default=list(CATEGORY_LABELS.keys()),
        format_func=lambda x: CATEGORY_ICONS[x] + " " + CATEGORY_LABELS[x],
    )

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_analyze, tab_prompts = st.tabs(["📦 Asset Breakdown", "🖼️ Midjourney Prompts"])

# ── Tab 1: Asset Breakdown ────────────────────────────────────────────────────
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
            st.metric("Model", model.split("/")[-1][:24])

        if not api_key:
            st.warning("Enter OpenRouter API key in sidebar — get it free at openrouter.ai/keys")

        if st.button("🔍 Analyze Assets", type="primary", disabled=not api_key):
            try:
                result = analyze_image(api_key, model, uploaded, extra_notes)
                st.session_state["result"] = result
                st.rerun()
            except json.JSONDecodeError as e:
                st.error(f"JSON parse error: {e}")
            except Exception as e:
                st.error(f"Error: {e}")

    if "result" in st.session_state:
        result = st.session_state["result"]
        zones  = result.get("zones", [])
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
                    cat  = asset.get("category", "")
                    icon = CATEGORY_ICONS.get(cat, "📦")
                    pri  = PRIORITY_COLOR.get(asset.get("priority", "medium"), "🟡")
                    cmp  = COMPLEXITY_COLOR.get(asset.get("complexity", "medium"), "🟡")
                    st.markdown("---")
                    st.markdown(f"#### {icon} {asset['name']} &nbsp; {pri} &nbsp; `{CATEGORY_LABELS.get(cat, cat)}`")
                    col_artist, col_dev = st.columns(2)
                    with col_artist:
                        st.markdown("**🎨 Artist Brief**")
                        ab = asset.get("artist_brief", {})
                        st.write(ab.get("description", ""))
                        if ab.get("style_notes"):    st.caption(f"Style: {ab['style_notes']}")
                        if ab.get("reference_notes"): st.caption(f"📌 Ref: {ab['reference_notes']}")
                        st.write("✅ Animated" if ab.get("animated") else "⬜ Static")
                        if ab.get("animation_notes"): st.caption(f"Anim: {ab['animation_notes']}")
                        for c in ab.get("color_palette", []):
                            safe = c["hex"] if c["hex"].startswith("#") else f'#{c["hex"]}'
                            st.markdown(hex_swatch(safe) + f"`{c['hex']}` {c['name']}", unsafe_allow_html=True)
                    with col_dev:
                        st.markdown("**⚙️ Dev Spec (Unity)**")
                        ds = asset.get("dev_spec", {})
                        for k, v in {
                            "Layer": ds.get("layer", "—"), "Tile Size": ds.get("tile_size", "—"),
                            "Pivot": ds.get("pivot", "—"), "Sorting Layer": ds.get("sorting_layer", "—"),
                            "Order in Layer": str(ds.get("order_in_layer", "—")),
                            "Collider": f"{ds.get('collider_type','none')} {'✅' if ds.get('has_collider') else '❌'}",
                            "Static": "✅" if ds.get("static") else "🔄 Dynamic",
                            "Complexity": f"{cmp} {asset.get('complexity','—').capitalize()}",
                        }.items():
                            st.write(f"**{k}:** {v}")
                        if ds.get("notes"): st.caption(f"📝 {ds['notes']}")

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
                    ab, ds = a.get("artist_brief", {}), a.get("dev_spec", {})
                    lines += [f"### {CATEGORY_ICONS.get(a.get('category',''),'📦')} {a['name']}",
                               f"- **Category:** {CATEGORY_LABELS.get(a.get('category',''), '')}",
                               f"- **Priority:** {a.get('priority','')} | **Complexity:** {a.get('complexity','')}",
                               f"\n**Artist Brief**", f"- {ab.get('description','')}",
                               f"- Style: {ab.get('style_notes','')}",
                               f"\n**Dev Spec**",
                               f"- Tile Size: {ds.get('tile_size','—')} | Pivot: {ds.get('pivot','—')}",
                               f"- Sorting Layer: {ds.get('sorting_layer','—')} / Order: {ds.get('order_in_layer','—')}",
                               f"- Collider: {ds.get('collider_type','none')} | Static: {'Yes' if ds.get('static') else 'No'}", ""]
            st.download_button("⬇️ Markdown (Artist)", data="\n".join(lines),
                               file_name=f"asset_breakdown_{ts}.md", mime="text/markdown")

        # CSV export for asset breakdown
        csv_buf2 = io.StringIO()
        fieldnames = ["#", "Zone", "Asset", "Category", "Priority", "Complexity",
                      "Tile Size", "Pivot", "Sorting Layer", "Order in Layer",
                      "Collider", "Static", "Animated", "Description", "Style Notes", "Dev Notes"]
        writer2 = csv.DictWriter(csv_buf2, fieldnames=fieldnames)
        writer2.writeheader()
        idx = 1
        for zone in zones:
            for a in zone.get("assets", []):
                ab = a.get("artist_brief", {})
                ds = a.get("dev_spec", {})
                writer2.writerow({
                    "#": idx, "Zone": zone["zone_name"], "Asset": a["name"],
                    "Category": CATEGORY_LABELS.get(a.get("category",""), a.get("category","")),
                    "Priority": a.get("priority",""), "Complexity": a.get("complexity",""),
                    "Tile Size": ds.get("tile_size",""), "Pivot": ds.get("pivot",""),
                    "Sorting Layer": ds.get("sorting_layer",""), "Order in Layer": ds.get("order_in_layer",""),
                    "Collider": ds.get("collider_type","none"), "Static": "Yes" if ds.get("static") else "No",
                    "Animated": "Yes" if ab.get("animated") else "No",
                    "Description": ab.get("description",""), "Style Notes": ab.get("style_notes",""),
                    "Dev Notes": ds.get("notes",""),
                })
                idx += 1
        st.download_button("⬇️ CSV (Google Sheet) — Full Asset List", data=csv_buf2.getvalue(),
                           file_name=f"asset_list_{ts}.csv", mime="text/csv")

# ── Tab 2: Midjourney Prompts ─────────────────────────────────────────────────
with tab_prompts:
    if "result" not in st.session_state:
        st.info("Analyze a concept art first in the Asset Breakdown tab.")
    else:
        result    = st.session_state["result"]
        art_style = result.get("art_style", "stylized 2D isometric game art")
        zones     = result.get("zones", [])

        st.subheader("🖼️ Midjourney Prompts")
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.info(f"**sref:** {sref_url if sref_url.strip() else '_(not set)_'}")
        col_s2.info(f"**seed:** {mj_seed if mj_seed.strip() else '_(not set)_'}")
        col_s3.info(f"**ar:** {mj_ar}")
        if not sref_url.strip() and not mj_seed.strip():
            st.warning("Enter --sref and/or --seed in the sidebar to complete the prompts.")
        st.caption(f"Art style: _{art_style}_")
        st.divider()

        prompts_export = []
        for zone in zones:
            zone_assets = [a for a in zone.get("assets", []) if a.get("category") in filter_categories]
            if not zone_assets:
                continue
            st.markdown(f"### 📍 {zone['zone_name']}")
            for asset in zone_assets:
                cat     = asset.get("category", "")
                ab      = asset.get("artist_brief", {})
                subject = ab.get("midjourney_subject") or ab.get("description") or asset["name"]
                prompt  = build_mj_prompt(subject, art_style, cat, sref_url, mj_seed, mj_ar)
                prompts_export.append({"asset": asset["name"], "category": CATEGORY_LABELS.get(cat, cat),
                                       "zone": zone["zone_name"], "prompt": prompt})
                st.markdown(f"**{CATEGORY_ICONS.get(cat,'📦')} {asset['name']}** `{CATEGORY_LABELS.get(cat,cat)}`")
                st.code(prompt, language=None)
                st.caption(f"Subject: _{subject}_")
                st.markdown("")

        st.divider()

        # ── Copy All Prompts ──────────────────────────────────────────────
        all_prompts_text = "\n\n".join(
            f"[{i+1}] {p['asset']} ({p['category']}) — {p['zone']}\n{p['prompt']}"
            for i, p in enumerate(prompts_export)
        )
        st.subheader("📋 Copy All Prompts")
        st.text_area("Select All → Copy", value=all_prompts_text, height=200, label_visibility="collapsed")
        st.components.v1.html(f"""
            <button onclick="navigator.clipboard.writeText({json.dumps(all_prompts_text)}).then(()=>{{
                this.innerText='✅ Copied!';
                setTimeout(()=>this.innerText='📋 Copy All Prompts',2000);
            }})" style="
                background:#FF4B4B;color:white;border:none;padding:10px 24px;
                border-radius:6px;font-size:15px;cursor:pointer;font-weight:600;
            ">📋 Copy All Prompts</button>
        """, height=50)

        # ── Google Sheet TSV ──────────────────────────────────────────────
        tsv_lines = ["#\tAsset\tCategory\tZone\tPrompt"]
        for i, p in enumerate(prompts_export, 1):
            tsv_lines.append(f"{i}\t{p['asset']}\t{p['category']}\t{p['zone']}\t{p['prompt']}")
        tsv_text = "\n".join(tsv_lines)
        st.subheader("📊 Copy for Google Sheet (TSV)")
        st.caption("Copy แล้ว Paste ลง Google Sheet ได้เลย — ข้อมูลจะแยก column อัตโนมัติ")
        st.text_area("TSV", value=tsv_text, height=150, label_visibility="collapsed")
        st.components.v1.html(f"""
            <button onclick="navigator.clipboard.writeText({json.dumps(tsv_text)}).then(()=>{{
                this.innerText='✅ Copied!';
                setTimeout(()=>this.innerText='📊 Copy for Google Sheet',2000);
            }})" style="
                background:#0F9D58;color:white;border:none;padding:10px 24px;
                border-radius:6px;font-size:15px;cursor:pointer;font-weight:600;
            ">📊 Copy for Google Sheet</button>
        """, height=50)

        # ── Save to Notion ────────────────────────────────────────────────
        st.divider()
        st.subheader("📓 Save to Notion")
        if not notion_token or not notion_page_id:
            st.info("กรอก Notion Token และ Parent Page ID ใน sidebar ก่อนครับ")
        else:
            if st.button("📓 Save to Notion", type="primary"):
                with st.spinner("กำลัง push ข้อมูลเข้า Notion..."):
                    try:
                        clean_page_id = notion_page_id.strip().replace("-", "")
                        asset_db, prompt_db = push_to_notion(
                            notion_token, clean_page_id,
                            st.session_state["result"], prompts_export
                        )
                        st.success("✅ บันทึกเข้า Notion สำเร็จแล้วครับ!")
                        st.markdown(f"- 🗂️ **Asset Breakdown DB:** [เปิดใน Notion](https://notion.so/{asset_db.replace('-','')})")
                        st.markdown(f"- 🖼️ **MJ Prompts DB:** [เปิดใน Notion](https://notion.so/{prompt_db.replace('-','')})")
                    except Exception as e:
                        st.error(f"Error: {e}")
                        st.caption("ตรวจสอบว่า Share page ให้ integration แล้วหรือยังครับ")

        st.divider()
        st.subheader("📤 Export Files")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        col_pj, col_pm, col_csv = st.columns(3)
        with col_pj:
            st.download_button("⬇️ JSON", data=json.dumps(prompts_export, indent=2, ensure_ascii=False),
                               file_name=f"mj_prompts_{ts}.json", mime="application/json")
        with col_pm:
            md_lines = [f"# Midjourney Prompts\nsref: {sref_url} | seed: {mj_seed} | ar: {mj_ar}\n---\n"]
            for p in prompts_export:
                md_lines += [f"## {p['asset']} ({p['category']})", f"Zone: {p['zone']}", "```", p["prompt"], "```", ""]
            st.download_button("⬇️ Markdown", data="\n".join(md_lines),
                               file_name=f"mj_prompts_{ts}.md", mime="text/markdown")
        with col_csv:
            csv_buf = io.StringIO()
            writer = csv.DictWriter(csv_buf, fieldnames=["#", "Asset", "Category", "Zone", "Prompt"])
            writer.writeheader()
            for i, p in enumerate(prompts_export, 1):
                writer.writerow({"#": i, "Asset": p["asset"], "Category": p["category"],
                                 "Zone": p["zone"], "Prompt": p["prompt"]})
            st.download_button("⬇️ CSV (Google Sheet)", data=csv_buf.getvalue(),
                               file_name=f"mj_prompts_{ts}.csv", mime="text/csv")
