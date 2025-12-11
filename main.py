from fasthtml.common import *
from starlette.datastructures import UploadFile

from topo4d_form.session import load_session
from topo4d_form.styles import *
from topo4d_form.templates import *
from topo4d_form.validation import validate_topo4d_item, model_required_keys
from topo4d_form.make_item import (
    construct_topo4d_properties,
    construct_assets,
    create_pystac_item,
    geometry_from_las_header,
)
from datetime import datetime
import pystac
import copy
import pytz
from datetime import datetime
import os
import shutil
import io

try:
    import laspy  # type: ignore
except Exception:
    laspy = None

app, rt = fast_app(hdrs=(picolink))

app_title = "Topo4D Metadata Form"

@app.get("/")
def homepage(session):
    session = load_session(session)
    return (
        Title(app_title),
        Main(
            Header(
                title_bar(app_title, session),
                tab_bar(selected="/"),
                Img(
                    src="https://static.scarf.sh/a.png?x-pxid=0a803684-62c5-4f72-8971-01626aa82623",
                    referrerpolicy="no-referrer-when-downgrade",
                ),
            ),
            Div(
                session_form(session, submitOnLoad=True),
                outputTemplate(),
                id="page",
                style="display: flex; flex-direction: row; overflow: auto;",
            ),
            style=main_element_style,
        ),
    )


@app.post("/clear_form")
def clear_form(session):
    session = load_session(session)
    session.clear()
    return session_form(session), button_bar(session)


def form_format_to_topo4d_input(d):
    """Normalize form dictionary before storing/using.

    - Collects inputs created by inputArrayTemplate with names like
      "<base>_r_c" (1-based indices) into a nested list stored under "<base>".
    """
    import re

    out = dict(d)

    # Group keys by base name if they match pattern <name>_r_c where r,c are ints
    pattern = re.compile(r"^(?P<base>.+)_(?P<r>\d+)_(?P<c>\d+)$")
    buckets = {}
    for k, v in d.items():
        m = pattern.match(k)
        if not m:
            continue
        base = m.group("base")
        r = int(m.group("r"))
        c = int(m.group("c"))
        buckets.setdefault(base, {})[(r, c)] = v

    # For each bucket, assemble rows in row-major order
    for base, grid in buckets.items():
        if not grid:
            continue
        max_r = max(rc[0] for rc in grid)
        max_c = max(rc[1] for rc in grid)
        nested = []
        for r in range(1, max_r + 1):
            row = []
            for c in range(1, max_c + 1):
                row.append(grid.get((r, c), ""))
            nested.append(row)
        out[base] = nested

    return out


@app.post("/submit")
def submit(session, d: dict):
    session = load_session(session)
    session.setdefault("stac_format_d", {})
    session.setdefault("form_format_d", {})
    session["form_format_d"].update(copy.deepcopy(d))
    d = form_format_to_topo4d_input(d)
    session["stac_format_d"].update(d)
    topo_props = construct_topo4d_properties(session["stac_format_d"])
    assets = construct_assets(session["stac_format_d"].get("assets"))
    item = create_pystac_item(
        topo_props,
        assets,
        geometry=session["stac_format_d"].get("geometry"),
        bbox=session["stac_format_d"].get("bbox"),
    )
    # Validate against local schema
    error = validate_topo4d_item(item)
    if error:
        return error_template(error), prettyJsonTemplate(item), button_bar(session)
    return prettyJsonTemplate(item), button_bar(session)


roles_options = []  # No predefined roles for topo4d; free-form CSV in UI


# helper function to render out the session form
# because of the `hx_swap_oob`, this snippet can be returned by any handler and will update the form
# see https://htmx.org/examples/update-other-content/#oob
#
# `submitOnLoad` should be set to true for the initial page load so that the form will
# auto-submit to populate the results if there is saved state in the session
def session_form(session, submitOnLoad=False):
    session.setdefault("stac_format_d", {})
    session.setdefault("form_format_d", {})
    result = session.get("form_format_d", {})
    stac_result = session.get("stac_format_d", {})
    trigger = (
        "input delay:200ms, load" if submitOnLoad else "input delay:200ms"
    )
    session_form = Form(
        hx_post="/submit",
        hx_target="#result",
        hx_trigger=trigger,
        id="session_form",
        hx_swap_oob="#session_form",
        style=form_style,
    )(
        P(
            "The ",
            A(
                "Topographic 4D ",
                href="https://github.com/tum-rsa/topo4d",
                target="_blank",
                rel="noopener noreferrer",
                cls="border-b-2 border-b-black/30 hover:border-b-black/80",
            ),
            " (Topo4D) metadata specification makes it easy to describe the time-dependent metadata in diverse 4D datasets (time series of 3D geographic data) and enable search and discovery under STAC ecosystem. ",
            "Please complete all required fields below and in the Asset Form prior to copying or downloading the JSON result. Downloaded JSONs will be stored in your download directory and named based on Item Name field. ",
            "For more information on the specification, refer to the ",
            A(
                "Topo4D documentation",
                href="https://github.com/tum-rsa/topo4d/blob/main/README.md",
                target="_blank",
                rel="noopener noreferrer",
                cls="border-b-2 border-b-black/30 hover:border-b-black/80",
            ),
            ".",
        ),
        inputTemplate(
            label="Item Name",
            name="item_id",
            placeholder="Identifier for this STAC Item",
            val="",
            input_type="text",
        ),
        inputTemplate(
            label="Datetime (ISO8601)",
            name="datetime",
            placeholder="e.g. 2024-01-01T00:00:00Z",
            val=datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            input_type="text",
        ),
        selectEnumTemplate(
            label="Data Type",
            options=["pointcloud", "raster", "mesh", "vector", "text", "other"],
            name="topo4d_data_type",
            value="",
        ),
        selectEnumTemplate(
            label="Timezone",
            options=pytz.all_timezones,
            name="topo4d_timezone",
            error_msg=None,
            canValidateInline=False,
        ),
        inputTemplate(
            label="Acquisition Mode",
            name="topo4d_acquisition_mode",
            placeholder="e.g. ULS, TLS, UPH",
            val="",
            input_type="text",
        ),
        inputTemplate(
            label="Duration [seconds]",
            name="topo4d_duration",
            val="",
            input_type="number",
        ),
        inputTemplate(
            label="Spatial Resolution [m]",
            name="topo4d_spatial_resolution",
            val="",
            input_type="number",
        ),
        inputTemplate(
            label="Positional Accuracy [m]",
            name="topo4d_positional_accuracy",
            val="",
            input_type="number",
        ),
        inputTemplate(
            label="Orientation",
            name="topo4d_orientation",
            placeholder="Survey pattern: Nadir, Oblique, Nadir+Oblique",
            val="",
            input_type="text",
        ),
        inputTemplate(
            label="Global Transformation (rows by semicolon, values by comma)",
            name="topo4d_global_trafo",
            placeholder="e.g. 1,0,0,0;0,1,0,0;0,0,1,0;0,0,0,1",
            val="",
            input_type="text",
        ),
        H4("Transformation Metadata (trafometa)"), #TODO make the trafometa section optional/collapsible
        relObjectTemplate(
            label="Reference Epoch (Relation/Object)",
            name="trafometa_reference_epoch",
            href="",
            type_="",
            title="",
        ),
        inputTemplate(
            label="Registration Error [m]",
            name="trafometa_registration_error",
            val="",
            input_type="number",
        ),
        inputTemplate(
            label="Transformation (rows by semicolon, values by comma)",
            name="trafometa_transformation",
            placeholder="e.g. 1,0,0,0;0,1,0,0;0,0,1,0;0,0,0,1",
            val="",
            input_type="text",
        ),
        H4("Product Metadata (productmeta)"), #TODO make the productmeta section optional/collapsible
        inputTemplate(
            label="Product Name",
            name="productmeta_product_name",
            val="",
            input_type="text",
        ),
        relObjectTemplate(
            label="Derived From (Relation/Object)",
            name="productmeta_derived_from",
        ),
        inputTemplate(
            label="Product Level",
            name="productmeta_product_level",
            val="",
            input_type="text",
        ),
        inputTemplate(
            label="Param (JSON object)",
            name="productmeta_param",
            placeholder='e.g. {"key": "value"}',
            val="",
            input_type="text",
        ),
    )
    fill_form(session_form, result)
    return session_form


def session_asset_form(session, submitOnLoad=False):
    session.setdefault("stac_format_d", {})
    session.setdefault("form_format_d", {})
    session["stac_format_d"].setdefault("assets", {})
    session["form_format_d"].setdefault("assets", {})
    # TODO decide whether to show just asset section or full json on asset page on load and edit
    # result = session['form_format_d'].get('assets', {})
    trigger = (
        "input delay:200ms, load" if submitOnLoad else "input delay:200ms"
    )
    session_asset_form = Form(
        hx_post="/submit_asset",
        hx_target="#result",
        hx_trigger=trigger,
        id="session_asset_form",
        hx_swap_oob="#session_asset_form",
        style=form_style,
    )(
        P("Describe the primary data asset for this Item (optional)."),
        inputTemplate(
            label="Title",
            name="title",
            val="",
            input_type="text",
            canValidateInline=False,
        ),
        inputTemplate(
            label="URI", name="href", val="https://example.com/data.laz", input_type="text", canValidateInline=False
        ),
        inputTemplate(
            label="Media Type",
            name="media_type",
            val="",
            input_type="text",
            canValidateInline=False,
        ),
        inputTemplate(
            label="Roles",
            name="roles",
            val="",
            input_type="text",
            canValidateInline=False,
        ),
    )
    fill_form(session_asset_form, session["form_format_d"].get("assets", {}))
    return session_asset_form


@app.get("/asset")
def asset_homepage(session):
    session = load_session(session)
    return (
        Title(app_title),
        Main(
            Header(title_bar(app_title, session), tab_bar(selected="/asset")),
            Div(
                session_asset_form(session, submitOnLoad=True),
                outputTemplate(),
                style="display: flex; flex-direction: row; overflow: auto;",
            ),
            style=main_element_style,
        ),
    )


@app.post("/submit_asset")
def submit_asset(session, d: dict):
    session = load_session(session)
    session["form_format_d"]["assets"].update(copy.deepcopy(d))
    # Normalize roles CSV if provided and map media_type to type
    roles = d.get("roles")
    if isinstance(roles, str):
        roles_list = [r.strip() for r in roles.split(",") if r.strip()]
        if roles_list:
            d["roles"] = roles_list
        else:
            d.pop("roles", None)
    # Map media_type to type expected by STAC
    d["type"] = d.pop("media_type")
    session["stac_format_d"]["assets"].update(copy.deepcopy(d))
    # pystac doesn't directly support validating an asset, so put the asset inside a
    # dummy item and run the validation on that
    dummy_item = pystac.Item(
        id="item",
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [-101.0, 40.0],
                    [-101.0, 41.0],
                    [-100.0, 41.0],
                    [-100.0, 40.0],
                    [-101.0, 40.0],
                ]
            ],
        },
        bbox=[-101.0, 40.0, -100.0, 41.0],
        datetime=datetime.utcnow(),
        properties={},
    )
    dummy_item.assets["data"] = pystac.Asset.from_dict(d)

    try:
        validation_result = pystac.validation.validate(dummy_item)
    except pystac.errors.STACValidationError as e:
        error_message = str(e)
        if "'href'" in error_message and "non-empty" in error_message:
            error_message = "The 'URI' field must be non-empty."
        else:
            error_message = f"STACValidationError: {error_message}".replace(
                "\\n", "<br>"
            )
        return error_template(error_message), prettyJsonTemplate(
            dummy_item.assets["data"].to_dict()
        )
    return prettyJsonTemplate(dummy_item.assets["data"].to_dict())


@app.post("/upload_las")
def upload_las(session, lasfile: UploadFile = None):
    session = load_session(session)
    if laspy is None:
        return error_template(
            "laspy is not installed. Please install dependencies and retry."
        ), button_bar(session)

    if lasfile is None:
        return error_template("No file uploaded."), button_bar(session)

    # Use the uploaded filename if present
    filename = getattr(lasfile, "filename", None) or "uploaded.las"
    # Starlette UploadFile exposes .file (a SpooledTemporaryFile) for sync access
    fileobj = getattr(lasfile, "file", None)
    if fileobj is None:
        return error_template("Invalid upload payload."), button_bar(session)

    # Persist temporary file (simplifies laspy.open handling for LAZ)
    uploads_dir = os.path.join(os.getcwd(), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    # Avoid path traversal in filename
    safe_name = os.path.basename(filename) or "uploaded.las"
    tmp_path = os.path.join(uploads_dir, safe_name)
    try:
        # Rewind and stream-copy to disk
        fileobj.seek(0, os.SEEK_SET)
        with open(tmp_path, "wb") as out:
            shutil.copyfileobj(fileobj, out, length=1024 * 1024)
    except Exception as e:
        return error_template(f"Failed to save upload: {e}"), button_bar(session)

    # Extract header metadata
    hdr_meta = {}
    try:
        with laspy.open(tmp_path) as lh:  # type: ignore
            hdr = lh.header
            # Basic header fields
            try:
                version = f"{hdr.version.major}.{hdr.version.minor}"
            except Exception:
                version = None
            try:
                crs = getattr(hdr, "parse_crs", lambda: None)()
            except Exception:
                crs = None
            hdr_meta = {
                "filename": safe_name,
                "version": version,
                "point_format": getattr(getattr(hdr, "point_format", None), "id", None),
                "point_count": getattr(hdr, "point_count", None),
                "xyz_min": list(getattr(hdr, "mins", getattr(hdr, "min", [None, None, None]))[:3]),
                "xyz_max": list(getattr(hdr, "maxs", getattr(hdr, "max", [None, None, None]))[:3]),
                "scales": list(getattr(hdr, "scales", [])) or None,
                "offsets": list(getattr(hdr, "offsets", [])) or None,
                "srs_wkt": getattr(crs, "to_wkt", lambda: None)(),
                "srs_epsg": getattr(crs, "to_epsg", lambda: None)(),
            }
    except Exception as e:
        return error_template(f"Failed to read LAS/LAZ: {e}"), button_bar(session)

    # Derive geometry & bbox and store in session
    
    geo_meta = geometry_from_las_header(hdr_meta)
    if "stac_format_d" not in session:
        session.setdefault("stac_format_d", {}) 
    session["stac_format_d"]["geometry"] = geo_meta["geometry"]
    session["stac_format_d"]["bbox"] = geo_meta["bbox"]
    topo_props = construct_topo4d_properties(session["stac_format_d"])
    assets = construct_assets(session["stac_format_d"].get("assets"))
    item = create_pystac_item(
        topo_props,
        assets,
        geometry=session["stac_format_d"].get("geometry"),
        bbox=session["stac_format_d"].get("bbox"),
    )
    # Validate against local schema
    error = validate_topo4d_item(item)
    if error:
        return error_template(error), prettyJsonTemplate(item), button_bar(session)
    return (
        Div(
            Div(f"Metadata extracted from {safe_name}.", style="color: green;"),
        ),
        prettyJsonTemplate(item), button_bar(session))


serve()
